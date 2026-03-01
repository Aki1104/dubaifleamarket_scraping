"""
=============================================================================
🌐 DUBAI FLEA MARKET ADMIN DASHBOARD - SECURE VERSION WITH EMAIL HISTORY
=============================================================================
Features:
- Password protection for all admin actions
- Rate limiting for DDoS protection
- Input sanitization for security
- Email masking for privacy (show only first 2 & last 2 letters)
- Email history tracking
- Enable/Disable individual recipients
=============================================================================
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import json
import os
from functools import wraps
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import threading
import requests
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html
import secrets
import time
import re

# Database layer — replaces all JSON file storage
from db import (
    get_connection, get_db_status, migrate_from_json,
    db_load_seen_events, db_save_seen_events_bulk,
    db_get_seen_event_count,
    db_load_status, db_save_status, db_get_status, db_set_status,
    db_add_log, db_get_logs, db_clear_logs,
    db_add_email_history, db_get_email_history,
    db_add_to_queue, db_get_queue, db_update_queue_item,
    db_remove_from_queue, db_clear_queue, db_get_queue_count,
    db_record_stat, db_get_stats, db_prune_stats,
    db_set_notification_setting, db_get_all_notification_settings,
    db_add_subscriber, db_remove_subscriber, db_toggle_subscriber,
    db_get_subscribers, db_get_active_subscriber_ids,
    db_get_subscriber_count,
    validate_chat_id, mask_chat_id,
    db_add_audit_log, db_get_audit_logs,
)

# Load .env file so credentials (ADMIN_PASSWORD, etc.) are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
)
app.permanent_session_lifetime = timedelta(hours=int(os.environ.get('ADMIN_SESSION_HOURS', '8')))
# ===== SECURITY: Rate Limiting =====
# ===== SECURITY: Input Validation =====
# ===== SECURITY: Password Protection =====
# ===== SECURITY: Headers Middleware =====
# ===== CONFIGURATION =====
# ===== EMAIL QUEUE - Persistent retry for failed emails =====
# ===== EVENT STATISTICS - For charting =====
# ===== SYSTEM CONSOLE - Terminal-like logging =====
# ===== RECIPIENT STATUS MANAGEMENT =====
# ===== EMAIL HISTORY MANAGEMENT =====
# ===== HELPER FUNCTIONS =====

# ===== SECURITY: Rate Limiting =====
rate_limit_data = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 100  # Increased from 30 - dashboard polls frequently
BLOCKED_IPS = set()
BLOCK_DURATION = 300

def get_client_ip():
    """Get real client IP, handling proxies."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
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

# --- Event Tracking Data Loader ---
def load_tracked_events():
    try:
        seen_data = load_seen_events()
        return seen_data.get('event_details', [])
    except Exception:
        return []

def get_latest_event_summary():
    try:
        events = load_tracked_events()
        if not events:
            return None
        latest = events[-1]
        return {
            'id': latest.get('id', ''),
            'title': sanitize_string(str(latest.get('title', 'Untitled')), 120),
            'link': latest.get('link', '#'),
            'first_seen': latest.get('first_seen') or latest.get('date_posted') or ''
        }
    except Exception:
        return None

# --- Admin Auth (simple, to be improved) ---
def is_admin():
    return session.get('admin_logged_in', False)

def safe_next_url(next_url):
    if not next_url or not isinstance(next_url, str):
        return url_for('dashboard')
    if not next_url.startswith('/'):
        return url_for('dashboard')
    return next_url

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if is_admin():
            return f(*args, **kwargs)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('admin_login', next=request.path))
    return decorated_function

# --- API: Get tracked events ---
@app.route('/api/events')
@rate_limit
@require_admin
def api_events():
    events = load_tracked_events()
    return jsonify({'events': events})

# ===== SECURITY: Input Validation =====
def sanitize_string(text, max_length: int = 500) -> str:
    """Sanitize and validate string input."""
    if not isinstance(text, str):
        return str(text)[:max_length] if text is not None else ''
    text = html.escape(text)
    text = re.sub(r'[<>"\';]|--|\bOR\b|\bAND\b|\bUNION\b|\bSELECT\b|\bDROP\b|\bINSERT\b|\bDELETE\b', '', text, flags=re.IGNORECASE)
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

# ===== SECURITY: Password Protection =====
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')

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

# ===== SECURITY: Headers Middleware =====
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

# ===== CONFIGURATION =====
API_URL = "https://dubai-fleamarket.com/wp-json/wp/v2/product?per_page=20"

DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
# Legacy JSON file paths — data now lives entirely in Turso DB.
# db.py has its own DATA_DIR for the one-time migration code.

# Telegram Bot (FREE - unlimited messages, instant push notifications)
# Create bot: @BotFather on Telegram, get token
# Get chat ID: Send message to bot, then visit: https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_IDS = os.environ.get('TELEGRAM_CHAT_IDS', '')  # Comma-separated chat IDs for NEW EVENTS
TELEGRAM_ADMIN_CHAT_ID = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')  # Admin only - receives heartbeat/status

# Gmail SMTP (may be blocked on some cloud hosts like Render free tier)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MY_EMAIL = os.environ.get('MY_EMAIL', '')
MY_PASSWORD = os.environ.get('MY_PASSWORD', '')
TO_EMAIL = os.environ.get('TO_EMAIL', '')

# Force IPv4 for SMTP connections (fixes "Network is unreachable" on some cloud hosts)
# This is a common issue on Render, Heroku, etc. where IPv6 is attempted but not available
SMTP_USE_IPV4 = os.environ.get('SMTP_USE_IPV4', 'true').lower() == 'true'

# Note: get_smtp_connection() function is defined after console_log() below

CONFIG = {
    'check_interval_minutes': int(os.environ.get('CHECK_INTERVAL', '15')),
    'heartbeat_enabled': os.environ.get('HEARTBEAT_ENABLED', 'true').lower() == 'true',
    'heartbeat_hours': int(os.environ.get('HEARTBEAT_HOURS', '3')),
    'heartbeat_email': os.environ.get('HEARTBEAT_EMAIL', ''),
    'daily_summary_enabled': os.environ.get('DAILY_SUMMARY_ENABLED', 'true').lower() == 'true',
    'daily_summary_hour': int(os.environ.get('DAILY_SUMMARY_HOUR', '9')),
    'tracker_enabled': True,
    'telegram_notifications_enabled': True,
    'email_notifications_enabled': True,
    'last_check': None,
    'next_check': (datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get('CHECK_INTERVAL', '15')))).isoformat(),
    'next_heartbeat': (datetime.now(timezone.utc) + timedelta(hours=int(os.environ.get('HEARTBEAT_HOURS', '3')))).isoformat(),
    'total_checks': 0,
    'total_new_events': 0,
    'emails_sent': 0,
    'uptime_start': datetime.now(timezone.utc).isoformat(),
    'last_smtp_error': None,
    'last_smtp_error_at': None,
    'last_daily_summary_sent_at': None,
    'last_daily_summary_recipient_count': 0
}

ACTIVITY_LOGS = []
MAX_LOGS = 100
ADMIN_AUDIT_LOGS = []
MAX_ADMIN_AUDIT = 300
VISITOR_TOTAL = 0
VISITOR_LOG = []  # List of ISO timestamps for last 24h
LAST_GMAIL_CONFIG_LOG_AT = None

# ===== CHECK HISTORY - Card-based check results =====
CHECK_HISTORY = []
MAX_CHECK_HISTORY = 50  # Keep last 50 check results

# ===== SYSTEM CONSOLE - Terminal-like logging =====
SYSTEM_CONSOLE = []
MAX_CONSOLE_LOGS = 200

# ===== EMAIL QUEUE - Persistent retry for failed emails =====
EMAIL_QUEUE = []  # List of {subject, body, recipient, created_at, attempts, next_retry, priority}
MAX_EMAIL_QUEUE = 50
EMAIL_RETRY_INTERVALS = [30, 60, 120, 240]  # Minutes: 30min, 1hr, 2hr, 4hr
MAX_EMAIL_AGE_HOURS = 24  # Give up after 24 hours

def load_email_queue():
    """Load email queue from database."""
    global EMAIL_QUEUE
    try:
        EMAIL_QUEUE = db_get_queue()
        console_log(f"📬 Email queue loaded: {len(EMAIL_QUEUE)} pending emails", "debug")
    except Exception as e:
        console_log(f"⚠️ Failed to load email queue: {e}", "warning")
        EMAIL_QUEUE = []

def load_admin_audit_on_startup():
    global ADMIN_AUDIT_LOGS
    ADMIN_AUDIT_LOGS = db_get_audit_logs(300)

def save_email_queue():
    """Sync in-memory queue with database."""
    global EMAIL_QUEUE
    try:
        EMAIL_QUEUE = db_get_queue()
    except Exception as e:
        console_log(f"⚠️ Failed to sync email queue: {e}", "warning")

def add_to_email_queue(subject, body, recipient, priority='normal'):
    """Add a failed email to the retry queue (database-backed)."""
    global EMAIL_QUEUE
    
    try:
        item_id = db_add_to_queue(subject, body, recipient, priority)
        EMAIL_QUEUE = db_get_queue()  # Refresh in-memory copy
        console_log(f"📬 Email queued for retry: {mask_email(recipient)} ({priority} priority)", "info")
        log_activity(f"📬 Email queued for retry to {mask_email(recipient)}", "warning")
    except Exception as e:
        console_log(f"⚠️ Failed to queue email: {e}", "warning")

def process_email_queue():
    """Process pending emails in the queue (DB-backed). Called periodically."""
    queue_items = db_get_queue()
    
    if not queue_items:
        return
    
    now = datetime.now(timezone.utc)
    processed = 0
    removed = 0
    
    console_log(f"📬 Processing email queue: {len(queue_items)} pending", "info")
    
    for item in queue_items:
        try:
            created = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
        except Exception:
            created = now  # fallback
        age_hours = (now - created).total_seconds() / 3600
        
        # Remove if too old
        if age_hours > MAX_EMAIL_AGE_HOURS:
            console_log(f"⏰ Email expired (>{MAX_EMAIL_AGE_HOURS}h old): {mask_email(item['recipient'])}", "warning")
            log_activity(f"📧 Email expired after {MAX_EMAIL_AGE_HOURS}h: {item['subject'][:30]}...", "error")
            db_remove_from_queue(item['id'])
            removed += 1
            continue
        
        # Check if it's time to retry
        try:
            next_retry = datetime.fromisoformat(item['next_retry'].replace('Z', '+00:00'))
        except Exception:
            next_retry = now  # retry now if can't parse
        if now < next_retry:
            continue
        
        # Try to send
        console_log(f"🔄 Retrying queued email to {mask_email(item['recipient'])} (attempt {item['attempts'] + 1})", "info")
        
        success = send_email_direct(item['subject'], item['body'], item['recipient'])
        
        if success:
            console_log(f"✅ Queued email delivered: {mask_email(item['recipient'])}", "success")
            log_activity(f"✅ Queued email finally delivered to {mask_email(item['recipient'])}", "success")
            db_remove_from_queue(item['id'])
            processed += 1
        else:
            new_attempts = item['attempts'] + 1
            
            # Calculate next retry
            if new_attempts < len(EMAIL_RETRY_INTERVALS):
                delay_minutes = EMAIL_RETRY_INTERVALS[new_attempts]
            else:
                delay_minutes = EMAIL_RETRY_INTERVALS[-1]  # Use last interval
            
            new_next_retry = (now + timedelta(minutes=delay_minutes)).isoformat()
            db_update_queue_item(item['id'], new_attempts, new_next_retry)
            console_log(f"⏳ Will retry in {delay_minutes} minutes", "debug")
    
    if processed or removed:
        remaining = db_get_queue_count()
        console_log(f"📬 Queue processed: {processed} sent, {removed} expired, {remaining} remaining", "info")
    
    # Sync in-memory list for dashboard compatibility
    EMAIL_QUEUE[:] = db_get_queue()

def build_email_queue_payload(limit=None):
    """Return a safe, UI-ready email queue payload (DB-backed)."""
    items = db_get_queue()
    total = len(items)
    high_priority = sum(1 for e in items if e.get('priority') == 'high')

    if isinstance(limit, int):
        items = items[:limit]

    payload_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        payload_items.append({
            'id': item.get('id'),
            'subject': sanitize_string(item.get('subject', ''), 120),
            'recipient_masked': mask_email(item.get('recipient', '')),
            'next_retry_display': format_timestamp(item.get('next_retry')),
            'priority': item.get('priority', 'normal'),
            'attempts': item.get('attempts', 0),
            'last_error': sanitize_string(item.get('last_error', ''), 120) if item.get('last_error') else None
        })

    return {
        'pending_count': total,
        'high_priority': high_priority,
        'items': payload_items
    }

# ===== EVENT STATISTICS - DB-backed =====
EVENT_STATS = {'daily': {}, 'hourly': {}}  # In-memory cache (rebuilt from DB on read)

def load_event_stats():
    """Load event statistics from database."""
    global EVENT_STATS
    try:
        daily_rows = db_get_stats('daily', 30)
        hourly_rows = db_get_stats('hourly', 48)
        EVENT_STATS['daily'] = {
            r['period']: {'checks': r['checks'], 'new_events': r['new_events'], 'emails_sent': r['emails_sent']}
            for r in daily_rows
        }
        EVENT_STATS['hourly'] = {
            r['period']: {'checks': r['checks'], 'new_events': r['new_events'], 'emails_sent': r['emails_sent']}
            for r in hourly_rows
        }
        console_log("📊 Event statistics loaded from database", "debug")
    except Exception as e:
        console_log(f"⚠️ Failed to load event stats: {e}", "warning")
        EVENT_STATS = {'daily': {}, 'hourly': {}}
    return EVENT_STATS

def record_stat(stat_type, value=1):
    """Record a statistic (checks, new_events, emails_sent) to DB."""
    now = datetime.now(timezone.utc)
    day_key = now.strftime('%Y-%m-%d')
    hour_key = now.strftime('%Y-%m-%dT%H')
    
    try:
        db_record_stat('daily', day_key, stat_type, value)
        db_record_stat('hourly', hour_key, stat_type, value)
    except Exception as e:
        console_log(f"⚠️ Failed to record stat: {e}", "warning")

# ===== THEME SETTINGS =====
def load_theme_settings():
    """Load theme settings from DB."""
    try:
        raw = db_get_status('theme_settings')
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {'theme': 'dark', 'notifications_enabled': False}

def save_theme_settings(settings):
    """Save theme settings to DB."""
    try:
        db_set_status('theme_settings', json.dumps(settings))
    except Exception as e:
        console_log(f"⚠️ Failed to save theme settings: {e}", "warning")

API_DIAGNOSTICS = {
    'last_request_time': None,
    'last_response_time_ms': 0,
    'last_status_code': None,
    'last_response_size': 0,
    'last_events_count': 0,
    'total_api_calls': 0,
    'failed_api_calls': 0,
    'avg_response_time_ms': 0,
    'last_error': None,
    'last_successful_call': None
}

def set_last_smtp_error(message):
    """Track latest SMTP error for diagnostics UI."""
    CONFIG['last_smtp_error'] = message
    CONFIG['last_smtp_error_at'] = datetime.now(timezone.utc).isoformat()

def console_log(message: str, log_type: str = "info") -> None:
    """Add detailed log to system console - terminal style. Thread-safe."""
    global SYSTEM_CONSOLE
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
        SYSTEM_CONSOLE.insert(0, entry)
        if len(SYSTEM_CONSOLE) > MAX_CONSOLE_LOGS:
            SYSTEM_CONSOLE = SYSTEM_CONSOLE[:MAX_CONSOLE_LOGS]
    try:
        print(f"[CONSOLE][{log_type.upper()}] {message}")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback for terminals that can't handle emoji (e.g. Windows cp1252)
        safe_msg = message.encode('ascii', 'replace').decode('ascii')
        print(f"[CONSOLE][{log_type.upper()}] {safe_msg}")

# ===== SMTP CONNECTION WITH IPv4 FORCING =====
def get_smtp_connection(timeout=30):
    """Create SMTP connection, forcing IPv4 if configured to avoid network issues.
    
    Many cloud providers (Render, Heroku, etc.) have IPv6 issues where Python's
    smtplib tries IPv6 first but IPv6 isn't properly configured, causing
    '[Errno 101] Network is unreachable' errors. This function forces IPv4.
    """
    if SMTP_USE_IPV4:
        # Force IPv4 by resolving the hostname and connecting directly
        try:
            # Get IPv4 address explicitly
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

checker_thread = None
stop_checker = threading.Event()

# Thread-safety lock for shared mutable state (CONFIG counters, logs, queues)
_data_lock = threading.RLock()



def parse_iso_timestamp(iso_string: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime, handling 'Z' suffix."""
    if not iso_string:
        raise ValueError("Empty timestamp")
    return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))


# ===== RECIPIENT STATUS MANAGEMENT =====
def load_recipient_status():
    """Load recipient enabled/disabled status from DB."""
    try:
        raw = db_get_status('recipient_status')
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    # Initialize all recipients as enabled
    status = {}
    for email in get_all_recipients():
        status[email] = {'enabled': True}
    save_recipient_status(status)
    return status

def save_recipient_status(status):
    """Save recipient status to DB."""
    try:
        db_set_status('recipient_status', json.dumps(status))
    except Exception as e:
        console_log(f"Failed to save recipient status: {e}", "error")

def is_recipient_enabled(email):
    """Check if recipient is enabled."""
    status = load_recipient_status()
    return status.get(email, {}).get('enabled', True)

# ===== EMAIL HISTORY MANAGEMENT =====
def load_email_history():
    """Load email history from database."""
    try:
        return db_get_email_history(500)
    except Exception:
        return []

def add_to_email_history(recipient, subject, success, error_msg=''):
    """Add entry to email history in database."""
    try:
        db_add_email_history(
            recipient, mask_email(recipient),
            sanitize_string(subject, 100),
            success, error_msg
        )
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to save email history: {e}", "warning")

def format_timestamp(iso_string: str) -> str:
    """Format ISO timestamp to readable format like 'Jan 30, 2026 at 02:45 PM'."""
    try:
        dt = parse_iso_timestamp(iso_string)
        return dt.strftime('%b %d, %Y at %I:%M %p')
    except Exception:
        return iso_string[:16] if iso_string else '--'

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

# ===== HELPER FUNCTIONS =====
def get_all_recipients() -> list:
    """Get all configured recipients."""
    if not TO_EMAIL:
        return []
    return [e.strip() for e in TO_EMAIL.split(',') if e.strip() and validate_email(e.strip())]

def get_recipients() -> list:
    """Get enabled recipients only."""
    all_recipients = get_all_recipients()
    return [e for e in all_recipients if is_recipient_enabled(e)]

def log_activity(message: str, level: str = "info") -> None:
    """Add activity log entry. Thread-safe. DB-backed."""
    global ACTIVITY_LOGS
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d, %Y at %I:%M %p'),
        'message': sanitize_string(message, 200),
        'level': level
    }
    with _data_lock:
        ACTIVITY_LOGS.insert(0, entry)
        if len(ACTIVITY_LOGS) > MAX_LOGS:
            ACTIVITY_LOGS = ACTIVITY_LOGS[:MAX_LOGS]
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
    global ADMIN_AUDIT_LOGS
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d, %Y at %I:%M %p'),
        'ip': get_client_ip(),
        'action': sanitize_string(action, 120),
        'details': sanitize_string(details or '', 200)
    }
    ADMIN_AUDIT_LOGS.insert(0, entry)
    if len(ADMIN_AUDIT_LOGS) > MAX_ADMIN_AUDIT:
        ADMIN_AUDIT_LOGS = ADMIN_AUDIT_LOGS[:MAX_ADMIN_AUDIT]
    try:
        db_add_audit_log(
            sanitize_string(action, 120),
            sanitize_string(details or '', 200),
            get_client_ip()
        )
    except Exception:
        pass  # In-memory copy still intact

_admin_alert_in_progress = False  # Guard against infinite recursion

def notify_admin_alert(message: str, subject: str = 'Admin Alert') -> bool:
    """Best-effort admin alert via Telegram to ADMIN ONLY.
    
    Error/status messages are sent ONLY to TELEGRAM_ADMIN_CHAT_ID.
    Regular subscribers never receive error alerts.
    Uses Telegram ONLY — never calls send_email to prevent recursion loops.
    """
    global _admin_alert_in_progress
    if _admin_alert_in_progress:
        console_log("⚠️ notify_admin_alert skipped (recursion guard)", "debug")
        return False
    
    _admin_alert_in_progress = True
    try:
        if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID:
            success, _ = send_telegram(message, chat_id=TELEGRAM_ADMIN_CHAT_ID)
            if success:
                return True
            console_log("⚠️ Admin alert Telegram failed — no email fallback (prevents recursion)", "warning")
        return False
    finally:
        _admin_alert_in_progress = False

def record_visit():
    """Record a client landing page visit without a database."""
    global VISITOR_TOTAL, VISITOR_LOG
    if session.get('visitor_tracked'):
        return
    now = datetime.now(timezone.utc)
    VISITOR_TOTAL += 1
    VISITOR_LOG.append(now.isoformat())
    cutoff = now - timedelta(hours=24)
    VISITOR_LOG = [ts for ts in VISITOR_LOG if datetime.fromisoformat(ts) >= cutoff]
    session['visitor_tracked'] = True

def load_logs():
    """Load activity logs from database."""
    global ACTIVITY_LOGS
    try:
        ACTIVITY_LOGS = db_get_logs(200)
    except Exception:
        ACTIVITY_LOGS = []

def load_status():
    """Load tracker status from database."""
    try:
        return db_load_status()
    except Exception:
        return {'last_daily_summary': None, 'total_checks': 0, 'last_heartbeat': None, 'last_check_time': None}

def save_status(status):
    """Save tracker status to database."""
    try:
        db_save_status(status)
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to save status to DB: {e}", "warning")

def should_send_daily_summary():
    """Check if daily summary is due based on hour and last sent date."""
    if not CONFIG.get('daily_summary_enabled', False):
        return False

    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    status = load_status()
    last_summary = status.get('last_daily_summary')

    if last_summary == today:
        return False

    return now.hour >= CONFIG.get('daily_summary_hour', 9)

def mark_daily_summary_sent():
    """Persist that today's summary was sent."""
    status = load_status()
    status['last_daily_summary'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    save_status(status)

def load_seen_events() -> dict:
    """Load seen events from database."""
    try:
        return db_load_seen_events()
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to load seen events from DB: {e}", "warning")
        return {'event_ids': [], 'event_details': []}

def save_seen_events(seen_data: dict) -> None:
    """Save seen events to database."""
    try:
        db_save_seen_events_bulk(seen_data)
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to save events to DB: {e}", "warning")
        log_activity(f"Failed to save events: {e}", "error")

def fetch_events() -> list | None:
    """Fetch events from API with detailed diagnostics."""
    global API_DIAGNOSTICS
    
    start_time = time.time()
    API_DIAGNOSTICS['last_request_time'] = datetime.now(timezone.utc).isoformat()
    API_DIAGNOSTICS['total_api_calls'] = API_DIAGNOSTICS.get('total_api_calls', 0) + 1
    
    console_log(f"📡 Initiating API request to dubai-fleamarket.com...", "api")
    console_log(f"   └─ URL: {API_URL}", "debug")
    console_log(f"   └─ Method: GET | Timeout: 15s", "debug")
    
    try:
        response = requests.get(API_URL, timeout=15)
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        API_DIAGNOSTICS['last_response_time_ms'] = elapsed_ms
        API_DIAGNOSTICS['last_status_code'] = response.status_code
        API_DIAGNOSTICS['last_response_size'] = len(response.content)
        
        # Update average response time
        total_calls = API_DIAGNOSTICS['total_api_calls']
        prev_avg = API_DIAGNOSTICS.get('avg_response_time_ms', 0)
        API_DIAGNOSTICS['avg_response_time_ms'] = int(((prev_avg * (total_calls - 1)) + elapsed_ms) / total_calls)
        
        console_log(f"✅ API Response received", "success")
        console_log(f"   └─ Status: {response.status_code} | Time: {elapsed_ms}ms | Size: {len(response.content)} bytes", "debug")
        
        response.raise_for_status()
        
        data = response.json()
        events_count = len(data) if isinstance(data, list) else 0
        API_DIAGNOSTICS['last_events_count'] = events_count
        API_DIAGNOSTICS['last_successful_call'] = datetime.now(timezone.utc).isoformat()
        API_DIAGNOSTICS['last_error'] = None
        
        console_log(f"📦 Parsed {events_count} events from API response", "info")
        
        # Log event titles for debugging
        if events_count > 0:
            for i, event in enumerate(data[:3]):  # Show first 3 events
                title = event.get('title', {}).get('rendered', 'Unknown')[:40]
                console_log(f"   └─ Event {i+1}: {title}...", "debug")
            if events_count > 3:
                console_log(f"   └─ ... and {events_count - 3} more events", "debug")
        
        return data
        
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - start_time) * 1000)
        API_DIAGNOSTICS['failed_api_calls'] = API_DIAGNOSTICS.get('failed_api_calls', 0) + 1
        API_DIAGNOSTICS['last_error'] = 'Timeout after 15s'
        console_log(f"⏱️ API request timed out after {elapsed_ms}ms", "error")
        log_activity("API request timed out", "error")
        return None
        
    except requests.exceptions.ConnectionError as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        API_DIAGNOSTICS['failed_api_calls'] = API_DIAGNOSTICS.get('failed_api_calls', 0) + 1
        API_DIAGNOSTICS['last_error'] = 'Connection failed'
        console_log(f"🔌 Connection error: {str(e)[:50]}", "error")
        log_activity(f"Connection error: {str(e)[:30]}", "error")
        return None
        
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        API_DIAGNOSTICS['failed_api_calls'] = API_DIAGNOSTICS.get('failed_api_calls', 0) + 1
        API_DIAGNOSTICS['last_error'] = str(e)[:100]
        console_log(f"❌ API Error: {str(e)[:80]}", "error")
        log_activity(f"Failed to fetch events: {e}", "error")
        return None

def send_email_gmail(subject, body, recipient, max_retries=3):
    """Send email via Gmail SMTP (may be blocked on cloud hosts like Render)."""
    global CONFIG
    
    if not MY_EMAIL or not MY_PASSWORD:
        set_last_smtp_error("Gmail not configured")
        return False, "Gmail not configured"
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = sanitize_string(subject, 100)
    msg['From'] = MY_EMAIL
    msg['To'] = recipient
    text_part = MIMEText(body, 'plain')
    msg.attach(text_part)
    
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            console_log(f"📧 Gmail SMTP to {mask_email(recipient)} (attempt {attempt}/{max_retries})...", "debug")
            
            server = get_smtp_connection(timeout=30)
            try:
                server.starttls()
                server.login(MY_EMAIL, MY_PASSWORD)
                server.sendmail(MY_EMAIL, recipient, msg.as_string())
            finally:
                server.quit()
            
            CONFIG['emails_sent'] = CONFIG.get('emails_sent', 0) + 1
            record_stat('emails_sent', 1)
            CONFIG['last_smtp_error'] = None
            CONFIG['last_smtp_error_at'] = None
            console_log(f"✅ Email sent via Gmail to {mask_email(recipient)}", "success")
            add_to_email_history(recipient, subject, True, "Gmail SMTP")
            return True, None
            
        except (OSError, socket.error) as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"Network error: {last_error}")
            console_log(f"⚠️ Network error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(5 * attempt)
                continue
        except smtplib.SMTPException as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"SMTP error: {last_error}")
            console_log(f"⚠️ SMTP error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(3)
                continue
        except Exception as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"Gmail error: {last_error}")
            console_log(f"❌ Gmail error: {last_error}", "error")
            break
    
    return False, last_error

def send_email_direct(subject, body, recipient):
    """Direct email send without queueing using Gmail SMTP."""
    global CONFIG
    
    if not recipient or not validate_email(recipient):
        return False
    
    # Use Gmail SMTP
    if MY_EMAIL and MY_PASSWORD:
        success, error = send_email_gmail(subject, body, recipient, max_retries=1)
        if success:
            return True
        console_log(f"❌ Gmail failed: {error}", "error")
    else:
        console_log("❌ Gmail not configured", "error")
    
    return False

def send_email(subject, body, to_email=None, max_retries=3, priority='normal'):
    """Send email notification via Gmail SMTP."""
    global CONFIG
    
    recipient = to_email or TO_EMAIL
    if not recipient:
        log_activity("No recipient email configured", "error")
        return False
    
    if not validate_email(recipient):
        log_activity(f"Invalid recipient email: {recipient[:20]}...", "error")
        add_to_email_history(recipient, subject, False, 'Invalid email format')
        return False
    
    # Check if Gmail is configured
    if not MY_EMAIL or not MY_PASSWORD:
        global LAST_GMAIL_CONFIG_LOG_AT
        now = datetime.now(timezone.utc)
        should_log = True
        if LAST_GMAIL_CONFIG_LOG_AT:
            delta = (now - LAST_GMAIL_CONFIG_LOG_AT).total_seconds()
            should_log = delta > 300

        if should_log:
            log_activity("Gmail not configured", "error")
            set_last_smtp_error("Gmail not configured")
            LAST_GMAIL_CONFIG_LOG_AT = now

        add_to_email_history(recipient, subject, False, 'Gmail not configured')
        return False
    
    # Send via Gmail SMTP
    success, error = send_email_gmail(subject, body, recipient, max_retries=max_retries)
    if success:
        log_activity(f"📧 Email sent via Gmail to {recipient[:15]}...", "success")
        return True
    
    # Failed - queue for deferred retry
    console_log(f"📬 Queueing email for deferred retry: {mask_email(recipient)}", "info")
    add_to_email_queue(subject, body, recipient, priority)
    add_to_email_history(recipient, subject, False, f"Queued for retry: {error}")
    return False

# ===== TELEGRAM BOT NOTIFICATIONS =====
def get_regular_chat_ids():
    """Get list of regular (non-admin) subscriber chat IDs."""
    if not TELEGRAM_CHAT_IDS:
        return []
    all_ids = [cid.strip() for cid in TELEGRAM_CHAT_IDS.split(',') if cid.strip()]
    # Exclude admin chat ID from regular list so admin doesn't get duplicates
    if TELEGRAM_ADMIN_CHAT_ID:
        return [cid for cid in all_ids if cid != TELEGRAM_ADMIN_CHAT_ID]
    return all_ids

def get_admin_chat_id():
    """Get the admin chat ID, falling back to first regular ID if not set."""
    if TELEGRAM_ADMIN_CHAT_ID:
        return TELEGRAM_ADMIN_CHAT_ID
    # Fallback: use first regular chat ID
    if TELEGRAM_CHAT_IDS:
        first_id = TELEGRAM_CHAT_IDS.split(',')[0].strip()
        if first_id:
            return first_id
    return None

def send_telegram(message: str, chat_id: str = None) -> tuple:
    """Send message via Telegram Bot to specified chat_id(s).
    
    If chat_id is given, sends only to that ID.
    If chat_id is None, sends to ALL configured TELEGRAM_CHAT_IDS.
    """
    if not TELEGRAM_BOT_TOKEN:
        console_log("⚠️ Telegram not configured (missing bot token)", "debug")
        return False, "Telegram not configured"
    
    # Get chat IDs to send to
    if chat_id:
        chat_ids = [str(chat_id).strip()]
    elif TELEGRAM_CHAT_IDS:
        chat_ids = [cid.strip() for cid in TELEGRAM_CHAT_IDS.split(',') if cid.strip()]
    else:
        console_log("⚠️ No Telegram chat IDs configured", "debug")
        return False, "No chat IDs configured"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    success_count = 0
    last_error = None
    failed_ids = []
    
    for cid in chat_ids:
        try:
            response = requests.post(url, json={
                'chat_id': cid,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }, timeout=10)
            
            if response.status_code == 200:
                success_count += 1
                console_log(f"✅ Telegram sent to chat {cid[:10]}...", "success")
            else:
                resp_data = {}
                try:
                    resp_data = response.json()
                except Exception:
                    pass
                error_desc = resp_data.get('description', response.text[:80])
                last_error = f"HTTP {response.status_code}: {error_desc}"
                failed_ids.append(cid)
                console_log(f"⚠️ Telegram error for {cid[:10]}: {last_error}", "warning")
                
                # Log specific common errors for debugging
                if response.status_code == 400:
                    console_log(f"   └─ Possible cause: invalid chat_id or bad HTML formatting", "debug")
                elif response.status_code == 403:
                    console_log(f"   └─ Bot was blocked by user or chat not found", "debug")
                elif response.status_code == 401:
                    console_log(f"   └─ Invalid bot token", "debug")
        except requests.exceptions.Timeout:
            last_error = "Request timed out (10s)"
            failed_ids.append(cid)
            console_log(f"⏱️ Telegram timeout for {cid[:10]}...", "warning")
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {str(e)[:40]}"
            failed_ids.append(cid)
            console_log(f"🔌 Telegram connection error for {cid[:10]}...", "warning")
        except Exception as e:
            last_error = str(e)[:50]
            failed_ids.append(cid)
            console_log(f"⚠️ Telegram exception: {last_error}", "warning")
    
    if success_count > 0:
        log_activity(f"📱 Telegram sent to {success_count}/{len(chat_ids)} chat(s)", "success")
        if failed_ids:
            log_activity(f"⚠️ Telegram failed for {len(failed_ids)} chat(s)", "warning")
        return True, None
    return False, last_error

def send_telegram_new_events(events: list) -> bool:
    """Send new event notification via Telegram to ALL subscribers + admin.
    
    New events are NON-ERROR messages, so they go to everyone.
    Admin also gets them so they don't miss events.
    Respects telegram_notifications_enabled toggle.
    """
    if not CONFIG.get('telegram_notifications_enabled', True):
        console_log("📵 Telegram notifications disabled, skipping event alert", "debug")
        return False
    
    if not TELEGRAM_BOT_TOKEN:
        return False
    
    # Need at least one chat ID (admin or regular)
    if not TELEGRAM_CHAT_IDS and not TELEGRAM_ADMIN_CHAT_ID:
        console_log("⚠️ No Telegram chat IDs configured for event alerts", "debug")
        return False
    
    now = datetime.now(timezone.utc)
    
    message = f"""🚨 <b>NEW EVENT ALERT!</b> 🚨

🎯 <b>{len(events)} New Dubai Flea Market Event{'s' if len(events) > 1 else ''} Found!</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
    
    for i, event in enumerate(events, 1):
        message += f"\n📍 <b>Event {i}:</b>\n"
        message += f"   📌 {event['title']}\n"
        message += f"   🔗 <a href=\"{event['link']}\">View Event →</a>\n"
        message += f"   📅 Posted: {event['date_posted']}\n"
        if i < len(events):
            message += "\n   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
    
    message += f"""\n━━━━━━━━━━━━━━━━━━━━━━
⏰ Detected: {now.strftime('%I:%M %p UTC')}
📱 Tap the link to view details!

🤖 <i>Dubai Flea Market Tracker</i>"""
    
    console_log(f"📱 Sending Telegram notification for {len(events)} event(s)", "info")
    
    # Send to ALL chat IDs (env-configured + DB subscribers + admin)
    # Build complete list: all regular IDs + admin + DB subscribers (deduplicated)
    all_ids = set()
    if TELEGRAM_CHAT_IDS:
        all_ids.update(cid.strip() for cid in TELEGRAM_CHAT_IDS.split(',') if cid.strip())
    if TELEGRAM_ADMIN_CHAT_ID:
        all_ids.add(TELEGRAM_ADMIN_CHAT_ID)
    # Add active DB subscribers
    try:
        db_sub_ids = db_get_active_subscriber_ids()
        all_ids.update(db_sub_ids)
    except Exception:
        pass  # DB unavailable, use env IDs only
    
    success_count = 0
    last_error = None
    for cid in all_ids:
        ok, err = send_telegram(message, chat_id=cid)
        if ok:
            success_count += 1
        else:
            last_error = err
    
    success = success_count > 0
    error = None if success else last_error
    console_log(f"📱 Event notification sent to {success_count}/{len(all_ids)} chat(s)", "success" if success else "warning")
    if not success:
        log_activity(f"📱 Telegram failed for new events: {error}", "warning")
        notify_admin_alert(f"Telegram failed for new event alerts: {error}", "Telegram Alert Failure")
    return success

def send_telegram_heartbeat() -> bool:
    """Send heartbeat via Telegram to ADMIN ONLY (not all subscribers).
    
    Heartbeats are admin-only status messages. Regular subscribers
    should NOT receive these.
    Respects telegram_notifications_enabled toggle.
    """
    if not CONFIG.get('telegram_notifications_enabled', True):
        console_log("📵 Telegram notifications disabled, skipping heartbeat", "debug")
        return False
    
    if not TELEGRAM_BOT_TOKEN:
        return False
    
    # Use admin chat ID only, falling back to first chat ID via helper
    admin_chat_id = get_admin_chat_id()
    if not admin_chat_id:
        return False
    
    if not CONFIG['heartbeat_enabled']:
        return False
    
    now = datetime.now(timezone.utc)
    seen_data = load_seen_events()
    uptime_start = parse_iso_timestamp(CONFIG['uptime_start'])
    uptime_delta = now - uptime_start
    uptime_hours = int(uptime_delta.total_seconds() // 3600)
    uptime_mins = int((uptime_delta.total_seconds() % 3600) // 60)
    
    message = f"""💓 <b>HEARTBEAT - Bot Status</b>
━━━━━━━━━━━━━━━━━━━━━━

✅ <b>Status:</b> RUNNING & HEALTHY

📊 <b>Statistics:</b>
   • Check #{CONFIG['total_checks']}
   • Events tracked: {len(seen_data.get('event_ids', []))}
   • New events found: {CONFIG['total_new_events']}
   • Notifications sent: {CONFIG['emails_sent']}

⏰ <b>Timing:</b>
   • Current: {now.strftime('%I:%M %p UTC')}
   • Check interval: Every {CONFIG['check_interval_minutes']} min
   • Uptime: {uptime_hours}h {uptime_mins}m

━━━━━━━━━━━━━━━━━━━━━━
🟢 <i>All systems operational</i>
🤖 <i>Dubai Flea Market Tracker</i>
👤 <i>Admin-only message</i>"""
    
    # Send to admin only
    success, error = send_telegram(message, chat_id=admin_chat_id)
    if not success:
        log_activity(f"📱 Telegram heartbeat failed: {error}", "warning")
        notify_admin_alert(f"Telegram heartbeat failed: {error}", "Telegram Heartbeat Failure")
    return success

def send_new_event_email(events):
    """Send new event notification to enabled recipients. Respects notification toggles."""
    # Send via Telegram first (instant, free, reliable) — if enabled
    telegram_success = send_telegram_new_events(events)
    
    # Check if email notifications are enabled
    if not CONFIG.get('email_notifications_enabled', True):
        console_log("📵 Email notifications disabled, skipping email send", "debug")
        if not telegram_success:
            console_log("⚠️ Both email and Telegram disabled — new events NOT notified!", "warning")
        return
    
    # Also send via email
    subject = f"🎉 {len(events)} New Dubai Flea Market Event(s)!"
    body = f"🎯 {len(events)} new event(s) have been posted!\n\n"
    
    for event in events:
        body += f"📍 {event['title']}\n"
        body += f"🔗 {event['link']}\n"
        body += f"📅 Posted: {event['date_posted']}\n"
        body += "-" * 50 + "\n\n"
    
    body += "\n🤖 Sent automatically by Dubai Flea Market Tracker"
    
    console_log(f"📧 Sending new event notification to {len(get_recipients())} recipient(s)", "info")
    fail_count = 0
    for email in get_recipients():
        if not send_email(subject, body, email, priority='high'):
            fail_count += 1

    if not telegram_success:
        notify_admin_alert("Telegram failed for new events. Email fallback attempted.", "Failover Notice")
    if fail_count > 0:
        notify_admin_alert(f"Email failed for {fail_count} recipient(s) during new event alert.", "Email Delivery Issues")

def send_heartbeat():
    """Send heartbeat status email. Respects email_notifications_enabled toggle."""
    if not CONFIG['heartbeat_enabled']:
        return False
    
    # Send via Telegram first (instant, free, reliable) — if enabled
    send_telegram_heartbeat()
    
    # Check if email notifications are enabled
    if not CONFIG.get('email_notifications_enabled', True):
        console_log("📵 Email notifications disabled, skipping heartbeat email", "debug")
        return False
    
    console_log("💓 Sending heartbeat email...", "info")
    now = datetime.now(timezone.utc)
    seen_data = load_seen_events()
    
    subject = f"💓 Bot Running OK - Check #{CONFIG['total_checks']} | {now.strftime('%H:%M')} UTC"
    
    body = f"""
{'=' * 60}
💓 DUBAI FLEA MARKET BOT - HEARTBEAT STATUS
{'=' * 60}

✅ STATUS: Bot is RUNNING and monitoring for new events!

📊 CURRENT STATS:
   • Check Number: #{CONFIG['total_checks']}
   • Current Time (UTC): {now.strftime('%B %d, %Y at %I:%M:%S %p')}
   • Events Already Seen: {len(seen_data.get('event_ids', []))}
   • Total New Events Found: {CONFIG['total_new_events']}
   • Emails Sent: {CONFIG['emails_sent']}

⏰ TIMING INFO:
   • Check Interval: Every {CONFIG['check_interval_minutes']} minutes
   • Heartbeat Interval: Every {CONFIG['heartbeat_hours']} hours
   • Uptime Since: {CONFIG['uptime_start']}

🎯 The bot is actively running 24/7!

🔗 Manual Check: https://dubai-fleamarket.com

{'=' * 60}
🤖 Automated Heartbeat from Dubai Flea Market Tracker
{'=' * 60}
"""
    
    result = send_email(subject, body, CONFIG['heartbeat_email'])
    if result:
        console_log("✅ Heartbeat email sent successfully", "success")
    else:
        console_log("❌ Failed to send heartbeat email", "error")
        notify_admin_alert("Heartbeat email failed. Telegram heartbeat may still be delivered.", "Heartbeat Email Failure")
    return result

def send_telegram_daily_summary():
    """Send daily summary via Telegram to ADMIN ONLY.
    
    Daily summaries are admin-only status reports. Regular subscribers
    should NOT receive these.
    Respects telegram_notifications_enabled toggle.
    """
    if not CONFIG.get('telegram_notifications_enabled', True):
        console_log("📵 Telegram notifications disabled, skipping daily summary", "debug")
        return False
    
    if not TELEGRAM_BOT_TOKEN:
        return False
    
    # Use admin chat ID only, falling back to first chat ID via helper
    admin_chat_id = get_admin_chat_id()
    if not admin_chat_id:
        return False
    
    now = datetime.now(timezone.utc)
    seen_data = load_seen_events()
    events = fetch_events()
    
    event_count = len(events) if events else 0
    seen_count = len(seen_data.get('event_ids', []))
    
    # Calculate uptime
    uptime_start = parse_iso_timestamp(CONFIG['uptime_start'])
    uptime_delta = now - uptime_start
    uptime_days = uptime_delta.days
    uptime_hours = int((uptime_delta.total_seconds() % 86400) // 3600)
    
    message = f"""📊 <b>DAILY SUMMARY REPORT</b>
━━━━━━━━━━━━━━━━━━━━━━
📅 {now.strftime('%A, %B %d, %Y')}

📈 <b>Today's Statistics:</b>
   • Events on website: {event_count}
   • Total events tracked: {seen_count}
   • Checks performed: {CONFIG['total_checks']}
   • New events detected: {CONFIG['total_new_events']}
   • Notifications sent: {CONFIG['emails_sent']}

⏱️ <b>Bot Performance:</b>
   • Status: ✅ Running normally
   • Uptime: {uptime_days}d {uptime_hours}h
   • Check interval: Every {CONFIG['check_interval_minutes']} min
   • Heartbeat: Every {CONFIG['heartbeat_hours']}h

━━━━━━━━━━━━━━━━━━━━━━
🔗 <a href="https://dubai-fleamarket.com">View All Events →</a>

🤖 <i>Dubai Flea Market Tracker</i>
👤 <i>Admin-only daily summary</i>"""
    
    # Send to admin only
    success, error = send_telegram(message, chat_id=admin_chat_id)
    if not success:
        log_activity(f"📱 Telegram daily summary failed: {error}", "warning")
        notify_admin_alert(f"Telegram daily summary failed: {error}", "Telegram Summary Failure")
    return success

def send_daily_summary_email():
    """Send daily summary email."""
    # Send via Telegram first (instant, free, reliable)
    telegram_success = send_telegram_daily_summary()
    
    console_log("📊 Generating daily summary...", "info")
    now = datetime.now(timezone.utc)
    seen_data = load_seen_events()
    events = fetch_events()
    
    subject = f"📊 Dubai Flea Market Daily Summary - {now.strftime('%B %d, %Y')}"
    
    event_count = len(events) if events else 0
    seen_count = len(seen_data.get('event_ids', []))
    
    body = f"""
{'=' * 60}
📊 DAILY SUMMARY - {now.strftime('%A, %B %d, %Y')}
{'=' * 60}

📈 STATISTICS:
   • Total events on website: {event_count}
   • Events already tracked: {seen_count}
   • Total checks performed: {CONFIG['total_checks']}
   • New events found today: {CONFIG['total_new_events']}
   • Emails sent: {CONFIG['emails_sent']}

💡 The tracker is running normally!
   You'll receive an instant notification when new events are posted.

🔗 Check manually: https://dubai-fleamarket.com

{'=' * 60}
🤖 Sent by Dubai Flea Market Tracker
{'=' * 60}
"""
    
    recipients = get_recipients()
    success_count = 0
    for email in recipients:
        if send_email(subject, body, email):
            success_count += 1

    if success_count > 0:
        CONFIG['last_daily_summary_sent_at'] = datetime.now(timezone.utc).isoformat()
        CONFIG['last_daily_summary_recipient_count'] = success_count

    if not telegram_success:
        notify_admin_alert("Telegram daily summary failed. Email summary attempted.", "Failover Notice")
    if success_count == 0:
        notify_admin_alert("Daily summary email failed for all recipients.", "Daily Summary Failure")

    return success_count > 0

def check_for_events() -> None:
    """Main event checking logic with detailed console logging."""
    console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
    console_log("🔍 STARTING EVENT CHECK CYCLE", "info")
    console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
    
    log_activity("🔍 Starting event check...")
    CONFIG['last_check'] = datetime.now(timezone.utc).isoformat()
    CONFIG['total_checks'] += 1
    
    # Record check statistic
    record_stat('checks', 1)
    console_log(f"📊 Check #{CONFIG['total_checks']} initiated", "info")
    console_log(f"   └─ Interval: Every {CONFIG['check_interval_minutes']} minutes", "debug")
    
    # Load existing seen events
    console_log("📂 Loading seen events database...", "info")
    seen_data = load_seen_events()
    seen_ids = seen_data.get('event_ids', [])
    console_log(f"   └─ Found {len(seen_ids)} previously seen events in database", "debug")
    
    # Fetch events from API
    events = fetch_events()
    if events is None:
        console_log("❌ Event check failed - API returned no data", "error")
        log_activity("Failed to fetch events from API", "error")
        return
    
    log_activity(f"📡 Fetched {len(events)} events from API")
    
    # Compare events
    console_log("🔄 Comparing events with database...", "info")
    new_events = []
    for event in events:
        event_id = event.get('id')
        if not isinstance(event_id, int) or event_id <= 0:
            console_log(f"   ⚠️ Skipping invalid event ID: {event_id}", "warning")
            continue
        
        if event_id not in seen_ids:
            link = event.get('link', '')
            if not validate_url(link):
                console_log(f"   ⚠️ Skipping event {event_id} - invalid URL", "warning")
                continue
            
            title = sanitize_string(event.get('title', {}).get('rendered', 'Unknown'), 200)
            console_log(f"   🆕 NEW EVENT DETECTED: {title[:50]}...", "success")
            
            event_info = {
                'id': event_id,
                'title': title,
                'date_posted': sanitize_string(event.get('date', 'Unknown'), 50),
                'link': link
            }
            new_events.append(event_info)
            
            seen_data['event_ids'].append(event_id)
            seen_data.setdefault('event_details', []).append({
                **event_info,
                'first_seen': datetime.now(timezone.utc).strftime('%b %d, %Y at %I:%M %p')
            })
    
    # Record check history
    check_result = {
        'check_number': CONFIG['total_checks'],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'time_display': datetime.now(timezone.utc).strftime('%I:%M %p'),
        'date_display': datetime.now(timezone.utc).strftime('%b %d'),
        'events_fetched': len(events) if events else 0,
        'new_events_found': len(new_events),
        'status': 'success' if events else 'error',
        'new_event_titles': [e.get('title', 'Unknown')[:50] for e in new_events[:3]]  # First 3 titles
    }
    
    if new_events:
        CONFIG['total_new_events'] += len(new_events)
        # Record new events statistic
        record_stat('new_events', len(new_events))
        console_log(f"🎉 FOUND {len(new_events)} NEW EVENT(S)!", "success")
        log_activity(f"🆕 Found {len(new_events)} NEW event(s)!", "success")
        
        console_log("📧 Sending email notifications...", "info")
        send_new_event_email(new_events)
        
        console_log("💾 Saving updated database...", "info")
        save_seen_events(seen_data)
        console_log("   └─ Database saved successfully", "debug")
        check_result['emails_sent'] = True
    else:
        console_log("✨ No new events found - all events already seen", "info")
        log_activity("✨ No new events found")
        check_result['emails_sent'] = False
    
    # Add to check history
    CHECK_HISTORY.insert(0, check_result)
    if len(CHECK_HISTORY) > MAX_CHECK_HISTORY:
        CHECK_HISTORY[:] = CHECK_HISTORY[:MAX_CHECK_HISTORY]
    
    status = load_status()
    status['total_checks'] = CONFIG['total_checks']
    status['last_check_time'] = CONFIG['last_check']
    save_status(status)
    
    next_check_time = datetime.now(timezone.utc) + timedelta(minutes=CONFIG['check_interval_minutes'])
    CONFIG['next_check'] = next_check_time.isoformat()
    console_log(f"⏰ Next check scheduled: {next_check_time.strftime('%H:%M:%S UTC')}", "info")
    console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")

def should_send_heartbeat() -> bool:
    """Check if heartbeat is due."""
    if not CONFIG['heartbeat_enabled']:
        return False
    
    status = load_status()
    last_heartbeat = status.get('last_heartbeat')
    
    if not last_heartbeat:
        return True
    
    try:
        last_time = parse_iso_timestamp(last_heartbeat)
        now = datetime.now(timezone.utc)
        hours_since = (now - last_time).total_seconds() / 3600
        return hours_since >= CONFIG['heartbeat_hours']
    except Exception:
        return True

def background_checker():
    """Background thread that runs the event checker with self-healing."""
    log_activity("🚀 Background checker started", "success")
    console_log("🚀 Background checker thread initialized", "success")
    
    # Load email queue on startup
    load_email_queue()
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    check_interval_seconds = CONFIG['check_interval_minutes'] * 60
    last_queue_check = datetime.now(timezone.utc)
    queue_check_interval = timedelta(minutes=15)  # Process queue every 15 minutes
    last_error_notify_at = None  # Throttle error notifications
    ERROR_NOTIFY_COOLDOWN = 300  # 5 minutes between error telegram notifications
    
    while not stop_checker.is_set():
        if CONFIG['tracker_enabled']:
            try:
                check_for_events()
                consecutive_errors = 0  # Reset error counter on success
                
                if should_send_heartbeat():
                    log_activity("💓 Sending scheduled heartbeat...")
                    console_log("💓 Sending scheduled heartbeat email...", "info")
                    if send_heartbeat():
                        status = load_status()
                        status['last_heartbeat'] = datetime.now(timezone.utc).isoformat()
                        save_status(status)
                        CONFIG['next_heartbeat'] = (datetime.now(timezone.utc) + timedelta(hours=CONFIG['heartbeat_hours'])).isoformat()
                        log_activity("💓 Heartbeat sent!", "success")
                        console_log("✅ Heartbeat email sent successfully", "success")

                if should_send_daily_summary():
                    log_activity("📊 Sending scheduled daily summary...")
                    console_log("📊 Sending scheduled daily summary...", "info")
                    if send_daily_summary_email():
                        mark_daily_summary_sent()
                        log_activity("📊 Daily summary sent", "success")
                        console_log("✅ Daily summary email sent", "success")
                    else:
                        console_log("❌ Failed to send daily summary", "error")
                
                # Process email queue periodically
                now = datetime.now(timezone.utc)
                if now - last_queue_check >= queue_check_interval:
                    if EMAIL_QUEUE:
                        console_log("📬 Checking email retry queue...", "debug")
                        process_email_queue()
                    last_queue_check = now
                
            except RecursionError:
                consecutive_errors += 1
                log_activity(f"RecursionError in checker ({consecutive_errors}/{max_consecutive_errors})", "error")
                console_log(f"❌ RecursionError caught — breaking recursion cycle", "error")
                # Do NOT call notify_admin_alert here to avoid making it worse
                # Just log and continue
                if consecutive_errors >= max_consecutive_errors:
                    console_log("🔄 Too many RecursionErrors, entering recovery mode (5 min cooldown)", "warning")
                    stop_checker.wait(timeout=300)
                    consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)[:50]
                import traceback
                full_trace = traceback.format_exc()
                log_activity(f"Error in checker ({consecutive_errors}/{max_consecutive_errors}): {error_msg}", "error")
                console_log(f"⚠️ Checker error ({consecutive_errors}/{max_consecutive_errors}): {error_msg}", "error")
                console_log(f"   └─ Exception type: {type(e).__name__}", "debug")
                console_log(f"   └─ Full trace logged to console", "debug")
                print(f"[FULL TRACEBACK]\n{full_trace}")
                
                # Throttled error notification — max once per 5 minutes
                now_ts = datetime.now(timezone.utc)
                should_notify = True
                if last_error_notify_at:
                    elapsed = (now_ts - last_error_notify_at).total_seconds()
                    should_notify = elapsed >= ERROR_NOTIFY_COOLDOWN
                
                if should_notify:
                    notify_admin_alert(
                        f"⚠️ Checker Error ({consecutive_errors}/{max_consecutive_errors})\n"
                        f"Type: {type(e).__name__}\n"
                        f"Error: {error_msg}",
                        "Checker Error Alert"
                    )
                    last_error_notify_at = now_ts
                else:
                    console_log("⚠️ Error notification throttled (cooldown active)", "debug")
                
                # If too many consecutive errors, wait longer before retry
                if consecutive_errors >= max_consecutive_errors:
                    console_log("🔄 Too many errors, entering recovery mode (5 min cooldown)", "warning")
                    console_log(f"   └─ Error threshold reached: {max_consecutive_errors} consecutive failures", "debug")
                    log_activity("⚠️ Entering recovery mode due to repeated errors", "warning")
                    stop_checker.wait(timeout=300)  # Wait 5 minutes
                    consecutive_errors = 0  # Reset after cooldown
                    console_log("🔄 Recovery cooldown complete, resuming normal operation", "info")
        
        # Wait for next check with countdown logging
        wait_start = datetime.now(timezone.utc)
        elapsed = 0
        logged_milestones = set()  # Track which milestones we've logged
        
        while elapsed < check_interval_seconds and not stop_checker.is_set():
            remaining = check_interval_seconds - elapsed
            
            # Log countdown at certain intervals (check ranges to avoid missing exact values)
            milestones = [
                (600, 601, "10 minutes"),
                (300, 301, "5 minutes"),
                (120, 121, "2 minutes"),
                (60, 61, "1 minute"),
                (30, 31, "30 seconds"),
                (10, 11, "10 seconds"),
            ]
            
            for low, high, label in milestones:
                if low <= remaining < high and low not in logged_milestones:
                    console_log(f"⏳ Next check in {label}...", "debug")
                    logged_milestones.add(low)
            
            stop_checker.wait(timeout=1)
            elapsed = int((datetime.now(timezone.utc) - wait_start).total_seconds())
    
    log_activity("Background checker stopped", "warning")
    console_log("⏹️ Background checker stopped", "warning")

# ===== ROUTES =====
@app.route('/')
def index():
    """Client-facing landing page."""
    now = datetime.now(timezone.utc)
    record_visit()
    return render_template('index.html', current_year=now.year)

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


@app.route('/login', methods=['GET', 'POST'])
@rate_limit
def admin_login():
    """Admin login page with CSRF protection."""
    if request.method == 'GET':
        next_url = safe_next_url(request.args.get('next'))
        csrf_token = _generate_csrf_token()
        return render_template('admin_login.html', error=None, next=next_url, csrf_token=csrf_token)

    # Validate CSRF token
    if not _validate_csrf_token():
        console_log(f"🚫 CSRF validation failed from {get_client_ip()[:15]}", "warning")
        next_url = safe_next_url(request.form.get('next'))
        csrf_token = _generate_csrf_token()
        return render_template('admin_login.html', error='Invalid request. Please try again.', next=next_url, csrf_token=csrf_token)

    password = request.form.get('password', '')
    next_url = safe_next_url(request.form.get('next'))

    if verify_password(password):
        session.permanent = True
        session['admin_logged_in'] = True
        session['admin_logged_in_at'] = datetime.now(timezone.utc).isoformat()
        log_admin_action('admin_login', f"{request.method} {request.path}")
        return redirect(next_url)

    csrf_token = _generate_csrf_token()
    return render_template('admin_login.html', error='Invalid password', next=next_url, csrf_token=csrf_token)

@app.route('/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
@app.route('/dashboard')
@rate_limit
@require_admin
def dashboard():
    """Admin dashboard page."""
    status = load_status()
    seen_data = load_seen_events()
    tracked_events_table = seen_data.get('event_details', [])[-50:][::-1]
    now = datetime.now(timezone.utc)
    
    next_check_seconds = 0
    if CONFIG['next_check']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_check'])
            next_check_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass
    
    next_heartbeat_seconds = 0
    if CONFIG['next_heartbeat']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_heartbeat'])
            next_heartbeat_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass

    recent_events = []
    event_details = seen_data.get('event_details', [])
    if isinstance(event_details, list) and event_details:
        for event in event_details[-6:][::-1]:
            if not isinstance(event, dict):
                continue
            recent_events.append({
                'id': event.get('id') or event.get('event_id'),
                'title': event.get('title') or event.get('name'),
                'first_seen': event.get('first_seen') or event.get('timestamp'),
                'link': event.get('link') or event.get('url')
            })
    
    uptime_str = "Just started"
    try:
        start = parse_iso_timestamp(CONFIG['uptime_start'])
        diff = now - start
        days = diff.days
        hours = diff.seconds // 3600
        mins = (diff.seconds % 3600) // 60
        if days > 0:
            uptime_str = f"{days}d {hours}h {mins}m"
        elif hours > 0:
            uptime_str = f"{hours}h {mins}m"
        else:
            uptime_str = f"{mins}m"
    except Exception:
        pass
    
    # Get recipient status
    all_recipients = get_all_recipients()
    recipient_status = load_recipient_status()
    
    # Get theme settings
    theme_settings = load_theme_settings()
    console_log(f"🔧 Dashboard: Theme settings loaded: {theme_settings.get('theme', 'dark')}", "debug")
    
    # Get live events from API for display
    # NOTE: Use CACHED events only to prevent dashboard hanging if API is slow
    live_events = []
    try:
        console_log("📡 Dashboard: Loading live events from last API response...", "debug")
        # Check if we have cached events from the background checker
        seen_data_for_live = load_seen_events()
        cached_events = seen_data_for_live.get('event_details', [])
        if cached_events:
            live_events = [{
                'id': e.get('id', 0),
                'title': sanitize_string(str(e.get('title', 'Unknown')), 200),
                'date_posted': sanitize_string(str(e.get('first_seen', 'Unknown')), 50),
                'link': e.get('link', '#')
            } for e in cached_events[-15:]]  # Get last 15 events
            console_log(f"✅ Dashboard: Loaded {len(live_events)} cached events for display", "debug")
        else:
            console_log("⚠️ Dashboard: No cached events available", "debug")
    except Exception as e:
        console_log(f"❌ Dashboard: Error loading live events: {str(e)[:50]}", "error")
        live_events = []
    
    console_log(f"🖥️ Dashboard page loaded - Theme: {theme_settings.get('theme', 'dark')}, Events: {len(live_events)}", "debug")
    
    return render_template('dashboard.html',
        config=CONFIG,
        status=status,
        seen_count=len(seen_data.get('event_ids', [])),
        recent_events=seen_data.get('event_details', [])[-10:][::-1],
        tracked_events_table=tracked_events_table,
        live_events=live_events,
        logs=ACTIVITY_LOGS[:50],
        all_recipients=all_recipients,
        recipient_status=recipient_status,
        mask_email=mask_email,
        format_timestamp=format_timestamp,
        format_hour_offset=format_hour_offset,
        email_queue=EMAIL_QUEUE,
        next_check_seconds=next_check_seconds,
        next_heartbeat_seconds=next_heartbeat_seconds,
        uptime_str=uptime_str,
        current_time=now.strftime('%B %d, %Y at %I:%M %p UTC'),
        email_history=load_email_history()[-20:][::-1],
        theme=theme_settings.get('theme', 'dark'),
        notifications_enabled=theme_settings.get('notifications_enabled', False),
        check_history=CHECK_HISTORY[:12]  # Show last 12 checks on initial load
    )

@app.route('/health')
def health():
    """Health check endpoint for UptimeRobot - no rate limit."""
    # Check if background checker is running
    checker_alive = checker_thread is not None and checker_thread.is_alive()
    
    # If checker died, the watchdog should restart it soon
    if not checker_alive:
        console_log("⚠️ Health check: Background checker not running!", "warning")
    
    return jsonify({
        'status': 'healthy',
        'tracker_enabled': CONFIG['tracker_enabled'],
        'total_checks': CONFIG['total_checks'],
        'uptime_start': CONFIG['uptime_start'],
        'checker_running': checker_alive,
        'next_check': CONFIG['next_check'],
        'next_heartbeat': CONFIG['next_heartbeat']
    })

@app.route('/api/health')
def api_health():
    """Health check endpoint for uptime monitoring."""
    return jsonify({
        'status': 'healthy',
        'uptime_start': CONFIG['uptime_start'],
        'total_checks': CONFIG['total_checks'],
        'tracker_enabled': CONFIG['tracker_enabled'],
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/api/status')
@rate_limit
@require_admin
def api_status():
    """API endpoint for status data with calculated timer values."""
    status = load_status()
    seen_data = load_seen_events()
    now = datetime.now(timezone.utc)
    
    # Calculate remaining seconds for timers
    next_check_seconds = 0
    if CONFIG['next_check']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_check'])
            next_check_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass
    
    next_heartbeat_seconds = 0
    if CONFIG['next_heartbeat']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_heartbeat'])
            next_heartbeat_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass
    
    # Build recent events from seen_data
    recent_events = []
    event_details = seen_data.get('event_details', [])
    if isinstance(event_details, list) and event_details:
        for event in event_details[-6:][::-1]:
            if not isinstance(event, dict):
                continue
            recent_events.append({
                'id': event.get('id') or event.get('event_id'),
                'title': event.get('title') or event.get('name'),
                'first_seen': event.get('first_seen') or event.get('timestamp'),
                'link': event.get('link') or event.get('url')
            })
    
    return jsonify({
        'config': CONFIG,
        'status': status,
        'seen_count': len(seen_data.get('event_ids', [])),
        'logs': ACTIVITY_LOGS[:20],
        'next_check_seconds': next_check_seconds,
        'next_heartbeat_seconds': next_heartbeat_seconds,
        'email_queue_count': len(EMAIL_QUEUE),
        'latest_event': get_latest_event_summary(),
        'recent_events': recent_events,
        'visitor_stats': {
            'total': VISITOR_TOTAL,
            'last_24h': len(VISITOR_LOG)
        }
    })

@app.route('/api/console')
@rate_limit
@require_admin
def api_console():
    """API endpoint for system console logs."""
    return jsonify({
        'console': SYSTEM_CONSOLE[:100],
        'diagnostics': {
            **API_DIAGNOSTICS,
            'email_provider': {
                'primary': 'Telegram' if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS) else 'Gmail SMTP',
                'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
                'telegram_chat_count': len([c for c in TELEGRAM_CHAT_IDS.split(',') if c.strip()]) if TELEGRAM_CHAT_IDS else 0,
                'telegram_admin_configured': bool(TELEGRAM_ADMIN_CHAT_ID),
                'gmail_configured': bool(MY_EMAIL and MY_PASSWORD),
                'gmail_from_email': MY_EMAIL if MY_EMAIL else None,
                'ipv4_forced': SMTP_USE_IPV4
            },
            'email_queue': build_email_queue_payload(limit=10),
            'last_smtp_error': CONFIG.get('last_smtp_error'),
            'last_smtp_error_at': CONFIG.get('last_smtp_error_at')
        },
        'check_history': CHECK_HISTORY[:20]  # Include recent check history
    })

@app.route('/api/check-history')
@rate_limit
@require_admin
def api_check_history():
    """API endpoint for check history cards."""
    return jsonify({
        'history': CHECK_HISTORY[:50],
        'total_checks': CONFIG['total_checks']
    })

@app.route('/api/diagnostics')
@rate_limit
@require_admin
def api_diagnostics():
    """API endpoint for detailed API diagnostics."""
    seen_data = load_seen_events()
    
    return jsonify({
        'api': API_DIAGNOSTICS,
        'system': {
            'uptime_start': CONFIG['uptime_start'],
            'tracker_enabled': CONFIG['tracker_enabled'],
            'check_interval_minutes': CONFIG['check_interval_minutes'],
            'heartbeat_enabled': CONFIG['heartbeat_enabled'],
            'heartbeat_hours': CONFIG['heartbeat_hours'],
            'total_checks': CONFIG['total_checks'],
            'total_new_events': CONFIG['total_new_events'],
            'emails_sent': CONFIG['emails_sent'],
            'total_events_tracked': len(seen_data.get('event_ids', [])),
            'recipients_count': len(get_all_recipients()),
            'enabled_recipients': len(get_recipients())
        },
        'email_provider': {
            'primary': 'Telegram' if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS) else 'Gmail SMTP',
            'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
            'telegram_chat_count': len([c for c in TELEGRAM_CHAT_IDS.split(',') if c.strip()]) if TELEGRAM_CHAT_IDS else 0,
            'telegram_admin_configured': bool(TELEGRAM_ADMIN_CHAT_ID),
            'gmail_configured': bool(MY_EMAIL and MY_PASSWORD),
            'gmail_from_email': MY_EMAIL if MY_EMAIL else None,
            'ipv4_forced': SMTP_USE_IPV4
        },
        'email_queue': {
            'pending_count': len(EMAIL_QUEUE),
            'high_priority': len([e for e in EMAIL_QUEUE if e.get('priority') == 'high']),
            'items': EMAIL_QUEUE[:10]  # Show first 10 for debugging
        },
        'console_entries': len(SYSTEM_CONSOLE),
        'activity_log_entries': len(ACTIVITY_LOGS)
    })

@app.route('/api/test-api', methods=['POST'])
@rate_limit
@require_password
def test_api_connection():
    """Test API connection - requires password."""
    console_log("🧪 MANUAL API TEST INITIATED", "info")
    log_activity("🧪 Manual API test triggered", "info")
    
    events = fetch_events()
    
    if events is not None:
        console_log(f"✅ API test successful - {len(events)} events returned", "success")
        return jsonify({
            'success': True,
            'events_count': len(events),
            'response_time_ms': API_DIAGNOSTICS.get('last_response_time_ms', 0),
            'status_code': API_DIAGNOSTICS.get('last_status_code', 0)
        })
    else:
        console_log("❌ API test failed", "error")
        return jsonify({
            'success': False,
            'error': API_DIAGNOSTICS.get('last_error', 'Unknown error')
        })

@app.route('/api/clear-console', methods=['POST'])
@rate_limit
@require_password
def clear_console():
    """Clear system console logs - requires password."""
    global SYSTEM_CONSOLE
    SYSTEM_CONSOLE = []
    console_log("🗑️ Console cleared by admin", "info")
    return jsonify({'success': True})

@app.route('/api/diagnose-smtp', methods=['POST'])
@rate_limit
@require_password
def diagnose_smtp():
    """Comprehensive Gmail SMTP diagnostic - tests each step of the connection."""
    console_log("🔧 SMTP DIAGNOSTIC: Starting comprehensive test...", "warning")
    
    results = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'steps': [],
        'overall_status': 'unknown',
        'recommendations': []
    }
    
    def add_step(name, status, details, duration_ms=None):
        step = {'name': name, 'status': status, 'details': details}
        if duration_ms is not None:
            step['duration_ms'] = duration_ms
        results['steps'].append(step)
        console_log(f"  {'✅' if status == 'pass' else '❌'} {name}: {details}", "success" if status == 'pass' else "error")
    
    # Step 1: Check credentials are configured
    console_log("🔧 Step 1: Checking credentials...", "info")
    if not MY_EMAIL:
        add_step("Credentials - Email", "fail", "MY_EMAIL environment variable not set")
        results['recommendations'].append("Set MY_EMAIL environment variable in Render dashboard")
    else:
        add_step("Credentials - Email", "pass", f"Email configured: {mask_email(MY_EMAIL)}")
    
    if not MY_PASSWORD:
        add_step("Credentials - Password", "fail", "MY_PASSWORD environment variable not set")
        results['recommendations'].append("Set MY_PASSWORD environment variable (use App Password, not regular password)")
    else:
        add_step("Credentials - Password", "pass", f"Password configured ({len(MY_PASSWORD)} characters)")
        # Check if it looks like an app password (16 chars, lowercase)
        if len(MY_PASSWORD) == 16 and MY_PASSWORD.islower() and ' ' not in MY_PASSWORD:
            add_step("Credentials - App Password Format", "pass", "Password looks like a valid App Password format")
        elif len(MY_PASSWORD) < 16:
            add_step("Credentials - App Password Format", "warning", f"Password is only {len(MY_PASSWORD)} chars - may not be an App Password")
            results['recommendations'].append("Gmail requires App Password (16 chars). Go to: Google Account → Security → 2-Step Verification → App Passwords")
    
    if not MY_EMAIL or not MY_PASSWORD:
        results['overall_status'] = 'fail'
        results['recommendations'].append("Cannot proceed without credentials")
        return jsonify(results)
    
    # Step 2: DNS resolution test
    console_log("🔧 Step 2: Testing DNS resolution...", "info")
    try:
        start = time.time()
        ip = socket.gethostbyname(SMTP_SERVER)
        duration = int((time.time() - start) * 1000)
        add_step("DNS Resolution (IPv4)", "pass", f"{SMTP_SERVER} → {ip}", duration)
        
        # Also check IPv6
        try:
            ipv6_info = socket.getaddrinfo(SMTP_SERVER, SMTP_PORT, socket.AF_INET6)
            if ipv6_info:
                add_step("IPv6 Available", "warning", f"IPv6 exists but may cause issues - IPv4 forcing is {'ON' if SMTP_USE_IPV4 else 'OFF'}")
                if not SMTP_USE_IPV4:
                    results['recommendations'].append("IPv6 is available but may cause 'Network unreachable' errors. Set SMTP_USE_IPV4=true in environment")
        except Exception:
            add_step("IPv6 Available", "pass", "No IPv6 (good - avoids network issues)")
            
    except socket.gaierror as e:
        add_step("DNS Resolution", "fail", f"Cannot resolve {SMTP_SERVER}: {str(e)}")
        results['recommendations'].append("DNS resolution failed - check network/firewall settings")
        results['overall_status'] = 'fail'
        return jsonify(results)
    
    # Step 3: TCP connection test (port 587)
    console_log("🔧 Step 3: Testing TCP connection to port 587...", "info")
    try:
        import socket
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((SMTP_SERVER, SMTP_PORT))
        sock.close()
        duration = int((time.time() - start) * 1000)
        
        if result == 0:
            add_step("TCP Connection", "pass", f"Port {SMTP_PORT} is reachable", duration)
        else:
            add_step("TCP Connection", "fail", f"Port {SMTP_PORT} connection failed (error code: {result})")
            results['recommendations'].append("Port 587 blocked - Render or cloud provider may block outbound SMTP")
            results['overall_status'] = 'fail'
            return jsonify(results)
    except Exception as e:
        add_step("TCP Connection", "fail", f"Connection error: {str(e)[:100]}")
        results['overall_status'] = 'fail'
        return jsonify(results)
    
    # Step 4: SMTP handshake and STARTTLS
    console_log("🔧 Step 4: Testing SMTP handshake...", "info")
    try:
        start = time.time()
        server = get_smtp_connection(timeout=30)
        duration = int((time.time() - start) * 1000)
        add_step("SMTP Handshake", "pass", f"Connected to SMTP server (IPv4 forced: {SMTP_USE_IPV4})", duration)
        
        # Get server banner
        banner = server.ehlo_resp.decode() if server.ehlo_resp else "No banner"
        add_step("SMTP Banner", "pass", f"Server responded: {banner[:100]}...")
        
    except smtplib.SMTPConnectError as e:
        add_step("SMTP Handshake", "fail", f"SMTP connect error: {str(e)[:100]}")
        results['overall_status'] = 'fail'
        return jsonify(results)
    except Exception as e:
        add_step("SMTP Handshake", "fail", f"Error: {str(e)[:100]}")
        results['overall_status'] = 'fail'
        return jsonify(results)
    
    # Step 5: STARTTLS
    console_log("🔧 Step 5: Testing STARTTLS encryption...", "info")
    try:
        start = time.time()
        server.starttls()
        duration = int((time.time() - start) * 1000)
        add_step("STARTTLS", "pass", "TLS encryption established", duration)
    except smtplib.SMTPException as e:
        add_step("STARTTLS", "fail", f"TLS error: {str(e)[:100]}")
        server.quit()
        results['overall_status'] = 'fail'
        return jsonify(results)
    
    # Step 6: Authentication
    console_log("🔧 Step 6: Testing authentication...", "info")
    try:
        start = time.time()
        server.login(MY_EMAIL, MY_PASSWORD)
        duration = int((time.time() - start) * 1000)
        add_step("Authentication", "pass", f"Logged in as {mask_email(MY_EMAIL)}", duration)
    except smtplib.SMTPAuthenticationError as e:
        error_msg = str(e)
        add_step("Authentication", "fail", f"Auth failed: {error_msg[:150]}")
        
        if "BadCredentials" in error_msg or "535" in error_msg:
            results['recommendations'].append("❌ WRONG PASSWORD: You must use an App Password, not your Google account password")
            results['recommendations'].append("Steps: 1) Enable 2-Step Verification at myaccount.google.com/security")
            results['recommendations'].append("Steps: 2) Go to myaccount.google.com/apppasswords")
            results['recommendations'].append("Steps: 3) Create App Password for 'Mail' on 'Other (Custom name)'")
            results['recommendations'].append("Steps: 4) Copy the 16-character password (no spaces) to MY_PASSWORD env var")
        elif "TooManyLoginAttempts" in error_msg:
            results['recommendations'].append("Too many login attempts - wait 24 hours or reset at accounts.google.com/DisplayUnlockCaptcha")
        
        server.quit()
        results['overall_status'] = 'fail'
        return jsonify(results)
    except Exception as e:
        add_step("Authentication", "fail", f"Error: {str(e)[:100]}")
        server.quit()
        results['overall_status'] = 'fail'
        return jsonify(results)
    
    # Step 7: Send test email (optional - only if we passed everything)
    console_log("🔧 Step 7: Testing email send...", "info")
    test_recipient = TO_EMAIL or MY_EMAIL
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "🔧 SMTP Diagnostic Test"
        msg['From'] = MY_EMAIL
        msg['To'] = test_recipient
        msg.attach(MIMEText(f"SMTP diagnostic passed at {datetime.now(timezone.utc).isoformat()}", 'plain'))
        
        start = time.time()
        server.sendmail(MY_EMAIL, test_recipient, msg.as_string())
        duration = int((time.time() - start) * 1000)
        add_step("Send Test Email", "pass", f"Email sent to {mask_email(test_recipient)}", duration)
        results['overall_status'] = 'pass'
        
    except smtplib.SMTPRecipientsRefused as e:
        add_step("Send Test Email", "fail", f"Recipient refused: {str(e)[:100]}")
        results['overall_status'] = 'partial'
    except smtplib.SMTPSenderRefused as e:
        add_step("Send Test Email", "fail", f"Sender refused: {str(e)[:100]}")
        results['recommendations'].append("Gmail may have flagged your account for suspicious activity")
        results['overall_status'] = 'partial'
    except Exception as e:
        add_step("Send Test Email", "fail", f"Send error: {str(e)[:100]}")
        results['overall_status'] = 'partial'
    
    try:
        server.quit()
    except Exception:
        pass
    
    # Summary
    passed = len([s for s in results['steps'] if s['status'] == 'pass'])
    total = len(results['steps'])
    console_log(f"🔧 SMTP DIAGNOSTIC COMPLETE: {passed}/{total} steps passed", "success" if passed == total else "warning")
    
    return jsonify(results)

@app.route('/api/toggle/<feature>', methods=['POST'])
@rate_limit
@require_password
def toggle_feature(feature):
    """Toggle a feature on/off - requires password."""
    enabled = False
    if feature == 'tracker':
        CONFIG['tracker_enabled'] = not CONFIG['tracker_enabled']
        enabled = CONFIG['tracker_enabled']
        log_activity(f"🔄 Tracker {'enabled' if enabled else 'disabled'}", "success" if enabled else "warning")
    elif feature == 'heartbeat':
        CONFIG['heartbeat_enabled'] = not CONFIG['heartbeat_enabled']
        enabled = CONFIG['heartbeat_enabled']
        log_activity(f"🔄 Heartbeat {'enabled' if enabled else 'disabled'}", "success" if enabled else "warning")
    elif feature == 'daily_summary':
        CONFIG['daily_summary_enabled'] = not CONFIG['daily_summary_enabled']
        enabled = CONFIG['daily_summary_enabled']
        log_activity(f"🔄 Daily summary {'enabled' if enabled else 'disabled'}", "success" if enabled else "warning")
    elif feature == 'email_notifications':
        CONFIG['email_notifications_enabled'] = not CONFIG['email_notifications_enabled']
        enabled = CONFIG['email_notifications_enabled']
        try:
            db_set_notification_setting('email_notifications_enabled', enabled)
        except Exception:
            pass
        log_activity(f"🔄 Email notifications {'enabled' if enabled else 'disabled'}", "success" if enabled else "warning")
    elif feature == 'telegram_notifications':
        CONFIG['telegram_notifications_enabled'] = not CONFIG['telegram_notifications_enabled']
        enabled = CONFIG['telegram_notifications_enabled']
        try:
            db_set_notification_setting('telegram_notifications_enabled', enabled)
        except Exception:
            pass
        log_activity(f"🔄 Telegram notifications {'enabled' if enabled else 'disabled'}", "success" if enabled else "warning")
    
    return jsonify({'success': True, 'enabled': enabled, 'config': CONFIG})

@app.route('/api/settings', methods=['POST'])
@rate_limit
@require_password
def update_settings():
    """Update multiple settings at once - requires password."""
    console_log("⚙️ SETTINGS: update_settings endpoint called", "info")
    
    try:
        data = request.get_json() or {}
        console_log(f"⚙️ SETTINGS: Received data keys: {list(data.keys())}", "debug")
    except Exception as e:
        console_log(f"❌ SETTINGS: Error parsing JSON: {str(e)[:50]}", "error")
        return jsonify({'error': 'Invalid JSON data'}), 400
    
    changes = []
    
    # Heartbeat setting
    if 'heartbeat_enabled' in data:
        new_val = bool(data['heartbeat_enabled'])
        if CONFIG['heartbeat_enabled'] != new_val:
            CONFIG['heartbeat_enabled'] = new_val
            changes.append(f"Heartbeat {'enabled' if new_val else 'disabled'}")
            console_log(f"💓 Heartbeat monitoring {'enabled' if new_val else 'disabled'}", "success" if new_val else "warning")
    
    # Daily summary setting
    if 'daily_summary_enabled' in data:
        new_val = bool(data['daily_summary_enabled'])
        if CONFIG['daily_summary_enabled'] != new_val:
            CONFIG['daily_summary_enabled'] = new_val
            changes.append(f"Daily summary {'enabled' if new_val else 'disabled'}")
            console_log(f"📅 Daily summary {'enabled' if new_val else 'disabled'}", "success" if new_val else "warning")
    
    # Tracker setting
    if 'tracker_enabled' in data:
        new_val = bool(data['tracker_enabled'])
        if CONFIG['tracker_enabled'] != new_val:
            CONFIG['tracker_enabled'] = new_val
            changes.append(f"Tracker {'enabled' if new_val else 'disabled'}")
            console_log(f"🔄 Event tracker {'enabled' if new_val else 'disabled'}", "success" if new_val else "warning")
    
    # Email notifications toggle
    if 'email_notifications_enabled' in data:
        new_val = bool(data['email_notifications_enabled'])
        if CONFIG.get('email_notifications_enabled', True) != new_val:
            CONFIG['email_notifications_enabled'] = new_val
            try:
                db_set_notification_setting('email_notifications_enabled', new_val)
            except Exception:
                pass
            changes.append(f"Email notifications {'enabled' if new_val else 'disabled'}")
            console_log(f"📧 Email notifications {'enabled' if new_val else 'disabled'}", "success" if new_val else "warning")
    
    # Telegram notifications toggle
    if 'telegram_notifications_enabled' in data:
        new_val = bool(data['telegram_notifications_enabled'])
        if CONFIG.get('telegram_notifications_enabled', True) != new_val:
            CONFIG['telegram_notifications_enabled'] = new_val
            try:
                db_set_notification_setting('telegram_notifications_enabled', new_val)
            except Exception:
                pass
            changes.append(f"Telegram notifications {'enabled' if new_val else 'disabled'}")
            console_log(f"📡 Telegram notifications {'enabled' if new_val else 'disabled'}", "success" if new_val else "warning")
    
    if changes:
        log_activity(f"⚙️ Settings updated: {', '.join(changes)}", "success")
        return jsonify({'success': True, 'message': f"Updated: {', '.join(changes)}", 'config': CONFIG})
    else:
        return jsonify({'success': True, 'message': 'No changes made', 'config': CONFIG})

@app.route('/api/toggle-recipient/<email>', methods=['POST'])
@rate_limit
@require_password
def toggle_recipient(email):
    """Toggle recipient enabled/disabled status - requires password."""
    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email'}), 400
    
    if email not in get_all_recipients():
        return jsonify({'success': False, 'message': 'Email not in recipient list'}), 400
    
    status = load_recipient_status()
    status[email]['enabled'] = not status[email]['enabled']
    save_recipient_status(status)
    
    state = 'enabled' if status[email]['enabled'] else 'disabled'
    log_activity(f"📧 Recipient {mask_email(email)} {state}", "success")
    
    return jsonify({
        'success': True,
        'message': f'Recipient {state}',
        'enabled': status[email]['enabled']
    })

# ===== TELEGRAM SUBSCRIBER MANAGEMENT API =====

@app.route('/api/telegram-subscribers', methods=['GET'])
@rate_limit
@require_password
def get_telegram_subscribers():
    """Get list of Telegram subscribers with masked IDs."""
    try:
        subscribers = db_get_subscribers()
        masked = []
        for sub in subscribers:
            masked.append({
                'chat_id_masked': mask_chat_id(sub['chat_id']),
                'chat_id_short': sub['chat_id'][-4:],  # last 4 digits for identification
                'label': sub.get('display_name', ''),
                'active': sub.get('is_active', True),
                'added_at': sub.get('added_at', ''),
                'last_notified': sub.get('last_notified_at', '')
            })
        
        # Also include env-configured chat IDs
        env_ids = []
        env_chat_list = [cid.strip() for cid in TELEGRAM_CHAT_IDS.split(',') if cid.strip()] if TELEGRAM_CHAT_IDS else []
        for cid in env_chat_list:
            env_ids.append({
                'chat_id_masked': mask_chat_id(cid),
                'chat_id_short': cid[-4:] if len(cid) >= 4 else cid,
                'source': 'env',
                'label': 'Admin' if cid == TELEGRAM_ADMIN_CHAT_ID else 'Env Config'
            })
        
        return jsonify({
            'success': True,
            'db_subscribers': masked,
            'env_subscribers': env_ids,
            'total_db': len(subscribers),
            'total_env': len(env_ids)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]}), 500

@app.route('/api/telegram-subscribers/add', methods=['POST'])
@rate_limit
@require_password
def add_telegram_subscriber():
    """Add a new Telegram subscriber. Requires admin."""
    try:
        data = request.get_json() or {}
        chat_id = str(data.get('chat_id', '')).strip()
        label = str(data.get('label', '')).strip()[:50]
        
        if not chat_id:
            return jsonify({'success': False, 'error': 'chat_id is required'}), 400
        
        if not validate_chat_id(chat_id):
            return jsonify({'success': False, 'error': 'Invalid chat_id format'}), 400
        
        success = db_add_subscriber(chat_id, label)
        if success:
            log_activity(f"📱 Telegram subscriber added: {mask_chat_id(chat_id)}", "success")
            log_admin_action("Add Telegram subscriber", f"Chat ID: {mask_chat_id(chat_id)}, Label: {label}")
            return jsonify({'success': True, 'message': f'Subscriber {mask_chat_id(chat_id)} added'})
        else:
            return jsonify({'success': False, 'error': 'Subscriber already exists'}), 409
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]}), 500

@app.route('/api/telegram-subscribers/remove', methods=['POST'])
@rate_limit
@require_password
def remove_telegram_subscriber():
    """Remove a Telegram subscriber by chat_id."""
    try:
        data = request.get_json() or {}
        chat_id = str(data.get('chat_id', '')).strip()
        
        if not chat_id:
            return jsonify({'success': False, 'error': 'chat_id is required'}), 400
        
        success = db_remove_subscriber(chat_id)
        if success:
            log_activity(f"📱 Telegram subscriber removed: {mask_chat_id(chat_id)}", "warning")
            log_admin_action("Remove Telegram subscriber", f"Chat ID: {mask_chat_id(chat_id)}")
            return jsonify({'success': True, 'message': 'Subscriber removed'})
        else:
            return jsonify({'success': False, 'error': 'Subscriber not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]}), 500

@app.route('/api/telegram-subscribers/toggle', methods=['POST'])
@rate_limit
@require_password
def toggle_telegram_subscriber():
    """Toggle a subscriber active/inactive."""
    try:
        data = request.get_json() or {}
        chat_id = str(data.get('chat_id', '')).strip()
        
        if not chat_id:
            return jsonify({'success': False, 'error': 'chat_id is required'}), 400
        
        new_state = db_toggle_subscriber(chat_id)
        if new_state is not None:
            state_str = 'activated' if new_state else 'deactivated'
            log_activity(f"📱 Telegram subscriber {state_str}: {mask_chat_id(chat_id)}", "success")
            return jsonify({'success': True, 'active': new_state, 'message': f'Subscriber {state_str}'})
        else:
            return jsonify({'success': False, 'error': 'Subscriber not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]}), 500

@app.route('/api/check-now', methods=['POST'])
@rate_limit
@require_password
def check_now():
    """Trigger an immediate check - requires password."""
    log_activity("⚡ Manual check triggered", "info")
    thread = threading.Thread(target=check_for_events)
    thread.start()
    return jsonify({'success': True, 'message': 'Check triggered'})

@app.route('/api/send-heartbeat', methods=['POST'])
@rate_limit
@require_password
def send_heartbeat_now():
    """Send heartbeat immediately - requires password."""
    log_activity("💓 Manual heartbeat triggered", "info")
    
    if send_heartbeat():
        status = load_status()
        status['last_heartbeat'] = datetime.now(timezone.utc).isoformat()
        save_status(status)
        return jsonify({'success': True, 'message': 'Heartbeat sent successfully!'})
    
    return jsonify({'success': False, 'message': 'Failed to send heartbeat'})

@app.route('/api/send-daily-summary', methods=['POST'])
@rate_limit
@require_password
def send_daily_summary_now():
    """Send daily summary immediately - requires password."""
    log_activity("📊 Manual daily summary triggered", "info")
    
    if send_daily_summary_email():
        mark_daily_summary_sent()
        return jsonify({'success': True, 'message': 'Daily summary sent!'})
    
    return jsonify({'success': False, 'message': 'Failed to send summary'})

@app.route('/api/test-email', methods=['POST'])
@rate_limit
@require_password
def test_email():
    """Send test email to a specific recipient - requires password."""
    data = request.get_json() or {}
    email = data.get('email', '')
    
    if not email or not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email provided'})
    
    if email not in get_all_recipients():
        return jsonify({'success': False, 'message': 'Email not in recipient list'})
    
    log_activity(f"🧪 Testing email to {mask_email(email)}", "info")
    
    now = datetime.now(timezone.utc)
    subject = f"🧪 Test Email - Dubai Flea Market Tracker"
    body = f"""
{'=' * 60}
🧪 TEST EMAIL
{'=' * 60}

✅ This is a test email from Dubai Flea Market Tracker!

If you received this, your email configuration is working.

📊 SYSTEM INFO:
   • Sent at: {now.strftime('%B %d, %Y at %I:%M %p UTC')}

🎯 You will receive instant notifications when new events are posted!

{'=' * 60}
🤖 Dubai Flea Market Tracker
{'=' * 60}
"""
    
    if send_email(subject, body, email):
        return jsonify({'success': True, 'message': f'Test email sent'})
    
    return jsonify({'success': False, 'message': 'Failed to send test email'})

@app.route('/api/test-all-emails', methods=['POST'])
@rate_limit
@require_password
def test_all_emails():
    """Send test email to all recipients - requires password."""
    recipients = get_recipients()
    if not recipients:
        return jsonify({'success': False, 'message': 'No recipients configured'})
    
    log_activity(f"🧪 Testing all {len(recipients)} emails", "info")
    
    success_count = 0
    now = datetime.now(timezone.utc)
    
    for email in recipients:
        subject = f"🧪 Test Email - Dubai Flea Market Tracker"
        body = f"""
{'=' * 60}
🧪 TEST EMAIL - Bulk Test
{'=' * 60}

✅ This is a test email from Dubai Flea Market Tracker!

📧 Testing all {len(recipients)} configured recipients.

📊 Sent at: {now.strftime('%B %d, %Y at %I:%M %p UTC')}

{'=' * 60}
🤖 Dubai Flea Market Tracker
{'=' * 60}
"""
        if send_email(subject, body, email):
            success_count += 1
    
    return jsonify({
        'success': success_count > 0,
        'message': f'Sent to {success_count}/{len(recipients)} recipients'
    })

@app.route('/api/live-events')
@rate_limit
@require_admin
def live_events():
    """Fetch current live events from website."""
    events = fetch_events()
    if events is None:
        return jsonify({'success': False, 'events': [], 'message': 'Failed to fetch'})
    
    event_list = []
    for event in events[:10]:
        link = event.get('link', '')
        if validate_url(link):
            event_list.append({
                'id': event.get('id'),
                'title': sanitize_string(event.get('title', {}).get('rendered', 'Unknown'), 100),
                'date': sanitize_string(event.get('date', 'Unknown'), 20)[:10],
                'link': link
            })
    
    return jsonify({'success': True, 'events': event_list})

@app.route('/api/email-history')
@rate_limit
@require_admin
def get_email_history():
    """Get email history."""
    history = load_email_history()
    return jsonify({'success': True, 'history': history[-50:][::-1]})

@app.route('/api/reveal-email', methods=['POST'])
@rate_limit
@require_password
def reveal_email():
    """Reveal full email address - requires password."""
    data = request.get_json() or {}
    masked = data.get('masked', '')
    
    all_recipients = get_all_recipients()
    for email in all_recipients:
        if mask_email(email) == masked:
            return jsonify({'success': True, 'email': email})
    
    return jsonify({'success': False, 'message': 'Email not found'})

@app.route('/api/logs')
@rate_limit
@require_admin
def get_logs():
    """Get activity logs."""
    return jsonify({'logs': ACTIVITY_LOGS})

@app.route('/api/clear-logs', methods=['POST'])
@rate_limit
@require_password
def clear_logs():
    """Clear activity logs - requires password."""
    global ACTIVITY_LOGS
    ACTIVITY_LOGS = []
    try:
        db_clear_logs()
    except Exception as e:
        console_log(f"⚠️ Failed to clear DB logs: {e}", "warning")
    log_activity("🗑️ Logs cleared", "info")
    console_log("🗑️ Activity logs cleared by admin", "info")
    return jsonify({'success': True})

# ===== NEW API ENDPOINTS =====

@app.route('/api/stats')
@rate_limit
@require_admin
def get_stats():
    """Get event statistics for charting."""
    console_log("📊 Stats API requested", "debug")
    load_event_stats()
    
    # Prepare data for charts (last 7 days and last 24 hours)
    now = datetime.now(timezone.utc)
    
    daily_labels = []
    daily_checks = []
    daily_events = []
    daily_emails = []
    
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).strftime('%Y-%m-%d')
        day_display = (now - timedelta(days=i)).strftime('%b %d')
        daily_labels.append(day_display)
        stats = EVENT_STATS['daily'].get(day, {'checks': 0, 'new_events': 0, 'emails_sent': 0})
        daily_checks.append(stats.get('checks', 0))
        daily_events.append(stats.get('new_events', 0))
        daily_emails.append(stats.get('emails_sent', 0))
    
    hourly_labels = []
    hourly_checks = []
    hourly_events = []
    
    for i in range(23, -1, -1):
        hour = (now - timedelta(hours=i)).strftime('%Y-%m-%dT%H')
        hour_display = (now - timedelta(hours=i)).strftime('%H:00')
        hourly_labels.append(hour_display)
        stats = EVENT_STATS['hourly'].get(hour, {'checks': 0, 'new_events': 0})
        hourly_checks.append(stats.get('checks', 0))
        hourly_events.append(stats.get('new_events', 0))
    
    return jsonify({
        'daily': {
            'labels': daily_labels,
            'checks': daily_checks,
            'new_events': daily_events,
            'emails_sent': daily_emails
        },
        'hourly': {
            'labels': hourly_labels,
            'checks': hourly_checks,
            'new_events': hourly_events
        },
        'totals': {
            'checks': CONFIG['total_checks'],
            'new_events': CONFIG['total_new_events'],
            'emails_sent': CONFIG['emails_sent']
        }
    })

@app.route('/api/export-logs')
@rate_limit
@require_admin
def export_logs():
    """Export activity logs as JSON or CSV."""
    format_type = request.args.get('format', 'json')
    console_log(f"📤 Exporting logs as {format_type.upper()}", "info")
    
    if format_type == 'csv':
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Timestamp', 'Level', 'Message'])
        
        for log in ACTIVITY_LOGS:
            writer.writerow([
                log.get('timestamp_formatted', log.get('timestamp', '')),
                log.get('level', 'info'),
                log.get('message', '')
            ])
        
        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=activity_logs.csv'}
        )
        return response
    else:
        from flask import Response
        return Response(
            json.dumps(ACTIVITY_LOGS, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment;filename=activity_logs.json'}
        )

@app.route('/api/export-events')
@rate_limit
@require_admin
def export_events():
    """Export tracked events as JSON or CSV."""
    format_type = request.args.get('format', 'json')
    console_log(f"📤 Exporting events as {format_type.upper()}", "info")
    
    seen_data = load_seen_events()
    events = seen_data.get('event_details', [])
    
    if format_type == 'csv':
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Title', 'Date Posted', 'Link', 'First Seen'])
        
        for event in events:
            writer.writerow([
                event.get('id', ''),
                event.get('title', ''),
                event.get('date_posted', ''),
                event.get('link', ''),
                event.get('first_seen', '')
            ])
        
        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=tracked_events.csv'}
        )
        return response
    else:
        from flask import Response
        return Response(
            json.dumps(events, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment;filename=tracked_events.json'}
        )

@app.route('/api/test-single-email', methods=['POST'])
@rate_limit
@require_password
def test_single_email():
    """Send test email to a single recipient - requires password."""
    data = request.get_json() or {}
    email = data.get('email', '')
    
    console_log(f"📧 Test single email requested for: {mask_email(email)}", "info")
    
    if not email:
        return jsonify({'success': False, 'message': 'Email required'}), 400
    
    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email format'}), 400
    
    # Check if email is in recipients list
    if email not in get_all_recipients():
        return jsonify({'success': False, 'message': 'Email not in recipient list'}), 400
    
    subject = "🧪 Test Email - Dubai Flea Market Tracker"
    body = f"""
🧪 TEST EMAIL

This is a test email from the Dubai Flea Market Event Tracker.

📊 System Status:
━━━━━━━━━━━━━━━━━
✅ Total Checks: {CONFIG['total_checks']}
✅ New Events Found: {CONFIG['total_new_events']}
✅ Emails Sent: {CONFIG['emails_sent']}

If you received this email, your notification setup is working correctly!

🤖 Sent automatically by Dubai Flea Market Tracker
📅 {datetime.now(timezone.utc).strftime('%b %d, %Y at %I:%M %p UTC')}
"""
    
    if send_email(subject, body, email):
        log_activity(f"📧 Test email sent to {mask_email(email)}", "success")
        return jsonify({'success': True, 'message': f'Test email sent to {mask_email(email)}'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send test email'}), 500

@app.route('/api/test-new-event', methods=['POST'])
@rate_limit
@require_password
def test_new_event():
    """Remove latest event from DB and trigger a real 'new event' notification.
    This tests the full notification flow by:
    1. Removing the most recent event from the database
    2. Immediately triggering an API check
    3. The event will be detected as 'new' and notifications sent to all recipients
    """
    console_log("⚡ TEST NEW EVENT: Starting real notification test...", "warning")
    log_activity("⚡ Test new event notification triggered", "warning")
    
    # Load seen events
    seen_data = load_seen_events()
    event_ids = seen_data.get('event_ids', [])
    event_details = seen_data.get('event_details', [])
    
    if not event_ids or not event_details:
        console_log("❌ TEST NEW EVENT: No events in database to remove", "error")
        return jsonify({'success': False, 'message': 'No events in database to test with'}), 400
    
    # Get the latest event (most recently added)
    latest_event = event_details[-1] if event_details else None
    latest_id = event_ids[-1] if event_ids else None
    
    if not latest_id or not latest_event:
        return jsonify({'success': False, 'message': 'Could not find latest event'}), 400
    
    # Log what we're removing
    console_log(f"📝 TEST NEW EVENT: Removing event ID {latest_id}: {latest_event.get('title', 'Unknown')[:50]}...", "info")
    
    # Remove the latest event
    seen_data['event_ids'] = event_ids[:-1]  # Remove last ID
    seen_data['event_details'] = event_details[:-1]  # Remove last detail
    
    # Save the modified database
    save_seen_events(seen_data)
    console_log(f"✅ TEST NEW EVENT: Event removed from database ({len(event_ids)-1} events remaining)", "success")
    
    # Now trigger an immediate event check
    console_log("🔄 TEST NEW EVENT: Triggering immediate API check...", "info")
    
    try:
        # This will detect the removed event as 'new' and send notifications
        check_for_events()
        console_log("✅ TEST NEW EVENT: Check completed - notification should have been sent", "success")
        log_activity("✅ Test new event notification completed", "success")
        
        return jsonify({
            'success': True, 
            'message': f'Removed event "{latest_event.get("title", "Unknown")[:40]}..." and triggered notification check. Check your email!'
        })
    except Exception as e:
        console_log(f"❌ TEST NEW EVENT: Error during check: {str(e)[:80]}", "error")
        return jsonify({'success': False, 'message': f'Check failed: {str(e)[:100]}'}), 500

# ===== TELEGRAM TEST ENDPOINTS =====
@app.route('/api/test-telegram', methods=['POST'])
@rate_limit
@require_password
def test_telegram():
    """Send a test message via Telegram - requires password."""
    data = request.get_json() or {}
    test_type = data.get('type', 'simple')  # simple, heartbeat, daily, events
    
    console_log(f"📱 Telegram test requested: {test_type}", "info")
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({'success': False, 'message': 'Telegram bot token not configured'}), 400
    
    if not TELEGRAM_CHAT_IDS:
        return jsonify({'success': False, 'message': 'Telegram chat IDs not configured'}), 400
    
    if test_type == 'heartbeat':
        # Test heartbeat format
        success = send_telegram_heartbeat()
        msg_type = "Heartbeat"
    elif test_type == 'daily':
        # Test daily summary format
        success = send_telegram_daily_summary()
        msg_type = "Daily Summary"
    elif test_type == 'events':
        # Test new events format with fake event
        fake_events = [{
            'title': '🧪 Test Event - Weekend Market at JBR',
            'link': 'https://dubai-fleamarket.com/test',
            'date_posted': datetime.now(timezone.utc).strftime('%B %d, %Y')
        }]
        success = send_telegram_new_events(fake_events)
        msg_type = "New Event"
    else:
        # Simple test message
        now = datetime.now(timezone.utc)
        message = f"""🧪 <b>Test Message</b>

✅ Telegram is working!

📊 System Status:
• Checks: {CONFIG['total_checks']}
• New Events: {CONFIG['total_new_events']}
• Uptime: {CONFIG['uptime_start'][:10]}

📅 {now.strftime('%B %d, %Y at %I:%M %p UTC')}

🤖 Dubai Flea Market Tracker"""
        success, error = send_telegram(message)
        msg_type = "Test"
    
    if success:
        log_activity(f"📱 Telegram {msg_type} test sent successfully", "success")
        return jsonify({'success': True, 'message': f'{msg_type} message sent to Telegram!'})
    else:
        return jsonify({'success': False, 'message': 'Failed to send Telegram message'}), 500

@app.route('/api/telegram-status')
@rate_limit
@require_admin
def telegram_status():
    """Get Telegram configuration status."""
    return jsonify({
        'configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
        'bot_token_set': bool(TELEGRAM_BOT_TOKEN),
        'chat_ids_set': bool(TELEGRAM_CHAT_IDS),
        'chat_count': len([c for c in TELEGRAM_CHAT_IDS.split(',') if c.strip()]) if TELEGRAM_CHAT_IDS else 0
    })

@app.route('/api/test-telegram-real', methods=['POST'])
@rate_limit
@require_password
def test_telegram_real():
    """Fetch REAL events from API and send via Telegram - tests full flow!"""
    console_log("📱 TEST REAL TELEGRAM: Starting real API test...", "info")
    
    try:
        # Check Telegram configuration
        if not TELEGRAM_BOT_TOKEN:
            console_log("❌ TEST REAL TELEGRAM: Bot token not configured", "error")
            return jsonify({'success': False, 'message': 'Telegram bot token not configured'}), 400
        
        # Use admin chat ID only for tests, or fall back to first chat ID
        admin_chat_id = TELEGRAM_ADMIN_CHAT_ID
        if not admin_chat_id and TELEGRAM_CHAT_IDS:
            admin_chat_id = TELEGRAM_CHAT_IDS.split(',')[0].strip()
        
        if not admin_chat_id:
            console_log("❌ TEST REAL TELEGRAM: No chat ID configured", "error")
            return jsonify({'success': False, 'message': 'No Telegram chat ID configured'}), 400
        
        console_log(f"📱 TEST REAL TELEGRAM: Using chat ID: {admin_chat_id[:6]}...", "debug")
        
        # Fetch real events from the Dubai Flea Market API
        console_log("📱 TEST REAL TELEGRAM: Fetching events from API...", "debug")
        events = fetch_events()
        
        if not events:
            console_log("❌ TEST REAL TELEGRAM: API returned no events", "error")
            return jsonify({'success': False, 'message': 'Could not fetch events from API - check API connection'}), 500
        
        console_log(f"📱 TEST REAL TELEGRAM: Fetched {len(events)} events", "debug")
        
        # Take the first 3 events for the test
        test_events = events[:3]
        
        now = datetime.now(timezone.utc)
        message = f"""🧪 <b>REAL API TEST - Live Events</b>
━━━━━━━━━━━━━━━━━━━━━━
📅 {now.strftime('%B %d, %Y at %I:%M %p UTC')}

🌐 <b>Fetched from:</b> dubai-fleamarket.com
📊 <b>Events on site:</b> {len(events)} total

━━━━━━━━━━━━━━━━━━━━━━
<b>📍 Sample Events (First {len(test_events)}):</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
        
        for i, event in enumerate(test_events, 1):
            title = event.get('title', 'Untitled')[:60]
            link = event.get('link', '#')
            date = event.get('date_posted', 'Unknown')
            message += f"""
{i}. <b>{title}</b>
   📅 Posted: {date}
   🔗 <a href="{link}">View Event →</a>
"""
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━
✅ <b>API Connection:</b> Working!
✅ <b>Telegram Delivery:</b> Success!
🤖 <i>Dubai Flea Market Tracker</i>
👤 <i>Admin test message</i>"""
        
        console_log("📱 TEST REAL TELEGRAM: Sending message...", "debug")
        
        # Send to admin only
        success, error = send_telegram(message, chat_id=admin_chat_id)
        
        if success:
            console_log(f"✅ TEST REAL TELEGRAM: Sent {len(test_events)} events successfully", "success")
            log_activity(f"📱 Real API Telegram test sent ({len(test_events)} events)", "success")
            return jsonify({
                'success': True, 
                'message': f'Real events sent via Telegram! ({len(events)} events on site, sent {len(test_events)} samples)'
            })
        else:
            console_log(f"❌ TEST REAL TELEGRAM: Send failed - {error}", "error")
            return jsonify({'success': False, 'message': f'Failed to send: {error}'}), 500
            
    except Exception as e:
        console_log(f"❌ TEST REAL TELEGRAM: Exception - {str(e)[:100]}", "error")
        return jsonify({'success': False, 'message': f'Error: {str(e)[:100]}'}), 500

@app.route('/api/retry-queue', methods=['POST'])
@rate_limit
@require_admin
def retry_email_queue():
    """Manually process the email retry queue."""
    before = len(EMAIL_QUEUE)
    process_email_queue()
    after = len(EMAIL_QUEUE)
    log_admin_action('retry_email_queue', f"processed={before - after}, remaining={after}")
    return jsonify({'success': True, 'processed': before - after, 'remaining': after})

@app.route('/api/email-queue', methods=['GET'])
@rate_limit
@require_admin
def get_email_queue():
    """Get full email queue for admin UI."""
    return jsonify({'success': True, **build_email_queue_payload()})

@app.route('/api/email-queue/clear', methods=['POST'])
@rate_limit
@require_admin
def clear_email_queue():
    """Clear all queued emails."""
    global EMAIL_QUEUE
    cleared = len(EMAIL_QUEUE)
    EMAIL_QUEUE = []
    try:
        db_clear_queue()
    except Exception as e:
        console_log(f"⚠️ Failed to clear DB queue: {e}", "warning")
    log_admin_action('email_queue_clear', f"cleared={cleared}")
    return jsonify({'success': True, 'cleared': cleared})

@app.route('/api/email-queue/delete/<item_id>', methods=['POST'])
@rate_limit
@require_admin
def delete_email_queue_item(item_id):
    """Delete a single queued email by id."""
    global EMAIL_QUEUE
    removed = False
    for item in EMAIL_QUEUE[:]:
        if item.get('id') == item_id:
            EMAIL_QUEUE.remove(item)
            removed = True
            break
    if removed:
        save_email_queue()
        log_admin_action('email_queue_delete', f"id={item_id}")
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Item not found'}), 404

@app.route('/api/email-queue/retry/<item_id>', methods=['POST'])
@rate_limit
@require_admin
def retry_email_queue_item(item_id):
    """Retry a single queued email by id."""
    global EMAIL_QUEUE
    target = None
    for item in EMAIL_QUEUE:
        if item.get('id') == item_id:
            target = item
            break
    if not target:
        return jsonify({'success': False, 'message': 'Item not found'}), 404

    success, error = send_email_gmail(target.get('subject', ''), target.get('body', ''), target.get('recipient', ''), max_retries=1)
    if success:
        EMAIL_QUEUE.remove(target)
        save_email_queue()
        log_admin_action('email_queue_retry', f"id={item_id} success")
        return jsonify({'success': True, 'message': 'Email sent'})

    target['attempts'] = target.get('attempts', 0) + 1
    target['last_error'] = error or 'Send failed'
    target['next_retry'] = (datetime.now(timezone.utc) + timedelta(minutes=EMAIL_RETRY_INTERVALS[-1])).isoformat()
    save_email_queue()
    log_admin_action('email_queue_retry', f"id={item_id} failed")
    return jsonify({'success': False, 'message': 'Send failed'})

@app.route('/api/theme', methods=['GET', 'POST'])
@rate_limit
def handle_theme():
    """Get or set theme settings."""
    if request.method == 'GET':
        settings = load_theme_settings()
        return jsonify(settings)
    else:
        data = request.get_json() or {}
        settings = load_theme_settings()
        
        if 'theme' in data:
            settings['theme'] = data['theme']
            console_log(f"🎨 Theme changed to: {data['theme']}", "info")
        
        if 'notifications_enabled' in data:
            settings['notifications_enabled'] = data['notifications_enabled']
            console_log(f"🔔 Notifications {'enabled' if data['notifications_enabled'] else 'disabled'}", "info")
        
        save_theme_settings(settings)
        return jsonify({'success': True, 'settings': settings})

@app.route('/api/search-events')
@rate_limit
@require_admin
def search_events():
    """Search through tracked events."""
    query = request.args.get('q', '').lower().strip()
    console_log(f"🔍 Event search: '{query}'", "debug")
    
    if not query:
        return jsonify({'events': [], 'count': 0})
    
    seen_data = load_seen_events()
    events = seen_data.get('event_details', [])
    
    # Search in title
    matched = [e for e in events if query in e.get('title', '').lower()]
    
    return jsonify({
        'events': matched[:50],  # Limit to 50 results
        'count': len(matched),
        'query': query
    })

@app.route('/api/notification-check')
@rate_limit
def notification_check():
    """Check if there are new events for browser notifications."""
    # This endpoint can be polled by the frontend to check for new events
    last_check = request.args.get('since', '')
    
    seen_data = load_seen_events()
    events = seen_data.get('event_details', [])
    
    if not last_check:
        return jsonify({'new_events': [], 'count': 0})
    
    # Find events added since last check
    new_events = []
    for event in events:
        first_seen = event.get('first_seen', '')
        if first_seen > last_check:
            new_events.append(event)
    
    return jsonify({
        'new_events': new_events,
        'count': len(new_events),
        'last_check': datetime.now(timezone.utc).strftime('%b %d, %Y at %I:%M %p')
    })


@app.route('/api/status-full')
@rate_limit
@require_admin
def api_status_full():
    """Consolidated polling endpoint: status + console + diagnostics + queue.
    
    Reduces dashboard from 4+ parallel AJAX calls to 1, cutting network overhead
    and making the dashboard snappier.
    """
    status = load_status()
    seen_data = load_seen_events()
    now = datetime.now(timezone.utc)

    next_check_seconds = 0
    if CONFIG['next_check']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_check'])
            next_check_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass

    next_heartbeat_seconds = 0
    if CONFIG['next_heartbeat']:
        try:
            next_dt = parse_iso_timestamp(CONFIG['next_heartbeat'])
            next_heartbeat_seconds = max(0, int((next_dt - now).total_seconds()))
        except Exception:
            pass

    checker_alive = checker_thread is not None and checker_thread.is_alive()

    return jsonify({
        'config': CONFIG,
        'status': status,
        'seen_count': len(seen_data.get('event_ids', [])),
        'next_check_seconds': next_check_seconds,
        'next_heartbeat_seconds': next_heartbeat_seconds,
        'checker_running': checker_alive,
        'email_queue': build_email_queue_payload(limit=10),
        'latest_event': get_latest_event_summary(),
        'logs': ACTIVITY_LOGS[:20],
        'console': SYSTEM_CONSOLE[:100],
        'check_history': CHECK_HISTORY[:20],
        'diagnostics': {
            **API_DIAGNOSTICS,
            'email_provider': {
                'primary': 'Telegram' if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS) else 'Gmail SMTP',
                'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
                'telegram_admin_configured': bool(TELEGRAM_ADMIN_CHAT_ID),
                'gmail_configured': bool(MY_EMAIL and MY_PASSWORD),
            },
            'last_smtp_error': CONFIG.get('last_smtp_error'),
            'last_smtp_error_at': CONFIG.get('last_smtp_error_at')
        },
        'visitor_stats': {
            'total': VISITOR_TOTAL,
            'last_24h': len(VISITOR_LOG)
        },
        'timestamp': now.isoformat()
    })


# ===== STARTUP =====
def start_background_checker():
    """Start the background checker thread."""
    global checker_thread
    if checker_thread is None or not checker_thread.is_alive():
        stop_checker.clear()
        checker_thread = threading.Thread(target=background_checker, daemon=True)
        checker_thread.start()

def watchdog_thread():
    """Watchdog that monitors and restarts the background checker if it dies."""
    global checker_thread
    console_log("🐕 Watchdog thread started - monitoring background checker", "debug")
    console_log("   └─ Check interval: 60 seconds", "debug")
    
    restart_count = 0
    
    while True:
        try:
            time.sleep(60)  # Check every minute
            
            is_alive = checker_thread is not None and checker_thread.is_alive()
            
            if not is_alive:
                restart_count += 1
                console_log(f"🔄 WATCHDOG: Background checker not running (restart #{restart_count})", "warning")
                console_log(f"   └─ Thread state: {'None' if checker_thread is None else 'Dead'}", "debug")
                log_activity(f"🔄 Watchdog restarting background checker (attempt #{restart_count})", "warning")
                
                # Reset timer values on restart
                CONFIG['next_check'] = (datetime.now(timezone.utc) + timedelta(minutes=CONFIG['check_interval_minutes'])).isoformat()
                CONFIG['next_heartbeat'] = (datetime.now(timezone.utc) + timedelta(hours=CONFIG['heartbeat_hours'])).isoformat()
                console_log(f"   └─ Timers reset: next check in {CONFIG['check_interval_minutes']} min", "debug")
                
                start_background_checker()
                console_log("✅ WATCHDOG: Background checker restarted successfully", "success")
        except Exception as e:
            console_log(f"⚠️ Watchdog error: {str(e)[:50]}", "error")

def start_watchdog():
    """Start the watchdog thread."""
    watchdog = threading.Thread(target=watchdog_thread, daemon=True)
    watchdog.start()

load_logs()
load_recipient_status()
load_event_stats()
load_admin_audit_on_startup()

# ===== DATABASE INITIALIZATION =====
try:
    _db_conn = get_connection()  # initializes tables on first call
    _db_info = get_db_status()
    console_log(f"\U0001f5c4\ufe0f Database: {_db_info.get('backend', 'unknown')} - Connected", "success")
except Exception as _db_err:
    console_log(f"\u26a0\ufe0f Database init failed: {_db_err} - falling back to JSON", "error")

# Load notification toggle settings from DB into CONFIG
try:
    all_settings = db_get_all_notification_settings()
    for key, enabled in all_settings.items():
        CONFIG[key] = enabled
    console_log(f"\U0001f514 Notification settings loaded: email={CONFIG.get('email_notifications_enabled', True)}, telegram={CONFIG.get('telegram_notifications_enabled', True)}", "debug")
except Exception:
    pass  # Defaults already set in CONFIG

# One-time migration from JSON to DB (safe to run multiple times)
try:
    _migration_marker = os.path.join(DATA_DIR, '.migrated_to_db')
    if not os.path.exists(_migration_marker):
        _summary = migrate_from_json(DATA_DIR)
        if _summary.get('migrated'):
            console_log(f"\U0001f4e6 JSON->DB migration complete: {_summary['migrated']}", "success")
            # Create marker so we don't re-migrate on every restart
            with open(_migration_marker, 'w') as _f:
                _f.write(datetime.now(timezone.utc).isoformat())
        if _summary.get('errors'):
            for _err in _summary['errors']:
                console_log(f"\u26a0\ufe0f Migration warning: {_err}", "warning")
except Exception as _mig_err:
    console_log(f"\u26a0\ufe0f Migration check failed: {_mig_err}", "warning")

# ===== STARTUP CONSOLE MESSAGES =====
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
console_log("🚀 DUBAI FLEA MARKET EVENT TRACKER STARTING...", "info")
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
console_log(f"📡 API Endpoint: {API_URL}", "debug")
console_log(f"⏰ Check Interval: {CONFIG['check_interval_minutes']} minutes", "debug")
console_log(f"💓 Heartbeat: Every {CONFIG['heartbeat_hours']} hours", "debug")
console_log(f"👥 Recipients configured: {len(get_all_recipients())}", "debug")
console_log(f"📊 Event stats loaded: {len(EVENT_STATS.get('daily', {}))} days of data", "debug")
console_log(f"📱 Telegram Admin: {'Configured' if TELEGRAM_ADMIN_CHAT_ID else 'Not set'}", "debug")
try:
    _sub_count = db_get_subscriber_count()
    console_log(f"📱 Telegram DB Subscribers: {_sub_count}", "debug")
except Exception:
    pass
console_log(f"📧 Email notifications: {'ON' if CONFIG.get('email_notifications_enabled', True) else 'OFF'}", "debug")
console_log(f"📡 Telegram notifications: {'ON' if CONFIG.get('telegram_notifications_enabled', True) else 'OFF'}", "debug")

# Security warnings
if not ADMIN_PASSWORD:
    console_log("🚨 WARNING: ADMIN_PASSWORD not set! Dashboard login will be disabled until set.", "error")
    console_log("   └─ Set ADMIN_PASSWORD environment variable in Render dashboard or .env file", "error")
if not CONFIG.get('heartbeat_email'):
    console_log("⚠️ HEARTBEAT_EMAIL not set. Heartbeat emails will not be sent.", "warning")

console_log("✅ System initialized successfully", "success")
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")

start_background_checker()
start_watchdog()  # Start the watchdog to auto-restart if checker dies

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
