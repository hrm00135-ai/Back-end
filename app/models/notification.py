from datetime import datetime
from app.extensions import db

class LoginSession(db.Model):
    __tablename__ = "login_sessions"
    __table_args__ = {"extend_existing": True}  # ← ADD THIS LINE

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)

    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    session_token = db.Column(db.String(255))
    status = db.Column(db.String(20), default="active")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "login_time": self.login_time.isoformat() if self.login_time else None,
            "logout_time": self.logout_time.isoformat() if self.logout_time else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
        }