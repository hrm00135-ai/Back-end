const express = require('express');
const router = express.Router();
const { User, EmployeeProfile, BankDetail, EmployeeDocument } = require('../models');
const { jwtRequired, requireRole, successResponse, errorResponse } = require('../utils/helpers');
const { encryptValue, decryptValue } = require('../utils/encryption');
const { uploadFile, deleteFile } = require('../utils/storage');
const { systemLog } = require('../utils/systemLogger');

// Helper: check access
async function checkAccess(req, res, targetId) {
  const currentUserId = parseInt(req.currentUserId);
  const currentUser = await User.findByPk(currentUserId);
  const isAdmin = ['super_admin', 'admin'].includes(currentUser.role);
  if (!isAdmin && currentUserId !== targetId) {
    errorResponse(res, 'Insufficient permissions', 403);
    return null;
  }
  const targetUser = await User.findByPk(targetId);
  if (!targetUser) { errorResponse(res, 'User not found', 404); return null; }
  return { currentUser, currentUserId, isAdmin, targetUser };
}

// ────────────────────────────────────────────────────────────
// GET PROFILE
// ────────────────────────────────────────────────────────────
router.get('/:userId', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    let profile = await EmployeeProfile.findOne({ where: { user_id: targetId } });
    if (!profile) {
      profile = await EmployeeProfile.create({ user_id: targetId });
    }
    return successResponse(res, { data: profile.toDict() });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// CREATE / UPDATE PROFILE
// ────────────────────────────────────────────────────────────
router.put('/:userId', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const data = req.body || {};
    const fields = [
      'date_of_birth', 'gender', 'blood_group', 'marital_status', 'nationality',
      'address_line1', 'address_line2', 'city', 'state', 'pincode',
      'perm_address_line1', 'perm_address_line2', 'perm_city', 'perm_state', 'perm_pincode',
      'emergency_contact_name', 'emergency_contact_relation', 'emergency_contact_phone',
      'father_name', 'spouse_name',
    ];

    let profile = await EmployeeProfile.findOne({ where: { user_id: targetId } });
    const before = profile ? profile.toDict() : null;

    const updates = {};
    for (const f of fields) {
      if (data[f] !== undefined) updates[f] = data[f];
    }

    if (profile) {
      await profile.update(updates);
    } else {
      profile = await EmployeeProfile.create({ user_id: targetId, ...updates });
    }

    await systemLog('PROFILE_UPDATED', {
      userId: ctx.currentUserId, resource: 'employee_profile', resourceId: profile.id,
      before, after: profile.toDict(), req,
    });

    return successResponse(res, { data: profile.toDict(), message: 'Profile updated successfully' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// BANK DETAILS
// ────────────────────────────────────────────────────────────
router.get('/:userId/bank', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const bank = await BankDetail.findOne({ where: { user_id: targetId } });
    if (!bank) return successResponse(res, { data: null });

    // Only super_admin can see full account number and PAN
    const decrypt = ctx.currentUser.role === 'super_admin';
    return successResponse(res, { data: bank.toDict(decrypt) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.put('/:userId/bank', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const data = req.body || {};
    const updates = {};
    const plainFields = ['bank_name', 'branch_name', 'ifsc_code', 'account_holder_name', 'uan_number', 'esi_number'];
    for (const f of plainFields) {
      if (data[f] !== undefined) updates[f] = data[f];
    }
    if (data.account_number) updates.account_number_enc = encryptValue(data.account_number);
    if (data.pan_number) updates.pan_number_enc = encryptValue(data.pan_number);

    let bank = await BankDetail.findOne({ where: { user_id: targetId } });
    if (bank) {
      await bank.update(updates);
    } else {
      bank = await BankDetail.create({ user_id: targetId, ...updates });
    }

    await systemLog('BANK_DETAILS_UPDATED', {
      userId: ctx.currentUserId, resource: 'bank_detail', resourceId: bank.id, req,
    });

    return successResponse(res, { data: bank.toDict(false), message: 'Bank details updated' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

// ────────────────────────────────────────────────────────────
// DOCUMENTS
// ────────────────────────────────────────────────────────────
router.get('/:userId/documents', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const docs = await EmployeeDocument.findAll({
      where: { user_id: targetId }, order: [['created_at', 'DESC']],
    });
    return successResponse(res, { data: docs.map(d => d.toDict()) });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.post('/:userId/documents', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const data = req.body || {};
    if (!data.doc_type) return errorResponse(res, 'doc_type is required', 400);
    if (!data.doc_name) return errorResponse(res, 'doc_name is required', 400);

    if (!req.files || !req.files.document) return errorResponse(res, 'No document file provided', 400);
    const file = req.files.document;

    const allowed = ['image/jpeg', 'image/png', 'application/pdf'];
    if (!allowed.includes(file.mimetype)) return errorResponse(res, 'Only JPEG, PNG, PDF files allowed', 400);
    if (file.size > 10 * 1024 * 1024) return errorResponse(res, 'File size exceeds 10MB', 400);

    const { url } = await uploadFile(file, {
      folder: `jewelcraft/employees/documents/${targetId}`,
      resourceType: 'auto',
    });

    const doc = await EmployeeDocument.create({
      user_id: targetId,
      doc_type: data.doc_type,
      doc_name: data.doc_name,
      file_path: url,
      file_type: file.mimetype,
      file_size: file.size,
      uploaded_by: ctx.currentUserId,
      notes: data.notes || null,
    });

    return successResponse(res, { data: doc.toDict(), message: 'Document uploaded' }, 201);
  } catch (err) {
    console.error(err);
    return errorResponse(res, 'Internal server error', 500);
  }
});

router.delete('/:userId/documents/:docId', jwtRequired, async (req, res) => {
  try {
    const targetId = parseInt(req.params.userId);
    const ctx = await checkAccess(req, res, targetId);
    if (!ctx) return;

    const doc = await EmployeeDocument.findOne({ where: { id: req.params.docId, user_id: targetId } });
    if (!doc) return errorResponse(res, 'Document not found', 404);

    try { await deleteFile(doc.file_path); } catch {}
    await doc.destroy();

    return successResponse(res, { message: 'Document deleted' });
  } catch (err) {
    return errorResponse(res, 'Internal server error', 500);
  }
});

module.exports = router;
