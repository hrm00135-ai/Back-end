const cloudinary = require('cloudinary').v2;
const config = require('../config/config');
const path = require('path');
const fs = require('fs');

let configured = false;

function ensureConfigured() {
  if (configured) return;
  if (!config.CLOUDINARY_CLOUD_NAME || !config.CLOUDINARY_API_KEY || !config.CLOUDINARY_API_SECRET) {
    throw new Error('Cloudinary not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET env vars.');
  }
  cloudinary.config({
    cloud_name: config.CLOUDINARY_CLOUD_NAME,
    api_key: config.CLOUDINARY_API_KEY,
    api_secret: config.CLOUDINARY_API_SECRET,
    secure: true,
  });
  configured = true;
}

async function uploadFile(fileOrPath, { folder, publicId = null, resourceType = 'auto' } = {}) {
  ensureConfigured();

  const options = { folder, resource_type: resourceType, overwrite: true };
  if (publicId) options.public_id = publicId;

  let uploadTarget;

  // If it's a multer/express-fileupload file object
  if (fileOrPath && fileOrPath.tempFilePath) {
    uploadTarget = fileOrPath.tempFilePath;
  } else if (fileOrPath && fileOrPath.data) {
    // express-fileupload in-memory buffer
    uploadTarget = `data:${fileOrPath.mimetype};base64,${fileOrPath.data.toString('base64')}`;
  } else if (typeof fileOrPath === 'string') {
    uploadTarget = fileOrPath;
  } else if (Buffer.isBuffer(fileOrPath)) {
    uploadTarget = `data:application/octet-stream;base64,${fileOrPath.toString('base64')}`;
  } else {
    uploadTarget = fileOrPath;
  }

  const result = await cloudinary.uploader.upload(uploadTarget, options);
  return { url: result.secure_url, public_id: result.public_id };
}

async function deleteFile(urlOrPublicId) {
  if (!urlOrPublicId) return false;
  try {
    ensureConfigured();
    const publicId = extractPublicId(urlOrPublicId);
    if (!publicId) return false;
    for (const rtype of ['image', 'video', 'raw']) {
      try {
        const result = await cloudinary.uploader.destroy(publicId, { resource_type: rtype });
        if (result.result === 'ok') return true;
      } catch {}
    }
    return false;
  } catch (e) {
    console.warn(`Cloudinary delete failed for ${urlOrPublicId}: ${e.message}`);
    return false;
  }
}

function extractPublicId(urlOrPublicId) {
  if (!urlOrPublicId) return null;
  if (!urlOrPublicId.startsWith('http')) return urlOrPublicId;
  const match = urlOrPublicId.match(/\/upload\/(?:v\d+\/)?(.+?)(?:\.[a-z0-9]+)?$/);
  return match ? match[1] : null;
}

module.exports = { uploadFile, deleteFile };
