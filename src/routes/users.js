const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, AuditLog } = require('../models');
const {
  hashPassword, generateEmployeeId, requireRole, jwtRequired,
  logAudit, successResponse, errorResponse,
} = require('../utils/helpers');
const { uploadFile, deleteFile } = require('../utils/storage');
const { compressImage } = require('../utils/imageCompress');
const { systemLog } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// CREATE USER  (super_admin | admin)
// ────────────────────────────────────────────────────────────
router.post('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};

    const required = ['email', 'password', 'role', 'first_name', 'last_name', 'phone', 'date_of_joining'];
    for (const f of required) {
      if (!data[f]) return errorResponse(res, `${f} is required`, 400);
    }

    if (data.role === 'super_admin') return errorResponse(res, 'Cannot create super_admin users', 403);
    if (data.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only super_admin can create admin users', 403);

    const email = data.email.trim().toLowerCase();
    const existing = await User.findOne({ where: { email } });
    if (existing) return errorResponse(res, 'Email already registered', 409);

    if (data.password.length < 8) return errorResponse(res, 'Password must be at least 8 characters', 400);

    const employeeId = await generateEmployeeId(data.role);
    const user = await User.create({
      employee_id: employeeId,
      email,
      password_hash: await hashPassword(data.password),
      role: data.role,
      first_name: data.first_name.trim(),
      last_name: data.last_name.trim(),
      phone: data.phone.trim(),
      alt_phone: data.alt_phone ? data.alt_phone.trim() : null,
      department: data.department || null,
      designation: data.designation || null,
      date_of_joining: data.date_of_joining,
      location_of_work: data.location_of_work || null,
      registered_by: currentUser.id,
    });

    await logAudit(currentUser.id, 'USER_CREATED', { targetUserId: user.id, req });
    await systemLog('USER_CREATED', {
      userId: currentUser.id, resource: 'user', resourceId: user.id,
      after: { employee_id: user.employee_id, email: user.email, role: user.role }, req,
    });

    return successResponse(res, { data: user.toDict(), message: 'User created successfully' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET ALL USERS
// ────────────────────────────────────────────────────────────
router.get('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const where = {};

    if (currentUser.role === 'admin') where.role = 'employee';

    if (req.query.is_active !== undefined) where.is_active = req.query.is_active === 'true';
    if (req.query.department) where.department = req.query.department;
    if (req.query.role && currentUser.role === 'super_admin') where.role = req.query.role;
    if (req.query.search) {
      const s = `%${req.query.search}%`;
      where[Op.or] = [
        { first_name: { [Op.like]: s } }, { last_name: { [Op.like]: s } },
        { email: { [Op.like]: s } }, { employee_id: { [Op.like]: s } },
        { designation: { [Op.like]: s } },
      ];
    }

    const users = await User.findAll({ where, order: [['created_at', 'DESC']] });
    return successResponse(res, { data: users.map(u => u.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET SINGLE USER
// ────────────────────────────────────────────────────────────
router.get('/:userId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const targetId = parseInt(req.params.userId);
    const currentUser = await User.findByPk(currentUserId);

    if (!['super_admin', 'admin'].includes(currentUser.role) && currentUserId !== targetId)
      return errorResponse(res, 'Insufficient permissions', 403);

    const user = await User.findByPk(targetId);
    if (!user) return errorResponse(res, 'User not found', 404);

    return successResponse(res, { data: user.toDict() });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// UPDATE USER
// ────────────────────────────────────────────────────────────
router.put('/:userId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const targetId = parseInt(req.params.userId);
    const currentUser = await User.findByPk(currentUserId);
    const targetUser = await User.findByPk(targetId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);

    const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
    if (!isAdmin && currentUserId !== targetId) return errorResponse(res, 'Insufficient permissions', 403);
    if (targetUser.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only super_admin can update admin accounts', 403);

    const data = req.body || {};
    const allowedFields = ['first_name', 'last_name', 'phone', 'alt_phone', 'location_of_work'];
    if (isAdmin) allowedFields.push('department', 'designation', 'date_of_joining', 'date_of_leaving', 'is_active');

    const before = targetUser.toDict();
    const updates = {};
    for (const f of allowedFields) {
      if (data[f] !== undefined) updates[f] = data[f];
    }

    await targetUser.update(updates);

    await systemLog('USER_UPDATED', {
      userId: currentUserId, resource: 'user', resourceId: targetId,
      before, after: targetUser.toDict(), req,
    });

    return successResponse(res, { data: targetUser.toDict(), message: 'User updated successfully' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// UPLOAD PHOTO
// ────────────────────────────────────────────────────────────
router.post('/:userId/photo', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const targetId = parseInt(req.params.userId);
    const currentUser = await User.findByPk(currentUserId);

    const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
    if (!isAdmin && currentUserId !== targetId) return errorResponse(res, 'Insufficient permissions', 403);

    const targetUser = await User.findByPk(targetId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);

    if (!req.files || !req.files.photo) return errorResponse(res, 'No photo file provided', 400);

    const file = req.files.photo;
    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!allowed.includes(file.mimetype)) return errorResponse(res, 'Only JPEG, PNG, WebP, GIF images allowed', 400);
    if (file.size > 10 * 1024 * 1024) return errorResponse(res, 'File size exceeds 10MB limit', 400);

    // Compress
    let uploadBuffer;
    try {
      const result = await compressImage(file.data, { maxSizeKb: 200, maxDimension: 800 });
      uploadBuffer = result.buffer;
    } catch {
      uploadBuffer = file.data;
    }

    // Delete old photo
    if (targetUser.photo_url) {
      try { await deleteFile(targetUser.photo_url); } catch {}
    }

    const { url } = await uploadFile(uploadBuffer, {
      folder: 'jewelcraft/employees/photos',
      publicId: `employee_${targetUser.employee_id}_${Date.now()}`,
      resourceType: 'image',
    });

    targetUser.photo_url = url;
    await targetUser.save();

    await systemLog('PHOTO_UPDATED', { userId: currentUserId, resource: 'user', resourceId: targetId, req });

    return successResponse(res, { data: { photo_url: url }, message: 'Photo uploaded successfully' });
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// CHANGE PASSWORD
// ────────────────────────────────────────────────────────────
router.post('/:userId/change-password', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const targetId = parseInt(req.params.userId);
    const currentUser = await User.findByPk(currentUserId);

    if (currentUserId !== targetId && !['super_admin', 'admin'].includes(currentUser.role))
      return errorResponse(res, 'Insufficient permissions', 403);

    const data = req.body || {};
    if (!data.new_password) return errorResponse(res, 'New password is required', 400);
    if (data.new_password.length < 8) return errorResponse(res, 'Password must be at least 8 characters', 400);

    const targetUser = await User.findByPk(targetId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);

    // Self-change requires current password
    if (currentUserId === targetId) {
      if (!data.current_password) return errorResponse(res, 'Current password is required', 400);
      const { verifyPassword } = require('../utils/helpers');
      if (!await verifyPassword(data.current_password, targetUser.password_hash))
        return errorResponse(res, 'Current password is incorrect', 401);
    }

    targetUser.password_hash = await hashPassword(data.new_password);
    await targetUser.save();

    await logAudit(currentUserId, 'PASSWORD_CHANGED', { targetUserId: targetId, req });
    return successResponse(res, { message: 'Password changed successfully' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// DEACTIVATE USER
// ────────────────────────────────────────────────────────────
router.post('/:userId/deactivate', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const targetUser = await User.findByPk(req.params.userId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);
    if (targetUser.role === 'super_admin') return errorResponse(res, 'Cannot deactivate super admin', 403);
    if (targetUser.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only super_admin can deactivate admin accounts', 403);
    if (targetUser.id === currentUser.id) return errorResponse(res, 'Cannot deactivate your own account', 400);

    const data = req.body || {};
    targetUser.is_active = false;
    if (data.date_of_leaving) targetUser.date_of_leaving = data.date_of_leaving;
    await targetUser.save();

    const { RefreshToken, LoginSession } = require('../models');
    await RefreshToken.update({ is_revoked: true }, { where: { user_id: targetUser.id } });
    await LoginSession.update({ status: 'logged_out', logout_time: new Date() }, { where: { user_id: targetUser.id, status: 'active' } });

    await logAudit(currentUser.id, 'USER_DEACTIVATED', { targetUserId: targetUser.id, req });
    return successResponse(res, { message: `User ${targetUser.employee_id} deactivated` });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// REACTIVATE USER
// ────────────────────────────────────────────────────────────
router.post('/:userId/activate', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const targetUser = await User.findByPk(req.params.userId);
    if (!targetUser) return errorResponse(res, 'User not found', 404);
    if (targetUser.role === 'admin' && currentUser.role !== 'super_admin')
      return errorResponse(res, 'Only super_admin can reactivate admin accounts', 403);

    targetUser.is_active = true;
    targetUser.date_of_leaving = null;
    await targetUser.save();

    await logAudit(currentUser.id, 'USER_REACTIVATED', { targetUserId: targetUser.id, req });
    return successResponse(res, { message: `User ${targetUser.employee_id} reactivated` });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// AUDIT LOGS
// ────────────────────────────────────────────────────────────
router.get('/:userId/audit-logs', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const logs = await AuditLog.findAll({
      where: { [Op.or]: [{ user_id: req.params.userId }, { target_user_id: req.params.userId }] },
      include: [
        { model: User, as: 'User', attributes: ['id', 'employee_id', 'first_name', 'last_name'] },
        { model: User, as: 'TargetUser', attributes: ['id', 'employee_id', 'first_name', 'last_name'] },
      ],
      order: [['created_at', 'DESC']],
      limit: 100,
    });
    return successResponse(res, { data: logs.map(l => l.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
