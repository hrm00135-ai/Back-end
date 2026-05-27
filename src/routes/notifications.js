const express = require('express');
const router = express.Router();
const { Notification } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');

// GET MY NOTIFICATIONS
router.get('/', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const where = { user_id: currentUserId };
    if (req.query.is_read !== undefined) where.is_read = req.query.is_read === 'true';

    const notifications = await Notification.findAll({
      where, order: [['created_at', 'DESC']], limit: 50,
    });
    return successResponse(res, { data: notifications.map(n => n.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// MARK AS READ
router.put('/:notificationId/read', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const notif = await Notification.findOne({ where: { id: req.params.notificationId, user_id: currentUserId } });
    if (!notif) return errorResponse(res, 'Notification not found', 404);
    notif.is_read = true;
    await notif.save();
    return successResponse(res, { message: 'Notification marked as read' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// MARK ALL AS READ
router.put('/mark-all-read', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    await Notification.update({ is_read: true }, { where: { user_id: currentUserId, is_read: false } });
    return successResponse(res, { message: 'All notifications marked as read' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// SEND NOTIFICATION (admin)
router.post('/', requireRole('super_admin', 'admin'), async (req, res) => {
  try {
    const data = req.body || {};
    if (!data.user_id) return errorResponse(res, 'user_id is required', 400);
    if (!data.message) return errorResponse(res, 'message is required', 400);

    const notif = await Notification.create({
      user_id: parseInt(data.user_id),
      type: data.type || 'general',
      message: data.message,
    });
    return successResponse(res, { data: notif.toDict(), message: 'Notification sent' }, 201);
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// UNREAD COUNT
router.get('/unread-count', jwtRequired, async (req, res) => {
  try {
    const currentUserId = parseInt(req.currentUserId);
    const count = await Notification.count({ where: { user_id: currentUserId, is_read: false } });
    return successResponse(res, { data: { count } });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
