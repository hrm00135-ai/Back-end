const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, Attendance, AttendanceConfig, Holiday, LeaveRequest } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');
const { systemLog } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// ATTENDANCE CONFIG (admin/super_admin)
// ────────────────────────────────────────────────────────────
router.get('/config', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const configs = await AttendanceConfig.findAll({ order: [['id', 'ASC']] });
    return successResponse(res, { data: configs.map(c => c.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/config', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.name) return errorResponse(res, 'name is required', 400);

    const existing = await AttendanceConfig.findOne({ where: { name: data.name } });
    if (existing) return errorResponse(res, 'Config with this name already exists', 409);

    const cfg = await AttendanceConfig.create({
      name: data.name,
      shift_start: data.shift_start || '09:00',
      shift_end: data.shift_end || '18:00',
      late_threshold_minutes: data.late_threshold_minutes ?? 15,
      half_day_threshold_hours: data.half_day_threshold_hours ?? 4.0,
      full_day_threshold_hours: data.full_day_threshold_hours ?? 8.0,
      overtime_after_hours: data.overtime_after_hours ?? 9.0,
    });
    return successResponse(res, { data: cfg.toDict(), message: 'Attendance config created' }, 201);
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/config/:configId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const cfg = await AttendanceConfig.findByPk(req.params.configId);
    if (!cfg) return errorResponse(res, 'Config not found', 404);
    const data = req.body || {};
    const fields = ['name', 'shift_start', 'shift_end', 'late_threshold_minutes',
      'half_day_threshold_hours', 'full_day_threshold_hours', 'overtime_after_hours', 'is_active'];
    for (const f of fields) if (data[f] !== undefined) cfg[f] = data[f];
    await cfg.save();
    return successResponse(res, { data: cfg.toDict(), message: 'Config updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// CHECK-IN
// ────────────────────────────────────────────────────────────
router.post('/checkin', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const data = req.body || {};

    let targetUserId;
    if (['admin', 'super_admin'].includes(currentUser.role) && data.user_id) {
      targetUserId = parseInt(data.user_id);
    } else {
      targetUserId = currentUserId;
    }

    const today = new Date().toISOString().split('T')[0];
    const existing = await Attendance.findOne({ where: { user_id: targetUserId, date: today } });
    if (existing && existing.check_in_time) {
      return errorResponse(res, 'Already checked in today', 409);
    }

    const cfg = await AttendanceConfig.findOne({ where: { is_active: true }, order: [['id', 'DESC']] });
    const now = new Date();

    let attendance;
    if (existing) {
      existing.check_in_time = now;
      existing.check_in_lat = data.latitude || null;
      existing.check_in_lng = data.longitude || null;
      existing.check_in_address = data.address || null;
      await existing.save();
      attendance = existing;
    } else {
      attendance = await Attendance.create({
        user_id: targetUserId, date: today,
        check_in_time: now,
        check_in_lat: data.latitude || null,
        check_in_lng: data.longitude || null,
        check_in_address: data.address || null,
        status: 'present',
      });
    }

    // Calculate late status
    if (cfg) {
      attendance.calculateHours(cfg);
      await attendance.save();
    }

    await systemLog('CHECK_IN', {
      userId: currentUserId, resource: 'attendance', resourceId: attendance.id,
      details: { target_user: targetUserId, check_in: now.toISOString() }, req,
    });

    return successResponse(res, { data: attendance.toDict(), message: 'Checked in successfully' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// CHECK-OUT
// ────────────────────────────────────────────────────────────
router.post('/checkout', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const data = req.body || {};

    let targetUserId;
    if (['admin', 'super_admin'].includes(currentUser.role) && data.user_id) {
      targetUserId = parseInt(data.user_id);
    } else {
      targetUserId = currentUserId;
    }

    const today = new Date().toISOString().split('T')[0];
    const attendance = await Attendance.findOne({ where: { user_id: targetUserId, date: today } });
    if (!attendance || !attendance.check_in_time) return errorResponse(res, 'No check-in found for today', 404);
    if (attendance.check_out_time) return errorResponse(res, 'Already checked out today', 409);

    const cfg = await AttendanceConfig.findOne({ where: { is_active: true }, order: [['id', 'DESC']] });
    const now = new Date();
    attendance.check_out_time = now;
    attendance.check_out_lat = data.latitude || null;
    attendance.check_out_lng = data.longitude || null;
    attendance.check_out_address = data.address || null;

    attendance.calculateHours(cfg);
    await attendance.save();

    await systemLog('CHECK_OUT', {
      userId: currentUserId, resource: 'attendance', resourceId: attendance.id,
      details: { target_user: targetUserId, check_out: now.toISOString(), total_hours: attendance.total_hours }, req,
    });

    return successResponse(res, { data: attendance.toDict(), message: 'Checked out successfully' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET TODAY'S ATTENDANCE (employee)
// ────────────────────────────────────────────────────────────
router.get('/today', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const today = new Date().toISOString().split('T')[0];
    const attendance = await Attendance.findOne({
      where: { user_id: currentUserId, date: today },
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });
    return successResponse(res, { data: attendance ? attendance.toDict() : null });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET MY ATTENDANCE HISTORY
// ────────────────────────────────────────────────────────────
router.get('/my', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const where = { user_id: currentUserId };
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };
    if (req.query.month && req.query.year) {
      const year = parseInt(req.query.year);
      const month = parseInt(req.query.month);
      const start = `${year}-${String(month).padStart(2, '0')}-01`;
      const end = new Date(year, month, 0).toISOString().split('T')[0];
      where.date = { [Op.between]: [start, end] };
    }

    const records = await Attendance.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
      order: [['date', 'DESC']],
    });
    return successResponse(res, { data: records.map(a => a.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET ALL ATTENDANCE (admin)
// ────────────────────────────────────────────────────────────
router.get('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.date) where.date = req.query.date;
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };
    if (req.query.status) where.status = req.query.status;
    if (req.query.month && req.query.year) {
      const year = parseInt(req.query.year);
      const month = parseInt(req.query.month);
      const start = `${year}-${String(month).padStart(2, '0')}-01`;
      const end = new Date(year, month, 0).toISOString().split('T')[0];
      where.date = { [Op.between]: [start, end] };
    }

    const records = await Attendance.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department'] }],
      order: [['date', 'DESC'], ['user_id', 'ASC']],
    });
    return successResponse(res, { data: records.map(a => a.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET ATTENDANCE FOR A SPECIFIC USER (admin)
// ────────────────────────────────────────────────────────────
router.get('/user/:userId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = { user_id: parseInt(req.params.userId) };
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };
    if (req.query.month && req.query.year) {
      const year = parseInt(req.query.year);
      const month = parseInt(req.query.month);
      const start = `${year}-${String(month).padStart(2, '0')}-01`;
      const end = new Date(year, month, 0).toISOString().split('T')[0];
      where.date = { [Op.between]: [start, end] };
    }

    const records = await Attendance.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
      order: [['date', 'DESC']],
    });
    return successResponse(res, { data: records.map(a => a.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// MANUAL EDIT (admin)
// ────────────────────────────────────────────────────────────
router.put('/:attendanceId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const attendance = await Attendance.findByPk(req.params.attendanceId);
    if (!attendance) return errorResponse(res, 'Attendance record not found', 404);

    const data = req.body || {};
    if (!data.edit_reason) return errorResponse(res, 'edit_reason is required for manual edits', 400);

    const before = attendance.toDict();
    const fields = ['check_in_time', 'check_out_time', 'check_in_address', 'check_out_address',
      'check_in_lat', 'check_in_lng', 'check_out_lat', 'check_out_lng', 'status', 'notes'];
    for (const f of fields) if (data[f] !== undefined) attendance[f] = data[f];

    attendance.is_manually_edited = true;
    attendance.edited_by = currentUser.id;
    attendance.edit_reason = data.edit_reason;

    const cfg = await AttendanceConfig.findOne({ where: { is_active: true }, order: [['id', 'DESC']] });
    if (attendance.check_in_time && attendance.check_out_time) {
      attendance.calculateHours(cfg);
    }

    await attendance.save();

    await systemLog('ATTENDANCE_EDITED', {
      userId: currentUser.id, resource: 'attendance', resourceId: attendance.id,
      before, after: attendance.toDict(), details: { reason: data.edit_reason }, req,
    });

    return successResponse(res, { data: attendance.toDict(), message: 'Attendance updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// MARK ABSENT (admin)
// ────────────────────────────────────────────────────────────
router.post('/mark-absent', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.date) return errorResponse(res, 'date is required', 400);

    const [attendance, created] = await Attendance.findOrCreate({
      where: { user_id: parseInt(data.user_id), date: data.date },
      defaults: {
        user_id: parseInt(data.user_id), date: data.date,
        status: 'absent', is_manually_edited: true,
        edited_by: currentUser.id, edit_reason: data.reason || 'Marked absent by admin',
      },
    });
    if (!created) {
      attendance.status = 'absent';
      attendance.is_manually_edited = true;
      attendance.edited_by = currentUser.id;
      attendance.edit_reason = data.reason || 'Marked absent by admin';
      await attendance.save();
    }
    return successResponse(res, { data: attendance.toDict(), message: 'Marked as absent' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// DAILY SUMMARY (admin)
// ────────────────────────────────────────────────────────────
router.get('/summary/daily', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const date = req.query.date || new Date().toISOString().split('T')[0];
    const employees = await User.findAll({ where: { role: 'employee', is_active: true } });
    const records = await Attendance.findAll({
      where: { date },
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });

    const recordMap = {};
    for (const r of records) recordMap[r.user_id] = r;

    const present = [], absent = [], onLeave = [], notMarked = [];
    for (const emp of employees) {
      const r = recordMap[emp.id];
      if (!r) {
        notMarked.push({ user_id: emp.id, employee_id: emp.employee_id, name: `${emp.first_name} ${emp.last_name}` });
      } else if (r.status === 'present') {
        present.push(r.toDict());
      } else if (r.status === 'on_leave') {
        onLeave.push(r.toDict());
      } else if (r.status === 'absent') {
        absent.push(r.toDict());
      }
    }

    return successResponse(res, {
      data: {
        date, total_employees: employees.length,
        present_count: present.length, absent_count: absent.length,
        on_leave_count: onLeave.length, not_marked_count: notMarked.length,
        present, absent, on_leave: onLeave, not_marked: notMarked,
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// MONTHLY REPORT (admin)
// ────────────────────────────────────────────────────────────
router.get('/summary/monthly', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const year = parseInt(req.query.year || new Date().getFullYear());
    const month = parseInt(req.query.month || (new Date().getMonth() + 1));
    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    const end = new Date(year, month, 0).toISOString().split('T')[0];

    const employees = await User.findAll({
      where: { role: 'employee', is_active: true },
      order: [['first_name', 'ASC']],
    });
    const records = await Attendance.findAll({
      where: { date: { [Op.between]: [start, end] } },
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });

    const byUser = {};
    for (const r of records) {
      if (!byUser[r.user_id]) byUser[r.user_id] = [];
      byUser[r.user_id].push(r);
    }

    const summary = employees.map(emp => {
      const recs = byUser[emp.id] || [];
      const present = recs.filter(r => r.status === 'present').length;
      const halfDay = recs.filter(r => r.status === 'half_day').length;
      const absent = recs.filter(r => r.status === 'absent').length;
      const onLeave = recs.filter(r => r.status === 'on_leave').length;
      const totalHours = recs.reduce((s, r) => s + (r.total_hours || 0), 0);
      const overTime = recs.reduce((s, r) => s + (r.overtime_hours || 0), 0);
      const lateCount = recs.filter(r => r.is_late).length;
      return {
        user_id: emp.id, employee_id: emp.employee_id,
        name: `${emp.first_name} ${emp.last_name}`,
        present_days: present, half_day_count: halfDay,
        absent_days: absent, on_leave_days: onLeave,
        total_hours: Math.round(totalHours * 100) / 100,
        overtime_hours: Math.round(overTime * 100) / 100,
        late_count: lateCount,
      };
    });

    return successResponse(res, { data: { year, month, summary } });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// HOLIDAYS
// ────────────────────────────────────────────────────────────
router.get('/holidays', jwtRequired, async (req, res) => {
  try {
    const year = parseInt(req.query.year || new Date().getFullYear());
    const { Holiday } = require('../models');
    const holidays = await Holiday.findAll({
      where: { year }, order: [['date', 'ASC']],
    });
    return successResponse(res, { data: holidays.map(h => h.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/holidays', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.name || !data.date) return errorResponse(res, 'name and date are required', 400);
    const year = parseInt(data.date.split('-')[0]);
    const { Holiday } = require('../models');
    const holiday = await Holiday.create({
      name: data.name, date: data.date, is_optional: data.is_optional || false, year,
    });
    return successResponse(res, { data: holiday.toDict(), message: 'Holiday added' }, 201);
  } catch (err) {
    if (err.name === 'SequelizeUniqueConstraintError') return errorResponse(res, 'Holiday on this date already exists', 409);
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.delete('/holidays/:holidayId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const { Holiday } = require('../models');
    const holiday = await Holiday.findByPk(req.params.holidayId);
    if (!holiday) return errorResponse(res, 'Holiday not found', 404);
    await holiday.destroy();
    return successResponse(res, { message: 'Holiday deleted' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
