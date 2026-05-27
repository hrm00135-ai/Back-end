const { Sequelize } = require('sequelize');
const config = require('./config');
const path = require('path');

let sequelize;

const rawUrl =
  process.env.MYSQL_URL ||
  process.env.SQLALCHEMY_DATABASE_URI ||
  process.env.DATABASE_URL ||
  null;

if (rawUrl) {
  let dbUrl = rawUrl;
  // Fix mysql+pymysql prefix if copied from Python env
  if (dbUrl.startsWith('mysql+pymysql://')) {
    dbUrl = dbUrl.replace('mysql+pymysql://', 'mysql://');
  }
  sequelize = new Sequelize(dbUrl, {
    dialect: 'mysql',
    dialectModule: require('mysql2'),
    logging: false,
    pool: {
      max: 20,
      min: 0,
      acquire: 30000,
      idle: 10000,
    },
  });
} else {
  // SQLite fallback for development
  sequelize = new Sequelize({
    dialect: 'sqlite',
    storage: path.join(__dirname, '../../instance/local.db'),
    logging: false,
  });
}

module.exports = sequelize;
