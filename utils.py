"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Utilities, Validation & Decorators
=============================================================================
"""

import html
import re
import secrets
import smtplib
import socket
import time
import threading
from functools import wraps
from datetime import datetime, timezone, timedelta

from flask import request, session, jsonify, redirect, url_for

import config
from config import (
    app, CONFIG, ADMIN_PASSWORD,
    SMTP_SERVER, SMTP_PORT, SMTP_USE_IPV4,
    MAX_CONSOLE_LOGS, MAX_LOGS, MAX_ADMIN_AUDIT,
    rate_limit_data, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX_REQUESTS,
    BLOCKED_IPS, BLOCK_DURATION,
    _data_lock,
)
from db import db_add_log, db_add_audit_log


# ===== Rate Limiting =====

def get_client_ip():
    """Get real client IP, handling proxies."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def is_rate_limited():
    """Check if client is rate limited."""
    ip = get_client_ip()
    now = time.time()

    if ip in BLOCKED_IPS:
        console_log(f"🚫 RATE LIMIT: Blocked IP attempted access: {ip[:15]}...", "warning")
        return True

    rate_limit_data[ip] = [t for t in rate_limit_data[ip] if now - t < RATE_LIMIT_WINDOW]
    current_count = len(rate_limit_data[ip])

    # Debug log every 10 requests to avoid spam
    if current_count > 0 and current_count % 10 == 0:
        console_log(f"📊 RATE LIMIT: {ip[:15]}... has {current_count}/{RATE_LIMIT_MAX_REQUESTS} requests in window", "debug")

    if current_count >= RATE_LIMIT_MAX_REQUESTS:
        BLOCKED_IPS.add(ip)
        threading.Timer(BLOCK_DURATION, lambda: BLOCKED_IPS.discard(ip)).start()
        log_activity(f"⚠️ Rate limit exceeded - IP blocked: {ip[:10]}...", "warning")
        console_log(f"🔒 RATE LIMIT TRIGGERED: {ip[:15]}... blocked for {BLOCK_DURATION}s ({current_count} requests)", "warning")
        return True

    rate_limit_data[ip].append(now)
    return False


def rate_limit(f):
    """Rate limiting decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_rate_limited():
            return jsonify({'error': 'Too many requests. Please wait.'}), 429
        return f(*args, **kwargs)
    return decorated_function


# ===== Input Validation =====

def sanitize_string(text, max_length: int = 500) -> str:
    """Sanitize and validate string input."""
    if not isinstance(text, str):
        return str(text)[:max_length] if text is not None else ''
    text = html.escape(text)
    text = re.sub(
        r'[<>"\';]|--|\bOR\b|\bAND\b|\bUNION\b|\bSELECT\b|\bDROP\b|\bINSERT\b|\bDELETE\b',
        '', text, flags=re.IGNORECASE
    )
    return text.strip()[:max_length]


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= 254


def validate_url(url: str) -> bool:
    """Validate URL is from expected domain."""
    if not url or not isinstance(url, str):
        return False
    allowed_domains = ['dubai-fleamarket.com', 'www.dubai-fleamarket.com']
    try:
        if not url.startswith(('http://', 'https://')):
            return False
        domain = url.split('/')[2].lower()
        return any(domain == allowed or domain.endswith('.' + allowed) for allowed in allowed_domains)
    except Exception:
        return False


def mask_email(email: str) -> str:
    """Mask email - show only first 2 and last 2 letters."""
    if not email or '@' not in email:
        return '***'

    local, domain = email.split('@', 1)

    if len(local) <= 4:
        masked_local = local[0] + '***'
    else:
        masked_local = local[:2] + '***' + local[-2:]

    return f"{masked_local}@{domain}"


# ===== Password Protection =====

def verify_password(password: str) -> bool:
    """Verify admin password."""
    if not password:
        return False
    return secrets.compare_digest(password, ADMIN_PASSWORD)


def require_password(f):
    """Decorator to require password for actions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        console_log(f"🔐 AUTH: Checking password for endpoint: {request.endpoint}", "debug")

        try:
            if is_admin():
                console_log(f"✅ AUTH SUCCESS (session): {request.endpoint}", "success")
                return f(*args, **kwargs)

            data = request.get_json() or {}
            password = data.get('password', '')

            console_log(f"🔐 AUTH: Password received: {'yes' if password else 'no'} (length: {len(password) if password else 0})", "debug")

            if not verify_password(password):
                log_activity(f"🚫 Failed auth attempt from {get_client_ip()[:10]}...", "warning")
                console_log(f"🔐 AUTH FAILED for {request.endpoint} from {get_client_ip()[:15]}...", "warning")
                console_log(f"   └─ Expected password length: {len(ADMIN_PASSWORD)}, Got: {len(password) if password else 0}", "debug")
                return jsonify({'error': 'Invalid password', 'auth_required': True}), 401

            console_log(f"✅ AUTH SUCCESS: {request.endpoint}", "success")
            log_admin_action(request.endpoint or request.path, f"{request.method} {request.path}")

            return f(*args, **kwargs)
        except Exception as e:
            console_log(f"❌ AUTH ERROR: {str(e)[:80]}", "error")
            import traceback
            console_log(f"   └─ Traceback: {traceback.format_exc()[:200]}", "debug")
            return jsonify({'error': 'Authentication error', 'details': str(e)[:100]}), 500
    return decorated_function


def is_admin():
    """Check if current session is admin."""
    return session.get('admin_logged_in', False)


def safe_next_url(next_url):
    """Validate redirect URL to prevent open redirect."""
    if not next_url or not isinstance(next_url, str):
        return url_for('dashboard')
    if not next_url.startswith('/'):
        return url_for('dashboard')
    return next_url


def require_admin(f):
    """Decorator to require admin session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_admin():
            return f(*args, **kwargs)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('admin_login', next=request.path))
    return decorated_function


# ===== Security Headers =====

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


# ===== Console Logging =====

def console_log(message: str, log_type: str = "info") -> None:
    """Add detailed log to system console — terminal style. Thread-safe."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%b %d, %Y %I:%M:%S %p')
    timestamp_short = now.strftime('%I:%M:%S %p')
    entry = {
        'time': timestamp,
        'time_short': timestamp_short,
        'type': log_type,  # info, success, error, warning, api, debug
        'msg': message
    }
    with _data_lock:
        config.SYSTEM_CONSOLE.insert(0, entry)
        if len(config.SYSTEM_CONSOLE) > MAX_CONSOLE_LOGS:
            config.SYSTEM_CONSOLE = config.SYSTEM_CONSOLE[:MAX_CONSOLE_LOGS]
    try:
        print(f"[CONSOLE][{log_type.upper()}] {message}")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback for terminals that can't handle emoji (e.g. Windows cp1252)
        safe_msg = message.encode('ascii', 'replace').decode('ascii')
        print(f"[CONSOLE][{log_type.upper()}] {safe_msg}")


def set_last_smtp_error(message):
    """Track latest SMTP error for diagnostics UI."""
    CONFIG['last_smtp_error'] = message
    CONFIG['last_smtp_error_at'] = datetime.now(timezone.utc).isoformat()


# ===== SMTP Connection =====

def get_smtp_connection(timeout=30):
    """Create SMTP connection, forcing IPv4 if configured to avoid network issues.

    Many cloud providers (Render, Heroku, etc.) have IPv6 issues where Python's
    smtplib tries IPv6 first but IPv6 isn't properly configured, causing
    '[Errno 101] Network is unreachable' errors. This function forces IPv4.
    """
    if SMTP_USE_IPV4:
        try:
            ipv4_addr = socket.gethostbyname(SMTP_SERVER)
            console_log(f"📡 SMTP: Connecting via IPv4 ({ipv4_addr}:{SMTP_PORT})", "debug")
            server = smtplib.SMTP(timeout=timeout)
            server.connect(ipv4_addr, SMTP_PORT)
            return server
        except socket.gaierror as e:
            console_log(f"⚠️ SMTP: IPv4 resolution failed: {e}, trying default", "warning")
        except Exception as e:
            console_log(f"⚠️ SMTP: IPv4 connect failed: {str(e)[:50]}, trying default", "warning")

    # Default connection (may use IPv6)
    console_log(f"📡 SMTP: Connecting via default ({SMTP_SERVER}:{SMTP_PORT})", "debug")
    return smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=timeout)


# ===== Timestamp Helpers =====

def parse_iso_timestamp(iso_string: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime, handling 'Z' suffix."""
    if not iso_string:
        raise ValueError("Empty timestamp")
    return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))


def format_timestamp(iso_string: str | None) -> str:
    """Format ISO timestamp to readable format like 'Jan 30, 2026 at 02:45 PM'."""
    if not iso_string:
        return '--'
    try:
        dt = parse_iso_timestamp(iso_string)
        return dt.strftime('%b %d, %Y at %I:%M %p')
    except Exception:
        return iso_string[:16] if iso_string else '--'


def format_multi_timezone(dt: datetime | None = None) -> str:
    """Return a multi-timezone string: UTC / Dubai (GST +4) / Philippines (PHT +8).

    If dt is None, uses the current UTC time.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    # Ensure UTC-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_str = dt.strftime('%I:%M %p UTC')
    dubai_dt = dt + timedelta(hours=4)
    dubai_str = dubai_dt.strftime('%I:%M %p GST')
    ph_dt = dt + timedelta(hours=8)
    ph_str = ph_dt.strftime('%I:%M %p PHT')
    return f"{utc_str} · {dubai_str} · {ph_str}"


def format_multi_timezone_date(dt: datetime | None = None) -> str:
    """Return full date + multi-timezone string for email bodies."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    date_str = dt.strftime('%B %d, %Y')
    time_str = format_multi_timezone(dt)
    return f"{date_str} at {time_str}"


def format_hour_offset(base_hour, offset_hours) -> str:
    """Format a UTC hour with offset as a local HH:00 AM/PM string."""
    try:
        local_hour = (int(base_hour) + int(offset_hours)) % 24
        period = 'AM' if local_hour < 12 else 'PM'
        display_hour = local_hour % 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour:02d}:00 {period}"
    except Exception:
        return '--'


# ===== Activity Logging =====

def log_activity(message: str, level: str = "info") -> None:
    """Add activity log entry. Thread-safe. DB-backed."""
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d, %Y at %I:%M %p'),
        'message': sanitize_string(message, 200),
        'level': level
    }
    with _data_lock:
        config.ACTIVITY_LOGS.insert(0, entry)
        if len(config.ACTIVITY_LOGS) > MAX_LOGS:
            config.ACTIVITY_LOGS = config.ACTIVITY_LOGS[:MAX_LOGS]
    try:
        db_add_log(sanitize_string(message, 200), level)
    except Exception:
        pass  # DB write failed, in-memory copy still intact
    try:
        print(f"[{level.upper()}] {message}")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass


def log_admin_action(action, details=None):
    """Record an admin action for auditing (DB-backed)."""
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d, %Y at %I:%M %p'),
        'ip': get_client_ip(),
        'action': sanitize_string(action, 120),
        'details': sanitize_string(details or '', 200)
    }
    config.ADMIN_AUDIT_LOGS.insert(0, entry)
    if len(config.ADMIN_AUDIT_LOGS) > MAX_ADMIN_AUDIT:
        config.ADMIN_AUDIT_LOGS = config.ADMIN_AUDIT_LOGS[:MAX_ADMIN_AUDIT]
    try:
        db_add_audit_log(
            sanitize_string(action, 120),
            sanitize_string(details or '', 200),
            get_client_ip()
        )
    except Exception:
        pass  # In-memory copy still intact


def record_visit():
    """Record a client landing page visit without a database."""
    if session.get('visitor_tracked'):
        return
    now = datetime.now(timezone.utc)
    config.VISITOR_TOTAL += 1
    config.VISITOR_LOG.append(now.isoformat())
    cutoff = now - timedelta(hours=24)
    config.VISITOR_LOG = [ts for ts in config.VISITOR_LOG if datetime.fromisoformat(ts) >= cutoff]
    session['visitor_tracked'] = True


# ===== CSRF =====

def _generate_csrf_token() -> str:
    """Generate a CSRF token and store it in the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def _validate_csrf_token() -> bool:
    """Validate the CSRF token from the form against the session."""
    token = request.form.get('csrf_token', '')
    expected = session.get('_csrf_token', '')
    if not token or not expected:
        return False
    return secrets.compare_digest(token, expected)
