const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const config = require('../config/config');

// ────────────────────────────────────────────────────────────
// Password Hashing
// ────────────────────────────────────────────────────────────
async function hashPassword(password) {
  return bcrypt.hash(password, 12);
}

async function verifyPassword(password, hash) {
  return bcrypt.compare(password, hash);
}

// ────────────────────────────────────────────────────────────
// OTP
// ────────────────────────────────────────────────────────────
function generateOtp(length) {
  length = length || 6;
  return Array.from({ length }, () => Math.floor(Math.random() * 10)).join('');
}

async function hashOtp(otp) {
  return hashPassword(otp);
}

async function verifyOtp(otp, otpHash) {
  return verifyPassword(otp, otpHash);
}

// ────────────────────────────────────────────────────────────
// Employee ID Generation
// ────────────────────────────────────────────────────────────
async function generateEmployeeId(role) {
  const { User } = require('../models');
  const { Op } = require('sequelize');
  const prefixMap = { super_admin: 'SA', admin: 'ADM', employee: 'EMP' };
  const prefix = prefixMap[role] || 'USR';

  const latest = await User.findOne({
    where: { employee_id: { [Op.like]: `${prefix}-%` } },
    order: [['id', 'DESC']],
  });

  let nextNum = 1;
  if (latest) {
    try {
      const lastNum = parseInt(latest.employee_id.split('-')[1], 10);
      if (!isNaN(lastNum)) nextNum = lastNum + 1;
    } catch (e) {
      nextNum = 1;
    }
  }
  return `${prefix}-${String(nextNum).padStart(3, '0')}`;
}

// ────────────────────────────────────────────────────────────
// Role-Based Access Middleware
// ────────────────────────────────────────────────────────────
function requireRole() {
  const allowedRoles = Array.from(arguments);
  return async function(req, res, next) {
    try {
      const authHeader = req.headers.authorization;
      if (!authHeader || !authHeader.startsWith('Bearer ')) {
        return res.status(401).json({ status: 'error', message: 'Authorization token is missing' });
      }
      const token = authHeader.split(' ')[1];
      let decoded;
      try {
        decoded = jwt.verify(token, config.JWT_SECRET_KEY);
      } catch (err) {
        if (err.name === 'TokenExpiredError') {
          return res.status(401).json({ status: 'error', message: 'Token has expired', error: 'token_expired' });
        }
        return res.status(401).json({ status: 'error', message: 'Invalid token', error: 'invalid_token' });
      }

      const { User } = require('../models');
      const userId = decoded.sub || decoded.id || decoded.user_id;
      const user = await User.findByPk(userId);
      if (!user) return res.status(404).json({ status: 'error', message: 'User not found' });
      if (!user.is_active) return res.status(403).json({ status: 'error', message: 'Account is deactivated' });
      if (user.is_locked) return res.status(403).json({ status: 'error', message: 'Account is locked' });
      if (!allowedRoles.includes(user.role)) {
        return res.status(403).json({ status: 'error', message: 'Insufficient permissions' });
      }
      req.currentUserId = user.id;
      req.currentUser = user;
      next();
    } catch (err) {
      console.error('[requireRole error]', err.message);
      return res.status(500).json({ status: 'error', message: 'Internal server error' });
    }
  };
}

// ────────────────────────────────────────────────────────────
// JWT Auth Middleware (any role)
// ────────────────────────────────────────────────────────────
function jwtRequired(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ status: 'error', message: 'Authorization token is missing', error: 'authorization_required' });
  }
  const token = authHeader.split(' ')[1];
  try {
    const decoded = jwt.verify(token, config.JWT_SECRET_KEY);
    req.currentUserId = String(decoded.sub || decoded.id || decoded.user_id);
    req.jwtPayload = decoded;
    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({ status: 'error', message: 'Token has expired', error: 'token_expired' });
    }
    return res.status(401).json({ status: 'error', message: 'Invalid token', error: 'invalid_token' });
  }
}

// ────────────────────────────────────────────────────────────
// JWT Token Creation
// ────────────────────────────────────────────────────────────
function createAccessToken(userId) {
  return jwt.sign(
    { sub: String(userId) },
    config.JWT_SECRET_KEY,
    { expiresIn: config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES + 'm' }
  );
}

function createRefreshToken(userId) {
  return jwt.sign(
    { sub: String(userId), type: 'refresh' },
    config.JWT_SECRET_KEY,
    { expiresIn: config.JWT_REFRESH_TOKEN_EXPIRES_DAYS + 'd' }
  );
}

// ────────────────────────────────────────────────────────────
// Audit Logging  — lazy-require to avoid circular dep at startup
// ────────────────────────────────────────────────────────────
async function logAudit(userId, action, opts) {
  opts = opts || {};
  try {
    const { AuditLog } = require('../models');
    let ipAddress = null;
    if (opts.req) {
      const fwd = opts.req.headers['x-forwarded-for'] || '';
      const remote = (opts.req.socket && opts.req.socket.remoteAddress) || '';
      ipAddress = (fwd || remote).split(',')[0].trim() || null;
    }
    await AuditLog.create({
      user_id:        userId       ? parseInt(userId)              : null,
      action:         action,
      target_user_id: opts.targetUserId ? parseInt(opts.targetUserId) : null,
      details:        opts.details  ? (typeof opts.details === 'object' ? JSON.stringify(opts.details) : opts.details) : null,
      ip_address:     ipAddress,
    });
  } catch (e) {
    // Never crash the main flow for audit logging
    console.warn('[logAudit failed]', e.message);
  }
}

// ────────────────────────────────────────────────────────────
// Response Helpers
// statusCode can be the 3rd argument OR inside the options object
// ────────────────────────────────────────────────────────────
function successResponse(res, options, httpStatus) {
  if (!options) options = {};
  var data       = options.data;
  var message    = options.message    || 'Success';
  var statusCode = options.statusCode || 200;
  var code       = httpStatus || statusCode || 200;
  var body = { status: 'success', message: message };
  if (data !== undefined) body.data = data;
  return res.status(code).json(body);
}

function errorResponse(res, message, statusCode, errors) {
  message    = message    || 'Error';
  statusCode = statusCode || 400;
  var body = { status: 'error', message: message };
  if (errors) body.errors = errors;
  return res.status(statusCode).json(body);
}

module.exports = {
  hashPassword,
  verifyPassword,
  generateOtp,
  hashOtp,
  verifyOtp,
  generateEmployeeId,
  requireRole,
  jwtRequired,
  createAccessToken,
  createRefreshToken,
  logAudit,
  successResponse,
  errorResponse,
};
