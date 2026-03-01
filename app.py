"""
=============================================================================
🚀 DUBAI FLEA MARKET EVENT TRACKER — Bootstrap
=============================================================================
Thin entry point that wires all modules together and starts the system.

Module layout:
  config.py         — Flask app, env vars, constants, shared state
  utils.py          — Helpers, validation, decorators, logging
  state.py          — DB wrappers (seen events, status, queue, etc.)
  notifications.py  — Email & Telegram sending
  events.py         — API fetching, background checker, watchdog
  routes_pages.py   — HTML page routes (/, /login, /dashboard, etc.)
  routes_api.py     — API routes (/api/*)
  db.py             — Database layer (Turso + SQLite fallback)
=============================================================================
"""

import os
import threading
from datetime import datetime, timezone

# Load .env file so credentials are available before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

# ── Core config & Flask app ──────────────────────────────────────────────
from config import (
    app, CONFIG, DATA_DIR, API_URL, EVENT_STATS,
    TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_CHAT_IDS,
)

# ── Utilities (registers after_request hooks on import) ──────────────────
from utils import console_log

# ── Data/state layer ────────────────────────────────────────────────────
from state import (
    load_logs, load_recipient_status, load_event_stats,
    load_admin_audit_on_startup, get_all_recipients,
)

# ── Notification layer ──────────────────────────────────────────────────
import notifications  # noqa: F401  — ensures module is loaded

# ── Background threads ─────────────────────────────────────────────────
from events import start_background_checker, start_watchdog

# ── Routes (registering on the Flask app via decorators on import) ──────
import routes_pages  # noqa: F401
import routes_api    # noqa: F401

# ── Database ────────────────────────────────────────────────────────────
from db import (
    get_connection, get_db_status, migrate_from_json,
    db_get_all_notification_settings, db_get_subscriber_count,
    db_add_subscriber, validate_chat_id,
)


# ===== LOAD PERSISTED STATE (with total timeout to prevent Render hang) =====
def _init_db_and_state():
    """All DB-dependent startup work. Runs in a thread with a hard timeout
    so the app can begin serving even if the database is unreachable."""
    load_logs()
    load_recipient_status()
    load_event_stats()
    load_admin_audit_on_startup()

    # Restore runtime counters from DB so they survive restarts
    from state import load_status as _load_status
    try:
        _saved_status = _load_status()
        for _key in ('total_checks', 'total_new_events', 'emails_sent'):
            _val = _saved_status.get(_key)
            if _val is not None:
                try:
                    CONFIG[_key] = int(_val)
                except (ValueError, TypeError):
                    pass
        console_log(
            f"📊 Restored counters: checks={CONFIG['total_checks']}, "
            f"events={CONFIG['total_new_events']}, emails={CONFIG['emails_sent']}",
            "debug",
        )
    except Exception as _e:
        console_log(f"⚠️ Could not restore counters from DB: {_e}", "warning")

    # Database initialization
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
        console_log(
            f"\U0001f514 Notification settings loaded: "
            f"email={CONFIG.get('email_notifications_enabled', True)}, "
            f"telegram={CONFIG.get('telegram_notifications_enabled', True)}",
            "debug",
        )
    except Exception:
        pass  # Defaults already set in CONFIG

    # One-time migration from JSON to DB (safe to run multiple times)
    try:
        _migration_marker = os.path.join(DATA_DIR, '.migrated_to_db')
        if not os.path.exists(_migration_marker):
            _summary = migrate_from_json(DATA_DIR)
            if _summary.get('migrated'):
                console_log(f"\U0001f4e6 JSON->DB migration complete: {_summary['migrated']}", "success")
                with open(_migration_marker, 'w') as _f:
                    _f.write(datetime.now(timezone.utc).isoformat())
            if _summary.get('errors'):
                for _err in _summary['errors']:
                    console_log(f"\u26a0\ufe0f Migration warning: {_err}", "warning")
    except Exception as _mig_err:
        console_log(f"\u26a0\ufe0f Migration check failed: {_mig_err}", "warning")

    # Seed env-configured Telegram chat IDs into the DB
    try:
        _seeded = 0
        for _raw_id in (TELEGRAM_CHAT_IDS or '').split(','):
            _cid = _raw_id.strip()
            if _cid and validate_chat_id(_cid):
                if db_add_subscriber(_cid, 'Env Config', added_by='env'):
                    _seeded += 1
        if TELEGRAM_ADMIN_CHAT_ID and validate_chat_id(TELEGRAM_ADMIN_CHAT_ID):
            if db_add_subscriber(TELEGRAM_ADMIN_CHAT_ID, 'Admin', added_by='env'):
                _seeded += 1
        if _seeded:
            console_log(f"\U0001f4f1 Seeded {_seeded} Telegram subscriber(s) from env", "success")
    except Exception as _seed_err:
        console_log(f"\u26a0\ufe0f Telegram subscriber seeding failed: {_seed_err}", "warning")


# Run DB init in background so gunicorn can bind the port immediately.
# The app will serve with defaults until the DB catches up.
_init_thread = threading.Thread(target=_init_db_and_state, daemon=True)
_init_thread.start()
_init_thread.join(timeout=15)  # Wait up to 15s; if not done, continue anyway
if _init_thread.is_alive():
    console_log(
        "⚠️ DB initialization still running — app starting with defaults",
        "warning",
    )


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
from config import ADMIN_PASSWORD
if not ADMIN_PASSWORD:
    console_log("🚨 WARNING: ADMIN_PASSWORD not set! Dashboard login will be disabled until set.", "error")
    console_log("   └─ Set ADMIN_PASSWORD environment variable in Render dashboard or .env file", "error")
if not CONFIG.get('heartbeat_email'):
    console_log("⚠️ HEARTBEAT_EMAIL not set. Heartbeat emails will not be sent.", "warning")

console_log("✅ System initialized successfully", "success")
console_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")

# ===== START BACKGROUND THREADS =====
start_background_checker()
start_watchdog()


# ===== ENTRY POINT =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
