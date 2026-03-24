import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-fallback-key")
    
    # Database
    MYSQL_URL = os.getenv("SQLALCHEMY_DATABASE_URI")

    if MYSQL_URL:
        if MYSQL_URL.startswith("mysql://"):
            MYSQL_URL = MYSQL_URL.replace("mysql://", "mysql+pymysql://")
    else:
        MYSQL_URL = "sqlite:///local.db"  # fallback so app doesn't crash

    SQLALCHEMY_DATABASE_URI = MYSQL_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-dev-fallback")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    
    # Mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    
    # Uploads
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "16777216"))  # 16MB
    
    # Auth settings
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCK_DURATION_MINUTES = 30
    OTP_EXPIRY_MINUTES = 10
