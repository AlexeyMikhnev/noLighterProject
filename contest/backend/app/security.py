import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from . import config


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_TTL_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": exp}, config.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
