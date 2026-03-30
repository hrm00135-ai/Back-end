import os
from flask import Flask, jsonify, request
from config import Config
from app.extensions import db, migrate, jwt, mail, cors
from flask_cors import CORS

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Create upload folder
    os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)
    CORS(app, resources={
        r"/api/*": {
             "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
     }, supports_credentials=False)

    # Register blueprints
# Import models so tables are created
    from app.models import User, RefreshToken, OTPRequest, AuditLog
    from app.models.notification import LoginSession, Notification

    with app.app_context():
        db.create_all()

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.users import users_bp
    from app.routes.profiles import profiles_bp
    from app.routes.tasks import tasks_bp
    from app.routes.attendance import attendance_bp
    from app.routes.leaves import leaves_bp
    from app.routes.payroll import payroll_bp
    from app.routes.reports import reports_bp
    from app.routes.metals import metals_bp
    from app.routes.notifications import notifications_bp   # ← ADD THIS

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(profiles_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(leaves_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(metals_bp)
    app.register_blueprint(notifications_bp)   # ← ADD THIS

    # JWT callbacks
    @jwt.user_identity_loader
    def user_identity_lookup(user_id):
        return str(user_id)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "status": "error",
            "message": "Token has expired",
            "error": "token_expired",
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "status": "error",
            "message": "Invalid token",
            "error": "invalid_token",
        }), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "status": "error",
            "message": "Authorization token is missing",
            "error": "authorization_required",
        }), 401

# Auto-log all authenticated API calls to system log
    @app.after_request
    def log_request(response):
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        from app.utils.system_logger import system_log
        
        # Only log API calls, skip health checks and static
        if not request.path.startswith("/api/") or request.path == "/api/health":
            return response
        
        # Skip GET requests to reduce noise (optional — remove if you want all)
        if request.method == "GET":
            return response

        try:
            verify_jwt_in_request(optional=True)
            uid = get_jwt_identity()
        except Exception:
            uid = None

        try:
            system_log(
                action=f"{request.method}_{request.path}",
                user_id=uid,
                resource=request.path.split("/")[2] if len(request.path.split("/")) > 2 else None,
                details={"status_code": response.status_code},
            )
        except Exception:
            pass  # Never break the response for logging

        return response
    
    # Health check
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy", "service": "JewelCraft HRM API"})

    @app.route("/api/seed-admin", methods=["GET"])
    def seed_admin():
        from app.utils.helpers import hash_password
        try:
            if User.query.filter_by(email="admin@jewelcraft.com").first():
                return jsonify({"message": "Already exists"})
            from datetime import date

            u = User(
                employee_id="SA001",
                first_name="Super",
                last_name="Admin",
                email="admin@jewelcraft.com",
                password_hash=hash_password("Admin@123"),
                role="super_admin",
                phone="0000000000",
                date_of_joining=date.today(),
                is_active=True,
            )
            db.session.add(u)
            db.session.commit()
            return jsonify({"message": "Super admin created"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500
        
    return app