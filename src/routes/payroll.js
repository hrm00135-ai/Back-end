const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, SalaryStructure, DailyWage, Payslip, Attendance } = require('../models');
const { requireRole, jwtRequired, successResponse, errorResponse } = require('../utils/helpers');
const { systemLog } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// SALARY STRUCTURES
// ────────────────────────────────────────────────────────────
router.get('/salary-structures', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.is_active !== undefined) where.is_active = req.query.is_active === 'true';

    const structs = await SalaryStructure.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department'] }],
      order: [['effective_from', 'DESC']],
    });
    return successResponse(res, { data: structs.map(s => s.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.get('/salary-structures/me', jwtRequired, async (req, res) => {
  try {
    const struct = await SalaryStructure.findOne({
      where: { user_id: parseInt(req.currentUserId), is_active: true },
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });
    return successResponse(res, { data: struct ? struct.toDict() : null });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/salary-structures', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.effective_from) return errorResponse(res, 'effective_from is required', 400);

    const targetUser = await User.findByPk(data.user_id);
    if (!targetUser) return errorResponse(res, 'User not found', 404);

    // Deactivate previous structure
    await SalaryStructure.update(
      { is_active: false, effective_to: data.effective_from },
      { where: { user_id: data.user_id, is_active: true } }
    );

    const struct = SalaryStructure.build({
      user_id: parseInt(data.user_id),
      basic_salary: data.basic_salary || 0,
      hra: data.hra || 0,
      da: data.da || 0,
      conveyance: data.conveyance || 0,
      medical_allowance: data.medical_allowance || 0,
      special_allowance: data.special_allowance || 0,
      other_allowance: data.other_allowance || 0,
      pf_employee: data.pf_employee || 0,
      pf_employer: data.pf_employer || 0,
      esi_employee: data.esi_employee || 0,
      esi_employer: data.esi_employer || 0,
      professional_tax: data.professional_tax || 0,
      tds: data.tds || 0,
      other_deduction: data.other_deduction || 0,
      effective_from: data.effective_from,
      effective_to: data.effective_to || null,
      is_active: true,
      created_by: currentUser.id,
    });
    struct.calculate();
    await struct.save();

    const full = await SalaryStructure.findByPk(struct.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Salary structure created' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// DAILY WAGES
// ────────────────────────────────────────────────────────────
router.get('/daily-wages', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.date) where.date = req.query.date;
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };
    if (req.query.payment_status) where.payment_status = req.query.payment_status;

    const wages = await DailyWage.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
      order: [['date', 'DESC']],
    });
    return successResponse(res, { data: wages.map(w => w.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.get('/daily-wages/me', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const where = { user_id: currentUserId };
    if (req.query.from_date) where.date = { ...(where.date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.date = { ...(where.date || {}), [Op.lte]: req.query.to_date };

    const wages = await DailyWage.findAll({ where, order: [['date', 'DESC']] });
    return successResponse(res, { data: wages.map(w => w.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/daily-wages', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.date) return errorResponse(res, 'date is required', 400);

    const existing = await DailyWage.findOne({ where: { user_id: data.user_id, date: data.date } });
    if (existing) return errorResponse(res, 'Daily wage record already exists for this date', 409);

    const wage = DailyWage.build({
      user_id: parseInt(data.user_id),
      date: data.date,
      hours_worked: data.hours_worked || 0,
      per_hour_rate: data.per_hour_rate || 0,
      per_day_rate: data.per_day_rate || 0,
      pieces_completed: data.pieces_completed || 0,
      per_piece_rate: data.per_piece_rate || 0,
      overtime_hours: data.overtime_hours || 0,
      overtime_rate: data.overtime_rate || 0,
      bonus: data.bonus || 0,
      deduction: data.deduction || 0,
      notes: data.notes || null,
      created_by: currentUser.id,
    });
    wage.calculate();
    await wage.save();

    const full = await DailyWage.findByPk(wage.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Daily wage recorded' }, 201);
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/daily-wages/:wageId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const wage = await DailyWage.findByPk(req.params.wageId);
    if (!wage) return errorResponse(res, 'Wage record not found', 404);
    const data = req.body || {};
    const fields = ['hours_worked', 'per_hour_rate', 'per_day_rate', 'pieces_completed', 'per_piece_rate',
      'overtime_hours', 'overtime_rate', 'bonus', 'deduction', 'payment_status',
      'payment_mode', 'payment_ref', 'notes'];
    for (const f of fields) if (data[f] !== undefined) wage[f] = data[f];

    if (data.payment_status === 'paid' && !wage.paid_at) {
      wage.paid_at = new Date();
      wage.paid_by = parseInt(req.currentUserId);
    }
    wage.calculate();
    await wage.save();

    const full = await DailyWage.findByPk(wage.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Wage updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PAYSLIPS
// ────────────────────────────────────────────────────────────
router.get('/payslips', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.month) where.month = parseInt(req.query.month);
    if (req.query.year) where.year = parseInt(req.query.year);
    if (req.query.payment_status) where.payment_status = req.query.payment_status;

    const payslips = await Payslip.findAll({
      where,
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department', 'designation'] }],
      order: [['year', 'DESC'], ['month', 'DESC']],
    });
    return successResponse(res, { data: payslips.map(p => p.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.get('/payslips/me', jwtRequired, async (req, res) => {
  try {
    const where = { user_id: parseInt(req.currentUserId) };
    if (req.query.year) where.year = parseInt(req.query.year);

    const payslips = await Payslip.findAll({ where, order: [['year', 'DESC'], ['month', 'DESC']] });
    return successResponse(res, { data: payslips.map(p => p.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/payslips/generate', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.month) return errorResponse(res, 'month is required', 400);
    if (!data.year) return errorResponse(res, 'year is required', 400);

    const month = parseInt(data.month);
    const year = parseInt(data.year);
    const userId = parseInt(data.user_id);

    const existing = await Payslip.findOne({ where: { user_id: userId, month, year } });
    if (existing) return errorResponse(res, 'Payslip already generated for this month/year', 409);

    const struct = await SalaryStructure.findOne({
      where: { user_id: userId, is_active: true },
    });
    if (!struct) return errorResponse(res, 'No active salary structure found', 404);

    // Attendance summary
    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    const endDay = new Date(year, month, 0).getDate();
    const end = `${year}-${String(month).padStart(2, '0')}-${String(endDay).padStart(2, '0')}`;

    const attendanceRecords = await Attendance.findAll({
      where: { user_id: userId, date: { [Op.between]: [start, end] } },
    });

    let presentDays = 0, leaveDays = 0, absentDays = 0, halfDays = 0, overtimeHours = 0;
    for (const a of attendanceRecords) {
      if (a.status === 'present') presentDays++;
      else if (a.status === 'half_day') { presentDays += 0.5; halfDays++; }
      else if (a.status === 'on_leave') leaveDays++;
      else if (a.status === 'absent') absentDays++;
      overtimeHours += a.overtime_hours || 0;
    }
    const workingDays = endDay;
    // Leave deduction for unpaid leave
    const leaveDeduction = 0; // Calculated if needed
    const lateDeduction = 0;
    const overtimePay = data.overtime_pay || 0;
    const bonus = data.bonus || 0;

    const grossEarnings = Math.round((
      struct.gross_salary + parseFloat(overtimePay) + parseFloat(bonus)
    ) * 100) / 100;
    const totalDeductions = Math.round((
      struct.total_deductions + leaveDeduction + lateDeduction
    ) * 100) / 100;
    const netPay = Math.round((grossEarnings - totalDeductions) * 100) / 100;

    const payslip = await Payslip.create({
      user_id: userId,
      salary_structure_id: struct.id,
      month, year,
      basic_salary: struct.basic_salary,
      hra: struct.hra,
      da: struct.da,
      conveyance: struct.conveyance,
      medical_allowance: struct.medical_allowance,
      special_allowance: struct.special_allowance,
      other_allowance: struct.other_allowance,
      pf_employee: struct.pf_employee,
      esi_employee: struct.esi_employee,
      professional_tax: struct.professional_tax,
      tds: struct.tds,
      other_deduction: struct.other_deduction,
      overtime_pay: overtimePay,
      bonus,
      leave_deduction: leaveDeduction,
      late_deduction: lateDeduction,
      working_days: workingDays,
      present_days: presentDays,
      leave_days: leaveDays,
      absent_days: absentDays,
      overtime_hours: overtimeHours,
      gross_earnings: grossEarnings,
      total_deductions: totalDeductions,
      net_pay: netPay,
      generated_by: currentUser.id,
    });

    const full = await Payslip.findByPk(payslip.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department', 'designation'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Payslip generated' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/payslips/:payslipId/payment', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const payslip = await Payslip.findByPk(req.params.payslipId);
    if (!payslip) return errorResponse(res, 'Payslip not found', 404);
    const data = req.body || {};

    const statusOrder = ['pending', 'processed', 'paid', 'failed'];
    if (!data.payment_status || !statusOrder.includes(data.payment_status))
      return errorResponse(res, 'Invalid payment_status', 400);

    payslip.payment_status = data.payment_status;
    if (data.payment_date) payslip.payment_date = data.payment_date;
    if (data.payment_mode) payslip.payment_mode = data.payment_mode;
    if (data.transaction_ref) payslip.transaction_ref = data.transaction_ref;
    if (data.payment_notes) payslip.payment_notes = data.payment_notes;
    await payslip.save();

    return successResponse(res, { data: payslip.toDict(), message: 'Payment status updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
