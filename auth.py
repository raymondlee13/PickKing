"""Username/password accounts and session cookies -- stdlib only (hashlib +
secrets for hashing/tokens, a flat JSON file for the user store).

This is a login gate, not multi-tenancy: every account shares the same scan
state, tracking workbook, and config.json -- see PRODUCT.md on why real
per-user data isolation is a separate, still-undecided feature.
"""

import hashlib
import json
import os
import secrets
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_PATH = os.path.join(BASE_DIR, "users.json")
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.json")

PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 8
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days -- a phone shouldn't need to log back in every visit


def _load_sessions():
    try:
        with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


# token -> [username, expires_at]. Persisted to sessions.json (gitignored) so a
# server restart doesn't log everyone out; writes go through _sessions_lock
# since requests run on their own threads.
_sessions = _load_sessions()
_sessions_lock = threading.Lock()


def _save_sessions():
    tmp_path = SESSIONS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_sessions, f)
    os.replace(tmp_path, SESSIONS_PATH)


def _load_users():
    if not os.path.exists(USERS_PATH):
        return {}
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users):
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def _hash_password(password, salt_hex=None):
    salt_hex = salt_hex or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return salt_hex, digest.hex()


def create_user(username, password):
    username = username.strip()
    if not username:
        return False, "Enter a username."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    users = _load_users()
    # Server listens on the whole LAN -- only the first account can self-register.
    # Add more by hand-editing users.json (or temporarily moving it aside).
    if users:
        return False, "Registration is closed."
    if username in users:
        return False, "That username is already taken."
    salt_hex, digest_hex = _hash_password(password)
    users[username] = {"salt": salt_hex, "hash": digest_hex}
    _save_users(users)
    return True, ""


def verify_user(username, password):
    users = _load_users()
    record = users.get(username.strip())
    if not record:
        return False
    _, digest_hex = _hash_password(password, record["salt"])
    return secrets.compare_digest(digest_hex, record["hash"])


def create_session(username):
    token = secrets.token_hex(32)
    now = time.time()
    with _sessions_lock:
        for expired in [t for t, (_, exp) in _sessions.items() if exp < now]:
            del _sessions[expired]
        _sessions[token] = [username, now + SESSION_MAX_AGE]
        _save_sessions()
    return token


def username_for_session(token):
    entry = _sessions.get(token)
    if entry and entry[1] > time.time():
        return entry[0]
    return None


def destroy_session(token):
    with _sessions_lock:
        if _sessions.pop(token, None):
            _save_sessions()


def parse_session_cookie(cookie_header):
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, _, value = part.strip().partition("=")
        if key == "session":
            return value
    return None
