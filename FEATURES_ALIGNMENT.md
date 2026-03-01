# 🚀 Features Alignment — Dubai Flea Market Scraper

> **Repository:** [github.com/Aki1104/dubaifleamarket_scraping](https://github.com/Aki1104/dubaifleamarket_scraping)  
> **Created:** February 17, 2026  
> **Status:** In Progress

---

## 📋 Overview

This document tracks the planned architecture improvements for the Dubai Flea Market Scraper project. Each phase is designed to be implemented sequentially, with security considerations baked into every step.

### Current Architecture
```
┌────────────────────┐      ┌──────────────────┐      ┌────────────────┐
│  Render (app.py)   │──────│  JSON Files      │──────│  GitHub Repo   │
│  Flask + Scheduler │      │  (local storage)  │      │  (persistence) │
└────────┬───────────┘      └──────────────────┘      └────────────────┘
         │
         ├──── Gmail SMTP ──── Recipients
         └──── Telegram Bot ── Chat IDs (env var)
```

### Target Architecture
```
┌────────────────────┐      ┌──────────────────┐
│  Render (app.py)   │──────│  Turso (LibSQL)  │
│  Flask + Scheduler │      │  (cloud database) │
└────────┬───────────┘      └──────────────────┘
         │
         ├──── Gmail SMTP ──── Recipients (toggle ON/OFF)
         └──── Telegram Bot ── Admin + Subscribers (managed via dashboard)
```

---

## 📦 Phases

| Phase | Feature | Status | Security Priority |
|-------|---------|--------|-------------------|
| **Phase 1** | [Turso Database Integration](#phase-1--turso-database-integration) | ✅ Complete | 🔴 High |
| **Phase 2** | [Remove GitHub Actions & JSON Files](#phase-2--remove-github-actions--json-files) | ✅ Complete | 🟡 Medium |
| **Phase 3** | [Notification Channel Toggles](#phase-3--notification-channel-toggles) | 🔲 Not Started | 🟡 Medium |
| **Phase 4** | [Multi-User Telegram Subscriber Management](#phase-4--multi-user-telegram-subscriber-management) | 🔲 Not Started | 🔴 High |
| **Phase 5** | [Dashboard UI Updates](#phase-5--dashboard-ui-updates) | 🔲 Not Started | 🟡 Medium |
| **Phase 6** | [Testing & Migration](#phase-6--testing--migration) | 🔲 Not Started | 🔴 High |

---

## Phase 1 — Turso Database Integration

### Goal
Replace all JSON file storage (`seen_events.json`, `tracker_status.json`, `activity_logs.json`, `email_history.json`, `event_stats.json`, `email_queue.json`) with a Turso (LibSQL) cloud database.

### Why Turso?
- **Free tier:** 9GB storage, 500M row reads/month — more than enough
- **SQLite-compatible:** Familiar query syntax, parameterized queries built-in
- **Edge replicas:** Low latency globally
- **No cold starts:** Always available (unlike Supabase free tier)
- **Simple setup:** One CLI command to create

### Files to Create/Modify
| File | Action | Description |
|------|--------|-------------|
| `db.py` | **CREATE** | Database layer — all queries, connection management |
| `requirements.txt` | **MODIFY** | Add `libsql-experimental>=0.0.34` |
| `.env` | **MODIFY** | Add `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` |
| `app.py` | **MODIFY** | Replace JSON read/write calls with `db.py` functions |

### Database Schema
```sql
-- Seen events (replaces seen_events.json)
CREATE TABLE IF NOT EXISTS seen_events (
    event_id INTEGER PRIMARY KEY,
    title TEXT,
    link TEXT,
    date_posted TEXT,
    first_seen_at TEXT DEFAULT (datetime('now'))
);

-- Tracker status (replaces tracker_status.json)
CREATE TABLE IF NOT EXISTS tracker_status (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Activity logs (replaces activity_logs.json)
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    level TEXT DEFAULT 'info',
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Email send history (replaces email_history.json)
CREATE TABLE IF NOT EXISTS email_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT NOT NULL,
    subject TEXT,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

-- Email retry queue (replaces email_queue.json)
CREATE TABLE IF NOT EXISTS email_queue (
    id TEXT PRIMARY KEY,
    subject TEXT,
    body TEXT,
    recipient TEXT,
    priority TEXT DEFAULT 'normal',
    attempts INTEGER DEFAULT 0,
    next_retry TEXT,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Event statistics (replaces event_stats.json)
CREATE TABLE IF NOT EXISTS event_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_type TEXT NOT NULL,
    period TEXT NOT NULL,
    checks INTEGER DEFAULT 0,
    new_events INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(stat_type, period)
);

-- Telegram subscribers (new - dynamic subscriber management)
CREATE TABLE IF NOT EXISTS telegram_subscribers (
    chat_id TEXT PRIMARY KEY,
    display_name TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    added_by TEXT DEFAULT 'admin',
    added_at TEXT DEFAULT (datetime('now')),
    last_notified_at TEXT
);

-- Notification settings (new - toggle channels)
CREATE TABLE IF NOT EXISTS notification_settings (
    key TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 🔒 Security Considerations — Phase 1

#### SQL Injection Prevention
- **MUST** use parameterized queries (`?` placeholders) for ALL user-supplied values
- **NEVER** use f-strings or `.format()` to build SQL queries
- Example:
  ```python
  # ✅ SAFE — parameterized query
  conn.execute("SELECT * FROM seen_events WHERE event_id = ?", (event_id,))

  # ❌ DANGEROUS — string interpolation
  conn.execute(f"SELECT * FROM seen_events WHERE event_id = {event_id}")
  ```

#### Connection Security
- `TURSO_AUTH_TOKEN` must be stored in environment variables, **never** in code or `.env` committed to Git
- Verify `.gitignore` includes `.env` and `local_data.db`
- Use HTTPS connection string (`libsql://...turso.io`) — never raw TCP
- Token rotation: Turso supports creating multiple tokens; rotate periodically

#### Data Validation
- Validate `event_id` is an integer before querying
- Sanitize `title`, `link`, `date_posted` (strip HTML, limit length)
- Limit query result sets (always use `LIMIT`) to prevent memory exhaustion
- Log pruning: Enforce max 500 log entries to prevent unbounded table growth

#### Fallback Strategy
- If Turso is unreachable, fall back to local SQLite file (`local_data.db`)
- Log the fallback event and notify admin via Telegram
- Don't crash the app if the database is temporarily unavailable

### Acceptance Criteria
- [ ] All 6 JSON files replaced with database tables
- [ ] All queries use parameterized statements (zero string interpolation)
- [ ] Connection errors gracefully handled with local SQLite fallback
- [ ] `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` stored only in env vars
- [ ] `.gitignore` updated for `local_data.db`
- [ ] Existing dashboard API endpoints return identical response shapes

---

## Phase 2 — Remove GitHub Actions & JSON Files

### Goal
Remove the GitHub Actions workflow and JSON file persistence since Turso now handles all data storage.

### Why Remove?
- GitHub Actions was only needed to `git commit` + `git push` JSON data back to the repo
- With a database, data persists server-side — no need for repo-as-storage
- Removes attack surface (GitHub token, repo write access from CI)
- Simplifies deployment: only Render + Turso, no GitHub CI dependency

### Files to Delete
| File | Reason |
|------|--------|
| `.github/workflows/check_events.yml` | No longer needed — scheduler runs in `app.py` |
| `event_tracker.py` | Duplicated by `check_for_events()` in `app.py` |
| `seen_events.json` | Replaced by `seen_events` table |
| `tracker_status.json` | Replaced by `tracker_status` table |
| `activity_logs.json` | Replaced by `activity_logs` table |
| `email_history.json` | Replaced by `email_history` table |
| `email_queue.json` | Replaced by `email_queue` table |
| `event_stats.json` | Replaced by `event_stats` table |

### Files to Modify
| File | Change |
|------|--------|
| `app.py` | Remove all `json.load()` / `json.dump()` / `atomic_json_write()` calls for data files |
| `app.py` | Remove `DATA_DIR` path references for deleted files |
| `.gitignore` | Add `local_data.db`, remove JSON file entries if any |
| `README.md` | Update architecture diagram |

### 🔒 Security Considerations — Phase 2

#### Secrets Cleanup
- Remove `GH_TOKEN` / `GITHUB_TOKEN` from Render environment variables if only used for Actions
- Audit remaining env vars — remove anything no longer needed
- Ensure `SECRET_PASSWORD` is still set and strong (used for dashboard auth)

#### Data Migration
- Before deleting JSON files, run a one-time migration script to import existing data into Turso
- Verify row counts match after migration
- Keep a local backup of JSON files for 30 days before permanent deletion

#### Reduced Attack Surface
- No more GitHub write tokens in CI
- No more automatic commits to the repo (prevents supply chain attacks via compromised workflows)

### Acceptance Criteria
- [ ] All JSON data successfully migrated to Turso
- [ ] GitHub Actions workflow deleted
- [ ] `event_tracker.py` deleted
- [ ] All JSON data files deleted (after migration verified)
- [ ] No remaining references to deleted files in codebase
- [ ] App starts and runs correctly with database-only storage
- [ ] `GH_TOKEN` removed from Render env vars (if applicable)

---

## Phase 3 — Notification Channel Toggles

### Goal
Add independent ON/OFF toggles for Email (Gmail SMTP) and Telegram notification channels. When a channel is OFF, no messages are sent through it AND no errors from that channel should appear in the other channel.

### Current Behavior
- Both Gmail and Telegram are always active
- If Gmail SMTP fails, the error is often sent to Telegram (noise)
- No way to disable one channel without code changes

### Target Behavior
| Gmail Toggle | Telegram Toggle | Behavior |
|:---:|:---:|---|
| ✅ ON | ✅ ON | Full functionality — both channels send notifications |
| ❌ OFF | ✅ ON | Only Telegram sends alerts. No SMTP calls = no SMTP errors in Telegram |
| ✅ ON | ❌ OFF | Only Gmail sends alerts. Telegram errors silently skipped |
| ❌ OFF | ❌ OFF | No notifications. Admin warned in logs, dashboard shows status |

### New Config Keys
```python
CONFIG = {
    # ...existing keys...
    'telegram_notifications_enabled': True,   # NEW
    'email_notifications_enabled': True,       # NEW
}
```

### Functions to Guard
| Function | Guard With |
|----------|-----------|
| `send_new_event_email()` | Check `email_notifications_enabled` before SMTP call |
| `send_telegram_new_events()` | Check `telegram_notifications_enabled` before API call |
| `send_heartbeat()` | Check both toggles independently |
| `send_telegram_heartbeat()` | Check `telegram_notifications_enabled` |
| `send_telegram_daily_summary()` | Check `telegram_notifications_enabled` |
| `notify_admin_alert()` | Check `telegram_notifications_enabled` |

### 🔒 Security Considerations — Phase 3

#### Toggle Persistence
- Store toggle state in the database (`notification_settings` table), not just in-memory `CONFIG`
- On app restart, load saved toggle state from database
- Prevents toggles resetting to defaults on Render redeploy

#### Authorization
- Toggle endpoints MUST require `@require_password` decorator (already exists)
- Log all toggle changes with `log_admin_action()` for audit trail
- Rate limit toggle API to prevent abuse

#### Edge Case: Both Channels Disabled
- If both channels are OFF, log a warning every check cycle
- Dashboard should show a prominent warning banner

#### No Silent Failures
- When a channel is toggled OFF, explicitly log: `"Email notifications disabled by admin"`
- Confirm the skip in activity logs

### Acceptance Criteria
- [ ] Two independent toggle switches on the dashboard
- [ ] Toggles persist across app restarts (stored in database)
- [ ] When Gmail is OFF, zero SMTP calls are made (verified in logs)
- [ ] When Gmail is OFF, zero SMTP errors appear in Telegram
- [ ] When Telegram is OFF, zero Telegram API calls are made
- [ ] Both-OFF scenario shows warning banner on dashboard
- [ ] All toggle changes logged with `log_admin_action()`
- [ ] Toggles protected by `@require_password`

---

## Phase 4 — Multi-User Telegram Subscriber Management

### Goal
Support multiple Telegram users as subscribers. Admin receives everything (alerts + errors). Regular subscribers receive only new event alerts — never errors, heartbeats, or system messages.

### Message Routing Matrix
| Message Type | Admin | Regular Subscribers |
|:---|:---:|:---:|
| 🆕 New event alerts | ✅ | ✅ |
| ❤️ Heartbeat status | ✅ | ❌ |
| 📊 Daily summary | ✅ | ❌ |
| 🚨 Error alerts | ✅ | ❌ |
| 🔧 System notifications | ✅ | ❌ |
| ✅ Test notifications | ✅ | ❌ |

### Dynamic Subscriber Management
Database-backed subscriber list (in addition to env var `TELEGRAM_CHAT_IDS`):

```sql
CREATE TABLE IF NOT EXISTS telegram_subscribers (
    chat_id TEXT PRIMARY KEY,
    display_name TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    added_by TEXT DEFAULT 'admin',
    added_at TEXT DEFAULT (datetime('now')),
    last_notified_at TEXT
);
```

### New API Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/telegram-subscribers` | GET | `@require_admin` | List all subscribers |
| `/api/telegram-subscribers/add` | POST | `@require_password` | Add subscriber by chat ID |
| `/api/telegram-subscribers/remove` | POST | `@require_password` | Remove a subscriber |
| `/api/telegram-subscribers/toggle` | POST | `@require_password` | Enable/disable a subscriber |

### Subscriber Onboarding Flow
```
1. New user opens Telegram
2. Searches for the bot (@YourBotName)
3. Clicks "Start" / sends any message
4. Gets their chat ID from @userinfobot
5. Gives chat ID to admin
6. Admin adds via dashboard → POST /api/telegram-subscribers/add
7. Bot sends verification message to new subscriber
8. Subscriber receives future event alerts
```

### 🔒 Security Considerations — Phase 4

#### Chat ID Validation
- Chat IDs must be numeric strings only — reject anything else
- Validate with: `chat_id.strip().lstrip('-').isdigit()` (negative IDs = group chats)
- Maximum length check: chat IDs are typically 7-13 digits
- **Never** store or process chat IDs that fail validation

#### Preventing Unauthorized Subscription
- Only admins can add subscribers (via password-protected endpoint)
- Subscribers cannot self-register (no public `/subscribe` endpoint)
- Verification message sent on add — confirms the chat ID is real and the bot can reach it
- If verification fails, the subscriber is NOT added

#### Subscriber Data Privacy
- Chat IDs are PII — treat accordingly
- Don't expose full chat IDs in public API responses without authentication
- Don't log full chat IDs in activity logs — use last 4 digits: `****8562`
- Admin-only endpoint to view full subscriber list

#### SQL Injection (Subscriber Endpoints)
- All subscriber queries MUST use parameterized statements
- `display_name` field is user-supplied text — sanitize and limit to 100 chars
- Never include subscriber-supplied text directly in SQL

### Acceptance Criteria
- [ ] Admin can add/remove subscribers from dashboard
- [ ] Subscribers receive ONLY new event alerts (no errors, heartbeats, system msgs)
- [ ] Admin receives ALL message types
- [ ] Chat ID validation rejects non-numeric and excessively long values
- [ ] Verification message sent on subscriber add
- [ ] Failed verification prevents subscriber addition
- [ ] All subscriber queries use parameterized SQL
- [ ] Chat IDs masked in activity logs (`****8562`)
- [ ] Subscriber endpoints protected by `@require_password`

---

## Phase 5 — Dashboard UI Updates

### Goal
Update the dashboard to reflect all new features: database status, notification toggles, subscriber management panel.

### New Dashboard Sections

#### 1. Database Status Card
- Connection status (Turso cloud / local SQLite fallback)
- Row counts per table
- Last sync timestamp

#### 2. Notification Channels Panel
- Toggle switch for Telegram (ON/OFF)
- Toggle switch for Email/Gmail (ON/OFF)
- Warning banner when both are OFF
- Last successful send timestamp per channel

#### 3. Subscriber Management Panel
- Table of all subscribers (chat ID masked, display name, status, added date)
- "Add Subscriber" button → modal with chat ID input
- "Remove" and "Disable" buttons per subscriber
- Subscriber count badge in header

### 🔒 Security Considerations — Phase 5

#### XSS Prevention
- All user-supplied data (subscriber names, log messages) must be HTML-escaped before rendering
- Jinja2 auto-escapes by default — verify `autoescape=True` in Flask config
- Never use `| safe` filter on user-supplied content
- CSP headers already present — verify they block inline scripts

#### Sensitive Data in HTML
- Don't embed `TURSO_AUTH_TOKEN`, `TELEGRAM_BOT_TOKEN`, or `SECRET_PASSWORD` in HTML source
- Chat IDs in subscriber table should be masked: `****8562`
- Database connection string in status card: show host only, not token

### Acceptance Criteria
- [ ] Database status card shows connection health
- [ ] Notification toggles are functional and visually clear
- [ ] Subscriber management panel allows add/remove/disable
- [ ] All user-supplied data is HTML-escaped
- [ ] No secrets visible in page source
- [ ] Chat IDs masked in subscriber table
- [ ] Warning banner appears when both notification channels are OFF
- [ ] Mobile-responsive layout for all new sections

---

## Phase 6 — Testing & Migration

### Goal
Ensure smooth transition from JSON files to Turso database with zero data loss, and verify all security measures work correctly.

### Migration Plan

#### Step 1: One-Time Data Migration Script
```python
# migrate_json_to_db.py (run once, then delete)
# Reads all JSON files → inserts into Turso tables
# Verifies row counts match
# Creates backup of JSON files before deletion
```

#### Step 2: Parallel Running (1 Week)
- Keep JSON files as read-only backup
- All writes go to database only
- Compare data between JSON and DB daily
- If discrepancy found, investigate before proceeding

#### Step 3: Cutover
- Delete JSON files from repo
- Delete GitHub Actions workflow
- Remove `event_tracker.py`
- Update `README.md` and documentation

### Testing Checklist

#### Functional Tests
- [ ] New event detection works with database storage
- [ ] Email notifications send correctly when toggled ON
- [ ] Email notifications are completely silent when toggled OFF
- [ ] Telegram notifications send to all subscribers
- [ ] Telegram notifications skip subscribers when toggled OFF
- [ ] Admin receives error alerts, subscribers do not
- [ ] Heartbeat sends to admin only
- [ ] Daily summary sends to admin only
- [ ] Dashboard displays all data correctly from database
- [ ] Subscriber add/remove works from dashboard
- [ ] Toggle states persist across app restart

#### Security Tests
- [ ] SQL injection attempted on all input fields — all rejected
- [ ] Invalid chat IDs rejected (letters, symbols, too long)
- [ ] Unauthenticated requests to protected endpoints return 401/403
- [ ] Rate limiting triggers on rapid requests
- [ ] No secrets visible in API responses or HTML source
- [ ] XSS payloads in subscriber names are escaped in dashboard
- [ ] Database connection falls back to local SQLite on Turso outage
- [ ] Turso auth token not logged anywhere

### 🔒 Security Considerations — Phase 6

#### Migration Script Security
- Migration script should be run locally or in a secure environment, not via public endpoint
- Delete the migration script after use — don't leave it in the repo
- Backup JSON files to a private location (not in the public repo)

#### Rollback Plan
- If Turso has extended outage: local SQLite fallback activates automatically
- If data corruption occurs: restore from JSON backup files
- If migration script has bug: JSON files are untouched (read-only migration)

### Acceptance Criteria
- [ ] All existing JSON data successfully migrated to Turso
- [ ] Zero data loss verified (row counts match)
- [ ] All functional tests pass
- [ ] All security tests pass
- [ ] GitHub Actions removed, app runs independently on Render + Turso
- [ ] `README.md` updated with new architecture
- [ ] Migration script deleted after successful migration

---

## 🔒 Global Security Checklist

These security practices apply across ALL phases:

### Environment Variables
- [ ] `TURSO_DATABASE_URL` — in Render env vars only
- [ ] `TURSO_AUTH_TOKEN` — in Render env vars only
- [ ] `TELEGRAM_BOT_TOKEN` — in Render env vars only
- [ ] `TELEGRAM_ADMIN_CHAT_ID` — in Render env vars only
- [ ] `ADMIN_PASSWORD` — in Render env vars only, strong (16+ chars)
- [ ] `.env` file in `.gitignore`
- [ ] No secrets in any committed file

### SQL Safety
- [ ] Every query uses `?` parameterized placeholders
- [ ] Zero string interpolation in SQL
- [ ] All user inputs validated before querying
- [ ] `LIMIT` on all `SELECT` queries to prevent memory exhaustion

### API Security
- [ ] All state-changing endpoints require `@require_password`
- [ ] Admin-only endpoints use `@require_admin`
- [ ] Rate limiting on all API endpoints
- [ ] No sensitive data in error responses

### Telegram Security
- [ ] Bot token never exposed in responses or logs
- [ ] Chat IDs masked in logs and non-admin UI
- [ ] Subscriber verification on add (test message)
- [ ] Message routing enforced (subscribers ≠ admin messages)

### Web Security
- [ ] CSP headers set (already present in `app.py`)
- [ ] XSS prevention via Jinja2 auto-escaping
- [ ] No inline JavaScript with user data
- [ ] HTTPS enforced (Render provides this)

---

## 📅 Timeline Estimate

| Phase | Estimated Effort | Dependencies |
|-------|-----------------|--------------|
| Phase 1 | 2-3 hours | Turso account setup |
| Phase 2 | 1 hour | Phase 1 complete |
| Phase 3 | 1-2 hours | Phase 1 complete |
| Phase 4 | 2-3 hours | Phase 1 complete |
| Phase 5 | 2-3 hours | Phase 3 & 4 complete |
| Phase 6 | 1-2 hours | All phases complete |
| **Total** | **~10-14 hours** | |

---

## 📝 Notes

- Phases 2, 3, and 4 can be worked on in parallel after Phase 1 is done
- Phase 5 (UI) should be last before Phase 6 (testing) since it depends on all backend changes
- If Turso setup is blocked, all other phases can still be developed against local SQLite
- Keep this document updated as phases are completed — check boxes and update status column
