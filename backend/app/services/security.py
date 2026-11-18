"""Password hashing and opaque, revocable session token helpers."""
import base64
import hashlib
import hmac
import os
import secrets

SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def hash_password(password: str) -> str:
    salt=secrets.token_bytes(16)
    derived=hashlib.scrypt(password.encode("utf-8"),salt=salt,n=SCRYPT_N,r=SCRYPT_R,p=SCRYPT_P,dklen=64,maxmem=128*1024*1024)
    return f"scrypt${SCRYPT_N}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm,n_value,salt_value,expected=encoded.split("$",3)
        if algorithm!="scrypt":return False
        salt=base64.urlsafe_b64decode(salt_value+"="*((4-len(salt_value)%4)%4))
        expected_bytes=base64.urlsafe_b64decode(expected+"="*((4-len(expected)%4)%4))
        actual=hashlib.scrypt(password.encode("utf-8"),salt=salt,n=int(n_value),r=SCRYPT_R,p=SCRYPT_P,dklen=len(expected_bytes),maxmem=128*1024*1024)
        return hmac.compare_digest(actual,expected_bytes)
    except (ValueError,TypeError,MemoryError):
        return False


def opaque_token(size: int=32) -> str:
    return _b64(secrets.token_bytes(size))


def token_hash(token: str) -> str:
    key=os.getenv("JOBPILOT_SECRET_KEY","").encode("utf-8")
    digest=hmac.new(key,token.encode("utf-8"),hashlib.sha256) if key else hashlib.sha256(token.encode("utf-8"))
    return digest.hexdigest()
