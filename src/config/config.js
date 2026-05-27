require('dotenv').config();

const config = {
  // App
  SECRET_KEY: process.env.SECRET_KEY || 'dev-fallback-key',
  PORT: parseInt(process.env.PORT || '5000'),

  // Database
  get DATABASE_URL() {
    const raw =
      process.env.MYSQL_URL ||
      process.env.SQLALCHEMY_DATABASE_URI ||
      process.env.DATABASE_URL ||
      null;
    if (raw) {
      return raw.replace(/^mysql:\/\//, 'mysql+pymysql://');
    }
    return null; // will use SQLite fallback
  },

  // JWT
  JWT_SECRET_KEY: process.env.JWT_SECRET_KEY || 'jwt-dev-fallback',
  JWT_ACCESS_TOKEN_EXPIRES_MINUTES: parseInt(process.env.JWT_ACCESS_TOKEN_EXPIRES_MINUTES || '15'),
  JWT_REFRESH_TOKEN_EXPIRES_DAYS: parseInt(process.env.JWT_REFRESH_TOKEN_EXPIRES_DAYS || '7'),

  // Mail
  MAIL_SERVER: process.env.MAIL_SERVER || 'smtp.gmail.com',
  MAIL_PORT: parseInt(process.env.MAIL_PORT || '587'),
  MAIL_USE_TLS: (process.env.MAIL_USE_TLS || 'True').toLowerCase() === 'true',
  MAIL_USERNAME: process.env.MAIL_USERNAME || '',
  MAIL_PASSWORD: process.env.MAIL_PASSWORD || '',
  MAIL_DEFAULT_SENDER: process.env.MAIL_DEFAULT_SENDER || '',

  // Encryption
  ENCRYPTION_KEY: process.env.ENCRYPTION_KEY || '',

  // Uploads
  UPLOAD_FOLDER: process.env.UPLOAD_FOLDER || 'uploads',
  MAX_CONTENT_LENGTH: parseInt(process.env.MAX_CONTENT_LENGTH || '52428800'), // 50MB

  // Auth settings
  MAX_FAILED_LOGIN_ATTEMPTS: 5,
  ACCOUNT_LOCK_DURATION_MINUTES: 30,
  OTP_EXPIRY_MINUTES: 10,

  // Metal API
  METAL_API_KEY: process.env.METAL_API_KEY || '',
  METAL_API_URL: 'https://www.goldapi.io/api',

  // Cloudinary
  CLOUDINARY_CLOUD_NAME: process.env.CLOUDINARY_CLOUD_NAME || '',
  CLOUDINARY_API_KEY: process.env.CLOUDINARY_API_KEY || '',
  CLOUDINARY_API_SECRET: process.env.CLOUDINARY_API_SECRET || '',
};

module.exports = config;
