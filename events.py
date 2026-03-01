"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Event Checking & Background Threads
=============================================================================
"""

import threading
import time
import requests
from datetime import datetime, timezone, timedelta

import config
from config import (
    CONFIG, API_URL, API_DIAGNOSTICS,
    CHECK_HISTORY, MAX_CHECK_HISTORY,
    stop_checker,
)
from utils import (
    console_log, log_activity,
    sanitize_string, validate_url,
    format_timestamp, parse_iso_timestamp,
)
from state import (
    load_seen_events, save_seen_events,
    load_status, save_status, record_stat,
    should_send_daily_summary, mark_daily_summary_sent,
    load_email_queue,
)
from notifications import (
    send_new_event_email, send_heartbeat,
    send_daily_summary_email, process_email_queue,
    notify_admin_alert,
)


def fetch_events() -> list | None:
    """Fetch events from API with detailed diagnostics."""
    start_time = time.time()
    API_DIAGNOSTICS['last_request_time'] = datetime.now(timezone.utc).isoformat()
    API_DIAGNOSTICS['total_api_calls'] = API_DIAGNOSTICS.get('total_api_calls', 0) + 1

    console_log("📡 Initiating API request to dubai-fleamarket.com...", "api")
    console_log(f"   └─ URL: {API_URL}", "debug")
    console_log("   └─ Method: GET | Timeout: 15s", "debug")

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

        console_log("✅ API Response received", "success")
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

            raw_date = event.get('date', '')
            date_posted = format_timestamp(raw_date) if raw_date else 'Unknown'

            event_info = {
                'id': event_id,
                'title': title,
                'date_posted': date_posted,
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
    status['total_new_events'] = CONFIG.get('total_new_events', 0)
    status['emails_sent'] = CONFIG.get('emails_sent', 0)
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
                    if config.EMAIL_QUEUE:
                        console_log("📬 Checking email retry queue...", "debug")
                        process_email_queue()
                    last_queue_check = now

            except RecursionError:
                consecutive_errors += 1
                log_activity(f"RecursionError in checker ({consecutive_errors}/{max_consecutive_errors})", "error")
                console_log("❌ RecursionError caught — breaking recursion cycle", "error")
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
                console_log("   └─ Full trace logged to console", "debug")
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


# ===== Startup Helpers =====

def start_background_checker():
    """Start the background checker thread."""
    if config.checker_thread is None or not config.checker_thread.is_alive():
        stop_checker.clear()
        config.checker_thread = threading.Thread(target=background_checker, daemon=True)
        config.checker_thread.start()


def watchdog_thread():
    """Watchdog that monitors and restarts the background checker if it dies."""
    console_log("🐕 Watchdog thread started - monitoring background checker", "debug")
    console_log("   └─ Check interval: 60 seconds", "debug")

    restart_count = 0

    while True:
        try:
            time.sleep(60)  # Check every minute

            is_alive = config.checker_thread is not None and config.checker_thread.is_alive()

            if not is_alive:
                restart_count += 1
                console_log(f"🔄 WATCHDOG: Background checker not running (restart #{restart_count})", "warning")
                console_log(f"   └─ Thread state: {'None' if config.checker_thread is None else 'Dead'}", "debug")
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
