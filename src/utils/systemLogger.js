const { SystemLog, User } = require('../models');

async function systemLog(action, { userId = null, resource = null, resourceId = null,
  before = null, after = null, details = null, req = null } = {}) {
  try {
    let userEmail = null, userRole = null, employeeIdStr = null;

    if (userId) {
      const user = await User.findByPk(parseInt(userId));
      if (user) {
        userEmail = user.email;
        userRole = user.role;
        employeeIdStr = user.employee_id;
      }
    }

    let ip = null, userAgent = null, endpoint = null, method = null;
    if (req) {
      ip = (req.headers['x-forwarded-for'] || req.socket?.remoteAddress || '').split(',')[0].trim();
      userAgent = (req.headers['user-agent'] || '').substring(0, 500);
      endpoint = req.path;
      method = req.method;
    }

    const lastLog = await SystemLog.findOne({ order: [['id', 'DESC']] });
    const previousHash = lastLog ? lastLog.entry_hash : 'GENESIS';

    const log = SystemLog.build({
      user_id: userId ? parseInt(userId) : null,
      user_email: userEmail,
      user_role: userRole,
      employee_id: employeeIdStr,
      action,
      resource,
      resource_id: resourceId,
      before_value: typeof before === 'object' && before ? JSON.stringify(before) : before,
      after_value: typeof after === 'object' && after ? JSON.stringify(after) : after,
      details: typeof details === 'object' && details ? JSON.stringify(details) : details,
      ip_address: ip,
      user_agent: userAgent,
      endpoint,
      method,
      previous_hash: previousHash,
      created_at: new Date(),
    });

    log.entry_hash = log.computeHash();
    await log.save();
    return log;
  } catch (e) {
    // Never break main flow
    console.error('[SYSTEM LOG ERROR]', e.message);
  }
}

async function verifyLogIntegrity() {
  const logs = await SystemLog.findAll({ order: [['id', 'ASC']] });

  if (!logs.length) return { status: 'empty', message: 'No logs found' };

  const broken = [];
  for (let i = 0; i < logs.length; i++) {
    const log = logs[i];
    const expectedHash = log.computeHash();
    if (log.entry_hash !== expectedHash) {
      broken.push({ id: log.id, issue: 'hash_mismatch', expected: expectedHash, actual: log.entry_hash });
    }
    if (i === 0) {
      if (log.previous_hash !== 'GENESIS') {
        broken.push({ id: log.id, issue: 'genesis_missing' });
      }
    } else {
      if (log.previous_hash !== logs[i - 1].entry_hash) {
        broken.push({ id: log.id, issue: 'chain_broken', expected_prev: logs[i - 1].entry_hash, actual_prev: log.previous_hash });
      }
    }
  }

  if (broken.length) {
    return { status: 'TAMPERED', broken_entries: broken, total_checked: logs.length };
  }
  return { status: 'INTACT', total_checked: logs.length, message: 'All log entries verified' };
}

module.exports = { systemLog, verifyLogIntegrity };
