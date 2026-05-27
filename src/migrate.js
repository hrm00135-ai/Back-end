require('dotenv').config();
const sequelize = require('./config/database');
const { hashPassword, generateEmployeeId } = require('./utils/helpers');

async function migrate() {
  try {
    console.log('[MIGRATE] Connecting to database...');
    await sequelize.authenticate();
    console.log('[MIGRATE] Connection OK.');

    // Check if users table already exists
    let tablesExist = false;
    try {
      const qi = sequelize.getQueryInterface();
      const tables = await qi.showAllTables();
      tablesExist = tables.includes('users');
    } catch (e) {
      tablesExist = false;
    }

    if (!tablesExist) {
      console.log('[MIGRATE] First run - creating all tables...');
      await sequelize.sync({ force: true });
      console.log('[MIGRATE] All tables created.');
    } else {
      console.log('[MIGRATE] Tables exist - syncing schema...');
      try {
        await sequelize.sync({ alter: false });
      } catch (e) {
        console.log('[MIGRATE] Sync note:', e.message);
      }
      console.log('[MIGRATE] Schema sync complete.');
    }

    // Seed super_admin if none exists
    const { User } = require('./models');
    const existingSA = await User.findOne({ where: { role: 'super_admin' } });

    if (!existingSA) {
      const superAdminEmail = process.env.SUPER_ADMIN_EMAIL || 'superadmin@jewelcraft.com';
      const superAdminPassword = process.env.SUPER_ADMIN_PASSWORD || 'Admin@123456';

      const employeeId = await generateEmployeeId('super_admin');
      const sa = await User.create({
        employee_id: employeeId,
        email: superAdminEmail,
        password_hash: await hashPassword(superAdminPassword),
        role: 'super_admin',
        first_name: 'Super',
        last_name: 'Admin',
        phone: '0000000000',
        date_of_joining: new Date().toISOString().split('T')[0],
        is_active: true,
      });

      console.log('[MIGRATE] Super Admin created:');
      console.log('          Email:    ' + superAdminEmail);
      console.log('          Password: ' + superAdminPassword);
      console.log('          EmpID:    ' + sa.employee_id);
      console.log('[MIGRATE] Change this password after first login!');
    } else {
      console.log('[MIGRATE] Super Admin already exists: ' + existingSA.email);
    }

    console.log('[MIGRATE] Done.');
    process.exit(0);
  } catch (err) {
    console.error('[MIGRATE ERROR]', err.message);
    console.error(err);
    process.exit(1);
  }
}

migrate();
