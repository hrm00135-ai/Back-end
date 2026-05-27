const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, RefreshToken, OTPRequest, LoginSession } = require('../models');
const {
  verifyPassword, hashPassword, generateOtp, hashOtp, verifyOtp,
  createAccessToken, createRefreshToken, jwtRequired, logAudit,
  successResponse, errorResponse,
} = require('../utils/helpers');
const { sendMail } = require('../utils/mailer');
const config = require('../config/config');

// ────────────────────────────────────────────────────────────
// LOGIN
// ────────────────────────────────────────────────────────────
router.post('/login', async (req, res) => {
  try {
    const data = req.body;
    if (!data) return errorResponse(res, 'Request body is required', 400);

    const email = (data.email || '').trim().toLowerCase();
    const password = data.password || '';
    if (!email || !password) return errorResponse(res, 'Email and password are required', 400);

    const user = await User.findOne({ where: { email } });
    if (!user) return errorResponse(res, 'Invalid email or password', 401);
    if (!user.is_active) return errorResponse(res, 'Account is deactivated. Contact your administrator.', 403);

    // Check lock
    if (user.is_locked) {
      const lockDurationMs = config.ACCOUNT_LOCK_DURATION_MINUTES * 60 * 1000;
      if (user.locked_at && (Date.now() - new Date(user.locked_at).getTime()) < lockDurationMs) {
        const remaining = lockDurationMs - (Date.now() - new Date(user.locked_at).getTime());
        const mins = Math.floor(remaining / 60000);
        return errorResponse(res, `Account is locked. Try again in ${mins} minutes or contact your administrator.`, 423);
      } else {
        user.is_locked = false;
        user.failed_login_attempts = 0;
        user.locked_at = null;
        await user.save();
      }
    }

    // Verify password
    const valid = await verifyPassword(password, user.password_hash);
    if (!valid) {
      user.failed_login_attempts += 1;
      if (user.failed_login_attempts >= config.MAX_FAILED_LOGIN_ATTEMPTS) {
        user.is_locked = true;
        user.locked_at = new Date();
        await user.save();
        await logAudit(user.id, 'ACCOUNT_LOCKED', { details: { reason: 'Max failed login attempts' } });
        return errorResponse(res, 'Account locked due to too many failed attempts. Contact your administrator.', 423);
      }
      await user.save();
      await logAudit(user.id, 'FAILED_LOGIN', { details: { attempt: user.failed_login_attempts } });
      const remaining = config.MAX_FAILED_LOGIN_ATTEMPTS - user.failed_login_attempts;
      return errorResponse(res, `Invalid email or password. ${remaining} attempts remaining.`, 401);
    }

    // Reset failed attempts
    user.failed_login_attempts = 0;
    user.is_locked = false;
    user.locked_at = null;
    await user.save();

    // Single-session enforcement: close previous sessions
    await LoginSession.update(
      { status: 'logged_out', logout_time: new Date() },
      { where: { user_id: user.id, status: 'active' } }
    );
    await RefreshToken.update({ is_revoked: true }, { where: { user_id: user.id, is_revoked: false } });

    // Generate tokens
    const accessToken = createAccessToken(user.id);
    const refreshTokenStr = createRefreshToken(user.id);

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + config.JWT_REFRESH_TOKEN_EXPIRES_DAYS);

    await RefreshToken.create({ user_id: user.id, token: refreshTokenStr, expires_at: expiresAt });

    // Track login session
    const ip = (req.headers['x-forwarded-for'] || req.socket?.remoteAddress || '').split(',')[0].trim();
    const ua = (req.headers['user-agent'] || '').substring(0, 500);
    await LoginSession.create({
      user_id: user.id, login_time: new Date(), ip_address: ip,
      user_agent: ua, session_token: refreshTokenStr.substring(0, 100), status: 'active',
    });

    await logAudit(user.id, 'LOGIN', { req });

    return successResponse(res, {
      data: { access_token: accessToken, refresh_token: refreshTokenStr, user: user.toDict() },
      message: 'Login successful',
    });
  } catch (err) {
    console.error('[LOGIN ERROR]', err.message);
    console.error(err.stack);
    return errorResponse(res, 'Internal server error: ' + err.message, 500);
  }
});

// ────────────────────────────────────────────────────────────
// REFRESH TOKEN
// ────────────────────────────────────────────────────────────
router.post('/refresh', jwtRequired, async (req, res) => {
  try {
    const currentUserId = req.currentUserId;
    const user = await User.findByPk(currentUserId);
    if (!user || !user.is_active) return errorResponse(res, 'Invalid user', 401);

    const newAccessToken = createAccessToken(user.id);
    return successResponse(res, { data: { access_token: newAccessToken }, message: 'Token refreshed' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// LOGOUT
// ────────────────────────────────────────────────────────────
router.post('/logout', jwtRequired, async (req, res) => {
  try {
    const currentUserId = req.currentUserId;
    const data = req.body || {};
    const refreshTokenStr = data.refresh_token;

    if (refreshTokenStr) {
      await RefreshToken.update({ is_revoked: true }, { where: { token: refreshTokenStr, user_id: currentUserId } });
    }

    await LoginSession.update(
      { status: 'logged_out', logout_time: new Date() },
      { where: { user_id: parseInt(currentUserId), status: 'active' }, order: [['login_time', 'DESC']], limit: 1 }
    );

    await logAudit(currentUserId, 'LOGOUT', { req });
    return successResponse(res, { message: 'Logged out successfully' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PASSWORD RESET - Step 1: Request OTP
// ────────────────────────────────────────────────────────────
router.post('/password-reset/request', async (req, res) => {
  try {
    const data = req.body;
    if (!data) return errorResponse(res, 'Request body is required', 400);
    const email = (data.email || '').trim().toLowerCase();
    if (!email) return errorResponse(res, 'Email is required', 400);

    const user = await User.findOne({ where: { email, is_active: true } });
    if (!user) return successResponse(res, { message: 'If the email exists, an OTP has been sent.' });
    if (user.role === 'super_admin') return errorResponse(res, 'Super Admin password can only be reset via backend.', 403);

    const otp = generateOtp();
    const otpHash = await hashOtp(otp);

    await OTPRequest.update({ is_verified: true }, { where: { user_id: user.id, otp_type: 'password_reset', is_verified: false } });

    const expiresAt = new Date();
    expiresAt.setMinutes(expiresAt.getMinutes() + config.OTP_EXPIRY_MINUTES);

    const otpRequest = await OTPRequest.create({
      user_id: user.id, otp_code: otpHash, otp_type: 'password_reset', expires_at: expiresAt,
    });

    try {
      await sendMail({
        to: user.email,
        subject: 'JewelCraft HRM - Password Reset OTP',
        text: `Your OTP for password reset is: ${otp}\n\nThis OTP expires in ${config.OTP_EXPIRY_MINUTES} minutes.\n\nIf you did not request this, please ignore this email.`,
      });
    } catch (e) {
      console.error(`[EMAIL ERROR] Failed to send OTP to ${user.email}: ${e.message}`);
      console.log(`[DEV OTP] User: ${user.email}, OTP: ${otp}`);
    }

    await logAudit(user.id, 'PASSWORD_RESET_REQUESTED', { req });
    return successResponse(res, { message: 'If the email exists, an OTP has been sent.', data: { otp_request_id: otpRequest.id } });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PASSWORD RESET - Step 2: Verify OTP
// ────────────────────────────────────────────────────────────
router.post('/password-reset/verify-otp', async (req, res) => {
  try {
    const data = req.body;
    if (!data) return errorResponse(res, 'Request body is required', 400);
    const { otp_request_id, otp } = data;
    if (!otp_request_id || !otp) return errorResponse(res, 'OTP request ID and OTP are required', 400);

    const otpReq = await OTPRequest.findByPk(otp_request_id);
    if (!otpReq) return errorResponse(res, 'Invalid OTP request', 404);
    if (otpReq.is_verified) return errorResponse(res, 'OTP already used', 400);
    if (new Date(otpReq.expires_at) < new Date()) return errorResponse(res, 'OTP has expired. Request a new one.', 400);
    if (!(await verifyOtp(otp, otpReq.otp_code))) return errorResponse(res, 'Invalid OTP', 400);

    otpReq.is_verified = true;
    await otpReq.save();

    await logAudit(otpReq.user_id, 'OTP_VERIFIED', { req });
    return successResponse(res, {
      message: 'OTP verified. Waiting for administrator approval to reset password.',
      data: { otp_request_id: otpReq.id, status: 'awaiting_approval' },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PASSWORD RESET - Step 3: Admin Approves
// ────────────────────────────────────────────────────────────
router.post('/password-reset/approve', jwtRequired, async (req, res) => {
  try {
    const currentUserId = req.currentUserId;
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser) return errorResponse(res, 'User not found', 404);

    const data = req.body;
    if (!data) return errorResponse(res, 'Request body is required', 400);
    const { otp_request_id, new_password } = data;
    if (!otp_request_id || !new_password) return errorResponse(res, 'OTP request ID and new password are required', 400);
    if (new_password.length < 8) return errorResponse(res, 'Password must be at least 8 characters', 400);

    const otpReq = await OTPRequest.findByPk(otp_request_id);
    if (!otpReq) return errorResponse(res, 'Invalid OTP request', 404);
    if (!otpReq.is_verified) return errorResponse(res, 'OTP has not been verified yet', 400);
    if (otpReq.is_approved) return errorResponse(res, 'Reset already approved', 400);

    const targetUser = await User.findByPk(otpReq.user_id);
    if (!targetUser) return errorResponse(res, 'Target user not found', 404);

    if (targetUser.role === 'employee' && !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Only Admin or Super Admin can approve employee password resets', 403);
    if (targetUser.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only Super Admin can approve admin password resets', 403);
    if (targetUser.role === 'super_admin')
      return errorResponse(res, 'Super Admin password can only be reset via backend', 403);

    otpReq.is_approved = true;
    otpReq.approved_by = currentUser.id;
    await otpReq.save();

    targetUser.password_hash = await hashPassword(new_password);
    targetUser.failed_login_attempts = 0;
    targetUser.is_locked = false;
    targetUser.locked_at = null;
    await targetUser.save();

    await RefreshToken.update({ is_revoked: true }, { where: { user_id: targetUser.id, is_revoked: false } });

    await logAudit(currentUser.id, 'PASSWORD_RESET_APPROVED', {
      targetUserId: targetUser.id, details: { target_role: targetUser.role }, req,
    });

    return successResponse(res, { message: `Password reset approved for ${targetUser.employee_id}` });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET PENDING RESETS
// ────────────────────────────────────────────────────────────
router.get('/password-reset/pending', jwtRequired, async (req, res) => {
  try {
    const currentUserId = req.currentUserId;
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser || !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    let where = { otp_type: 'password_reset', is_verified: true, is_approved: false };
    const pending = await OTPRequest.findAll({
      where, include: [{ model: User, as: 'User', required: true }],
      order: [['created_at', 'DESC']],
    });

    const result = pending
      .filter(otp => {
        if (currentUser.role === 'admin') return otp.User.role === 'employee';
        return true;
      })
      .map(otp => ({
        otp_request_id: otp.id, user_id: otp.User.id,
        employee_id: otp.User.employee_id,
        name: `${otp.User.first_name} ${otp.User.last_name}`,
        email: otp.User.email, role: otp.User.role,
        requested_at: otp.created_at.toISOString(),
      }));

    return successResponse(res, { data: result });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET ME
// ────────────────────────────────────────────────────────────
router.get('/me', jwtRequired, async (req, res) => {
  try {
    const user = await User.findByPk(req.currentUserId);
    if (!user) return errorResponse(res, 'User not found', 404);
    return successResponse(res, { data: user.toDict() });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// UNLOCK ACCOUNT
// ────────────────────────────────────────────────────────────
router.post('/unlock/:userId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = req.currentUserId;
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser || !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    const targetUser = await User.findByPk(req.params.userId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);
    if (targetUser.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only Super Admin can unlock admin accounts', 403);

    targetUser.is_locked = false;
    targetUser.failed_login_attempts = 0;
    targetUser.locked_at = null;
    await targetUser.save();

    await logAudit(currentUser.id, 'ACCOUNT_UNLOCKED', { targetUserId: targetUser.id, req });
    return successResponse(res, { message: `Account ${targetUser.employee_id} unlocked` });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// LOGIN SESSIONS
// ────────────────────────────────────────────────────────────
router.get('/sessions', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser || !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    const { Op, fn, col, where: Swhere } = require('sequelize');
    const sequelize = require('../config/database');

    let targetDate;
    if (req.query.date) {
      targetDate = new Date(req.query.date);
      if (isNaN(targetDate)) return errorResponse(res, 'Invalid date format. Use YYYY-MM-DD', 400);
    } else {
      targetDate = new Date();
      targetDate.setHours(0, 0, 0, 0);
    }

    const nextDay = new Date(targetDate);
    nextDay.setDate(nextDay.getDate() + 1);

    const userWhere = { is_active: true };
    if (currentUser.role === 'admin') userWhere.role = 'employee';

    const sessions = await LoginSession.findAll({
      include: [{ model: User, where: userWhere, required: true }],
      where: { login_time: { [Op.gte]: targetDate, [Op.lt]: nextDay } },
      order: [['login_time', 'DESC']],
    });

    const result = sessions.map(s => {
      const d = s.toDict();
      d.first_name = s.User.first_name; d.last_name = s.User.last_name;
      d.role = s.User.role; d.employee_id = s.User.employee_id; d.photo_url = s.User.photo_url;
      return d;
    });
    return successResponse(res, { data: result });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// ACTIVE SESSIONS
// ────────────────────────────────────────────────────────────
router.get('/sessions/active', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser || !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    const userWhere = { is_active: true };
    if (currentUser.role === 'admin') userWhere.role = 'employee';

    const active = await LoginSession.findAll({
      include: [{ model: User, where: userWhere, required: true }],
      where: { status: 'active' },
      order: [['login_time', 'DESC']],
    });

    const result = active.map(s => {
      const d = s.toDict();
      d.first_name = s.User.first_name; d.last_name = s.User.last_name;
      d.role = s.User.role; d.employee_id = s.User.employee_id; d.photo_url = s.User.photo_url;
      return d;
    });
    return successResponse(res, { data: result });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// BULK LOGOUT
// ────────────────────────────────────────────────────────────
router.post('/logout/bulk', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    if (!currentUser || !['admin', 'super_admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    const data = req.body || {};
    const target = data.target || 'employees';

    if (target === 'admins' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only Super Admin can logout admins', 403);
    if (target === 'all' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only Super Admin can logout all users', 403);

    const rolesToLogout = [];
    if (['employees', 'all'].includes(target)) rolesToLogout.push('employee');
    if (['admins', 'all'].includes(target)) rolesToLogout.push('admin');

    const { Op } = require('sequelize');
    const users = await User.findAll({
      where: { role: { [Op.in]: rolesToLogout }, is_active: true, id: { [Op.ne]: currentUserId } },
      attributes: ['id'],
    });
    const userIds = users.map(u => u.id);
    if (!userIds.length) return successResponse(res, { message: 'No active users to logout', data: { count: 0 } });

    const count = await LoginSession.update(
      { status: 'logged_out', logout_time: new Date() },
      { where: { user_id: { [Op.in]: userIds }, status: 'active' } }
    );
    await RefreshToken.update({ is_revoked: true }, { where: { user_id: { [Op.in]: userIds }, is_revoked: false } });

    await logAudit(currentUserId, 'BULK_LOGOUT', { details: { target, users_affected: count[0] }, req });
    return successResponse(res, { message: `Logged out ${count[0]} active session(s)`, data: { count: count[0], target } });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
