const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const sequelize = require('../config/database');
const { User, Attendance, LeaveRequest, Task, Payslip, PaymentTransaction, AuditLog, SystemLog } = require('../models');
const { requireRole, jwtRequired, successResponse, errorResponse } = require('../utils/helpers');
const { verifyLogIntegrity } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// DASHBOARD STATS (admin)
// ────────────────────────────────────────────────────────────
router.get('/dashboard', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const today = new Date().toISOString().split('T')[0];

    const [
      totalEmployees, activeEmployees,
      presentToday, onLeaveToday,
      pendingLeaves, pendingTasks,
      completedTasksThisMonth,
    ] = await Promise.all([
      User.count({ where: { role: 'employee' } }),
      User.count({ where: { role: 'employee', is_active: true } }),
      Attendance.count({ where: { date: today, status: 'present' } }),
      Attendance.count({ where: { date: today, status: 'on_leave' } }),
      LeaveRequest.count({ where: { status: 'pending' } }),
      Task.count({ where: { status: { [Op.in]: ['pending', 'in_progress'] } } }),
      Task.count({
        where: {
          status: 'completed',
          completed_at: {
            [Op.gte]: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
          },
        },
      }),
    ]);

    return successResponse(res, {
      data: {
        total_employees: totalEmployees,
        active_employees: activeEmployees,
        present_today: presentToday,
        on_leave_today: onLeaveToday,
        absent_today: activeEmployees - presentToday - onLeaveToday,
        pending_leaves: pendingLeaves,
        pending_tasks: pendingTasks,
        completed_tasks_this_month: completedTasksThisMonth,
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// ATTENDANCE REPORT
// ────────────────────────────────────────────────────────────
router.get('/attendance', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const year = parseInt(req.query.year || new Date().getFullYear());
    const month = parseInt(req.query.month || (new Date().getMonth() + 1));
    const start = `${year}-${String(month).padStart(2, '0')}-01`;
    const end = new Date(year, month, 0).toISOString().split('T')[0];

    const where = { date: { [Op.between]: [start, end] } };
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);

    const records = await Attendance.findAll({
      where,
      include: [{
        model: User, as: 'User',
        attributes: ['first_name', 'last_name', 'employee_id', 'department', 'designation'],
        where: { is_active: true },
        required: true,
      }],
      order: [['date', 'ASC']],
    });

    return successResponse(res, {
      data: {
        period: { year, month, from: start, to: end },
        records: records.map(r => r.toDict()),
        total: records.length,
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// LEAVE REPORT
// ────────────────────────────────────────────────────────────
router.get('/leaves', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const year = parseInt(req.query.year || new Date().getFullYear());
    const where = { from_date: { [Op.between]: [`${year}-01-01`, `${year}-12-31`] } };
    if (req.query.status) where.status = req.query.status;
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);

    const { LeaveType } = require('../models');
    const requests = await LeaveRequest.findAll({
      where,
      include: [
        { model: User, as: 'User', attributes: ['first_name', 'last_name', 'employee_id', 'department'] },
        { model: LeaveType, as: 'LeaveType', attributes: ['name', 'code', 'is_paid'] },
      ],
      order: [['from_date', 'DESC']],
    });

    return successResponse(res, {
      data: {
        year,
        records: requests.map(r => r.toDict()),
        total: requests.length,
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PAYROLL REPORT
// ────────────────────────────────────────────────────────────
router.get('/payroll', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const month = parseInt(req.query.month || (new Date().getMonth() + 1));
    const year = parseInt(req.query.year || new Date().getFullYear());
    const where = { month, year };
    if (req.query.payment_status) where.payment_status = req.query.payment_status;

    const payslips = await Payslip.findAll({
      where,
      include: [{
        model: User, as: 'User',
        attributes: ['first_name', 'last_name', 'employee_id', 'department', 'designation'],
      }],
      order: [['generated_at', 'DESC']],
    });

    const totalGross = payslips.reduce((s, p) => s + (p.gross_earnings || 0), 0);
    const totalNet = payslips.reduce((s, p) => s + (p.net_pay || 0), 0);
    const totalDeductions = payslips.reduce((s, p) => s + (p.total_deductions || 0), 0);

    return successResponse(res, {
      data: {
        period: { month, year },
        payslips: payslips.map(p => p.toDict()),
        summary: {
          total_employees: payslips.length,
          total_gross: Math.round(totalGross * 100) / 100,
          total_net: Math.round(totalNet * 100) / 100,
          total_deductions: Math.round(totalDeductions * 100) / 100,
        },
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// TASK REPORT
// ────────────────────────────────────────────────────────────
router.get('/tasks', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.assigned_to = parseInt(req.query.user_id);
    if (req.query.status) where.status = req.query.status;
    if (req.query.from_date) where.created_at = { ...(where.created_at || {}), [Op.gte]: new Date(req.query.from_date) };
    if (req.query.to_date) where.created_at = { ...(where.created_at || {}), [Op.lte]: new Date(req.query.to_date) };

    const tasks = await Task.findAll({
      where,
      include: [
        { model: User, as: 'Assignee', attributes: ['first_name', 'last_name', 'employee_id', 'department'] },
        { model: User, as: 'Assigner', attributes: ['first_name', 'last_name'] },
      ],
      order: [['created_at', 'DESC']],
    });

    return successResponse(res, {
      data: { tasks: tasks.map(t => t.toDict()), total: tasks.length },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// PAYMENT REPORT
// ────────────────────────────────────────────────────────────
router.get('/payments', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.employee_id) where.employee_id = parseInt(req.query.employee_id);
    if (req.query.from_date) where.payment_date = { ...(where.payment_date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.payment_date = { ...(where.payment_date || {}), [Op.lte]: req.query.to_date };

    const txs = await PaymentTransaction.findAll({
      where,
      include: [
        { model: User, as: 'Employee', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: User, as: 'Admin', attributes: ['first_name', 'last_name'] },
      ],
      order: [['payment_date', 'DESC']],
    });

    const completed = txs.filter(t => t.status === 'completed');
    const totalPaid = completed.reduce((s, t) => s + parseFloat(t.amount), 0);

    return successResponse(res, {
      data: {
        transactions: txs.map(tx => {
          const d = tx.toDict();
          d.employee_name = tx.Employee ? `${tx.Employee.first_name} ${tx.Employee.last_name}` : null;
          d.paid_by_name = tx.Admin ? `${tx.Admin.first_name} ${tx.Admin.last_name}` : null;
          return d;
        }),
        total_paid: Math.round(totalPaid * 100) / 100,
        total_transactions: txs.length,
      },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// AUDIT LOGS (admin)
// ────────────────────────────────────────────────────────────
router.get('/audit-logs', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.action) where.action = { [Op.like]: `%${req.query.action}%` };

    const logs = await AuditLog.findAll({
      where,
      include: [
        { model: User, as: 'User', attributes: ['id', 'employee_id', 'first_name', 'last_name'], required: false },
        { model: User, as: 'TargetUser', attributes: ['id', 'employee_id', 'first_name', 'last_name'], required: false },
      ],
      order: [['created_at', 'DESC']],
      limit: 500,
    });
    return successResponse(res, { data: logs.map(l => l.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// SYSTEM LOGS (super_admin only)
// ────────────────────────────────────────────────────────────
router.get('/system-logs', requireRole('super_admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.user_id = parseInt(req.query.user_id);
    if (req.query.action) where.action = { [Op.like]: `%${req.query.action}%` };
    if (req.query.resource) where.resource = req.query.resource;
    if (req.query.from_date) where.created_at = { ...(where.created_at || {}), [Op.gte]: new Date(req.query.from_date) };
    if (req.query.to_date) where.created_at = { ...(where.created_at || {}), [Op.lte]: new Date(req.query.to_date) };

    const logs = await SystemLog.findAll({
      where, order: [['created_at', 'DESC']], limit: 1000,
    });
    return successResponse(res, { data: logs.map(l => l.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// VERIFY LOG INTEGRITY (super_admin)
router.get('/system-logs/verify', requireRole('super_admin'), async (req, res) => {
  try {
    const result = await verifyLogIntegrity();
    return successResponse(res, { data: result });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
