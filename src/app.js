require('dotenv').config();
const express = require('express');
const cors = require('cors');
const fileUpload = require('express-fileupload');
const path = require('path');
const fs = require('fs');
const config = require('./config/config');

const app = express();

// ─── CORS ─────────────────────────────────────────────────
app.use(cors({
  origin: [
    'http://localhost:5173',
    'http://localhost:3000',
    'http://127.0.0.1:5173',
    'http://127.0.0.1:3000',
  ],
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
  credentials: true,
}));

// ─── Body parsers ─────────────────────────────────────────
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// ─── File uploads ─────────────────────────────────────────
app.use(fileUpload({
  limits: { fileSize: config.MAX_CONTENT_LENGTH },
  useTempFiles: false,
  abortOnLimit: true,
}));

// ─── Static uploads ───────────────────────────────────────
const uploadDir = path.join(__dirname, '..', config.UPLOAD_FOLDER);
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
app.use('/uploads', express.static(uploadDir));

// ─── Health check ─────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: '1.0.0',
    environment: process.env.NODE_ENV || 'development',
  });
});

app.get('/', (req, res) => {
  res.json({ message: 'JewelCraft HRM API', status: 'running', version: '1.0.0' });
});

// ─── Routes ───────────────────────────────────────────────
app.use('/api/auth',          require('./routes/auth'));
app.use('/api/users',         require('./routes/users'));
app.use('/api/profiles',      require('./routes/profiles'));
app.use('/api/attendance',    require('./routes/attendance'));
app.use('/api/leaves',        require('./routes/leaves'));
app.use('/api/tasks',         require('./routes/tasks'));
app.use('/api/payroll',       require('./routes/payroll'));
app.use('/api/metals',        require('./routes/metals'));
app.use('/api/notifications', require('./routes/notifications'));
app.use('/api/payments',      require('./routes/payments'));
app.use('/api/reports',       require('./routes/reports'));

// ─── 404 ──────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json({ status: 'error', message: `Cannot ${req.method} ${req.path}` });
});

// ─── Global error handler ─────────────────────────────────
app.use((err, req, res, next) => {
  console.error('[UNHANDLED ERROR]', err);
  res.status(500).json({ status: 'error', message: 'Internal server error', detail: err.message });
});

module.exports = app;
