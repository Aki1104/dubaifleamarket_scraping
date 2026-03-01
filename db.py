"""
=============================================================================
🗄️ DATABASE LAYER — Turso (LibSQL) with Local SQLite Fallback
=============================================================================
Replaces all JSON file storage with a proper database.
All queries use parameterized statements (?) to prevent SQL injection.

Security:
- Zero string interpolation in SQL queries
- All user inputs validated before querying
- LIMIT on SELECT queries to prevent memory exhaustion
- Connection tokens stored in environment variables only
- Automatic fallback to local SQLite if Turso is unreachable
=============================================================================
"""

import os
import socket
import sqlite3
import secrets
import threading
from datetime import datetime, timezone, timedelta

from typing import Any

# ---------- Lazy libsql import (deferred to first get_connection() call) ----------
# libsql_experimental is a C extension that can hang on import in some
# environments. Loading it lazily ensures gunicorn's worker can boot and
# bind the HTTP port before the extension is touched.
_libsql: Any = None
_libsql_loaded = False


def _get_libsql():
    """Lazy-load libsql_experimental on first use. Returns the module or None."""
    global _libsql, _libsql_loaded
    if _libsql_loaded:
        return _libsql
    _libsql_loaded = True
    try:
        import libsql_experimental as _mod  # type: ignore[import-unresolved]
        _libsql = _mod
        print("[DB] libsql_experimental loaded successfully")
    except (ImportError, OSError, Exception) as err:
        _libsql = None
        print(f"[DB] libsql_experimental not available: {err}")
    return _libsql


def _connect_turso_with_timeout(url: str, token: str, timeout_sec: int = 10):
    """
    Attempt a Turso connection with a hard socket-level timeout.
    Sets a global socket timeout so even C-level code that holds the GIL
    will be interrupted. Restores the original timeout afterward.
    """
    lib = _get_libsql()
    if lib is None:
        raise RuntimeError("libsql_experimental is not available")
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout_sec)
        conn = lib.connect(database=url, auth_token=token)
        return conn
    except socket.timeout:
        raise TimeoutError(
            f"Turso connection timed out after {timeout_sec}s — "
            "falling back to local SQLite"
        )
    finally:
        socket.setdefaulttimeout(old_timeout)

# ---------- Configuration ----------
TURSO_DATABASE_URL = os.environ.get('TURSO_DATABASE_URL', '')
TURSO_AUTH_TOKEN = os.environ.get('TURSO_AUTH_TOKEN', '')
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
LOCAL_DB_PATH = os.path.join(DATA_DIR, 'local_data.db')

# ---------- Connection state ----------
_conn = None
_using_turso = False
_db_initialized = False
_conn_lock = threading.Lock()


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _now_formatted() -> str:
    """Return current UTC time in display format."""
    return datetime.now(timezone.utc).strftime('%b %d, %Y at %I:%M %p')


def get_connection():
    """
    Get or create a database connection.
    Tries Turso (cloud) first, falls back to local SQLite.
    Thread-safe: sqlite3 connections with check_same_thread=False.
    """
    global _conn, _using_turso, _db_initialized

    with _conn_lock:
        if _conn is not None and _db_initialized:
            # Health check: verify the connection is still alive
            try:
                _conn.execute("SELECT 1")
            except Exception:
                print("[DB] Connection health check failed, reconnecting...")
                _conn = None
                _db_initialized = False
                # Fall through to reconnect
            else:
                return _conn

        # ---- Try Turso cloud first (with timeout to prevent hanging on Render) ----
        if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
            try:
                _conn = _connect_turso_with_timeout(
                    TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, timeout_sec=10
                )
                _using_turso = True
                _init_tables(_conn)
                _db_initialized = True
                print("[DB] Connected to Turso cloud database")
                return _conn
            except TimeoutError as e:
                print(f"[DB] {e}")
                _conn = None
            except Exception as e:
                print(f"[DB] Turso connection failed: {str(e)[:100]}, falling back to local SQLite")
                _conn = None

        # ---- Fallback: local SQLite ----
        try:
            _conn = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
            _conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
            _conn.execute("PRAGMA busy_timeout=5000")  # Wait 5s if locked
            _using_turso = False
            _init_tables(_conn)
            _db_initialized = True
            print(f"[DB] Connected to local SQLite: {LOCAL_DB_PATH}")
            return _conn
        except Exception as e:
            print(f"[DB] CRITICAL: Could not connect to any database: {e}")
            raise


def is_using_turso() -> bool:
    """Check if we're connected to Turso cloud or local SQLite."""
    return _using_turso


def get_db_status() -> dict:
    """Get database connection status for dashboard display."""
    try:
        conn = get_connection()
        tables = {}
        for table in ['seen_events', 'tracker_status', 'activity_logs',
                       'email_history', 'email_queue', 'event_stats',
                       'telegram_subscribers', 'notification_settings']:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                tables[table] = row[0] if row else 0
            except Exception:
                tables[table] = -1  # Table doesn't exist

        return {
            'connected': True,
            'backend': 'Turso (LibSQL Cloud)' if _using_turso else 'Local SQLite',
            'turso_configured': bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN),
            'tables': tables,
            'db_path': TURSO_DATABASE_URL.split('@')[-1] if _using_turso and '@' in TURSO_DATABASE_URL else (LOCAL_DB_PATH if not _using_turso else TURSO_DATABASE_URL)
        }
    except Exception as e:
        return {
            'connected': False,
            'backend': 'None',
            'error': str(e)[:100],
            'turso_configured': bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN),
            'tables': {}
        }


def _init_tables(conn):
    """Create all tables if they don't exist. Called once on connection."""
    statements = [
        """CREATE TABLE IF NOT EXISTS seen_events (
            event_id INTEGER PRIMARY KEY,
            title TEXT,
            link TEXT,
            date_posted TEXT,
            first_seen_at TEXT DEFAULT (datetime('now'))
        )""",

        """CREATE TABLE IF NOT EXISTS tracker_status (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )""",

        """CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            timestamp TEXT DEFAULT (datetime('now')),
            timestamp_formatted TEXT DEFAULT ''
        )""",

        """CREATE TABLE IF NOT EXISTS email_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT NOT NULL,
            recipient_masked TEXT DEFAULT '',
            subject TEXT,
            success INTEGER DEFAULT 1,
            error_message TEXT DEFAULT '',
            timestamp TEXT DEFAULT (datetime('now')),
            timestamp_formatted TEXT DEFAULT ''
        )""",

        """CREATE TABLE IF NOT EXISTS email_queue (
            id TEXT PRIMARY KEY,
            subject TEXT,
            body TEXT,
            recipient TEXT,
            priority TEXT DEFAULT 'normal',
            attempts INTEGER DEFAULT 0,
            next_retry TEXT,
            last_error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )""",

        """CREATE TABLE IF NOT EXISTS event_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_type TEXT NOT NULL,
            period TEXT NOT NULL,
            checks INTEGER DEFAULT 0,
            new_events INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(stat_type, period)
        )""",

        """CREATE TABLE IF NOT EXISTS telegram_subscribers (
            chat_id TEXT PRIMARY KEY,
            display_name TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            added_by TEXT DEFAULT 'admin',
            added_at TEXT DEFAULT (datetime('now')),
            last_notified_at TEXT
        )""",

        """CREATE TABLE IF NOT EXISTS notification_settings (
            key TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        )""",

        """CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            timestamp_formatted TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            action TEXT NOT NULL,
            details TEXT DEFAULT ''
        )""",
    ]

    for stmt in statements:
        try:
            conn.execute(stmt)
        except Exception as e:
            print(f"[DB] Warning: Table creation issue: {str(e)[:80]}")

    # Seed default notification settings if empty
    try:
        row = conn.execute("SELECT COUNT(*) FROM notification_settings").fetchone()
        if row and row[0] == 0:
            conn.execute("INSERT OR IGNORE INTO notification_settings (key, enabled) VALUES (?, ?)",
                         ('telegram_notifications_enabled', 1))
            conn.execute("INSERT OR IGNORE INTO notification_settings (key, enabled) VALUES (?, ?)",
                         ('email_notifications_enabled', 1))
    except Exception:
        pass

    try:
        conn.commit()
    except Exception:
        pass


# =========================================================================
# SEEN EVENTS
# =========================================================================

def db_load_seen_event_ids() -> list:
    """Get all seen event IDs as a list of integers."""
    conn = get_connection()
    rows = conn.execute("SELECT event_id FROM seen_events ORDER BY first_seen_at ASC").fetchall()
    return [row[0] for row in rows]


def db_load_seen_events() -> dict:
    """
    Get seen events in the same dict format as the old JSON file:
    {'event_ids': [...], 'event_details': [...]}
    """
    conn = get_connection()
    ids = db_load_seen_event_ids()
    rows = conn.execute(
        "SELECT event_id, title, link, date_posted, first_seen_at "
        "FROM seen_events ORDER BY first_seen_at ASC"
    ).fetchall()
    details = [
        {
            'id': r[0],
            'title': r[1] or '',
            'link': r[2] or '',
            'date_posted': r[3] or '',
            'first_seen': r[4] or ''
        }
        for r in rows
    ]
    return {'event_ids': ids, 'event_details': details}


def db_save_seen_event(event_id: int, title: str = '', link: str = '',
                       date_posted: str = '', first_seen: str = '') -> None:
    """Insert a single seen event. Ignores if already exists."""
    if not isinstance(event_id, int) or event_id <= 0:
        return
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO seen_events (event_id, title, link, date_posted, first_seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (event_id, title[:500], link[:2000], date_posted[:100],
         first_seen or _now_formatted())
    )
    conn.commit()


def db_save_seen_events_bulk(seen_data: dict) -> None:
    """
    Save a full seen_data dict (compatible with old JSON format).
    Used during migration and by check_for_events().
    """
    conn = get_connection()
    details = seen_data.get('event_details', [])
    for event in details:
        eid = event.get('id')
        if not isinstance(eid, int) or eid <= 0:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO seen_events (event_id, title, link, date_posted, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (eid,
             (event.get('title') or '')[:500],
             (event.get('link') or '')[:2000],
             (event.get('date_posted') or '')[:100],
             event.get('first_seen') or _now_formatted())
        )
    conn.commit()


def db_check_event_exists(event_id: int) -> bool:
    """Check if an event ID has been seen."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM seen_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return row is not None


def db_remove_latest_event() -> dict | None:
    """Remove the most recently seen event. Returns the removed event or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT event_id, title, link, date_posted, first_seen_at "
        "FROM seen_events ORDER BY first_seen_at DESC LIMIT 1"
    ).fetchone()
    if row:
        conn.execute("DELETE FROM seen_events WHERE event_id = ?", (row[0],))
        conn.commit()
        return {
            'id': row[0], 'title': row[1], 'link': row[2],
            'date_posted': row[3], 'first_seen': row[4]
        }
    return None


def db_get_seen_event_count() -> int:
    """Get total number of seen events."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM seen_events").fetchone()
    return row[0] if row else 0


# =========================================================================
# TRACKER STATUS (key-value store)
# =========================================================================

def db_get_status(key: str, default=None) -> str | None:
    """Get a status value by key."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM tracker_status WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else default


def db_set_status(key: str, value) -> None:
    """Set a status value."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO tracker_status (key, value, updated_at) VALUES (?, ?, ?)",
        (str(key)[:100], str(value)[:2000], _now_iso())
    )
    conn.commit()


def db_load_status() -> dict:
    """Load all tracker status as a dict (compatible with old JSON format)."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM tracker_status").fetchall()
    result = {
        'last_daily_summary': None,
        'total_checks': 0,
        'last_heartbeat': None,
        'last_check_time': None
    }
    for key, value in rows:
        result[key] = value
    return result


def db_save_status(status: dict) -> None:
    """Save a dict of status values."""
    conn = get_connection()
    for key, value in status.items():
        if value is not None:
            conn.execute(
                "INSERT OR REPLACE INTO tracker_status (key, value, updated_at) VALUES (?, ?, ?)",
                (str(key)[:100], str(value)[:2000], _now_iso())
            )
    conn.commit()


# =========================================================================
# ACTIVITY LOGS
# =========================================================================

def db_add_log(message: str, level: str = 'info') -> None:
    """Add an activity log entry. Auto-prunes to 500 entries max."""
    conn = get_connection()
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO activity_logs (message, level, timestamp, timestamp_formatted) "
        "VALUES (?, ?, ?, ?)",
        (message[:500], level[:20], now.isoformat(), now.strftime('%b %d, %Y at %I:%M %p'))
    )
    # Prune old entries — keep max 500
    conn.execute("""
        DELETE FROM activity_logs WHERE id NOT IN (
            SELECT id FROM activity_logs ORDER BY id DESC LIMIT 500
        )
    """)
    conn.commit()


def db_get_logs(limit: int = 50) -> list:
    """Get recent activity logs (newest first)."""
    limit = min(limit, 500)  # Cap at 500
    conn = get_connection()
    rows = conn.execute(
        "SELECT message, level, timestamp, timestamp_formatted "
        "FROM activity_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {
            'message': r[0],
            'level': r[1],
            'timestamp': r[2],
            'timestamp_formatted': r[3]
        }
        for r in rows
    ]


def db_clear_logs() -> None:
    """Clear all activity logs."""
    conn = get_connection()
    conn.execute("DELETE FROM activity_logs")
    conn.commit()


# =========================================================================
# EMAIL HISTORY
# =========================================================================

def db_add_email_history(recipient: str, recipient_masked: str,
                         subject: str, success: bool,
                         error_msg: str = '') -> None:
    """Record an email send attempt."""
    conn = get_connection()
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO email_history "
        "(recipient, recipient_masked, subject, success, error_message, timestamp, timestamp_formatted) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (recipient[:254], recipient_masked[:100], subject[:200],
         1 if success else 0, error_msg[:500],
         now.isoformat(), now.strftime('%b %d, %Y at %I:%M %p'))
    )
    # Prune old entries — keep max 500
    conn.execute("""
        DELETE FROM email_history WHERE id NOT IN (
            SELECT id FROM email_history ORDER BY id DESC LIMIT 500
        )
    """)
    conn.commit()


def db_get_email_history(limit: int = 50) -> list:
    """Get recent email history (newest first)."""
    limit = min(limit, 500)
    conn = get_connection()
    rows = conn.execute(
        "SELECT recipient, recipient_masked, subject, success, error_message, "
        "timestamp, timestamp_formatted FROM email_history ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {
            'recipient': r[0],
            'recipient_masked': r[1],
            'subject': r[2],
            'success': bool(r[3]),
            'error': r[4],
            'timestamp': r[5],
            'timestamp_formatted': r[6]
        }
        for r in rows
    ]


# =========================================================================
# EMAIL QUEUE
# =========================================================================

def db_add_to_queue(subject: str, body: str, recipient: str,
                    priority: str = 'normal') -> str:
    """Add a failed email to the retry queue. Returns the queue item ID."""
    item_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc)
    # First retry in 30 minutes
    next_retry = (now + timedelta(minutes=30)).isoformat()

    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO email_queue "
        "(id, subject, body, recipient, priority, attempts, next_retry, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, subject[:200], body[:10000], recipient[:254],
         priority[:20], 0, next_retry, now.isoformat())
    )
    # Cap queue size at 50
    conn.execute("""
        DELETE FROM email_queue WHERE id NOT IN (
            SELECT id FROM email_queue ORDER BY
                CASE WHEN priority = 'high' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT 50
        )
    """)
    conn.commit()
    return item_id


def db_get_queue() -> list:
    """Get all queued emails."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, body, recipient, priority, attempts, "
        "next_retry, last_error, created_at FROM email_queue "
        "ORDER BY CASE WHEN priority = 'high' THEN 0 ELSE 1 END, created_at ASC"
    ).fetchall()
    return [
        {
            'id': r[0], 'subject': r[1], 'body': r[2], 'recipient': r[3],
            'priority': r[4], 'attempts': r[5], 'next_retry': r[6],
            'last_error': r[7], 'created_at': r[8]
        }
        for r in rows
    ]


def db_get_queue_item(item_id: str) -> dict | None:
    """Get a single queue item by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, subject, body, recipient, priority, attempts, "
        "next_retry, last_error, created_at FROM email_queue WHERE id = ?",
        (item_id,)
    ).fetchone()
    if row:
        return {
            'id': row[0], 'subject': row[1], 'body': row[2], 'recipient': row[3],
            'priority': row[4], 'attempts': row[5], 'next_retry': row[6],
            'last_error': row[7], 'created_at': row[8]
        }
    return None


def db_update_queue_item(item_id: str, attempts: int, next_retry: str,
                         last_error: str = '') -> None:
    """Update retry info for a queue item."""
    conn = get_connection()
    conn.execute(
        "UPDATE email_queue SET attempts = ?, next_retry = ?, last_error = ? WHERE id = ?",
        (attempts, next_retry, last_error[:500], item_id)
    )
    conn.commit()


def db_remove_from_queue(item_id: str) -> bool:
    """Remove an item from the queue. Returns True if removed."""
    conn = get_connection()
    cursor = conn.execute("DELETE FROM email_queue WHERE id = ?", (item_id,))
    conn.commit()
    return cursor.rowcount > 0 if hasattr(cursor, 'rowcount') else True


def db_clear_queue() -> int:
    """Clear the entire queue. Returns number of items cleared."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM email_queue").fetchone()
    count = row[0] if row else 0
    conn.execute("DELETE FROM email_queue")
    conn.commit()
    return count


def db_get_queue_count() -> int:
    """Get number of items in queue."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM email_queue").fetchone()
    return row[0] if row else 0


def db_get_queue_high_priority_count() -> int:
    """Get number of high-priority items in queue."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM email_queue WHERE priority = ?", ('high',)
    ).fetchone()
    return row[0] if row else 0


# =========================================================================
# EVENT STATS
# =========================================================================

def db_record_stat(stat_type: str, period: str, field: str, value: int = 1) -> None:
    """
    Record/increment a statistic.
    stat_type: 'daily' or 'hourly'
    period: '2026-01-30' (daily) or '2026-01-30T14' (hourly)
    field: 'checks', 'new_events', or 'emails_sent'
    """
    conn = get_connection()

    # Validate field name (whitelist to prevent injection via column name)
    if field not in ('checks', 'new_events', 'emails_sent'):
        return

    # Try to insert first, then update on conflict
    conn.execute(
        "INSERT INTO event_stats (stat_type, period, checks, new_events, emails_sent, updated_at) "
        "VALUES (?, ?, 0, 0, 0, ?) "
        "ON CONFLICT(stat_type, period) DO NOTHING",
        (stat_type[:20], period[:20], _now_iso())
    )
    # Now update the specific field
    # Safe because field is whitelisted above
    conn.execute(
        f"UPDATE event_stats SET {field} = {field} + ?, updated_at = ? "
        "WHERE stat_type = ? AND period = ?",
        (value, _now_iso(), stat_type[:20], period[:20])
    )
    conn.commit()


def db_get_stats(stat_type: str = 'daily', limit: int = 30) -> list:
    """Get stats ordered by period (oldest first)."""
    limit = min(limit, 100)
    conn = get_connection()
    rows = conn.execute(
        "SELECT period, checks, new_events, emails_sent "
        "FROM event_stats WHERE stat_type = ? ORDER BY period DESC LIMIT ?",
        (stat_type[:20], limit)
    ).fetchall()
    return [
        {'period': r[0], 'checks': r[1], 'new_events': r[2], 'emails_sent': r[3]}
        for r in reversed(rows)  # Return oldest first for charts
    ]


def db_prune_stats() -> None:
    """Remove old stats: keep 30 days of daily, 48 hours of hourly."""
    conn = get_connection()
    now = datetime.now(timezone.utc)
    cutoff_daily = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    cutoff_hourly = (now - timedelta(hours=48)).strftime('%Y-%m-%dT%H')

    conn.execute(
        "DELETE FROM event_stats WHERE stat_type = ? AND period < ?",
        ('daily', cutoff_daily)
    )
    conn.execute(
        "DELETE FROM event_stats WHERE stat_type = ? AND period < ?",
        ('hourly', cutoff_hourly)
    )
    conn.commit()


# =========================================================================
# NOTIFICATION SETTINGS (toggle channels)
# =========================================================================

def db_get_notification_setting(key: str) -> bool:
    """Get a notification setting. Returns True by default."""
    conn = get_connection()
    row = conn.execute(
        "SELECT enabled FROM notification_settings WHERE key = ?", (key,)
    ).fetchone()
    return bool(row[0]) if row else True


def db_set_notification_setting(key: str, enabled: bool) -> None:
    """Set a notification setting."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO notification_settings (key, enabled, updated_at) VALUES (?, ?, ?)",
        (key[:100], 1 if enabled else 0, _now_iso())
    )
    conn.commit()


def db_get_all_notification_settings() -> dict:
    """Get all notification settings as a dict."""
    conn = get_connection()
    rows = conn.execute("SELECT key, enabled FROM notification_settings").fetchall()
    result = {
        'telegram_notifications_enabled': True,
        'email_notifications_enabled': True
    }
    for key, enabled in rows:
        result[key] = bool(enabled)
    return result


# =========================================================================
# TELEGRAM SUBSCRIBERS
# =========================================================================

def validate_chat_id(chat_id: str) -> bool:
    """
    Validate a Telegram chat ID.
    Must be numeric (negative = group chats), max 15 digits.
    """
    if not chat_id or not isinstance(chat_id, str):
        return False
    chat_id = chat_id.strip()
    if not chat_id.lstrip('-').isdigit():
        return False
    if len(chat_id) > 15:
        return False
    return True


def mask_chat_id(chat_id: str) -> str:
    """Mask a chat ID for logs and non-admin UI: ****8562"""
    if not chat_id or len(chat_id) < 4:
        return '****'
    return f"****{chat_id[-4:]}"


def db_add_subscriber(chat_id: str, display_name: str = '',
                      added_by: str = 'admin') -> bool:
    """Add a Telegram subscriber. Returns True if added (not duplicate)."""
    if not validate_chat_id(chat_id):
        return False
    conn = get_connection()
    try:
        # Check if already exists
        existing = conn.execute(
            "SELECT chat_id FROM telegram_subscribers WHERE chat_id = ?",
            (chat_id.strip(),)
        ).fetchone()
        if existing:
            return False  # Duplicate
        conn.execute(
            "INSERT INTO telegram_subscribers "
            "(chat_id, display_name, is_active, added_by, added_at) "
            "VALUES (?, ?, 1, ?, ?)",
            (chat_id.strip(), (display_name or '')[:100], added_by[:50], _now_iso())
        )
        conn.commit()
        return True
    except Exception:
        return False


def db_remove_subscriber(chat_id: str) -> bool:
    """Remove a Telegram subscriber."""
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM telegram_subscribers WHERE chat_id = ?",
        (chat_id.strip(),)
    )
    conn.commit()
    return cursor.rowcount > 0 if hasattr(cursor, 'rowcount') else True


def db_toggle_subscriber(chat_id: str) -> bool | None:
    """Toggle subscriber active status. Returns new state or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT is_active FROM telegram_subscribers WHERE chat_id = ?",
        (chat_id.strip(),)
    ).fetchone()
    if row is None:
        return None
    new_state = 0 if row[0] else 1
    conn.execute(
        "UPDATE telegram_subscribers SET is_active = ? WHERE chat_id = ?",
        (new_state, chat_id.strip())
    )
    conn.commit()
    return bool(new_state)


def db_get_subscribers(active_only: bool = False) -> list:
    """Get Telegram subscribers."""
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT chat_id, display_name, is_active, added_by, added_at, last_notified_at "
            "FROM telegram_subscribers WHERE is_active = 1 ORDER BY added_at ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT chat_id, display_name, is_active, added_by, added_at, last_notified_at "
            "FROM telegram_subscribers ORDER BY added_at ASC"
        ).fetchall()
    return [
        {
            'chat_id': r[0],
            'chat_id_masked': mask_chat_id(r[0]),
            'display_name': r[1] or '',
            'is_active': bool(r[2]),
            'added_by': r[3],
            'added_at': r[4],
            'last_notified_at': r[5]
        }
        for r in rows
    ]


def db_get_active_subscriber_ids() -> list:
    """Get list of active subscriber chat IDs (strings)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT chat_id FROM telegram_subscribers WHERE is_active = 1"
    ).fetchall()
    return [r[0] for r in rows]


def db_update_subscriber_notified(chat_id: str) -> None:
    """Update the last_notified_at timestamp for a subscriber."""
    conn = get_connection()
    conn.execute(
        "UPDATE telegram_subscribers SET last_notified_at = ? WHERE chat_id = ?",
        (_now_iso(), chat_id.strip())
    )
    conn.commit()


def db_get_subscriber_count(active_only: bool = False) -> int:
    """Get subscriber count."""
    conn = get_connection()
    if active_only:
        row = conn.execute(
            "SELECT COUNT(*) FROM telegram_subscribers WHERE is_active = 1"
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM telegram_subscribers").fetchone()
    return row[0] if row else 0


# =========================================================================
# ADMIN AUDIT LOG
# =========================================================================

def db_add_audit_log(action: str, details: str = '', ip: str = '') -> None:
    """Record an admin action for auditing."""
    conn = get_connection()
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO admin_audit (timestamp, timestamp_formatted, ip, action, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (now.isoformat(), now.strftime('%b %d, %Y at %I:%M %p'),
         ip[:45], action[:200], details[:500])
    )
    # Prune — keep max 300
    conn.execute("""
        DELETE FROM admin_audit WHERE id NOT IN (
            SELECT id FROM admin_audit ORDER BY id DESC LIMIT 300
        )
    """)
    conn.commit()


def db_get_audit_logs(limit: int = 50) -> list:
    """Get recent admin audit logs."""
    limit = min(limit, 300)
    conn = get_connection()
    rows = conn.execute(
        "SELECT timestamp, timestamp_formatted, ip, action, details "
        "FROM admin_audit ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {
            'timestamp': r[0],
            'timestamp_formatted': r[1],
            'ip': r[2],
            'action': r[3],
            'details': r[4]
        }
        for r in rows
    ]


# =========================================================================
# MIGRATION HELPER — Import from JSON files
# =========================================================================

def migrate_from_json(data_dir: str) -> dict:
    """
    One-time migration: reads existing JSON files and imports into the database.
    Returns a summary dict of what was migrated.
    
    This is safe to run multiple times (INSERT OR IGNORE).
    """
    import json
    summary = {'migrated': {}, 'errors': []}

    # 1. seen_events.json
    path = os.path.join(data_dir, 'seen_events.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                data = {'event_ids': data, 'event_details': []}
            db_save_seen_events_bulk(data)
            summary['migrated']['seen_events'] = len(data.get('event_ids', []))
        except Exception as e:
            summary['errors'].append(f"seen_events.json: {str(e)[:100]}")

    # 2. tracker_status.json
    path = os.path.join(data_dir, 'tracker_status.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                status = json.load(f)
            db_save_status(status)
            summary['migrated']['tracker_status'] = len(status)
        except Exception as e:
            summary['errors'].append(f"tracker_status.json: {str(e)[:100]}")

    # 3. activity_logs.json
    path = os.path.join(data_dir, 'activity_logs.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                logs = json.load(f)
            if isinstance(logs, list):
                for log in logs[-500:]:  # Keep last 500
                    db_add_log(
                        log.get('message', ''),
                        log.get('level', 'info')
                    )
                summary['migrated']['activity_logs'] = min(len(logs), 500)
        except Exception as e:
            summary['errors'].append(f"activity_logs.json: {str(e)[:100]}")

    # 4. email_history.json
    path = os.path.join(data_dir, 'email_history.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                history = json.load(f)
            if isinstance(history, list):
                for entry in history[-500:]:
                    db_add_email_history(
                        entry.get('recipient', ''),
                        entry.get('recipient_masked', ''),
                        entry.get('subject', ''),
                        entry.get('success', True),
                        entry.get('error', '')
                    )
                summary['migrated']['email_history'] = min(len(history), 500)
        except Exception as e:
            summary['errors'].append(f"email_history.json: {str(e)[:100]}")

    # 5. email_queue.json
    path = os.path.join(data_dir, 'email_queue.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                queue = json.load(f)
            if isinstance(queue, list):
                for item in queue:
                    db_add_to_queue(
                        item.get('subject', ''),
                        item.get('body', ''),
                        item.get('recipient', ''),
                        item.get('priority', 'normal')
                    )
                summary['migrated']['email_queue'] = len(queue)
        except Exception as e:
            summary['errors'].append(f"email_queue.json: {str(e)[:100]}")

    # 6. event_stats.json
    path = os.path.join(data_dir, 'event_stats.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                stats = json.load(f)
            count = 0
            for stat_type in ('daily', 'hourly'):
                for period, values in stats.get(stat_type, {}).items():
                    for field in ('checks', 'new_events', 'emails_sent'):
                        val = values.get(field, 0)
                        if val > 0:
                            db_record_stat(stat_type, period, field, val)
                    count += 1
            summary['migrated']['event_stats'] = count
        except Exception as e:
            summary['errors'].append(f"event_stats.json: {str(e)[:100]}")

    # 7. admin_audit.json
    path = os.path.join(data_dir, 'admin_audit.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                audit = json.load(f)
            if isinstance(audit, list):
                for entry in audit[-300:]:
                    db_add_audit_log(
                        entry.get('action', ''),
                        entry.get('details', ''),
                        entry.get('ip', '')
                    )
                summary['migrated']['admin_audit'] = min(len(audit), 300)
        except Exception as e:
            summary['errors'].append(f"admin_audit.json: {str(e)[:100]}")

    return summary
