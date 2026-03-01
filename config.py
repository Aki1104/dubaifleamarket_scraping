"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Configuration & Shared State
=============================================================================
All environment variables, runtime configuration, and shared mutable state
live here so every module can import them without circular dependencies.

Variables that get REASSIGNED (=) across modules must be accessed via
``config.VAR``, not ``from config import VAR``.  Variables that are only
MUTATED (dict/list ops) can safely use either import style.
=============================================================================
"""

import os
import secrets
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from flask import Flask

# Load .env file so credentials are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

# ===== Flask App =====
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
)
app.permanent_session_lifetime = timedelta(hours=int(os.environ.get('ADMIN_SESSION_HOURS', '8')))

# ===== Environment Variables =====
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
API_URL = "https://dubai-fleamarket.com/wp-json/wp/v2/product?per_page=20"
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))

# Telegram Bot (FREE - unlimited messages, instant push notifications)
# Create bot: @BotFather on Telegram, get token
# Get chat ID: Send message to bot, then visit:
#   https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_IDS = os.environ.get('TELEGRAM_CHAT_IDS', '')       # Comma-separated for NEW EVENTS
TELEGRAM_ADMIN_CHAT_ID = os.environ.get('TELEGRAM_ADMIN_CHAT_ID', '')  # Admin only

# Gmail SMTP (may be blocked on some cloud hosts like Render free tier)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MY_EMAIL = os.environ.get('MY_EMAIL', '')
MY_PASSWORD = os.environ.get('MY_PASSWORD', '')
TO_EMAIL = os.environ.get('TO_EMAIL', '')

# Force IPv4 for SMTP connections (fixes "Network is unreachable" on some cloud hosts)
SMTP_USE_IPV4 = os.environ.get('SMTP_USE_IPV4', 'true').lower() == 'true'

# ===== Runtime Configuration =====
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

# ===== Shared Mutable State =====
# NOTE: Variables below that get reassigned (=) across modules must be
# accessed via ``config.VARIABLE``, not ``from config import VARIABLE``.

ACTIVITY_LOGS = []
MAX_LOGS = 100

ADMIN_AUDIT_LOGS = []
MAX_ADMIN_AUDIT = 300

VISITOR_TOTAL = 0
VISITOR_LOG = []  # ISO timestamps for last 24h

LAST_GMAIL_CONFIG_LOG_AT = None  # Throttle "Gmail not configured" log

CHECK_HISTORY = []
MAX_CHECK_HISTORY = 50

SYSTEM_CONSOLE = []
MAX_CONSOLE_LOGS = 200

EMAIL_QUEUE = []
MAX_EMAIL_QUEUE = 50
EMAIL_RETRY_INTERVALS = [30, 60, 120, 240]  # Minutes: 30min, 1hr, 2hr, 4hr
MAX_EMAIL_AGE_HOURS = 24

EVENT_STATS = {'daily': {}, 'hourly': {}}  # In-memory cache

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

# ===== Security: Rate Limiting =====
rate_limit_data = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 100  # Increased from 30 — dashboard polls frequently
BLOCKED_IPS = set()
BLOCK_DURATION = 300

# ===== Threading =====
checker_thread = None
stop_checker = threading.Event()
_data_lock = threading.RLock()

# ===== Recursion Guard =====
_admin_alert_in_progress = False
