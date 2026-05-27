const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, PaymentTransaction, EmployeePaymentConfig, Task } = require('../models');
const { requireRole, jwtRequired, successResponse, errorResponse } = require('../utils/helpers');
const { calculateEarnings, getBalanceSummary } = require('../services/earningsCalculator');
const { systemLog } = require('../utils/systemLogger');
const { uploadFile } = require('../utils/storage');

// ────────────────────────────────────────────────────────────
// PAYMENT CONFIG
// ────────────────────────────────────────────────────────────
router.get('/config/:userId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const config = await EmployeePaymentConfig.findOne({
      where: { user_id: parseInt(req.params.userId), is_active: true },
      order: [['effective_from', 'DESC']],
    });
    return successResponse(res, { data: config ? config.toDict() : null });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/config', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.wage_type) return errorResponse(res, 'wage_type is required', 400);
    if (data.wage_amount === undefined) return errorResponse(res, 'wage_amount is required', 400);
    if (!data.effective_from) return errorResponse(res, 'effective_from is required', 400);

    const validTypes = ['monthly_salary', 'daily_wage', 'per_task'];
    if (!validTypes.includes(data.wage_type)) return errorResponse(res, `wage_type must be one of: ${validTypes.join(', ')}`, 400);

    await EmployeePaymentConfig.update(
      { is_active: false },
      { where: { user_id: parseInt(data.user_id), is_active: true } }
    );

    const cfg = await EmployeePaymentConfig.create({
      user_id: parseInt(data.user_id),
      wage_type: data.wage_type,
      wage_amount: parseFloat(data.wage_amount),
      effective_from: data.effective_from,
      is_active: true,
      notes: data.notes || null,
    });

    await systemLog('PAYMENT_CONFIG_CREATED', {
      userId: req.currentUserId, resource: 'employee_payment_config', resourceId: cfg.id,
      after: cfg.toDict(), req,
    });

    return successResponse(res, { data: cfg.toDict(), message: 'Payment config set' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// EARNINGS SUMMARY
// ────────────────────────────────────────────────────────────
router.get('/earnings/:userId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const userId = parseInt(req.params.userId);
    const fromDate = req.query.from_date ? new Date(req.query.from_date) : null;
    const toDate = req.query.to_date ? new Date(req.query.to_date) : null;

    const summary = await getBalanceSummary(userId, fromDate, toDate);
    return successResponse(res, { data: summary });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.get('/earnings/me', jwtRequired, async (req, res) => {
  try {
    const userId = parseInt(req.currentUserId);
    const fromDate = req.query.from_date ? new Date(req.query.from_date) : null;
    const toDate = req.query.to_date ? new Date(req.query.to_date) : null;

    const summary = await getBalanceSummary(userId, fromDate, toDate);
    return successResponse(res, { data: summary });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// RECORD PAYMENT
// ────────────────────────────────────────────────────────────
router.post('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};

    if (!data.employee_id) return errorResponse(res, 'employee_id is required', 400);
    if (!data.amount) return errorResponse(res, 'amount is required', 400);
    if (!data.payment_date) return errorResponse(res, 'payment_date is required', 400);
    if (!data.payment_method) return errorResponse(res, 'payment_method is required', 400);

    const employee = await User.findByPk(parseInt(data.employee_id));
    if (!employee) return errorResponse(res, 'Employee not found', 404);

    let invoiceUrl = null;
    if (req.files && req.files.invoice) {
      const file = req.files.invoice;
      const { url } = await uploadFile(file, {
        folder: 'jewelcraft/invoices', resourceType: 'auto',
      });
      invoiceUrl = url;
    }

    const tx = await PaymentTransaction.create({
      employee_id: parseInt(data.employee_id),
      paid_by: currentUser.id,
      amount: parseFloat(data.amount),
      payment_date: data.payment_date,
      payment_method: data.payment_method,
      reference_note: data.reference_note || null,
      task_id: data.task_id ? parseInt(data.task_id) : null,
      is_advance: data.is_advance || false,
      invoice_url: invoiceUrl,
      status: 'completed',
    });

    await systemLog('PAYMENT_RECORDED', {
      userId: currentUser.id, resource: 'payment_transaction', resourceId: tx.id,
      after: { employee_id: data.employee_id, amount: data.amount, method: data.payment_method }, req,
    });

    const full = await PaymentTransaction.findByPk(tx.id, {
      include: [
        { model: User, as: 'Employee', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: User, as: 'Admin', attributes: ['first_name', 'last_name'] },
        { model: Task, as: 'Task', attributes: ['title'] },
      ],
    });

    const result = full.toDict();
    result.employee_name = full.Employee ? `${full.Employee.first_name} ${full.Employee.last_name}` : null;
    result.paid_by_name = full.Admin ? `${full.Admin.first_name} ${full.Admin.last_name}` : null;

    return successResponse(res, { data: result, message: 'Payment recorded' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET PAYMENTS
// ────────────────────────────────────────────────────────────
router.get('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.employee_id) where.employee_id = parseInt(req.query.employee_id);
    if (req.query.status) where.status = req.query.status;
    if (req.query.from_date) where.payment_date = { ...(where.payment_date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.payment_date = { ...(where.payment_date || {}), [Op.lte]: req.query.to_date };
    if (req.query.is_advance !== undefined) where.is_advance = req.query.is_advance === 'true';

    const txs = await PaymentTransaction.findAll({
      where,
      include: [
        { model: User, as: 'Employee', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: User, as: 'Admin', attributes: ['first_name', 'last_name'] },
        { model: Task, as: 'Task', attributes: ['title'] },
      ],
      order: [['created_at', 'DESC']],
    });

    const results = txs.map(tx => {
      const d = tx.toDict();
      d.employee_name = tx.Employee ? `${tx.Employee.first_name} ${tx.Employee.last_name}` : null;
      d.paid_by_name = tx.Admin ? `${tx.Admin.first_name} ${tx.Admin.last_name}` : null;
      return d;
    });
    return successResponse(res, { data: results });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// MY PAYMENTS
router.get('/me', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const where = { employee_id: currentUserId };
    if (req.query.from_date) where.payment_date = { ...(where.payment_date || {}), [Op.gte]: req.query.from_date };
    if (req.query.to_date) where.payment_date = { ...(where.payment_date || {}), [Op.lte]: req.query.to_date };

    const txs = await PaymentTransaction.findAll({
      where,
      include: [{ model: Task, as: 'Task', attributes: ['title'] }],
      order: [['created_at', 'DESC']],
    });

    const results = txs.map(tx => {
      const d = tx.toDict();
      d.task_title = tx.Task ? tx.Task.title : null;
      return d;
    });
    return successResponse(res, { data: results });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// REVERSE PAYMENT
router.post('/:txId/reverse', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const tx = await PaymentTransaction.findByPk(req.params.txId);
    if (!tx) return errorResponse(res, 'Payment not found', 404);
    if (tx.status !== 'completed') return errorResponse(res, 'Only completed payments can be reversed', 400);

    const data = req.body || {};
    if (!data.reason) return errorResponse(res, 'reason is required for reversal', 400);

    const reversalTx = await PaymentTransaction.create({
      employee_id: tx.employee_id,
      paid_by: currentUser.id,
      amount: -Math.abs(parseFloat(tx.amount)),
      payment_date: new Date().toISOString().split('T')[0],
      payment_method: tx.payment_method,
      reference_note: `Reversal of transaction #${tx.id}: ${data.reason}`,
      status: 'reversed',
      reversal_of: tx.id,
      reversal_reason: data.reason,
    });

    await systemLog('PAYMENT_REVERSED', {
      userId: currentUser.id, resource: 'payment_transaction', resourceId: reversalTx.id,
      details: { original_tx: tx.id, reason: data.reason, amount: tx.amount }, req,
    });

    return successResponse(res, { data: reversalTx.toDict(), message: 'Payment reversed' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
