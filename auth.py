"""
AgriWaste AI — local development authentication.

Security boundary:
- Passwords are never stored in plaintext.
- PBKDF2-HMAC-SHA256 with a unique random salt is used for local development.
- Farmer and buyer self-registration is supported.
- Admin accounts are provisioned only through environment variables.
- Production should replace this module with an enterprise OIDC/OAuth identity provider.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path("data/auth.db")
PBKDF2_ITERATIONS = 310_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return digest.hex()


def initialize_auth_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT DEFAULT '',
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('farmer','buyer','admin')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                last_login_at TEXT
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "phone" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        conn.commit()

    _ensure_env_admin()


def _ensure_env_admin() -> None:
    email = os.getenv("AGRIWASTE_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("AGRIWASTE_ADMIN_PASSWORD", "")

    if not email or not password:
        return
    if len(password) < 12 or not EMAIL_RE.match(email):
        return

    with _connect() as conn:
        exists = conn.execute(
            "SELECT user_id FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if exists:
            return

        salt = secrets.token_bytes(16)
        conn.execute(
            """
            INSERT INTO users
            (user_id, full_name, email, password_hash, password_salt, role)
            VALUES (?, ?, ?, ?, ?, 'admin')
            """,
            (
                "USR-" + secrets.token_hex(8).upper(),
                "AgriWaste Administrator",
                email,
                _hash_password(password, salt),
                salt.hex(),
            ),
        )
        conn.commit()


def validate_registration(
    full_name: str,
    email: str,
    password: str,
    role: str,
) -> Optional[str]:
    if len(full_name.strip()) < 2:
        return "Enter your full name."

    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return "Enter a valid email address."

    if role not in {"farmer", "buyer"}:
        return "Select a valid account type."

    if len(password) < 8:
        return "Password must contain at least 8 characters."

    if password.lower() == password or password.upper() == password:
        return "Use a mix of uppercase and lowercase characters."

    if not any(ch.isdigit() for ch in password):
        return "Include at least one number in the password."

    return None


def create_user(
    full_name: str,
    email: str,
    password: str,
    role: str,
    phone: str = "",
) -> Dict[str, Any]:
    initialize_auth_db()

    error = validate_registration(full_name, email, password, role)
    if error:
        raise ValueError(error)

    email = email.strip().lower()
    salt = secrets.token_bytes(16)
    user_id = "USR-" + secrets.token_hex(8).upper()

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users
                (user_id, full_name, email, phone, password_hash, password_salt, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    full_name.strip(),
                    email,
                    phone.strip(),
                    _hash_password(password, salt),
                    salt.hex(),
                    role,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists.")

    return {
        "user_id": user_id,
        "full_name": full_name.strip(),
        "email": email,
        "phone": phone.strip(),
        "role": role,
    }


def get_user_contact(user_id: str) -> Optional[Dict[str, Any]]:
    """Return marketplace contact information for an authenticated participant."""
    initialize_auth_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, full_name, email, phone, role
            FROM users
            WHERE user_id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def authenticate(email: str, password: str) -> Optional[Dict[str, Any]]:
    initialize_auth_db()
    email = email.strip().lower()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()

        if not row:
            return None

        salt = bytes.fromhex(row["password_salt"])
        candidate = _hash_password(password, salt)

        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None

        conn.execute(
            "UPDATE users SET last_login_at = datetime('now','localtime') WHERE user_id = ?",
            (row["user_id"],),
        )
        conn.commit()

    return {
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"] or "",
        "role": row["role"],
    }
