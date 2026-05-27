const express = require('express');
const router = express.Router();
const { Op } = require('sequelize');
const { User, Task, TaskComment, TaskAttachment } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');
const { uploadFile, deleteFile } = require('../utils/storage');
const { systemLog } = require('../utils/systemLogger');

// ────────────────────────────────────────────────────────────
// CREATE TASK (admin)
// ────────────────────────────────────────────────────────────
router.post('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const currentUser = req.currentUser;
    const data = req.body || {};
    if (!data.title) return errorResponse(res, 'title is required', 400);
    if (!data.assigned_to) return errorResponse(res, 'assigned_to is required', 400);

    const assignee = await User.findByPk(data.assigned_to);
    if (!assignee || !assignee.is_active) return errorResponse(res, 'Assigned employee not found', 404);

    const task = await Task.create({
      title: data.title,
      description: data.description || null,
      assigned_to: parseInt(data.assigned_to),
      assigned_by: currentUser.id,
      status: 'pending',
      priority: data.priority || 'medium',
      due_date: data.due_date || null,
      category: data.category || null,
      estimated_hours: data.estimated_hours || null,
      quantity: data.quantity || 1,
      weight_grams: data.weight_grams || null,
      payment_amount: data.payment_amount || 0,
      admin_notes: data.admin_notes || null,
    });

    await systemLog('TASK_CREATED', {
      userId: currentUser.id, resource: 'task', resourceId: task.id,
      after: { title: task.title, assigned_to: task.assigned_to }, req,
    });

    const full = await Task.findByPk(task.id, {
      include: [
        { model: User, as: 'Assignee', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: User, as: 'Assigner', attributes: ['first_name', 'last_name'] },
        { model: TaskAttachment, as: 'TaskAttachments', include: [{ model: User, as: 'User' }] },
      ],
    });
    return successResponse(res, { data: full.toDict(), message: 'Task created' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET ALL TASKS
// ────────────────────────────────────────────────────────────
router.get('/', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);

    const where = {};
    if (currentUser.role === 'employee') {
      where.assigned_to = currentUserId;
    } else {
      if (req.query.assigned_to) where.assigned_to = parseInt(req.query.assigned_to);
      if (req.query.assigned_by) where.assigned_by = parseInt(req.query.assigned_by);
    }
    if (req.query.status) where.status = req.query.status;
    if (req.query.priority) where.priority = req.query.priority;
    if (req.query.category) where.category = { [Op.like]: `%${req.query.category}%` };

    const tasks = await Task.findAll({
      where,
      include: [
        { model: User, as: 'Assignee', attributes: ['first_name', 'last_name', 'employee_id', 'photo_url'] },
        { model: User, as: 'Assigner', attributes: ['first_name', 'last_name'] },
        { model: TaskAttachment, as: 'TaskAttachments', include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role'] }] },
      ],
      order: [['created_at', 'DESC']],
    });
    return successResponse(res, { data: tasks.map(t => t.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// GET SINGLE TASK
// ────────────────────────────────────────────────────────────
router.get('/:taskId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);

    const task = await Task.findByPk(req.params.taskId, {
      include: [
        { model: User, as: 'Assignee', attributes: ['first_name', 'last_name', 'employee_id', 'photo_url'] },
        { model: User, as: 'Assigner', attributes: ['first_name', 'last_name'] },
        { model: TaskAttachment, as: 'TaskAttachments', include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role'] }] },
        { model: TaskComment, as: 'TaskComments', include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role', 'photo_url'] }] },
      ],
    });
    if (!task) return errorResponse(res, 'Task not found', 404);

    if (currentUser.role === 'employee' && task.assigned_to !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);

    return successResponse(res, { data: task.toDict(true) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// UPDATE TASK
// ────────────────────────────────────────────────────────────
router.put('/:taskId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const task = await Task.findByPk(req.params.taskId);
    if (!task) return errorResponse(res, 'Task not found', 404);

    const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
    if (!isAdmin && task.assigned_to !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);

    const data = req.body || {};
    const before = task.toDict();

    if (isAdmin) {
      const adminFields = ['title', 'description', 'assigned_to', 'priority', 'due_date',
        'category', 'estimated_hours', 'quantity', 'weight_grams', 'payment_amount', 'admin_notes', 'status'];
      for (const f of adminFields) if (data[f] !== undefined) task[f] = data[f];
    }

    // Employee can update status, notes
    const employeeFields = ['employee_notes', 'completion_notes'];
    for (const f of employeeFields) if (data[f] !== undefined) task[f] = data[f];

    // Status transitions
    if (data.status) {
      if (data.status === 'in_progress' && !task.started_at) task.started_at = new Date();
      if (data.status === 'completed' && !task.completed_at) {
        task.completed_at = new Date();
        if (task.started_at) {
          task.actual_hours = Math.round(
            ((new Date() - new Date(task.started_at)) / 3600000) * 100
          ) / 100;
        }
      }
      task.status = data.status;
    }

    await task.save();

    await systemLog('TASK_UPDATED', {
      userId: currentUserId, resource: 'task', resourceId: task.id,
      before, after: task.toDict(), req,
    });

    const full = await Task.findByPk(task.id, {
      include: [
        { model: User, as: 'Assignee', attributes: ['first_name', 'last_name', 'employee_id'] },
        { model: User, as: 'Assigner', attributes: ['first_name', 'last_name'] },
        { model: TaskAttachment, as: 'TaskAttachments', include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role'] }] },
      ],
    });
    return successResponse(res, { data: full.toDict(), message: 'Task updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// DELETE TASK (admin)
// ────────────────────────────────────────────────────────────
router.delete('/:taskId', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const task = await Task.findByPk(req.params.taskId, {
      include: [{ model: TaskAttachment, as: 'TaskAttachments' }],
    });
    if (!task) return errorResponse(res, 'Task not found', 404);

    for (const att of task.TaskAttachments || []) {
      try { await deleteFile(att.file_url); } catch {}
    }
    await task.destroy();
    return successResponse(res, { message: 'Task deleted' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// ADD COMMENT
// ────────────────────────────────────────────────────────────
router.post('/:taskId/comments', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const task = await Task.findByPk(req.params.taskId);
    if (!task) return errorResponse(res, 'Task not found', 404);

    if (currentUser.role === 'employee' && task.assigned_to !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);

    const data = req.body || {};
    if (!data.comment) return errorResponse(res, 'comment is required', 400);

    const comment = await TaskComment.create({
      task_id: task.id, user_id: currentUserId, comment: data.comment,
    });

    const full = await TaskComment.findByPk(comment.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role', 'photo_url'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Comment added' }, 201);
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// UPLOAD ATTACHMENT
// ────────────────────────────────────────────────────────────
router.post('/:taskId/attachments', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const task = await Task.findByPk(req.params.taskId);
    if (!task) return errorResponse(res, 'Task not found', 404);

    if (currentUser.role === 'employee' && task.assigned_to !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);

    if (!req.files || !req.files.file) return errorResponse(res, 'No file provided', 400);
    const file = req.files.file;

    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'video/mp4', 'video/quicktime'];
    if (!allowed.includes(file.mimetype)) return errorResponse(res, 'File type not allowed', 400);
    if (file.size > 50 * 1024 * 1024) return errorResponse(res, 'File size exceeds 50MB', 400);

    const fileType = file.mimetype.startsWith('image/') ? 'image' :
      file.mimetype.startsWith('video/') ? 'video' : 'document';

    const { url } = await uploadFile(file, {
      folder: `jewelcraft/tasks/${task.id}`, resourceType: 'auto',
    });

    const attachment = await TaskAttachment.create({
      task_id: task.id, user_id: currentUserId,
      file_url: url, file_type: fileType, original_name: file.name,
    });

    const full = await TaskAttachment.findByPk(attachment.id, {
      include: [{ model: User, as: 'User', attributes: ['first_name', 'last_name', 'role'] }],
    });
    return successResponse(res, { data: full.toDict(), message: 'Attachment uploaded' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.delete('/:taskId/attachments/:attachmentId', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const currentUser = await User.findByPk(currentUserId);
    const attachment = await TaskAttachment.findOne({
      where: { id: req.params.attachmentId, task_id: req.params.taskId },
    });
    if (!attachment) return errorResponse(res, 'Attachment not found', 404);

    const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
    if (!isAdmin && attachment.user_id !== currentUserId)
      return errorResponse(res, 'Insufficient permissions', 403);

    try { await deleteFile(attachment.file_url); } catch {}
    await attachment.destroy();

    return successResponse(res, { message: 'Attachment deleted' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// TASK STATS
// ────────────────────────────────────────────────────────────
router.get('/stats/overview', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const where = {};
    if (req.query.user_id) where.assigned_to = parseInt(req.query.user_id);

    const [pending, inProgress, completed, cancelled, onHold] = await Promise.all([
      Task.count({ where: { ...where, status: 'pending' } }),
      Task.count({ where: { ...where, status: 'in_progress' } }),
      Task.count({ where: { ...where, status: 'completed' } }),
      Task.count({ where: { ...where, status: 'cancelled' } }),
      Task.count({ where: { ...where, status: 'on_hold' } }),
    ]);

    const total = pending + inProgress + completed + cancelled + onHold;
    return successResponse(res, {
      data: { total, pending, in_progress: inProgress, completed, cancelled, on_hold: onHold },
    });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
