import os
from flask import Flask, jsonify
from config import Config
from app.extensions import db, migrate, jwt, mail, cors


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
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    # Import models so they are registered with SQLAlchemy
    from app.models import User, RefreshToken, OTPRequest, AuditLog

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    @jwt.user_identity_loader
    def user_identity_lookup(user_id):
        return str(user_id)
    
    # JWT error handlers
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

    # Health check
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy", "service": "JewelCraft HRM API"})

    return app
