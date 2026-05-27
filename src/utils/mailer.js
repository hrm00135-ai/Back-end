const nodemailer = require('nodemailer');
const config = require('../config/config');

let transporter = null;

function getTransporter() {
  if (!transporter) {
    transporter = nodemailer.createTransport({
      host: config.MAIL_SERVER,
      port: config.MAIL_PORT,
      secure: config.MAIL_PORT === 465,
      auth: {
        user: config.MAIL_USERNAME,
        pass: config.MAIL_PASSWORD,
      },
    });
  }
  return transporter;
}

async function sendMail({ to, subject, text, html }) {
  const t = getTransporter();
  await t.sendMail({
    from: config.MAIL_DEFAULT_SENDER || config.MAIL_USERNAME,
    to,
    subject,
    text,
    html,
  });
}

module.exports = { sendMail };
