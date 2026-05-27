const { Op } = require('sequelize');
const { EmployeePaymentConfig, PaymentTransaction, Attendance, Task } = require('../models');

async function getConfig(userId) {
  return EmployeePaymentConfig.findOne({
    where: { user_id: userId, is_active: true },
    order: [['effective_from', 'DESC']],
  });
}

async function totalPaid(employeeId) {
  const result = await PaymentTransaction.sum('amount', {
    where: { employee_id: employeeId, status: 'completed' },
  });
  return parseFloat(result || 0);
}

// ─── Monthly Salary ────────────────────────────────────────
function countMonths(start, end) {
  if (end < start) return 0;
  return (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth()) + 1;
}

async function monthlySalaryEarnings(employeeId, monthlyWage, fromDate, toDate) {
  const config = await getConfig(employeeId);
  const start = fromDate || (config ? new Date(config.effective_from) : new Date());
  const end = toDate || new Date();
  const months = countMonths(start, end);
  const totalEarned = monthlyWage * months;
  return {
    totalEarned,
    summary: {
      months_worked: months,
      monthly_rate: monthlyWage,
      period_start: start.toISOString().split('T')[0],
      period_end: end.toISOString().split('T')[0],
    },
  };
}

// ─── Daily Wage ────────────────────────────────────────────
async function dailyWageEarnings(employeeId, dailyRate, fromDate, toDate) {
  const where = {
    user_id: employeeId,
    status: { [Op.in]: ['present', 'Present', 'PRESENT', 'P'] },
  };
  if (fromDate) where.date = { ...(where.date || {}), [Op.gte]: fromDate };
  if (toDate) where.date = { ...(where.date || {}), [Op.lte]: toDate };

  const daysPresent = await Attendance.count({ where });
  const totalEarned = dailyRate * daysPresent;
  return { totalEarned, summary: { days_present: daysPresent, daily_rate: dailyRate } };
}

// ─── Per Task ──────────────────────────────────────────────
async function perTaskEarnings(employeeId, perTaskRate, fromDate, toDate) {
  const where = {
    assigned_to: employeeId,
    status: { [Op.in]: ['completed', 'Completed', 'COMPLETED', 'done'] },
  };
  if (fromDate || toDate) {
    const dateFilter = {};
    if (fromDate) dateFilter[Op.gte] = fromDate;
    if (toDate) dateFilter[Op.lte] = toDate;
    where.completed_at = dateFilter;
  }
  const tasksCompleted = await Task.count({ where });
  const totalEarned = perTaskRate * tasksCompleted;
  return { totalEarned, summary: { tasks_completed: tasksCompleted, per_task_rate: perTaskRate } };
}

// ─── Main ──────────────────────────────────────────────────
async function calculateEarnings(employeeId, fromDate = null, toDate = null) {
  const config = await getConfig(employeeId);
  if (!config) {
    return {
      wage_type: null, wage_amount: 0.0, total_earned: 0.0,
      work_summary: { error: 'No payment config found for this employee' },
      from_date: fromDate ? fromDate.toISOString().split('T')[0] : null,
      to_date: toDate ? toDate.toISOString().split('T')[0] : null,
    };
  }

  const wage = parseFloat(config.wage_amount);
  let totalEarned, summary;

  if (config.wage_type === 'monthly_salary') {
    ({ totalEarned, summary } = await monthlySalaryEarnings(employeeId, wage, fromDate, toDate));
  } else if (config.wage_type === 'daily_wage') {
    ({ totalEarned, summary } = await dailyWageEarnings(employeeId, wage, fromDate, toDate));
  } else if (config.wage_type === 'per_task') {
    ({ totalEarned, summary } = await perTaskEarnings(employeeId, wage, fromDate, toDate));
  } else {
    totalEarned = 0;
    summary = { error: 'Unknown wage type' };
  }

  return {
    wage_type: config.wage_type,
    wage_amount: wage,
    total_earned: totalEarned,
    work_summary: summary,
    from_date: fromDate ? fromDate.toISOString().split('T')[0] : null,
    to_date: toDate ? toDate.toISOString().split('T')[0] : null,
  };
}

async function getBalanceSummary(employeeId, fromDate = null, toDate = null) {
  const earnings = await calculateEarnings(employeeId, fromDate, toDate);
  const paid = await totalPaid(employeeId);
  const remaining = earnings.total_earned - paid;
  return {
    employee_id: employeeId,
    total_earned: earnings.total_earned,
    total_paid: paid,
    remaining,
    wage_type: earnings.wage_type,
    wage_amount: earnings.wage_amount,
    work_summary: earnings.work_summary,
    from_date: earnings.from_date,
    to_date: earnings.to_date,
  };
}

// Sum of all COMPLETED payments for a specific task
async function taskPaidTotal(taskId, excludeTxId = null) {
  const where = { task_id: taskId, status: 'completed' };
  if (excludeTxId) where.id = { [Op.ne]: excludeTxId };
  const result = await PaymentTransaction.sum('amount', { where });
  return parseFloat(result || 0);
}

module.exports = { calculateEarnings, getBalanceSummary, taskPaidTotal };
