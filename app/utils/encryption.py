from cryptography.fernet import Fernet
from config import Config


def get_cipher():
    key = Config.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY not set in .env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(value):
    """Encrypt a string value using Fernet."""
    if not value:
        return None
    cipher = get_cipher()
    return cipher.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value):
    """Decrypt a Fernet-encrypted string."""
    if not encrypted_value:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted_value.encode()).decode()