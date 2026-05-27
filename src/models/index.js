const { DataTypes, Model } = require('sequelize');
const sequelize = require('../config/database');

// ─── Safe date helpers (work with both Date objects and SQLite strings) ───────
function safeISO(val) {
  if (!val) return null;
  if (val instanceof Date) return isNaN(val.getTime()) ? null : val.toISOString();
  const d = new Date(val);
  return isNaN(d.getTime()) ? String(val) : d.toISOString();
}
function safeDate(val) {
  if (!val) return null;
  if (val instanceof Date) return isNaN(val.getTime()) ? null : val.toISOString().split('T')[0];
  // Already a YYYY-MM-DD string?
  if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(val)) return val;
  const d = new Date(val);
  return isNaN(d.getTime()) ? String(val) : d.toISOString().split('T')[0];
}

// ─────────────────────────────────────────────────────────────────────────────
// User
// ─────────────────────────────────────────────────────────────────────────────
class User extends Model {
  toDict(includeSensitive = false) {
    const data = {
      id: this.id,
      employee_id: this.employee_id,
      email: this.email,
      role: this.role,
      first_name: this.first_name,
      last_name: this.last_name,
      phone: this.phone,
      alt_phone: this.alt_phone,
      photo_url: this.photo_url,
      department: this.department,
      designation: this.designation,
      date_of_joining: safeDate(this.date_of_joining),
      date_of_leaving: safeDate(this.date_of_leaving),
      is_active: this.is_active,
      is_locked: this.is_locked,
      location_of_work: this.location_of_work,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      updated_at: this.updated_at ? safeISO(this.updated_at) : null,
    };
    if (includeSensitive) {
      data.failed_login_attempts = this.failed_login_attempts;
      data.locked_at = this.locked_at ? safeISO(this.locked_at) : null;
      data.registered_by = this.registered_by;
    }
    return data;
  }
}

User.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  employee_id: { type: DataTypes.STRING(20), unique: true, allowNull: false },
  email: { type: DataTypes.STRING(255), unique: true, allowNull: false },
  password_hash: { type: DataTypes.STRING(255), allowNull: false },
  role: { type: DataTypes.ENUM('super_admin', 'admin', 'employee'), allowNull: false },
  first_name: { type: DataTypes.STRING(100), allowNull: false },
  last_name: { type: DataTypes.STRING(100), allowNull: false },
  phone: { type: DataTypes.STRING(20), allowNull: false },
  alt_phone: { type: DataTypes.STRING(20) },
  photo_url: { type: DataTypes.STRING(500) },
  department: { type: DataTypes.STRING(100) },
  designation: { type: DataTypes.STRING(100) },
  date_of_joining: { type: DataTypes.DATEONLY, allowNull: false },
  date_of_leaving: { type: DataTypes.DATEONLY },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true },
  is_locked: { type: DataTypes.BOOLEAN, defaultValue: false },
  failed_login_attempts: { type: DataTypes.INTEGER, defaultValue: 0 },
  locked_at: { type: DataTypes.DATE },
  location_of_work: { type: DataTypes.STRING(255) },
  registered_by: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
}, {
  sequelize,
  modelName: 'User',
  tableName: 'users',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// RefreshToken
// ─────────────────────────────────────────────────────────────────────────────
class RefreshToken extends Model {}
RefreshToken.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  token: { type: DataTypes.STRING(500), unique: true, allowNull: false },
  expires_at: { type: DataTypes.DATE, allowNull: false },
  is_revoked: { type: DataTypes.BOOLEAN, defaultValue: false },
}, {
  sequelize,
  modelName: 'RefreshToken',
  tableName: 'refresh_tokens',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// OTPRequest
// ─────────────────────────────────────────────────────────────────────────────
class OTPRequest extends Model {}
OTPRequest.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  otp_code: { type: DataTypes.STRING(255), allowNull: false },
  otp_type: { type: DataTypes.ENUM('password_reset', 'verification'), allowNull: false },
  is_verified: { type: DataTypes.BOOLEAN, defaultValue: false },
  is_approved: { type: DataTypes.BOOLEAN, defaultValue: false },
  approved_by: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  expires_at: { type: DataTypes.DATE, allowNull: false },
}, {
  sequelize,
  modelName: 'OTPRequest',
  tableName: 'otp_requests',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// AuditLog
// ─────────────────────────────────────────────────────────────────────────────
class AuditLog extends Model {
  toDict() {
    return {
      id: this.id,
      user_id: this.user_id,
      action: this.action,
      target_user_id: this.target_user_id,
      details: this.details,
      ip_address: this.ip_address,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
AuditLog.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  action: { type: DataTypes.STRING(100), allowNull: false },
  target_user_id: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  details: { type: DataTypes.TEXT },
  ip_address: { type: DataTypes.STRING(50) },
}, {
  sequelize,
  modelName: 'AuditLog',
  tableName: 'audit_logs',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// SystemLog
// ─────────────────────────────────────────────────────────────────────────────
const crypto = require('crypto');
class SystemLog extends Model {
  computeHash() {
    const ts = this.created_at ? safeISO(this.created_at).replace('T', ' ').split('.')[0] : '';
    const data = `${this.user_id}|${this.action}|${this.resource}|${this.resource_id}|${this.details}|${this.ip_address}|${ts}|${this.previous_hash}`;
    return crypto.createHash('sha256').update(data).digest('hex');
  }
  toDict() {
    return {
      id: this.id,
      user_id: this.user_id,
      user_email: this.user_email,
      user_role: this.user_role,
      employee_id: this.employee_id,
      action: this.action,
      resource: this.resource,
      resource_id: this.resource_id,
      before_value: this.before_value,
      after_value: this.after_value,
      details: this.details,
      ip_address: this.ip_address,
      user_agent: this.user_agent,
      endpoint: this.endpoint,
      method: this.method,
      entry_hash: this.entry_hash,
      previous_hash: this.previous_hash,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
SystemLog.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  user_email: { type: DataTypes.STRING(255) },
  user_role: { type: DataTypes.STRING(50) },
  employee_id: { type: DataTypes.STRING(20) },
  action: { type: DataTypes.STRING(100), allowNull: false },
  resource: { type: DataTypes.STRING(100) },
  resource_id: { type: DataTypes.INTEGER },
  before_value: { type: DataTypes.TEXT },
  after_value: { type: DataTypes.TEXT },
  details: { type: DataTypes.TEXT },
  ip_address: { type: DataTypes.STRING(50) },
  user_agent: { type: DataTypes.STRING(500) },
  endpoint: { type: DataTypes.STRING(255) },
  method: { type: DataTypes.STRING(10) },
  previous_hash: { type: DataTypes.STRING(64) },
  entry_hash: { type: DataTypes.STRING(64), allowNull: false },
}, {
  sequelize,
  modelName: 'SystemLog',
  tableName: 'system_logs',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// LoginSession
// ─────────────────────────────────────────────────────────────────────────────
class LoginSession extends Model {
  toDict() {
    return {
      id: this.id,
      user_id: this.user_id,
      login_time: this.login_time ? safeISO(this.login_time) : null,
      logout_time: this.logout_time ? safeISO(this.logout_time) : null,
      ip_address: this.ip_address,
      user_agent: this.user_agent,
      status: this.status,
    };
  }
}
LoginSession.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  login_time: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
  logout_time: { type: DataTypes.DATE },
  ip_address: { type: DataTypes.STRING(50) },
  user_agent: { type: DataTypes.STRING(255) },
  session_token: { type: DataTypes.STRING(255) },
  status: { type: DataTypes.STRING(20), defaultValue: 'active' },
}, {
  sequelize,
  modelName: 'LoginSession',
  tableName: 'login_sessions',
  timestamps: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// Notification
// ─────────────────────────────────────────────────────────────────────────────
class Notification extends Model {
  toDict() {
    return {
      id: this.id,
      type: this.type,
      message: this.message,
      is_read: this.is_read,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
Notification.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  type: { type: DataTypes.STRING(50) },
  message: { type: DataTypes.STRING(255) },
  is_read: { type: DataTypes.BOOLEAN, defaultValue: false },
}, {
  sequelize,
  modelName: 'Notification',
  tableName: 'notifications',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// AttendanceConfig
// ─────────────────────────────────────────────────────────────────────────────
class AttendanceConfig extends Model {
  toDict() {
    return {
      id: this.id,
      name: this.name,
      shift_start: this.shift_start,
      shift_end: this.shift_end,
      late_threshold_minutes: this.late_threshold_minutes,
      half_day_threshold_hours: this.half_day_threshold_hours,
      full_day_threshold_hours: this.full_day_threshold_hours,
      overtime_after_hours: this.overtime_after_hours,
      is_active: this.is_active,
    };
  }
}
AttendanceConfig.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  name: { type: DataTypes.STRING(100), allowNull: false, unique: true },
  shift_start: { type: DataTypes.STRING(5), defaultValue: '09:00' },
  shift_end: { type: DataTypes.STRING(5), defaultValue: '18:00' },
  late_threshold_minutes: { type: DataTypes.INTEGER, defaultValue: 15 },
  half_day_threshold_hours: { type: DataTypes.FLOAT, defaultValue: 4.0 },
  full_day_threshold_hours: { type: DataTypes.FLOAT, defaultValue: 8.0 },
  overtime_after_hours: { type: DataTypes.FLOAT, defaultValue: 9.0 },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true },
}, {
  sequelize,
  modelName: 'AttendanceConfig',
  tableName: 'attendance_config',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// Attendance
// ─────────────────────────────────────────────────────────────────────────────
class Attendance extends Model {
  calculateHours(config) {
    if (!this.check_in_time || !this.check_out_time) return;

    const diffMs = new Date(this.check_out_time) - new Date(this.check_in_time);
    this.total_hours = Math.round((diffMs / 3600000) * 100) / 100;

    if (config) {
      const [sh, sm] = config.shift_start.split(':').map(Number);
      const checkInDate = new Date(this.check_in_time);
      const shiftStart = new Date(checkInDate);
      shiftStart.setHours(sh, sm, 0, 0);
      const graceMs = config.late_threshold_minutes * 60000;
      const graceTime = new Date(shiftStart.getTime() + graceMs);

      if (new Date(this.check_in_time) > graceTime) {
        this.is_late = true;
        this.late_minutes = Math.floor((new Date(this.check_in_time) - shiftStart) / 60000);
      } else {
        this.is_late = false;
        this.late_minutes = 0;
      }

      if (this.total_hours > config.overtime_after_hours) {
        this.overtime_hours = Math.round((this.total_hours - config.overtime_after_hours) * 100) / 100;
      } else {
        this.overtime_hours = 0;
      }

      if (this.total_hours >= config.full_day_threshold_hours) {
        this.status = 'present';
      } else {
        this.status = 'half_day';
      }
    }
  }
  toDict() {
    return {
      id: this.id,
      user_id: this.user_id,
      employee_id: this.User ? this.User.employee_id : null,
      employee_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      date: this.date,
      check_in_time: this.check_in_time ? new Date(this.check_in_time).toISOString() : null,
      check_in_lat: this.check_in_lat,
      check_in_lng: this.check_in_lng,
      check_in_address: this.check_in_address,
      check_out_time: this.check_out_time ? new Date(this.check_out_time).toISOString() : null,
      check_out_lat: this.check_out_lat,
      check_out_lng: this.check_out_lng,
      check_out_address: this.check_out_address,
      total_hours: this.total_hours,
      overtime_hours: this.overtime_hours,
      is_late: this.is_late,
      late_minutes: this.late_minutes,
      status: this.status,
      is_manually_edited: this.is_manually_edited,
      edited_by: this.edited_by,
      edit_reason: this.edit_reason,
      notes: this.notes,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
Attendance.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  date: { type: DataTypes.DATEONLY, allowNull: false },
  check_in_time: { type: DataTypes.DATE },
  check_in_lat: { type: DataTypes.FLOAT },
  check_in_lng: { type: DataTypes.FLOAT },
  check_in_address: { type: DataTypes.STRING(500) },
  check_out_time: { type: DataTypes.DATE },
  check_out_lat: { type: DataTypes.FLOAT },
  check_out_lng: { type: DataTypes.FLOAT },
  check_out_address: { type: DataTypes.STRING(500) },
  total_hours: { type: DataTypes.FLOAT },
  overtime_hours: { type: DataTypes.FLOAT, defaultValue: 0 },
  is_late: { type: DataTypes.BOOLEAN, defaultValue: false },
  late_minutes: { type: DataTypes.INTEGER, defaultValue: 0 },
  status: {
    type: DataTypes.ENUM('present', 'absent', 'half_day', 'on_leave', 'holiday', 'weekend'),
    defaultValue: 'present',
  },
  is_manually_edited: { type: DataTypes.BOOLEAN, defaultValue: false },
  edited_by: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  edit_reason: { type: DataTypes.STRING(500) },
  notes: { type: DataTypes.STRING(500) },
}, {
  sequelize,
  modelName: 'Attendance',
  tableName: 'attendance',
  timestamps: true,
  createdAt: 'created_at',
  updatedAt: 'updated_at',
  indexes: [{ unique: true, fields: ['user_id', 'date'], name: 'uq_user_date' }],
});

// ─────────────────────────────────────────────────────────────────────────────
// EmployeeProfile
// ─────────────────────────────────────────────────────────────────────────────
class EmployeeProfile extends Model {
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      date_of_birth: this.date_of_birth,
      gender: this.gender, blood_group: this.blood_group,
      marital_status: this.marital_status, nationality: this.nationality,
      address_line1: this.address_line1, address_line2: this.address_line2,
      city: this.city, state: this.state, pincode: this.pincode,
      perm_address_line1: this.perm_address_line1, perm_address_line2: this.perm_address_line2,
      perm_city: this.perm_city, perm_state: this.perm_state, perm_pincode: this.perm_pincode,
      emergency_contact_name: this.emergency_contact_name,
      emergency_contact_relation: this.emergency_contact_relation,
      emergency_contact_phone: this.emergency_contact_phone,
      father_name: this.father_name, spouse_name: this.spouse_name,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      updated_at: this.updated_at ? safeISO(this.updated_at) : null,
    };
  }
}
EmployeeProfile.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, unique: true, allowNull: false, references: { model: 'users', key: 'id' } },
  date_of_birth: { type: DataTypes.DATEONLY },
  gender: { type: DataTypes.ENUM('male', 'female', 'other') },
  blood_group: { type: DataTypes.STRING(10) },
  marital_status: { type: DataTypes.ENUM('single', 'married', 'divorced', 'widowed') },
  nationality: { type: DataTypes.STRING(50), defaultValue: 'Indian' },
  address_line1: { type: DataTypes.STRING(255) },
  address_line2: { type: DataTypes.STRING(255) },
  city: { type: DataTypes.STRING(100) },
  state: { type: DataTypes.STRING(100) },
  pincode: { type: DataTypes.STRING(10) },
  perm_address_line1: { type: DataTypes.STRING(255) },
  perm_address_line2: { type: DataTypes.STRING(255) },
  perm_city: { type: DataTypes.STRING(100) },
  perm_state: { type: DataTypes.STRING(100) },
  perm_pincode: { type: DataTypes.STRING(10) },
  emergency_contact_name: { type: DataTypes.STRING(100) },
  emergency_contact_relation: { type: DataTypes.STRING(50) },
  emergency_contact_phone: { type: DataTypes.STRING(20) },
  father_name: { type: DataTypes.STRING(100) },
  spouse_name: { type: DataTypes.STRING(100) },
}, {
  sequelize, modelName: 'EmployeeProfile', tableName: 'employee_profiles',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// BankDetail
// ─────────────────────────────────────────────────────────────────────────────
class BankDetail extends Model {
  toDict(decrypt = false) {
    const data = {
      id: this.id, user_id: this.user_id,
      bank_name: this.bank_name, branch_name: this.branch_name,
      ifsc_code: this.ifsc_code, account_holder_name: this.account_holder_name,
      uan_number: this.uan_number, esi_number: this.esi_number,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      updated_at: this.updated_at ? safeISO(this.updated_at) : null,
    };
    if (decrypt) {
      data.account_number = this.account_number_enc;
      data.pan_number = this.pan_number_enc;
    } else {
      data.account_number = this.account_number_enc ? '********' : null;
      data.pan_number = this.pan_number_enc ? '********' : null;
    }
    return data;
  }
}
BankDetail.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, unique: true, allowNull: false, references: { model: 'users', key: 'id' } },
  bank_name: { type: DataTypes.STRING(100) },
  branch_name: { type: DataTypes.STRING(100) },
  account_number_enc: { type: DataTypes.TEXT },
  ifsc_code: { type: DataTypes.STRING(20) },
  account_holder_name: { type: DataTypes.STRING(100) },
  pan_number_enc: { type: DataTypes.TEXT },
  uan_number: { type: DataTypes.STRING(30) },
  esi_number: { type: DataTypes.STRING(30) },
}, {
  sequelize, modelName: 'BankDetail', tableName: 'bank_details',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// EmployeeDocument
// ─────────────────────────────────────────────────────────────────────────────
class EmployeeDocument extends Model {
  toDict() {
    return {
      id: this.id, user_id: this.user_id, doc_type: this.doc_type,
      doc_name: this.doc_name, file_path: this.file_path,
      file_type: this.file_type, file_size: this.file_size,
      uploaded_by: this.uploaded_by, notes: this.notes,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
EmployeeDocument.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  doc_type: {
    type: DataTypes.ENUM('aadhaar','pan','passport','driving_license','voter_id',
      'offer_letter','experience_letter','relieving_letter','salary_slip',
      'bank_statement','photo','other'), allowNull: false,
  },
  doc_name: { type: DataTypes.STRING(255), allowNull: false },
  file_path: { type: DataTypes.STRING(500), allowNull: false },
  file_type: { type: DataTypes.STRING(50) },
  file_size: { type: DataTypes.INTEGER },
  uploaded_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  notes: { type: DataTypes.STRING(500) },
}, {
  sequelize, modelName: 'EmployeeDocument', tableName: 'employee_documents',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// LeaveType
// ─────────────────────────────────────────────────────────────────────────────
class LeaveType extends Model {
  toDict() {
    return {
      id: this.id, name: this.name, code: this.code,
      annual_quota: this.annual_quota, is_paid: this.is_paid,
      is_carry_forward: this.is_carry_forward, max_carry_forward: this.max_carry_forward,
      requires_approval: this.requires_approval, min_days_advance: this.min_days_advance,
      description: this.description, is_active: this.is_active,
    };
  }
}
LeaveType.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  name: { type: DataTypes.STRING(50), unique: true, allowNull: false },
  code: { type: DataTypes.STRING(10), unique: true, allowNull: false },
  annual_quota: { type: DataTypes.INTEGER, defaultValue: 0 },
  is_paid: { type: DataTypes.BOOLEAN, defaultValue: true },
  is_carry_forward: { type: DataTypes.BOOLEAN, defaultValue: false },
  max_carry_forward: { type: DataTypes.INTEGER, defaultValue: 0 },
  requires_approval: { type: DataTypes.BOOLEAN, defaultValue: true },
  min_days_advance: { type: DataTypes.INTEGER, defaultValue: 0 },
  description: { type: DataTypes.STRING(255) },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true },
}, {
  sequelize, modelName: 'LeaveType', tableName: 'leave_types',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// LeaveBalance
// ─────────────────────────────────────────────────────────────────────────────
class LeaveBalance extends Model {
  get available() {
    return (this.total_quota || 0) + (this.carry_forward || 0) - (this.used || 0);
  }
  toDict() {
    return {
      id: this.id, user_id: this.user_id, leave_type_id: this.leave_type_id,
      leave_type_name: this.LeaveType ? this.LeaveType.name : null,
      leave_type_code: this.LeaveType ? this.LeaveType.code : null,
      year: this.year, total_quota: this.total_quota,
      carry_forward: this.carry_forward, used: this.used,
      available: this.available,
    };
  }
}
LeaveBalance.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  leave_type_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'leave_types', key: 'id' } },
  year: { type: DataTypes.INTEGER, allowNull: false },
  total_quota: { type: DataTypes.INTEGER, defaultValue: 0 },
  used: { type: DataTypes.FLOAT, defaultValue: 0 },
  carry_forward: { type: DataTypes.INTEGER, defaultValue: 0 },
}, {
  sequelize, modelName: 'LeaveBalance', tableName: 'leave_balances', timestamps: false,
  indexes: [{ unique: true, fields: ['user_id', 'leave_type_id', 'year'], name: 'uq_user_leavetype_year' }],
});

// ─────────────────────────────────────────────────────────────────────────────
// LeaveRequest
// ─────────────────────────────────────────────────────────────────────────────
class LeaveRequest extends Model {
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      employee_id: this.User ? this.User.employee_id : null,
      employee_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      leave_type_id: this.leave_type_id,
      leave_type_name: this.LeaveType ? this.LeaveType.name : null,
      leave_type_code: this.LeaveType ? this.LeaveType.code : null,
      from_date: this.from_date, to_date: this.to_date,
      total_days: this.total_days, is_half_day: this.is_half_day,
      half_day_period: this.half_day_period, reason: this.reason, status: this.status,
      reviewed_by: this.reviewed_by,
      reviewer_name: this.Reviewer ? `${this.Reviewer.first_name} ${this.Reviewer.last_name}` : null,
      reviewed_at: this.reviewed_at ? safeISO(this.reviewed_at) : null,
      review_comment: this.review_comment,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      updated_at: this.updated_at ? safeISO(this.updated_at) : null,
    };
  }
}
LeaveRequest.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  leave_type_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'leave_types', key: 'id' } },
  from_date: { type: DataTypes.DATEONLY, allowNull: false },
  to_date: { type: DataTypes.DATEONLY, allowNull: false },
  total_days: { type: DataTypes.FLOAT, allowNull: false },
  is_half_day: { type: DataTypes.BOOLEAN, defaultValue: false },
  half_day_period: { type: DataTypes.ENUM('first_half', 'second_half') },
  reason: { type: DataTypes.TEXT, allowNull: false },
  status: { type: DataTypes.ENUM('pending', 'approved', 'rejected', 'cancelled'), defaultValue: 'pending' },
  reviewed_by: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  reviewed_at: { type: DataTypes.DATE },
  review_comment: { type: DataTypes.TEXT },
}, {
  sequelize, modelName: 'LeaveRequest', tableName: 'leave_requests',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// Holiday
// ─────────────────────────────────────────────────────────────────────────────
class Holiday extends Model {
  toDict() {
    return {
      id: this.id, name: this.name,
      date: this.date, is_optional: this.is_optional, year: this.year,
    };
  }
}
Holiday.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  name: { type: DataTypes.STRING(100), allowNull: false },
  date: { type: DataTypes.DATEONLY, allowNull: false, unique: true },
  is_optional: { type: DataTypes.BOOLEAN, defaultValue: false },
  year: { type: DataTypes.INTEGER, allowNull: false },
}, {
  sequelize, modelName: 'Holiday', tableName: 'holidays',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// MetalPrice
// ─────────────────────────────────────────────────────────────────────────────
class MetalPrice extends Model {
  toDict() {
    return {
      id: this.id, metal: this.metal, purity: this.purity,
      price_per_gram: this.price_per_gram, price_per_10gram: this.price_per_10gram,
      price_per_kg: this.price_per_kg, currency: this.currency, source: this.source,
      fetched_at: this.fetched_at ? safeISO(this.fetched_at) : null,
    };
  }
}
MetalPrice.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  metal: { type: DataTypes.STRING(20), allowNull: false },
  purity: { type: DataTypes.STRING(20) },
  price_per_gram: { type: DataTypes.FLOAT, allowNull: false },
  price_per_10gram: { type: DataTypes.FLOAT },
  price_per_kg: { type: DataTypes.FLOAT },
  currency: { type: DataTypes.STRING(5), defaultValue: 'INR' },
  source: { type: DataTypes.STRING(100) },
  fetched_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
}, {
  sequelize, modelName: 'MetalPrice', tableName: 'metal_prices', timestamps: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// MetalPriceHistory
// ─────────────────────────────────────────────────────────────────────────────
class MetalPriceHistory extends Model {
  toDict() {
    return {
      metal: this.metal, purity: this.purity,
      price_per_gram: this.price_per_gram, date: this.date,
    };
  }
}
MetalPriceHistory.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  metal: { type: DataTypes.STRING(20), allowNull: false },
  purity: { type: DataTypes.STRING(20) },
  price_per_gram: { type: DataTypes.FLOAT, allowNull: false },
  currency: { type: DataTypes.STRING(5), defaultValue: 'INR' },
  date: { type: DataTypes.DATEONLY, allowNull: false },
  source: { type: DataTypes.STRING(100) },
}, {
  sequelize, modelName: 'MetalPriceHistory', tableName: 'metal_price_history',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
  indexes: [{ unique: true, fields: ['metal', 'purity', 'date'], name: 'uq_metal_purity_date' }],
});

// ─────────────────────────────────────────────────────────────────────────────
// Task
// ─────────────────────────────────────────────────────────────────────────────
class Task extends Model {
  toDict(includeComments = false) {
    const data = {
      id: this.id, title: this.title, description: this.description,
      assigned_to: this.assigned_to, assigned_by: this.assigned_by,
      assignee_name: this.Assignee ? `${this.Assignee.first_name} ${this.Assignee.last_name}` : null,
      assigner_name: this.Assigner ? `${this.Assigner.first_name} ${this.Assigner.last_name}` : null,
      assignee_employee_id: this.Assignee ? this.Assignee.employee_id : null,
      status: this.status, priority: this.priority,
      due_date: this.due_date,
      started_at: this.started_at ? safeISO(this.started_at) : null,
      completed_at: this.completed_at ? safeISO(this.completed_at) : null,
      category: this.category, estimated_hours: this.estimated_hours,
      actual_hours: this.actual_hours, quantity: this.quantity, weight_grams: this.weight_grams,
      payment_amount: this.payment_amount || 0,
      admin_notes: this.admin_notes, employee_notes: this.employee_notes,
      completion_notes: this.completion_notes,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      updated_at: this.updated_at ? safeISO(this.updated_at) : null,
      attachments: this.TaskAttachments ? this.TaskAttachments.map(a => a.toDict()) : [],
    };
    if (includeComments && this.TaskComments) {
      data.comments = this.TaskComments.map(c => c.toDict());
    }
    return data;
  }
}
Task.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  title: { type: DataTypes.STRING(255), allowNull: false },
  description: { type: DataTypes.TEXT },
  assigned_to: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  assigned_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  status: {
    type: DataTypes.ENUM('pending', 'in_progress', 'completed', 'cancelled', 'on_hold'),
    defaultValue: 'pending',
  },
  priority: { type: DataTypes.ENUM('low', 'medium', 'high', 'urgent'), defaultValue: 'medium' },
  due_date: { type: DataTypes.DATEONLY },
  started_at: { type: DataTypes.DATE },
  completed_at: { type: DataTypes.DATE },
  category: { type: DataTypes.STRING(100) },
  estimated_hours: { type: DataTypes.FLOAT },
  actual_hours: { type: DataTypes.FLOAT },
  quantity: { type: DataTypes.INTEGER, defaultValue: 1 },
  weight_grams: { type: DataTypes.FLOAT },
  payment_amount: { type: DataTypes.FLOAT, defaultValue: 0 },
  admin_notes: { type: DataTypes.TEXT },
  employee_notes: { type: DataTypes.TEXT },
  completion_notes: { type: DataTypes.TEXT },
}, {
  sequelize, modelName: 'Task', tableName: 'tasks',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// TaskComment
// ─────────────────────────────────────────────────────────────────────────────
class TaskComment extends Model {
  toDict() {
    return {
      id: this.id, task_id: this.task_id, user_id: this.user_id,
      user_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      user_role: this.User ? this.User.role : null,
      comment: this.comment,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
TaskComment.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  task_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'tasks', key: 'id' } },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  comment: { type: DataTypes.TEXT, allowNull: false },
}, {
  sequelize, modelName: 'TaskComment', tableName: 'task_comments',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// TaskAttachment
// ─────────────────────────────────────────────────────────────────────────────
class TaskAttachment extends Model {
  toDict() {
    return {
      id: this.id, task_id: this.task_id, user_id: this.user_id,
      user_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      user_role: this.User ? this.User.role : null,
      file_url: this.file_url, file_type: this.file_type, original_name: this.original_name,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
TaskAttachment.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  task_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'tasks', key: 'id' } },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  file_url: { type: DataTypes.STRING(500), allowNull: false },
  file_type: { type: DataTypes.STRING(20), defaultValue: 'image' },
  original_name: { type: DataTypes.STRING(255) },
}, {
  sequelize, modelName: 'TaskAttachment', tableName: 'task_attachments',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// SalaryStructure
// ─────────────────────────────────────────────────────────────────────────────
class SalaryStructure extends Model {
  calculate() {
    this.gross_salary = Math.round(
      ((this.basic_salary||0) + (this.hra||0) + (this.da||0) + (this.conveyance||0) +
      (this.medical_allowance||0) + (this.special_allowance||0) + (this.other_allowance||0)) * 100
    ) / 100;
    this.total_deductions = Math.round(
      ((this.pf_employee||0) + (this.esi_employee||0) + (this.professional_tax||0) +
      (this.tds||0) + (this.other_deduction||0)) * 100
    ) / 100;
    this.net_salary = Math.round((this.gross_salary - this.total_deductions) * 100) / 100;
    this.ctc = Math.round((this.gross_salary + (this.pf_employer||0) + (this.esi_employer||0)) * 100) / 100;
  }
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      employee_id: this.User ? this.User.employee_id : null,
      employee_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      basic_salary: this.basic_salary, hra: this.hra, da: this.da,
      conveyance: this.conveyance, medical_allowance: this.medical_allowance,
      special_allowance: this.special_allowance, other_allowance: this.other_allowance,
      gross_salary: this.gross_salary,
      pf_employee: this.pf_employee, pf_employer: this.pf_employer,
      esi_employee: this.esi_employee, esi_employer: this.esi_employer,
      professional_tax: this.professional_tax, tds: this.tds,
      other_deduction: this.other_deduction,
      total_deductions: this.total_deductions, net_salary: this.net_salary, ctc: this.ctc,
      effective_from: this.effective_from, effective_to: this.effective_to, is_active: this.is_active,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
SalaryStructure.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  basic_salary: { type: DataTypes.FLOAT, defaultValue: 0 },
  hra: { type: DataTypes.FLOAT, defaultValue: 0 },
  da: { type: DataTypes.FLOAT, defaultValue: 0 },
  conveyance: { type: DataTypes.FLOAT, defaultValue: 0 },
  medical_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  special_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  other_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  pf_employee: { type: DataTypes.FLOAT, defaultValue: 0 },
  pf_employer: { type: DataTypes.FLOAT, defaultValue: 0 },
  esi_employee: { type: DataTypes.FLOAT, defaultValue: 0 },
  esi_employer: { type: DataTypes.FLOAT, defaultValue: 0 },
  professional_tax: { type: DataTypes.FLOAT, defaultValue: 0 },
  tds: { type: DataTypes.FLOAT, defaultValue: 0 },
  other_deduction: { type: DataTypes.FLOAT, defaultValue: 0 },
  gross_salary: { type: DataTypes.FLOAT, defaultValue: 0 },
  total_deductions: { type: DataTypes.FLOAT, defaultValue: 0 },
  net_salary: { type: DataTypes.FLOAT, defaultValue: 0 },
  ctc: { type: DataTypes.FLOAT, defaultValue: 0 },
  effective_from: { type: DataTypes.DATEONLY, allowNull: false },
  effective_to: { type: DataTypes.DATEONLY },
  is_active: { type: DataTypes.BOOLEAN, defaultValue: true },
  created_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
}, {
  sequelize, modelName: 'SalaryStructure', tableName: 'salary_structures',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// DailyWage
// ─────────────────────────────────────────────────────────────────────────────
class DailyWage extends Model {
  calculate() {
    if (this.per_day_rate && this.per_day_rate > 0) {
      this.base_pay = this.per_day_rate;
    } else if (this.per_hour_rate > 0 && this.hours_worked > 0) {
      this.base_pay = Math.round(this.per_hour_rate * this.hours_worked * 100) / 100;
    } else if (this.per_piece_rate > 0 && this.pieces_completed > 0) {
      this.base_pay = Math.round(this.per_piece_rate * this.pieces_completed * 100) / 100;
    }
    if (this.overtime_hours > 0 && this.overtime_rate > 0) {
      const hourly = this.per_hour_rate > 0 ? this.per_hour_rate : (this.per_day_rate > 0 ? this.per_day_rate / 8 : 0);
      this.overtime_pay = Math.round(this.overtime_hours * hourly * this.overtime_rate * 100) / 100;
    } else {
      this.overtime_pay = 0;
    }
    this.total_pay = Math.round(
      ((this.base_pay||0) + (this.overtime_pay||0) + (this.bonus||0) - (this.deduction||0)) * 100
    ) / 100;
  }
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      employee_id: this.User ? this.User.employee_id : null,
      employee_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      date: this.date, hours_worked: this.hours_worked, per_hour_rate: this.per_hour_rate,
      per_day_rate: this.per_day_rate, pieces_completed: this.pieces_completed,
      per_piece_rate: this.per_piece_rate, base_pay: this.base_pay,
      overtime_hours: this.overtime_hours, overtime_rate: this.overtime_rate,
      overtime_pay: this.overtime_pay, bonus: this.bonus, deduction: this.deduction,
      total_pay: this.total_pay, payment_status: this.payment_status,
      payment_mode: this.payment_mode, payment_ref: this.payment_ref,
      paid_at: this.paid_at ? safeISO(this.paid_at) : null,
      notes: this.notes,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
DailyWage.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  date: { type: DataTypes.DATEONLY, allowNull: false },
  hours_worked: { type: DataTypes.FLOAT, defaultValue: 0 },
  per_hour_rate: { type: DataTypes.FLOAT, defaultValue: 0 },
  per_day_rate: { type: DataTypes.FLOAT, defaultValue: 0 },
  pieces_completed: { type: DataTypes.INTEGER, defaultValue: 0 },
  per_piece_rate: { type: DataTypes.FLOAT, defaultValue: 0 },
  base_pay: { type: DataTypes.FLOAT, defaultValue: 0 },
  overtime_hours: { type: DataTypes.FLOAT, defaultValue: 0 },
  overtime_rate: { type: DataTypes.FLOAT, defaultValue: 0 },
  overtime_pay: { type: DataTypes.FLOAT, defaultValue: 0 },
  bonus: { type: DataTypes.FLOAT, defaultValue: 0 },
  deduction: { type: DataTypes.FLOAT, defaultValue: 0 },
  total_pay: { type: DataTypes.FLOAT, defaultValue: 0 },
  payment_status: { type: DataTypes.ENUM('pending', 'paid'), defaultValue: 'pending' },
  payment_mode: { type: DataTypes.STRING(50) },
  payment_ref: { type: DataTypes.STRING(100) },
  paid_at: { type: DataTypes.DATE },
  paid_by: { type: DataTypes.INTEGER, references: { model: 'users', key: 'id' } },
  notes: { type: DataTypes.STRING(500) },
  created_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
}, {
  sequelize, modelName: 'DailyWage', tableName: 'daily_wages',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
  indexes: [{ unique: true, fields: ['user_id', 'date'], name: 'uq_daily_wage_user_date' }],
});

// ─────────────────────────────────────────────────────────────────────────────
// Payslip
// ─────────────────────────────────────────────────────────────────────────────
const MONTH_NAMES = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
class Payslip extends Model {
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      employee_id: this.User ? this.User.employee_id : null,
      employee_name: this.User ? `${this.User.first_name} ${this.User.last_name}` : null,
      month: this.month, year: this.year, month_name: MONTH_NAMES[this.month] || '',
      basic_salary: this.basic_salary, hra: this.hra, da: this.da,
      conveyance: this.conveyance, medical_allowance: this.medical_allowance,
      special_allowance: this.special_allowance, other_allowance: this.other_allowance,
      overtime_pay: this.overtime_pay, bonus: this.bonus,
      gross_earnings: this.gross_earnings,
      pf_employee: this.pf_employee, esi_employee: this.esi_employee,
      professional_tax: this.professional_tax, tds: this.tds,
      other_deduction: this.other_deduction, leave_deduction: this.leave_deduction,
      late_deduction: this.late_deduction, total_deductions: this.total_deductions,
      net_pay: this.net_pay,
      working_days: this.working_days, present_days: this.present_days,
      leave_days: this.leave_days, absent_days: this.absent_days,
      overtime_hours: this.overtime_hours,
      payment_status: this.payment_status,
      payment_date: this.payment_date,
      payment_mode: this.payment_mode, transaction_ref: this.transaction_ref,
      payment_notes: this.payment_notes,
      generated_at: this.generated_at ? safeISO(this.generated_at) : null,
    };
  }
}
Payslip.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  salary_structure_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'salary_structures', key: 'id' } },
  month: { type: DataTypes.INTEGER, allowNull: false },
  year: { type: DataTypes.INTEGER, allowNull: false },
  basic_salary: { type: DataTypes.FLOAT, defaultValue: 0 },
  hra: { type: DataTypes.FLOAT, defaultValue: 0 },
  da: { type: DataTypes.FLOAT, defaultValue: 0 },
  conveyance: { type: DataTypes.FLOAT, defaultValue: 0 },
  medical_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  special_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  other_allowance: { type: DataTypes.FLOAT, defaultValue: 0 },
  pf_employee: { type: DataTypes.FLOAT, defaultValue: 0 },
  esi_employee: { type: DataTypes.FLOAT, defaultValue: 0 },
  professional_tax: { type: DataTypes.FLOAT, defaultValue: 0 },
  tds: { type: DataTypes.FLOAT, defaultValue: 0 },
  other_deduction: { type: DataTypes.FLOAT, defaultValue: 0 },
  overtime_pay: { type: DataTypes.FLOAT, defaultValue: 0 },
  bonus: { type: DataTypes.FLOAT, defaultValue: 0 },
  leave_deduction: { type: DataTypes.FLOAT, defaultValue: 0 },
  late_deduction: { type: DataTypes.FLOAT, defaultValue: 0 },
  working_days: { type: DataTypes.INTEGER, defaultValue: 0 },
  present_days: { type: DataTypes.FLOAT, defaultValue: 0 },
  leave_days: { type: DataTypes.FLOAT, defaultValue: 0 },
  absent_days: { type: DataTypes.FLOAT, defaultValue: 0 },
  overtime_hours: { type: DataTypes.FLOAT, defaultValue: 0 },
  gross_earnings: { type: DataTypes.FLOAT, defaultValue: 0 },
  total_deductions: { type: DataTypes.FLOAT, defaultValue: 0 },
  net_pay: { type: DataTypes.FLOAT, defaultValue: 0 },
  payment_status: { type: DataTypes.ENUM('pending','processed','paid','failed'), defaultValue: 'pending' },
  payment_date: { type: DataTypes.DATEONLY },
  payment_mode: { type: DataTypes.STRING(50) },
  transaction_ref: { type: DataTypes.STRING(100) },
  payment_notes: { type: DataTypes.TEXT },
  generated_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
}, {
  sequelize, modelName: 'Payslip', tableName: 'payslips',
  timestamps: true, createdAt: 'generated_at', updatedAt: false,
  indexes: [{ unique: true, fields: ['user_id', 'month', 'year'], name: 'uq_user_month_year' }],
});

// ─────────────────────────────────────────────────────────────────────────────
// EmployeePaymentConfig
// ─────────────────────────────────────────────────────────────────────────────
class EmployeePaymentConfig extends Model {
  toDict() {
    return {
      id: this.id, user_id: this.user_id,
      wage_type: this.wage_type, wage_amount: parseFloat(this.wage_amount),
      effective_from: this.effective_from, is_active: this.is_active, notes: this.notes,
      created_at: this.created_at ? safeISO(this.created_at) : null,
    };
  }
}
EmployeePaymentConfig.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  user_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  wage_type: { type: DataTypes.ENUM('monthly_salary','daily_wage','per_task'), allowNull: false, defaultValue: 'monthly_salary' },
  wage_amount: { type: DataTypes.DECIMAL(12, 2), allowNull: false, defaultValue: 0 },
  effective_from: { type: DataTypes.DATEONLY, allowNull: false },
  is_active: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: true },
  notes: { type: DataTypes.TEXT },
}, {
  sequelize, modelName: 'EmployeePaymentConfig', tableName: 'employee_payment_configs',
  timestamps: true, createdAt: 'created_at', updatedAt: 'updated_at',
});

// ─────────────────────────────────────────────────────────────────────────────
// PaymentTransaction
// ─────────────────────────────────────────────────────────────────────────────
class PaymentTransaction extends Model {
  toDict() {
    return {
      id: this.id, employee_id: this.employee_id, paid_by: this.paid_by,
      amount: parseFloat(this.amount), payment_date: this.payment_date,
      payment_method: this.payment_method, reference_note: this.reference_note,
      task_id: this.task_id,
      task_title: this.Task ? this.Task.title : null,
      is_advance: this.is_advance, invoice_url: this.invoice_url,
      status: this.status, reversal_of: this.reversal_of, reversal_reason: this.reversal_reason,
      created_at: this.created_at ? safeISO(this.created_at) : null,
      employee_name: null, paid_by_name: null,
    };
  }
}
PaymentTransaction.init({
  id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
  employee_id: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  paid_by: { type: DataTypes.INTEGER, allowNull: false, references: { model: 'users', key: 'id' } },
  amount: { type: DataTypes.DECIMAL(12, 2), allowNull: false },
  payment_date: { type: DataTypes.DATEONLY, allowNull: false },
  payment_method: { type: DataTypes.ENUM('cash','bank','upi'), allowNull: false, defaultValue: 'cash' },
  reference_note: { type: DataTypes.STRING(500) },
  task_id: { type: DataTypes.INTEGER, references: { model: 'tasks', key: 'id' } },
  is_advance: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
  invoice_url: { type: DataTypes.STRING(500) },
  status: { type: DataTypes.ENUM('completed','reversed'), allowNull: false, defaultValue: 'completed' },
  reversal_of: { type: DataTypes.INTEGER, references: { model: 'payment_transactions', key: 'id' } },
  reversal_reason: { type: DataTypes.STRING(500) },
}, {
  sequelize, modelName: 'PaymentTransaction', tableName: 'payment_transactions',
  timestamps: true, createdAt: 'created_at', updatedAt: false,
});

// ─────────────────────────────────────────────────────────────────────────────
// Associations
// ─────────────────────────────────────────────────────────────────────────────
User.hasMany(RefreshToken, { foreignKey: 'user_id' });
RefreshToken.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(OTPRequest, { foreignKey: 'user_id', as: 'otpRequests' });
OTPRequest.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
OTPRequest.belongsTo(User, { foreignKey: 'approved_by', as: 'Approver' });

User.hasMany(AuditLog, { foreignKey: 'user_id' });
AuditLog.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
AuditLog.belongsTo(User, { foreignKey: 'target_user_id', as: 'TargetUser' });

User.hasMany(LoginSession, { foreignKey: 'user_id' });
LoginSession.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(Notification, { foreignKey: 'user_id' });
Notification.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(Attendance, { foreignKey: 'user_id', as: 'attendance_records' });
Attendance.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
Attendance.belongsTo(User, { foreignKey: 'edited_by', as: 'Editor' });

User.hasOne(EmployeeProfile, { foreignKey: 'user_id' });
EmployeeProfile.belongsTo(User, { foreignKey: 'user_id' });

User.hasOne(BankDetail, { foreignKey: 'user_id' });
BankDetail.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(EmployeeDocument, { foreignKey: 'user_id', as: 'documents' });
EmployeeDocument.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
EmployeeDocument.belongsTo(User, { foreignKey: 'uploaded_by', as: 'Uploader' });

LeaveType.hasMany(LeaveBalance, { foreignKey: 'leave_type_id' });
LeaveBalance.belongsTo(LeaveType, { foreignKey: 'leave_type_id', as: 'LeaveType' });
LeaveBalance.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(LeaveRequest, { foreignKey: 'user_id', as: 'leave_requests' });
LeaveRequest.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
LeaveRequest.belongsTo(User, { foreignKey: 'reviewed_by', as: 'Reviewer' });
LeaveRequest.belongsTo(LeaveType, { foreignKey: 'leave_type_id', as: 'LeaveType' });

Task.belongsTo(User, { foreignKey: 'assigned_to', as: 'Assignee' });
Task.belongsTo(User, { foreignKey: 'assigned_by', as: 'Assigner' });
Task.hasMany(TaskComment, { foreignKey: 'task_id', as: 'TaskComments', onDelete: 'CASCADE' });
Task.hasMany(TaskAttachment, { foreignKey: 'task_id', as: 'TaskAttachments', onDelete: 'CASCADE' });
TaskComment.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
TaskAttachment.belongsTo(User, { foreignKey: 'user_id', as: 'User' });

User.hasMany(SalaryStructure, { foreignKey: 'user_id', as: 'salary_structures' });
SalaryStructure.belongsTo(User, { foreignKey: 'user_id', as: 'User' });

User.hasMany(DailyWage, { foreignKey: 'user_id', as: 'daily_wages' });
DailyWage.belongsTo(User, { foreignKey: 'user_id', as: 'User' });

User.hasMany(Payslip, { foreignKey: 'user_id', as: 'payslips' });
Payslip.belongsTo(User, { foreignKey: 'user_id', as: 'User' });
Payslip.belongsTo(SalaryStructure, { foreignKey: 'salary_structure_id' });

User.hasOne(EmployeePaymentConfig, { foreignKey: 'user_id', as: 'payment_config' });
EmployeePaymentConfig.belongsTo(User, { foreignKey: 'user_id' });

User.hasMany(PaymentTransaction, { foreignKey: 'employee_id', as: 'payments_received' });
PaymentTransaction.belongsTo(User, { foreignKey: 'employee_id', as: 'Employee' });
PaymentTransaction.belongsTo(User, { foreignKey: 'paid_by', as: 'Admin' });
PaymentTransaction.belongsTo(Task, { foreignKey: 'task_id', as: 'Task' });

module.exports = {
  sequelize, User, RefreshToken, OTPRequest, AuditLog, SystemLog,
  LoginSession, Notification, AttendanceConfig, Attendance,
  EmployeeProfile, BankDetail, EmployeeDocument,
  LeaveType, LeaveBalance, LeaveRequest, Holiday,
  MetalPrice, MetalPriceHistory,
  Task, TaskComment, TaskAttachment,
  SalaryStructure, DailyWage, Payslip,
  EmployeePaymentConfig, PaymentTransaction,
};
