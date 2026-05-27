require('dotenv').config();
const app = require('./app');
const sequelize = require('./config/database');
const config = require('./config/config');

const PORT = config.PORT || 5000;
const HOST = process.env.HOST || '0.0.0.0';

async function start() {
  try {
    // Test DB connection
    await sequelize.authenticate();
    console.log('[DB] Connection established successfully.');

    // Sync all models (creates tables if they don't exist, does NOT drop existing data)
    await sequelize.sync({ alter: false });
    console.log('[DB] All models synced.');

    app.listen(PORT, HOST, () => {
      console.log(`[SERVER] JewelCraft HRM API running on http://${HOST}:${PORT}`);
      console.log(`[ENV]    NODE_ENV = ${process.env.NODE_ENV || 'development'}`);
    });
  } catch (err) {
    console.error('[STARTUP ERROR]', err);
    process.exit(1);
  }
}

start();
