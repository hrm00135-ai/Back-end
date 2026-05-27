const crypto = require('crypto');
const config = require('../config/config');

// Fernet-compatible encryption using AES-128-CBC + HMAC-SHA256
// The Python Fernet key is a base64url-encoded 32-byte key
// First 16 bytes = signing key (HMAC), last 16 bytes = encryption key (AES-128-CBC)

function getKeys() {
  const key = config.ENCRYPTION_KEY;
  if (!key) throw new Error('ENCRYPTION_KEY not set in .env');
  const keyBytes = Buffer.from(key, 'base64');
  if (keyBytes.length !== 32) throw new Error('ENCRYPTION_KEY must be a 32-byte base64 key (Fernet format)');
  const signingKey = keyBytes.slice(0, 16);
  const encryptionKey = keyBytes.slice(16, 32);
  return { signingKey, encryptionKey };
}

function encryptValue(value) {
  if (!value) return null;
  try {
    const { signingKey, encryptionKey } = getKeys();
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv('aes-128-cbc', encryptionKey, iv);
    const plaintext = Buffer.from(value, 'utf8');
    const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);

    // Fernet token structure: version(1) + timestamp(8) + iv(16) + ciphertext + hmac(32)
    const version = Buffer.from([0x80]);
    const timestamp = Buffer.alloc(8);
    const now = Math.floor(Date.now() / 1000);
    timestamp.writeUInt32BE(Math.floor(now / 0x100000000), 0);
    timestamp.writeUInt32BE(now >>> 0, 4);

    const payload = Buffer.concat([version, timestamp, iv, ciphertext]);
    const hmac = crypto.createHmac('sha256', signingKey).update(payload).digest();
    const token = Buffer.concat([payload, hmac]);
    return token.toString('base64url');
  } catch {
    // Fallback: simple AES encryption if key format differs
    const key32 = crypto.createHash('sha256').update(config.ENCRYPTION_KEY).digest();
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv('aes-256-cbc', key32, iv);
    const encrypted = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]);
    return iv.toString('hex') + ':' + encrypted.toString('hex');
  }
}

function decryptValue(encryptedValue) {
  if (!encryptedValue) return null;
  try {
    // Try Fernet format first
    const { signingKey, encryptionKey } = getKeys();
    const token = Buffer.from(encryptedValue, 'base64url');
    if (token[0] === 0x80 && token.length > 57) {
      const payload = token.slice(0, token.length - 32);
      const hmac = token.slice(token.length - 32);
      const expectedHmac = crypto.createHmac('sha256', signingKey).update(payload).digest();
      if (!crypto.timingSafeEqual(hmac, expectedHmac)) throw new Error('Invalid HMAC');
      const iv = token.slice(9, 25);
      const ciphertext = token.slice(25, token.length - 32);
      const decipher = crypto.createDecipheriv('aes-128-cbc', encryptionKey, iv);
      const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
      return plaintext.toString('utf8');
    }
    throw new Error('Not Fernet format');
  } catch {
    // Fallback: simple AES decryption
    if (encryptedValue.includes(':')) {
      const [ivHex, encHex] = encryptedValue.split(':');
      const key32 = crypto.createHash('sha256').update(config.ENCRYPTION_KEY).digest();
      const iv = Buffer.from(ivHex, 'hex');
      const encrypted = Buffer.from(encHex, 'hex');
      const decipher = crypto.createDecipheriv('aes-256-cbc', key32, iv);
      const decrypted = Buffer.concat([decipher.update(encrypted), decipher.final()]);
      return decrypted.toString('utf8');
    }
    return null;
  }
}

module.exports = { encryptValue, decryptValue };
