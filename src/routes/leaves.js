const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, LeaveType, LeaveBalance, LeaveRequest, Holiday, Attendance } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');
const { systemLog } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// Business Days Calculation
// ────────────────────────────────────────────────────────────
async function calcBusinessDays(fromDate, toDate) {
  const year = new Date(fromDate).getFullYear();
  const holidays = await Holiday.findAll({ where: { year, is_optional: false } });
  const holidaySet = new Set(holidays.map(h => h.date));

  let days = 0;
  const current = new Date(fromDate);
  const end = new Date(toDate);
  while (current <= end) {
    const dow = current.getDay();
    const ds = current.toISOString().split('T')[0];
    if (dow !== 0 && dow !== 6 && !holidaySet.has(ds)) days++;
    current.setDate(current.getDate() + 1);
  }
  return days;
}

// ────────────────────────────────────────────────────────────
// LEAVE TYPES
// ────────────────────────────────────────────────────────────
router.get('/types', jwtRequired, async (req, res) => {
  try {
    const types = await LeaveType.findAll({ where: { is_active: true }, order: [['name', 'ASC']] });
    return successResponse(res, { data: types.map(t => t.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/types', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.name || !data.code) return errorResponse(res, 'name and code are required', 400);
    const existing = await LeaveType.findOne({ where: { [Op.or]: [{ name: data.name }, { code: data.code }] } });
    if (existing) return errorResponse(res, 'Leave type with this name or code already exists', 409);

    const lt = await LeaveType.create({
      name: data.name, code: data.code.toUpperCase(),
      annual_quota: data.annual_quota ?? 0,
      is_paid: data.is_paid ?? true,
      is_carry_forward: data.is_carry_forward ?? false,
      max_carry_forward: data.max_carry_forward ?? 0,
      requires_approval: data.requires_approval ?? true,
      min_days_advance: data.min_days_advance ?? 0,
      description: data.description || null,
    });
    return successResponse(res, { data: lt.toDict(), message: 'Leave type created' }, 201);
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/types/:typeId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const lt = await LeaveType.findByPk(req.params.typeId);
    if (!lt) return errorResponse(res, 'Leave type not found', 404);
    const data = req.body || {};
    const fields = ['name', 'annual_quota', 'is_paid', 'is_carry_forward',
      'max_carry_forward', 'requires_approval', 'min_days_advance', 'description', 'is_active'];
    for (const f of fields) if (data[f] !== undefined) lt[f] = data[f];
    await lt.save();
    return successResponse(res, { data: lt.toDict(), message: 'Leave type updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// LEAVE BALANCES
// ────────────────────────────────────────────────────────────
router.get('/balances/me', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const year = parseInt(req.query.year || new Date().getFullYear());
    const balances = await LeaveBalance.findAll({
      where: { user_id: currentUserId, year },
      include: [{ model: LeaveType, as: 'LeaveType' }],
    });
    return successResponse(res, { data: balances.map(b => b.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.get('/balances/:userId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const year = parseInt(req.query.year || new Date().getFullYear());
    const balances = await LeaveBalance.findAll({
      where: { user_id: parseInt(req.params.userId), year },
      include: [{ model: LeaveType, as: 'LeaveType' }],
    });
    return successResponse(res, { data: balances.map(b => b.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/balances/init', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    const year = parseInt(data.year || new Date().getFullYear());
    const where = { role: 'employee', is_active: true };
    if (data.user_id) where.id = parseInt(data.user_id);

    const employees = await User.findAll({ where });
    const leaveTypes = await LeaveType.findAll({ where: { is_active: true } });
    let created = 0;

    for (const emp of employees) {
      for (const lt of leaveTypes) {
        const [, wasCreated] = await LeaveBalance.findOrCreate({
          where: { user_id: emp.id, leave_type_id: lt.id, year },
          defaults: { user_id: emp.id, leave_type_id: lt.id, year, total_quota: lt.annual_quota, used: 0, carry_forward: 0 },
        });
        if (wasCreated) created++;
      }
    }

    return successResponse(res, { message: `Initialized ${created} leave balances`, data: { created } });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/balances/:userId/:leaveTypeId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    const year = parseInt(data.year || new Date().getFullYear());

    let balance = await LeaveBalance.findOne({
      where: { user_id: parseInt(req.params.userId), leave_type_id: parseInt(req.params.leaveTypeId), year },
    });
    if (!balance) {
      const lt = await LeaveType.findByPk(req.params.leaveTypeId);
      if (!lt) return errorResponse(res, 'Leave type not found', 404);
      balance = await LeaveBalance.create({
        user_id: parseInt(req.params.userId), leave_type_id: parseInt(req.params.leaveTypeId),
        year, total_quota: lt.annual_quota, used: 0, carry_forward: 0,
      });
    }

    if (data.total_quota !== undefined) balance.total_quota = parseInt(data.total_quota);
    if (data.carry_forward !== undefined) balance.carry_forward = parseInt(data.carry_forward);
    if (data.used !== undefined) balance.used = parseFloat(data.used);
    await balance.save();

    const withType = await LeaveBalance.findByPk(balance.id, {
      include: [{ model: LeaveType, as: 'LeaveType' }],
    });
    return successResponse(res, { data: withType.toDict(), message: 'Leave balance updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// APPLY FOR LEAVE
// ────────────────────────────────────────────────────────────
router.post('/apply', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const data = req.body || {};
    const required = ['leave_type_id', 'from_date', 'to_date', 'reason'];
    for (const f of required) {
      if (!data[f]) return errorResponse(res, `${f} is required`, 400);
    }

    const leaveType = await LeaveType.findByPk(data.leave_type_id);
    if (!leaveType || !leaveType.is_active) return errorResponse(res, 'Invalid leave type', 404);

    const fromDate = new Date(data.from_date);
    const toDate = new Date(data.to_date);
    if (toDate < fromDate) return errorResponse(res, 'to_date must be >= from_date', 400);

    let totalDays;
    if (data.is_half_day) {
      totalDays = 0.5;
    } else {
      totalDays = await calcBusinessDays(data.from_date, data.to_date);
    }

    // Check advance notice
    if (leaveType.min_days_advance > 0) {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const diffDays = Math.floor((fromDate - today) / 86400000);
      if (diffDays < leaveType.min_days_advance)
        return errorResponse(res, `This leave requires ${leaveType.min_days_advance} days advance notice`, 400);
    }

    // Check balance
    const year = fromDate.getFullYear();
    const balance = await LeaveBalance.findOne({
      where: { user_id: currentUserId, leave_type_id: leaveType.id, year },
    });
    if (balance) {
      const available = balance.total_quota + balance.carry_forward - balance.used;
      if (available < totalDays)
        return errorResponse(res, `Insufficient leave balance. Available: ${available}, Requested: ${totalDays}`, 400);
    }

    // Check overlap
    const overlap = await LeaveRequest.findOne({
      where: {
        user_id: currentUserId,
        status: { [Op.in]: ['pending', 'approved'] },
        [Op.or]: [
          { from_date: { [Op.between]: [data.from_date, data.to_date] } },
          { to_date: { [Op.between]: [data.from_date, data.to_date] } },
          { from_date: { [Op.lte]: data.from_date }, to_date: { [Op.gte]: data.to_date } },
        ],
      },
    });
    if (overlap) return errorResponse(res, 'Leave request overlaps with an existing request', 409);

    const leaveRequest = await LeaveRequest.create({
      user_id: currentUserId,
      leave_type_id: parseInt(data.leave_type_id),
      from_date: data.from_date,
      to_date: data.to_date,
      total_days: totalDays,
      is_half_day: data.is_half_day || false,
      half_day_period: data.is_half_day ? data.half_day_period : null,
      reason: data.reason,
      status: leaveType.requires_approval ? 'pending' : 'approved',
    });

    // Auto-approve: deduct balance
    if (!leaveType.requires_approval && balance) {
      balance.used += totalDays;
      await balance.save();
    }

    await systemLog('LEAVE_APPLIED', {
      userId: currentUserId, resource: 'leave_request', resourceId: leaveRequest.id,
      after: { leave_type: leaveType.name, from: data.from_date, to: data.to_date, days: totalDays }, req,
    });

    const full = await LeaveRequest.findByPk(leaveRequest.id, {
      include: [
        { model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: LeaveType, as: 'LeaveType', attributes: ['name', 'code'] },
      ],
    });
    return successResponse(res, { data: full.toDict(), message: 'Leave request submitted' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// MY LEAVE REQUESTS
// ────────────────────────────────────────────────────────────
router.get('/my', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const where = { user_id: currentUserId };
    if (req.query.status) where.status = req.query.status;
    if (req.query.year) {
      const y = parseInt(req.query.year);
      where.from_date = { [Op.between]: [`${y}-01-01`, `${y}-12-31`] };
    }
    const requests = await LeaveRequest.findAll({
      where,
      include: [
        { model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: LeaveType, as: 'LeaveType', attributes: ['name', 'code'] },
        { model: User, as: 'Reviewer', attributes: ['first_name', 'last_name'] },
      ],
      order: [['created_at', 'DESC']],
    });
    return successResponse(res, { data: requests.map(r => r.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// ALL LEAVE REQUESTS (admin)
// ────────────────────────────────────────────────────────────
router.get('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.status) where.status = req.query.status;
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.year) {
      const y = parseInt(req.query.year);
      where.from_date = { [Op.between]: [`${y}-01-01`, `${y}-12-31`] };
    }
    const requests = await LeaveRequest.findAll({
      where,
      include: [
        { model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department'] },
        { model: LeaveType, as: 'LeaveType', attributes: ['name', 'code', 'is_paid'] },
        { model: User, as: 'Reviewer', attributes: ['first_name', 'last_name'] },
      ],
      order: [['created_at', 'DESC']],
    });
    return successResponse(res, { data: requests.map(r => r.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// REVIEW (approve/reject)
// ────────────────────────────────────────────────────────────
router.post('/:requestId/review', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const leaveRequest = await LeaveRequest.findByPk(req.params.requestId, {
      include: [
        { model: LeaveType, as: 'LeaveType' },
        { model: User, as: 'User' },
      ],
    });
    if (!leaveRequest) return errorResponse(res, 'Leave request not found', 404);
    if (leaveRequest.status !== 'pending') return errorResponse(res, 'Only pending requests can be reviewed', 400);

    const data = req.body || {};
    if (!data.action || !['approved', 'rejected'].includes(data.action))
      return errorResponse(res, 'action must be "approved" or "rejected"', 400);

    leaveRequest.status = data.action;
    leaveRequest.reviewed_by = currentUser.id;
    leaveRequest.reviewed_at = new Date();
    leaveRequest.review_comment = data.comment || null;
    await leaveRequest.save();

    // If approved, deduct balance and update attendance
    if (data.action === 'approved') {
      const year = new Date(leaveRequest.from_date).getFullYear();
      const balance = await LeaveBalance.findOne({
        where: { user_id: leaveRequest.user_id, leave_type_id: leaveRequest.leave_type_id, year },
      });
      if (balance) {
        balance.used += leaveRequest.total_days;
        await balance.save();
      }

      // Mark attendance as on_leave for the date range
      const current = new Date(leaveRequest.from_date);
      const end = new Date(leaveRequest.to_date);
      while (current <= end) {
        const ds = current.toISOString().split('T')[0];
        const [att] = await Attendance.findOrCreate({
          where: { user_id: leaveRequest.user_id, date: ds },
          defaults: {
            user_id: leaveRequest.user_id, date: ds, status: 'on_leave',
            is_manually_edited: true, edited_by: currentUser.id, edit_reason: 'Leave approved',
          },
        });
        if (att.status !== 'on_leave') {
          att.status = 'on_leave'; await att.save();
        }
        current.setDate(current.getDate() + 1);
      }
    }

    await systemLog('LEAVE_REVIEWED', {
      userId: currentUser.id, resource: 'leave_request', resourceId: leaveRequest.id,
      after: { status: data.action, comment: data.comment }, req,
    });

    return successResponse(res, {
      data: leaveRequest.toDict(),
      message: `Leave request ${data.action}`,
    });
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// CANCEL LEAVE
// ────────────────────────────────────────────────────────────
router.post('/:requestId/cancel', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const leaveRequest = await LeaveRequest.findByPk(req.params.requestId, {
      include: [{ model: LeaveType, as: 'LeaveType' }],
    });
    if (!leaveRequest) return errorResponse(res, 'Leave request not found', 404);

    const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
    if (!isAdmin && leaveRequest.user_id !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);
    if (!['pending', 'approved'].includes(leaveRequest.status))
      return errorResponse(res, 'Only pending or approved requests can be cancelled', 400);

    const wasApproved = leaveRequest.status === 'approved';
    leaveRequest.status = 'cancelled';
    await leaveRequest.save();

    // Restore balance if was approved
    if (wasApproved) {
      const year = new Date(leaveRequest.from_date).getFullYear();
      const balance = await LeaveBalance.findOne({
        where: { user_id: leaveRequest.user_id, leave_type_id: leaveRequest.leave_type_id, year },
      });
      if (balance) {
        balance.used = Math.max(0, balance.used - leaveRequest.total_days);
        await balance.save();
      }
    }

    return successResponse(res, { message: 'Leave request cancelled' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
