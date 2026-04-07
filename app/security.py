from __future__ import annotations

import hashlib
import hmac
import secrets


PBKDF2_ROUNDS = 120_000


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS)
    return f"{PBKDF2_ROUNDS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        rounds_raw, salt, digest = stored_hash.split("$", 2)
        rounds = int(rounds_raw)
    except ValueError:
        return False

    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return hmac.compare_digest(computed.hex(), digest)
