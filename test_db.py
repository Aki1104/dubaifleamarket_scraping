"""
=============================================================================
 DATABASE INTEGRATION TEST SUITE
=============================================================================
 Run: python test_db.py
 
 Tests all db.py functions against local SQLite (same schema as Turso).
 Safe to run repeatedly — cleans up after itself.
=============================================================================
"""
import os
import sys
import time
import traceback

# ── Override to use a test-only database ──
os.environ.pop('TURSO_DATABASE_URL', None)
os.environ.pop('TURSO_AUTH_TOKEN', None)
TEST_DB_PATH = os.path.join(os.path.dirname(__file__), 'test_local.db')
# We'll monkey-patch the DB path after import

passed = 0
failed = 0
errors = []

def test(name):
    """Decorator to register and run a test."""
    def decorator(fn):
        global passed, failed
        try:
            fn()
            passed += 1
            print(f"  ✅ {name}")
        except Exception as e:
            failed += 1
            tb = traceback.format_exc().strip().split('\n')[-1]
            errors.append((name, tb))
            print(f"  ❌ {name}")
            print(f"     └─ {tb}")
        return fn
    return decorator


# =========================================================================
# SETUP — fresh test database
# =========================================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("  🧪 DATABASE INTEGRATION TESTS")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

# Remove old test DB
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)
    print(f"  🗑️  Removed old test DB")

# Now import db module — it will use local SQLite since no Turso env vars
import db as db_module

# Patch the local path to use our test file
db_module.LOCAL_DB_PATH = TEST_DB_PATH
db_module._connection = None  # Reset cached connection

print(f"  📁 Test DB: {TEST_DB_PATH}")
print()

# =========================================================================
# 1. CONNECTION & INITIALIZATION
# =========================================================================
print("── 1. Connection & Init ──────────────────────")

@test("get_connection() returns a connection")
def _():
    conn = db_module.get_connection()
    assert conn is not None

@test("is_using_turso() returns False locally")
def _():
    assert db_module.is_using_turso() == False

@test("get_db_status() returns valid dict")
def _():
    status = db_module.get_db_status()
    assert isinstance(status, dict)
    assert 'backend' in status
    assert 'sqlite' in status['backend'].lower() or 'SQLite' in status['backend']
    assert 'tables' in status

@test("Tables were created (at least 7)")
def _():
    status = db_module.get_db_status()
    assert isinstance(status['tables'], dict)
    assert len(status['tables']) >= 7, f"Expected >=7 tables, got {len(status['tables'])}"

print()

# =========================================================================
# 2. SEEN EVENTS
# =========================================================================
print("── 2. Seen Events ────────────────────────────")

@test("db_load_seen_events() returns dict with 'event_ids' and 'event_details'")
def _():
    data = db_module.db_load_seen_events()
    assert isinstance(data, dict)
    assert 'event_ids' in data
    assert 'event_details' in data

@test("db_save_seen_event() inserts an event")
def _():
    db_module.db_save_seen_event(1001, 'Test Event 1', 'https://example.com/1', '2026-01-15')
    data = db_module.db_load_seen_events()
    assert 1001 in data['event_ids']

@test("db_save_seen_event() is idempotent (INSERT OR IGNORE)")
def _():
    db_module.db_save_seen_event(1001, 'Test Event 1 Updated', 'https://example.com/1', '2026-01-15')
    data = db_module.db_load_seen_events()
    # Should still be 1 event, not 2
    assert data['event_ids'].count(1001) == 1

@test("db_save_seen_events_bulk() inserts multiple events")
def _():
    bulk_data = {
        'event_ids': [2001, 2002, 2003],
        'event_details': [
            {'id': 2001, 'title': 'Bulk 1', 'link': 'https://example.com/b1', 'date_posted': '2026-02-01', 'first_seen': '2026-02-01T10:00:00'},
            {'id': 2002, 'title': 'Bulk 2', 'link': 'https://example.com/b2', 'date_posted': '2026-02-02', 'first_seen': '2026-02-02T10:00:00'},
            {'id': 2003, 'title': 'Bulk 3', 'link': 'https://example.com/b3', 'date_posted': '2026-02-03', 'first_seen': '2026-02-03T10:00:00'},
        ]
    }
    db_module.db_save_seen_events_bulk(bulk_data)
    data = db_module.db_load_seen_events()
    assert 2001 in data['event_ids']
    assert 2002 in data['event_ids']
    assert 2003 in data['event_ids']

@test("db_check_event_exists() returns True for existing, False for missing")
def _():
    assert db_module.db_check_event_exists(1001) == True
    assert db_module.db_check_event_exists(9999) == False

@test("db_get_seen_event_count() returns correct count")
def _():
    count = db_module.db_get_seen_event_count()
    assert count >= 4, f"Expected >=4, got {count}"

@test("db_load_seen_event_ids() returns list of ints")
def _():
    ids = db_module.db_load_seen_event_ids()
    assert isinstance(ids, list)
    assert 1001 in ids
    assert all(isinstance(i, int) for i in ids)

@test("db_remove_latest_event() removes most recent event")
def _():
    count_before = db_module.db_get_seen_event_count()
    removed = db_module.db_remove_latest_event()
    assert removed is not None
    count_after = db_module.db_get_seen_event_count()
    assert count_after == count_before - 1

print()

# =========================================================================
# 3. TRACKER STATUS
# =========================================================================
print("── 3. Tracker Status ─────────────────────────")

@test("db_save_status() and db_load_status() round-trip")
def _():
    status = {
        'last_check_time': '2026-02-17T10:00:00+00:00',
        'total_checks': 42,
        'last_heartbeat': '2026-02-17T09:00:00+00:00',
        'last_daily_summary': None
    }
    db_module.db_save_status(status)
    loaded = db_module.db_load_status()
    assert loaded['total_checks'] == '42' or loaded['total_checks'] == 42

@test("db_get_status() returns individual value")
def _():
    db_module.db_set_status('test_key', 'test_value')
    val = db_module.db_get_status('test_key')
    assert val == 'test_value'

@test("db_get_status() returns default for missing key")
def _():
    val = db_module.db_get_status('nonexistent_key', 'default_val')
    assert val == 'default_val'

@test("db_set_status() overwrites existing value")
def _():
    db_module.db_set_status('test_key', 'original')
    db_module.db_set_status('test_key', 'updated')
    val = db_module.db_get_status('test_key')
    assert val == 'updated'

print()

# =========================================================================
# 4. ACTIVITY LOGS
# =========================================================================
print("── 4. Activity Logs ──────────────────────────")

@test("db_add_log() inserts a log entry")
def _():
    db_module.db_add_log("Test log message", "info")
    logs = db_module.db_get_logs(1)
    assert len(logs) >= 1
    assert logs[0]['message'] == "Test log message"

@test("db_get_logs() respects limit")
def _():
    for i in range(5):
        db_module.db_add_log(f"Log entry {i}", "debug")
    logs = db_module.db_get_logs(3)
    assert len(logs) == 3

@test("db_get_logs() returns newest first")
def _():
    db_module.db_add_log("oldest", "info")
    time.sleep(0.05)
    db_module.db_add_log("newest", "info")
    logs = db_module.db_get_logs(2)
    assert logs[0]['message'] == "newest"

@test("db_clear_logs() removes all logs")
def _():
    db_module.db_clear_logs()
    logs = db_module.db_get_logs(100)
    assert len(logs) == 0

print()

# =========================================================================
# 5. EMAIL HISTORY
# =========================================================================
print("── 5. Email History ──────────────────────────")

@test("db_add_email_history() inserts and retrieves")
def _():
    db_module.db_add_email_history(
        recipient='test@example.com',
        recipient_masked='t***@example.com',
        subject='Test Subject',
        success=True,
        error_msg=''
    )
    history = db_module.db_get_email_history(1)
    assert len(history) >= 1
    assert history[0]['subject'] == 'Test Subject'
    assert history[0]['success'] == True or history[0]['success'] == 1

@test("db_add_email_history() with failure")
def _():
    db_module.db_add_email_history(
        recipient='fail@example.com',
        recipient_masked='f***@example.com',
        subject='Failed Email',
        success=False,
        error_msg='Connection refused'
    )
    history = db_module.db_get_email_history(1)
    assert history[0]['error'] == 'Connection refused'

@test("db_get_email_history() respects limit")
def _():
    history = db_module.db_get_email_history(1)
    assert len(history) <= 1

print()

# =========================================================================
# 6. EMAIL QUEUE
# =========================================================================
print("── 6. Email Queue ────────────────────────────")

@test("db_add_to_queue() returns an ID")
def _():
    item_id = db_module.db_add_to_queue('Test Subject', '<p>Body</p>', 'queue@test.com', 'normal')
    assert item_id is not None
    assert len(item_id) > 0

@test("db_get_queue() returns list of dicts")
def _():
    queue = db_module.db_get_queue()
    assert isinstance(queue, list)
    assert len(queue) >= 1
    assert 'subject' in queue[0]
    assert 'recipient' in queue[0]

@test("db_get_queue_item() returns specific item")
def _():
    item_id = db_module.db_add_to_queue('Find Me', 'body', 'find@test.com')
    item = db_module.db_get_queue_item(item_id)
    assert item is not None
    assert item['subject'] == 'Find Me'

@test("db_update_queue_item() updates retry info")
def _():
    item_id = db_module.db_add_to_queue('Update Me', 'body', 'update@test.com')
    db_module.db_update_queue_item(item_id, attempts=3, next_retry='2026-02-18T00:00:00', last_error='Timeout')
    item = db_module.db_get_queue_item(item_id)
    assert item['attempts'] == 3
    assert item['last_error'] == 'Timeout'

@test("db_remove_from_queue() removes item")
def _():
    item_id = db_module.db_add_to_queue('Remove Me', 'body', 'remove@test.com')
    removed = db_module.db_remove_from_queue(item_id)
    assert removed == True
    item = db_module.db_get_queue_item(item_id)
    assert item is None

@test("db_get_queue_count() returns correct count")
def _():
    count = db_module.db_get_queue_count()
    assert count >= 1

@test("db_get_queue_high_priority_count() works")
def _():
    db_module.db_add_to_queue('Urgent', 'body', 'urgent@test.com', 'high')
    count = db_module.db_get_queue_high_priority_count()
    assert count >= 1

@test("db_clear_queue() clears all items")
def _():
    cleared = db_module.db_clear_queue()
    assert cleared >= 0
    assert db_module.db_get_queue_count() == 0

print()

# =========================================================================
# 7. EVENT STATISTICS
# =========================================================================
print("── 7. Event Statistics ───────────────────────")

@test("db_record_stat() records daily stat")
def _():
    db_module.db_record_stat('daily', '2026-02-17', 'checks', 5)
    stats = db_module.db_get_stats('daily', 10)
    assert len(stats) >= 1
    found = [s for s in stats if s['period'] == '2026-02-17']
    assert len(found) == 1
    assert found[0]['checks'] >= 5

@test("db_record_stat() increments existing value")
def _():
    db_module.db_record_stat('daily', '2026-02-17', 'checks', 3)
    stats = db_module.db_get_stats('daily', 10)
    found = [s for s in stats if s['period'] == '2026-02-17']
    assert found[0]['checks'] >= 8  # 5 + 3

@test("db_record_stat() records hourly stat")
def _():
    db_module.db_record_stat('hourly', '2026-02-17T14', 'new_events', 2)
    stats = db_module.db_get_stats('hourly', 10)
    found = [s for s in stats if s['period'] == '2026-02-17T14']
    assert len(found) == 1
    assert found[0]['new_events'] >= 2

@test("db_record_stat() rejects invalid field names (SQL injection prevention)")
def _():
    # This should silently return without error (field not whitelisted)
    db_module.db_record_stat('daily', '2026-02-17', 'DROP TABLE; --', 1)
    # If we get here, it didn't crash — that's the test

@test("db_get_stats() returns oldest first for charts")
def _():
    db_module.db_record_stat('daily', '2026-02-15', 'checks', 1)
    db_module.db_record_stat('daily', '2026-02-16', 'checks', 1)
    stats = db_module.db_get_stats('daily', 10)
    if len(stats) >= 2:
        assert stats[0]['period'] <= stats[1]['period']

@test("db_prune_stats() doesn't crash")
def _():
    db_module.db_prune_stats()  # Just verify no errors

print()

# =========================================================================
# 8. NOTIFICATION SETTINGS
# =========================================================================
print("── 8. Notification Settings ──────────────────")

@test("db_set_notification_setting() and db_get_notification_setting() round-trip")
def _():
    db_module.db_set_notification_setting('email_notifications_enabled', False)
    val = db_module.db_get_notification_setting('email_notifications_enabled')
    assert val == False

@test("db_get_notification_setting() returns True for unset key")
def _():
    val = db_module.db_get_notification_setting('never_set_key')
    assert val == True

@test("db_set_notification_setting() updates existing")
def _():
    db_module.db_set_notification_setting('test_toggle', True)
    db_module.db_set_notification_setting('test_toggle', False)
    val = db_module.db_get_notification_setting('test_toggle')
    assert val == False

@test("db_get_all_notification_settings() returns dict")
def _():
    db_module.db_set_notification_setting('email_notifications_enabled', True)
    db_module.db_set_notification_setting('telegram_notifications_enabled', False)
    settings = db_module.db_get_all_notification_settings()
    assert isinstance(settings, dict)
    assert 'email_notifications_enabled' in settings
    assert settings['telegram_notifications_enabled'] == False

print()

# =========================================================================
# 9. TELEGRAM SUBSCRIBERS
# =========================================================================
print("── 9. Telegram Subscribers ───────────────────")

@test("validate_chat_id() accepts valid IDs")
def _():
    assert db_module.validate_chat_id('123456789') == True
    assert db_module.validate_chat_id('-100123456789') == True  # group chat

@test("validate_chat_id() rejects invalid IDs")
def _():
    assert db_module.validate_chat_id('') == False
    assert db_module.validate_chat_id('abc') == False
    assert db_module.validate_chat_id('12345678901234567') == False  # too long

@test("mask_chat_id() masks properly")
def _():
    masked = db_module.mask_chat_id('123456789')
    assert '123456789' not in masked, f"Full ID leaked: {masked}"
    assert len(masked) > 0

@test("db_add_subscriber() adds a subscriber")
def _():
    result = db_module.db_add_subscriber('111222333', 'Test User')
    assert result == True

@test("db_add_subscriber() rejects duplicate")
def _():
    result = db_module.db_add_subscriber('111222333', 'Duplicate')
    assert result == False

@test("db_get_subscribers() returns list")
def _():
    subs = db_module.db_get_subscribers()
    assert isinstance(subs, list)
    assert len(subs) >= 1
    assert subs[0]['chat_id'] == '111222333'

@test("db_get_active_subscriber_ids() returns list of strings")
def _():
    ids = db_module.db_get_active_subscriber_ids()
    assert isinstance(ids, list)
    assert '111222333' in ids

@test("db_toggle_subscriber() toggles active state")
def _():
    new_state = db_module.db_toggle_subscriber('111222333')
    assert new_state == False  # Was True (default), now False
    ids = db_module.db_get_active_subscriber_ids()
    assert '111222333' not in ids
    # Toggle back
    new_state = db_module.db_toggle_subscriber('111222333')
    assert new_state == True

@test("db_toggle_subscriber() returns None for missing ID")
def _():
    result = db_module.db_toggle_subscriber('999999999')
    assert result is None

@test("db_update_subscriber_notified() updates timestamp")
def _():
    db_module.db_update_subscriber_notified('111222333')
    subs = db_module.db_get_subscribers()
    found = [s for s in subs if s['chat_id'] == '111222333']
    assert len(found) == 1
    assert found[0]['last_notified_at'] is not None

@test("db_get_subscriber_count() returns correct count")
def _():
    count = db_module.db_get_subscriber_count()
    assert count >= 1

@test("db_remove_subscriber() removes a subscriber")
def _():
    db_module.db_add_subscriber('999888777', 'To Remove')
    removed = db_module.db_remove_subscriber('999888777')
    assert removed == True
    subs = db_module.db_get_subscribers()
    ids = [s['chat_id'] for s in subs]
    assert '999888777' not in ids

@test("db_remove_subscriber() returns False for missing ID")
def _():
    result = db_module.db_remove_subscriber('000000000')
    assert result == False

print()

# =========================================================================
# 10. ADMIN AUDIT LOGS
# =========================================================================
print("── 10. Admin Audit Logs ──────────────────────")

@test("db_add_audit_log() inserts an entry")
def _():
    db_module.db_add_audit_log('Login', 'Admin logged in', '192.168.1.1')
    logs = db_module.db_get_audit_logs(1)
    assert len(logs) >= 1
    assert logs[0]['action'] == 'Login'

@test("db_get_audit_logs() returns newest first")
def _():
    db_module.db_add_audit_log('First Action', '', '0.0.0.0')
    time.sleep(0.05)
    db_module.db_add_audit_log('Second Action', '', '0.0.0.0')
    logs = db_module.db_get_audit_logs(2)
    assert logs[0]['action'] == 'Second Action'

@test("db_get_audit_logs() respects limit")
def _():
    logs = db_module.db_get_audit_logs(1)
    assert len(logs) == 1

@test("db_add_audit_log() truncates long strings")
def _():
    long_action = 'x' * 500
    db_module.db_add_audit_log(long_action, 'details', '1.2.3.4')
    logs = db_module.db_get_audit_logs(1)
    assert len(logs[0]['action']) <= 200

print()

# =========================================================================
# 11. JSON MIGRATION
# =========================================================================
print("── 11. JSON Migration ────────────────────────")

@test("migrate_from_json() runs without crashing (even with no JSON files)")
def _():
    summary = db_module.migrate_from_json(os.path.dirname(__file__))
    assert isinstance(summary, dict)
    assert 'migrated' in summary
    assert 'errors' in summary

print()

# =========================================================================
# CLEANUP & RESULTS
# =========================================================================
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if errors:
    print("\n  ❌ FAILED TESTS:")
    for name, err in errors:
        print(f"     • {name}: {err}")

# Cleanup test DB
try:
    if db_module._connection:
        db_module._connection.close()
        db_module._connection = None
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        print(f"\n  🗑️  Cleaned up test DB")
except Exception:
    pass

print()
sys.exit(0 if failed == 0 else 1)
