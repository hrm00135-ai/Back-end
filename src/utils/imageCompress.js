const sharp = require('sharp');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

/**
 * Compress an image buffer/path to target KB and max dimension.
 * Returns { buffer, size, format }
 */
async function compressImage(input, { maxSizeKb = 200, maxDimension = 800, quality = 80 } = {}) {
  let buffer;
  if (Buffer.isBuffer(input)) {
    buffer = input;
  } else if (typeof input === 'string') {
    buffer = fs.readFileSync(input);
  } else if (input && input.data) {
    buffer = input.data;
  } else {
    buffer = await streamToBuffer(input);
  }

  let img = sharp(buffer);
  const meta = await img.metadata();

  // Resize if too large
  if ((meta.width || 0) > maxDimension || (meta.height || 0) > maxDimension) {
    img = img.resize(maxDimension, maxDimension, { fit: 'inside', withoutEnlargement: true });
  }

  // Try JPEG compression, reduce quality until small enough
  let q = quality;
  let out;
  while (q >= 20) {
    out = await img.jpeg({ quality: q }).toBuffer();
    if (out.length <= maxSizeKb * 1024) break;
    q -= 10;
  }

  if (!out) {
    out = await img.jpeg({ quality: 60 }).toBuffer();
  }

  return { buffer: out, size: out.length, format: 'JPEG' };
}

function getCompressedSizeLabel(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function streamToBuffer(stream) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    stream.on('data', chunk => chunks.push(chunk));
    stream.on('end', () => resolve(Buffer.concat(chunks)));
    stream.on('error', reject);
  });
}

module.exports = { compressImage, getCompressedSizeLabel };
