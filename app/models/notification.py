from datetime import datetime
from app.extensions import db

class LoginSession(db.Model):
    __tablename__ = "login_sessions"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)

    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

    status = db.Column(db.String(20), default="active")  # active, logged_out

    def __repr__(self):
        return f"<LoginSession User {self.user_id} - {self.status}>"