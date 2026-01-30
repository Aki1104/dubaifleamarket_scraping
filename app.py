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

from flask import Flask, render_template, jsonify, request, session, abort
from functools import wraps
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import json
import os
import threading
import requests
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html
import hashlib
import secrets
import time
import re

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

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

# ===== SECURITY: Input Validation =====
def sanitize_string(text, max_length=500):
    """Sanitize and validate string input."""
    if not isinstance(text, str):
        return str(text)[:max_length] if text is not None else ''
    text = html.escape(text)
    text = re.sub(r'[<>"\';]|--|\bOR\b|\bAND\b|\bUNION\b|\bSELECT\b|\bDROP\b|\bINSERT\b|\bDELETE\b', '', text, flags=re.IGNORECASE)
    return text.strip()[:max_length]

def validate_email(email):
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= 254

def validate_url(url):
    """Validate URL is from expected domain."""
    if not url or not isinstance(url, str):
        return False
    allowed_domains = ['dubai-fleamarket.com', 'www.dubai-fleamarket.com']
    try:
        if not url.startswith(('http://', 'https://')):
            return False
        domain = url.split('/')[2].lower()
        return any(domain == allowed or domain.endswith('.' + allowed) for allowed in allowed_domains)
    except:
        return False

def mask_email(email):
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
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

def verify_password(password):
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
            data = request.get_json() or {}
            password = data.get('password', '')
            
            console_log(f"🔐 AUTH: Password received: {'yes' if password else 'no'} (length: {len(password) if password else 0})", "debug")
            
            if not verify_password(password):
                log_activity(f"🚫 Failed auth attempt from {get_client_ip()[:10]}...", "warning")
                console_log(f"🔐 AUTH FAILED for {request.endpoint} from {get_client_ip()[:15]}...", "warning")
                console_log(f"   └─ Expected password length: {len(ADMIN_PASSWORD)}, Got: {len(password) if password else 0}", "debug")
                return jsonify({'error': 'Invalid password', 'auth_required': True}), 401
            
            console_log(f"✅ AUTH SUCCESS: {request.endpoint}", "success")
            
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
DB_FILE = os.path.join(DATA_DIR, "seen_events.json")
STATUS_FILE = os.path.join(DATA_DIR, "tracker_status.json")
LOGS_FILE = os.path.join(DATA_DIR, "activity_logs.json")
RECIPIENT_STATUS_FILE = os.path.join(DATA_DIR, "recipient_status.json")
EMAIL_HISTORY_FILE = os.path.join(DATA_DIR, "email_history.json")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MY_EMAIL = os.environ.get('MY_EMAIL', '')
MY_PASSWORD = os.environ.get('MY_PASSWORD', '')
TO_EMAIL = os.environ.get('TO_EMAIL', '')

CONFIG = {
    'check_interval_minutes': int(os.environ.get('CHECK_INTERVAL', '15')),
    'heartbeat_enabled': os.environ.get('HEARTBEAT_ENABLED', 'true').lower() == 'true',
    'heartbeat_hours': int(os.environ.get('HEARTBEAT_HOURS', '3')),
    'heartbeat_email': os.environ.get('HEARTBEAT_EMAIL', 'steevenparubrub@gmail.com'),
    'daily_summary_enabled': os.environ.get('DAILY_SUMMARY_ENABLED', 'true').lower() == 'true',
    'daily_summary_hour': int(os.environ.get('DAILY_SUMMARY_HOUR', '9')),
    'tracker_enabled': True,
    'last_check': None,
    'next_check': (datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get('CHECK_INTERVAL', '15')))).isoformat(),
    'next_heartbeat': (datetime.now(timezone.utc) + timedelta(hours=int(os.environ.get('HEARTBEAT_HOURS', '3')))).isoformat(),
    'total_checks': 0,
    'total_new_events': 0,
    'emails_sent': 0,
    'uptime_start': datetime.now(timezone.utc).isoformat()
}

ACTIVITY_LOGS = []
MAX_LOGS = 100

# ===== CHECK HISTORY - Card-based check results =====
CHECK_HISTORY = []
MAX_CHECK_HISTORY = 50  # Keep last 50 check results

# ===== SYSTEM CONSOLE - Terminal-like logging =====
SYSTEM_CONSOLE = []
MAX_CONSOLE_LOGS = 200

# ===== EVENT STATISTICS - For charting =====
EVENT_STATS_FILE = os.path.join(DATA_DIR, "event_stats.json")
EVENT_STATS = {
    'daily': {},  # {'2026-01-30': {'checks': 5, 'new_events': 2, 'emails_sent': 3}}
    'hourly': {}  # {'2026-01-30T14': {'checks': 1, 'new_events': 0}}
}

def load_event_stats():
    """Load event statistics from file."""
    global EVENT_STATS
    if os.path.exists(EVENT_STATS_FILE):
        try:
            with open(EVENT_STATS_FILE, 'r') as f:
                EVENT_STATS = json.load(f)
                console_log("📊 Event statistics loaded from file", "debug")
        except Exception as e:
            console_log(f"⚠️ Failed to load event stats: {e}", "warning")
            EVENT_STATS = {'daily': {}, 'hourly': {}}
    return EVENT_STATS

def save_event_stats():
    """Save event statistics to file."""
    try:
        # Keep only last 30 days of daily stats and 48 hours of hourly stats
        now = datetime.now(timezone.utc)
        cutoff_daily = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        cutoff_hourly = (now - timedelta(hours=48)).strftime('%Y-%m-%dT%H')
        
        EVENT_STATS['daily'] = {k: v for k, v in EVENT_STATS['daily'].items() if k >= cutoff_daily}
        EVENT_STATS['hourly'] = {k: v for k, v in EVENT_STATS['hourly'].items() if k >= cutoff_hourly}
        
        with open(EVENT_STATS_FILE, 'w') as f:
            json.dump(EVENT_STATS, f, indent=2)
    except Exception as e:
        console_log(f"⚠️ Failed to save event stats: {e}", "warning")

def record_stat(stat_type, value=1):
    """Record a statistic (checks, new_events, emails_sent)."""
    now = datetime.now(timezone.utc)
    day_key = now.strftime('%Y-%m-%d')
    hour_key = now.strftime('%Y-%m-%dT%H')
    
    # Daily stats
    if day_key not in EVENT_STATS['daily']:
        EVENT_STATS['daily'][day_key] = {'checks': 0, 'new_events': 0, 'emails_sent': 0}
    EVENT_STATS['daily'][day_key][stat_type] = EVENT_STATS['daily'][day_key].get(stat_type, 0) + value
    
    # Hourly stats
    if hour_key not in EVENT_STATS['hourly']:
        EVENT_STATS['hourly'][hour_key] = {'checks': 0, 'new_events': 0, 'emails_sent': 0}
    EVENT_STATS['hourly'][hour_key][stat_type] = EVENT_STATS['hourly'][hour_key].get(stat_type, 0) + value
    
    save_event_stats()

# ===== THEME SETTINGS =====
THEME_FILE = os.path.join(DATA_DIR, "theme_settings.json")

def load_theme_settings():
    """Load theme settings."""
    if os.path.exists(THEME_FILE):
        try:
            with open(THEME_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'theme': 'dark', 'notifications_enabled': False}

def save_theme_settings(settings):
    """Save theme settings."""
    try:
        with open(THEME_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
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

def console_log(message, log_type="info"):
    """Add detailed log to system console - terminal style."""
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
    SYSTEM_CONSOLE.insert(0, entry)
    if len(SYSTEM_CONSOLE) > MAX_CONSOLE_LOGS:
        SYSTEM_CONSOLE = SYSTEM_CONSOLE[:MAX_CONSOLE_LOGS]
    print(f"[CONSOLE][{log_type.upper()}] {message}")

checker_thread = None
stop_checker = threading.Event()

# ===== RECIPIENT STATUS MANAGEMENT =====
def load_recipient_status():
    """Load recipient enabled/disabled status."""
    if os.path.exists(RECIPIENT_STATUS_FILE):
        try:
            with open(RECIPIENT_STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    
    # Initialize all recipients as enabled
    status = {}
    for email in get_all_recipients():
        status[email] = {'enabled': True}
    
    save_recipient_status(status)
    return status

def save_recipient_status(status):
    """Save recipient status."""
    try:
        with open(RECIPIENT_STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save recipient status: {e}", "error")

def is_recipient_enabled(email):
    """Check if recipient is enabled."""
    status = load_recipient_status()
    return status.get(email, {}).get('enabled', True)

# ===== EMAIL HISTORY MANAGEMENT =====
def load_email_history():
    """Load email history."""
    if os.path.exists(EMAIL_HISTORY_FILE):
        try:
            with open(EMAIL_HISTORY_FILE, 'r') as f:
                history = json.load(f)
                if isinstance(history, list):
                    return history
        except:
            pass
    return []

def save_email_history(history):
    """Save email history."""
    try:
        with open(EMAIL_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save email history: {e}", "error")

def add_to_email_history(recipient, subject, success, error_msg=''):
    """Add entry to email history."""
    history = load_email_history()
    
    # Keep last 500 entries
    if len(history) > 500:
        history = history[-500:]
    
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d at %I:%M %p'),
        'recipient': recipient,
        'recipient_masked': mask_email(recipient),
        'subject': sanitize_string(subject, 100),
        'success': success,
        'error': error_msg if not success else ''
    }
    
    history.append(entry)
    save_email_history(history)

def format_timestamp(iso_string):
    """Format ISO timestamp to readable format like 'Jan 30, 2026 at 02:45 PM'."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %Y at %I:%M %p')
    except:
        return iso_string[:16] if iso_string else '--'

# ===== HELPER FUNCTIONS =====
def get_all_recipients():
    """Get all configured recipients."""
    if not TO_EMAIL:
        return []
    return [e.strip() for e in TO_EMAIL.split(',') if e.strip() and validate_email(e.strip())]

def get_recipients():
    """Get enabled recipients only."""
    all_recipients = get_all_recipients()
    return [e for e in all_recipients if is_recipient_enabled(e)]

def log_activity(message, level="info"):
    """Add activity log entry."""
    global ACTIVITY_LOGS
    now = datetime.now(timezone.utc)
    entry = {
        'timestamp': now.isoformat(),
        'timestamp_formatted': now.strftime('%b %d, %Y at %I:%M %p'),
        'message': sanitize_string(message, 200),
        'level': level
    }
    ACTIVITY_LOGS.insert(0, entry)
    if len(ACTIVITY_LOGS) > MAX_LOGS:
        ACTIVITY_LOGS = ACTIVITY_LOGS[:MAX_LOGS]
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(ACTIVITY_LOGS, f, indent=2)
    except:
        pass
    print(f"[{level.upper()}] {message}")

def load_logs():
    """Load activity logs from file."""
    global ACTIVITY_LOGS
    try:
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                ACTIVITY_LOGS = json.load(f)
    except:
        ACTIVITY_LOGS = []

def load_status():
    """Load tracker status."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'last_daily_summary': None, 'total_checks': 0, 'last_heartbeat': None, 'last_check_time': None}

def save_status(status):
    """Save tracker status."""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save status: {e}", "error")

def load_seen_events():
    """Load seen events."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {'event_ids': data, 'event_details': []}
                return data
        except:
            pass
    return {'event_ids': [], 'event_details': []}

def save_seen_events(seen_data):
    """Save seen events."""
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(seen_data, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save events: {e}", "error")

def fetch_events():
    """Fetch events from API with detailed diagnostics."""
    global API_DIAGNOSTICS
    import time
    
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

def send_email(subject, body, to_email=None, max_retries=3):
    """Send email notification with retry logic for transient failures."""
    global CONFIG
    if not MY_EMAIL or not MY_PASSWORD:
        log_activity("Email credentials not configured", "error")
        add_to_email_history(to_email or 'unknown', subject, False, 'Credentials not configured')
        return False
    
    recipient = to_email or TO_EMAIL
    if not recipient:
        log_activity("No recipient email configured", "error")
        return False
    
    if not validate_email(recipient):
        log_activity(f"Invalid recipient email: {recipient[:20]}...", "error")
        add_to_email_history(recipient, subject, False, 'Invalid email format')
        return False
    
    # Prepare message once
    msg = MIMEMultipart('alternative')
    msg['Subject'] = sanitize_string(subject, 100)
    msg['From'] = MY_EMAIL
    msg['To'] = recipient
    text_part = MIMEText(body, 'plain')
    msg.attach(text_part)
    
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            console_log(f"📧 Sending to {mask_email(recipient)} (attempt {attempt}/{max_retries})...", "debug")
            
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(MY_EMAIL, MY_PASSWORD)
                server.sendmail(MY_EMAIL, recipient, msg.as_string())
            
            CONFIG['emails_sent'] = CONFIG.get('emails_sent', 0) + 1
            # Record email sent statistic
            record_stat('emails_sent', 1)
            log_activity(f"📧 Email sent to {recipient[:15]}...", "success")
            console_log(f"✅ Email delivered successfully to {mask_email(recipient)}", "success")
            add_to_email_history(recipient, subject, True)
            return True
            
        except (OSError, socket.error) as e:
            # Network errors - retry
            last_error = str(e)[:50]
            console_log(f"⚠️ Network error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(5 * attempt)  # Exponential backoff: 5s, 10s, 15s
                continue
        except smtplib.SMTPException as e:
            # SMTP errors - may or may not be retryable
            last_error = str(e)[:50]
            console_log(f"⚠️ SMTP error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(3)
                continue
        except Exception as e:
            # Other errors - don't retry
            last_error = str(e)[:50]
            console_log(f"❌ Email error: {last_error}", "error")
            break
    
    # All retries failed
    log_activity(f"Failed to send email after {max_retries} attempts: {last_error}", "error")
    console_log(f"❌ Email delivery failed after {max_retries} retries: {last_error}", "error")
    add_to_email_history(recipient, subject, False, f"Failed after {max_retries} retries: {last_error}")
    return False

def send_new_event_email(events):
    """Send new event notification to enabled recipients."""
    subject = f"🎉 {len(events)} New Dubai Flea Market Event(s)!"
    body = f"🎯 {len(events)} new event(s) have been posted!\n\n"
    
    for event in events:
        body += f"📍 {event['title']}\n"
        body += f"🔗 {event['link']}\n"
        body += f"📅 Posted: {event['date_posted']}\n"
        body += "-" * 50 + "\n\n"
    
    body += "\n🤖 Sent automatically by Dubai Flea Market Tracker"
    
    console_log(f"📧 Sending new event notification to {len(get_recipients())} recipient(s)", "info")
    for email in get_recipients():
        send_email(subject, body, email)

def send_heartbeat():
    """Send heartbeat status email."""
    if not CONFIG['heartbeat_enabled']:
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
    return result

def send_daily_summary_email():
    """Send daily summary email."""
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
    
    success = True
    for email in get_recipients():
        if not send_email(subject, body, email):
            success = False
    
    return success

def check_for_events():
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

def should_send_heartbeat():
    """Check if heartbeat is due."""
    if not CONFIG['heartbeat_enabled']:
        return False
    
    status = load_status()
    last_heartbeat = status.get('last_heartbeat')
    
    if not last_heartbeat:
        return True
    
    try:
        last_time = datetime.fromisoformat(last_heartbeat.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours_since = (now - last_time).total_seconds() / 3600
        return hours_since >= CONFIG['heartbeat_hours']
    except:
        return True

def background_checker():
    """Background thread that runs the event checker with self-healing."""
    log_activity("🚀 Background checker started", "success")
    console_log("🚀 Background checker thread initialized", "success")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    check_interval_seconds = CONFIG['check_interval_minutes'] * 60
    
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
@rate_limit
def dashboard():
    """Main dashboard page."""
    status = load_status()
    seen_data = load_seen_events()
    now = datetime.now(timezone.utc)
    
    next_check_seconds = 0
    if CONFIG['next_check']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_check'].replace('Z', '+00:00'))
            next_check_seconds = max(0, int((next_dt - now).total_seconds()))
        except:
            pass
    
    next_heartbeat_seconds = 0
    if CONFIG['next_heartbeat']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_heartbeat'].replace('Z', '+00:00'))
            next_heartbeat_seconds = max(0, int((next_dt - now).total_seconds()))
        except:
            pass
    
    uptime_str = "Just started"
    try:
        start = datetime.fromisoformat(CONFIG['uptime_start'].replace('Z', '+00:00'))
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
    except:
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
        live_events=live_events,
        logs=ACTIVITY_LOGS[:50],
        all_recipients=all_recipients,
        recipient_status=recipient_status,
        mask_email=mask_email,
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

@app.route('/api/status')
@rate_limit
def api_status():
    """API endpoint for status data with calculated timer values."""
    status = load_status()
    seen_data = load_seen_events()
    now = datetime.now(timezone.utc)
    
    # Calculate remaining seconds for timers
    next_check_seconds = 0
    if CONFIG['next_check']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_check'].replace('Z', '+00:00'))
            next_check_seconds = max(0, int((next_dt - now).total_seconds()))
        except:
            pass
    
    next_heartbeat_seconds = 0
    if CONFIG['next_heartbeat']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_heartbeat'].replace('Z', '+00:00'))
            next_heartbeat_seconds = max(0, int((next_dt - now).total_seconds()))
        except:
            pass
    
    return jsonify({
        'config': CONFIG,
        'status': status,
        'seen_count': len(seen_data.get('event_ids', [])),
        'logs': ACTIVITY_LOGS[:20],
        'next_check_seconds': next_check_seconds,
        'next_heartbeat_seconds': next_heartbeat_seconds
    })

@app.route('/api/console')
@rate_limit
def api_console():
    """API endpoint for system console logs."""
    return jsonify({
        'console': SYSTEM_CONSOLE[:100],
        'diagnostics': API_DIAGNOSTICS,
        'check_history': CHECK_HISTORY[:20]  # Include recent check history
    })

@app.route('/api/check-history')
@rate_limit
def api_check_history():
    """API endpoint for check history cards."""
    return jsonify({
        'history': CHECK_HISTORY[:50],
        'total_checks': CONFIG['total_checks']
    })

@app.route('/api/diagnostics')
@rate_limit
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
    log_activity("🗑️ Logs cleared", "info")
    console_log("🗑️ Activity logs cleared by admin", "info")
    return jsonify({'success': True})

# ===== NEW API ENDPOINTS =====

@app.route('/api/stats')
@rate_limit
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
    1. Removing the most recent event from seen_events.json
    2. Immediately triggering an API check
    3. The event will be detected as 'new' and emails sent to all recipients
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

# ===== STARTUP CONSOLE MESSAGES =====
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
console_log("🚀 DUBAI FLEA MARKET EVENT TRACKER STARTING...", "info")
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
console_log(f"📡 API Endpoint: {API_URL}", "debug")
console_log(f"⏰ Check Interval: {CONFIG['check_interval_minutes']} minutes", "debug")
console_log(f"💓 Heartbeat: Every {CONFIG['heartbeat_hours']} hours", "debug")
console_log(f"👥 Recipients configured: {len(get_all_recipients())}", "debug")
console_log(f"📊 Event stats loaded: {len(EVENT_STATS.get('daily', {}))} days of data", "debug")
console_log("✅ System initialized successfully", "success")
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")

start_background_checker()
start_watchdog()  # Start the watchdog to auto-restart if checker dies

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
