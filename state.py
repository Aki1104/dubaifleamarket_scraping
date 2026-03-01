"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Data / State Layer
=============================================================================
Pure DB wrappers and shared data accessors that sit between the database
layer (db.py) and the business logic (notifications.py, events.py).

Intentionally has NO dependency on notifications.py or events.py to
prevent circular imports.
=============================================================================
"""

import json
from datetime import datetime, timezone

import config
from config import CONFIG, TO_EMAIL
from utils import (
    console_log, sanitize_string, validate_email, mask_email,
    format_timestamp, log_activity,
)
from db import (
    db_load_seen_events, db_save_seen_events_bulk,
    db_load_status, db_save_status, db_get_status, db_set_status,
    db_get_logs,
    db_add_email_history, db_get_email_history,
    db_get_queue, db_add_to_queue, db_update_queue_item,
    db_remove_from_queue, db_clear_queue, db_get_queue_count,
    db_record_stat, db_get_stats,
    db_get_audit_logs,
)


# ===== Seen Events =====

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


# ===== Tracker Status =====

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


# ===== Event Statistics =====

def load_event_stats():
    """Load event statistics from database."""
    try:
        daily_rows = db_get_stats('daily', 30)
        hourly_rows = db_get_stats('hourly', 48)
        config.EVENT_STATS['daily'] = {
            r['period']: {'checks': r['checks'], 'new_events': r['new_events'], 'emails_sent': r['emails_sent']}
            for r in daily_rows
        }
        config.EVENT_STATS['hourly'] = {
            r['period']: {'checks': r['checks'], 'new_events': r['new_events'], 'emails_sent': r['emails_sent']}
            for r in hourly_rows
        }
        console_log("📊 Event statistics loaded from database", "debug")
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to load event stats: {e}", "warning")
        config.EVENT_STATS = {'daily': {}, 'hourly': {}}
    return config.EVENT_STATS


def record_stat(stat_type, value=1):
    """Record a statistic (checks, new_events, emails_sent) to DB."""
    now = datetime.now(timezone.utc)
    day_key = now.strftime('%Y-%m-%d')
    hour_key = now.strftime('%Y-%m-%dT%H')

    try:
        db_record_stat('daily', day_key, stat_type, value)
        db_record_stat('hourly', hour_key, stat_type, value)
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to record stat: {e}", "warning")


# ===== Activity Logs =====

def load_logs():
    """Load activity logs from database."""
    try:
        config.ACTIVITY_LOGS = db_get_logs(200)
    except Exception:
        config.ACTIVITY_LOGS = []


# ===== Email History =====

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


# ===== Daily Summary =====

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


# ===== Theme Settings =====

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
        console_log(f"\u26a0\ufe0f Failed to save theme settings: {e}", "warning")


# ===== Recipient Status =====

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


# ===== Recipients =====

def get_all_recipients() -> list:
    """Get all configured recipients."""
    if not TO_EMAIL:
        return []
    return [e.strip() for e in TO_EMAIL.split(',') if e.strip() and validate_email(e.strip())]


def get_recipients() -> list:
    """Get enabled recipients only."""
    all_recipients = get_all_recipients()
    return [e for e in all_recipients if is_recipient_enabled(e)]


# ===== Admin Audit =====

def load_admin_audit_on_startup():
    """Load admin audit logs from DB on startup."""
    config.ADMIN_AUDIT_LOGS = db_get_audit_logs(300)


# ===== Email Queue =====

def load_email_queue():
    """Load email queue from database."""
    try:
        config.EMAIL_QUEUE = db_get_queue()
        console_log(f"📬 Email queue loaded: {len(config.EMAIL_QUEUE)} pending emails", "debug")
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to load email queue: {e}", "warning")
        config.EMAIL_QUEUE = []


def save_email_queue():
    """Sync in-memory queue with database."""
    try:
        config.EMAIL_QUEUE = db_get_queue()
    except Exception as e:
        console_log(f"\u26a0\ufe0f Failed to sync email queue: {e}", "warning")


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
            'next_retry_display': format_timestamp(item.get('next_retry', '')),
            'priority': item.get('priority', 'normal'),
            'attempts': item.get('attempts', 0),
            'last_error': sanitize_string(item.get('last_error', ''), 120) if item.get('last_error') else None
        })

    return {
        'pending_count': total,
        'high_priority': high_priority,
        'items': payload_items
    }


# ===== Tracked Events Helpers =====

def load_tracked_events():
    """Load tracked event details list."""
    try:
        seen_data = load_seen_events()
        return seen_data.get('event_details', [])
    except Exception:
        return []


def get_latest_event_summary():
    """Get summary of the most recently tracked event."""
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
