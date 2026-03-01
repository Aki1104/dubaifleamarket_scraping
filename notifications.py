"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Notifications (Email + Telegram)
=============================================================================
All email sending, Telegram messaging, email queue processing, and
notification orchestration lives here.
=============================================================================
"""

import smtplib
import socket
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

import config
from config import (
    CONFIG,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, TELEGRAM_ADMIN_CHAT_ID,
    MY_EMAIL, MY_PASSWORD, TO_EMAIL,
    EMAIL_RETRY_INTERVALS, MAX_EMAIL_AGE_HOURS,
)
from utils import (
    console_log, log_activity,
    sanitize_string, validate_email, mask_email,
    set_last_smtp_error, get_smtp_connection,
    parse_iso_timestamp, format_timestamp,
    format_multi_timezone, format_multi_timezone_date,
)
from state import (
    load_seen_events, load_status, save_status, record_stat,
    add_to_email_history,
    should_send_daily_summary, mark_daily_summary_sent,
    get_recipients, get_all_recipients,
    save_email_queue,
)
from db import (
    db_get_active_subscriber_ids,
    db_add_to_queue, db_get_queue, db_update_queue_item,
    db_remove_from_queue, db_get_queue_count,
)


# ===== Telegram Helpers =====

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


# ===== Send Telegram =====

def send_telegram(message: str, chat_id: str | None = None) -> tuple:
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
                    console_log("   └─ Possible cause: invalid chat_id or bad HTML formatting", "debug")
                elif response.status_code == 403:
                    console_log("   └─ Bot was blocked by user or chat not found", "debug")
                elif response.status_code == 401:
                    console_log("   └─ Invalid bot token", "debug")
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


# ===== Admin Alert (Telegram-only, recursion-safe) =====

def notify_admin_alert(message: str, subject: str = 'Admin Alert') -> bool:
    """Best-effort admin alert via Telegram to ADMIN ONLY.

    Error/status messages are sent ONLY to TELEGRAM_ADMIN_CHAT_ID.
    Regular subscribers never receive error alerts.
    Uses Telegram ONLY — never calls send_email to prevent recursion loops.
    """
    if config._admin_alert_in_progress:
        console_log("⚠️ notify_admin_alert skipped (recursion guard)", "debug")
        return False

    config._admin_alert_in_progress = True
    try:
        if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID:
            success, _ = send_telegram(message, chat_id=TELEGRAM_ADMIN_CHAT_ID)
            if success:
                return True
            console_log("⚠️ Admin alert Telegram failed — no email fallback (prevents recursion)", "warning")
        return False
    finally:
        config._admin_alert_in_progress = False


# ===== Telegram Notification Types =====

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

    import re as _re

    def _clean(text, maxlen=120):
        """Strip HTML tags and truncate."""
        if not text:
            return ''
        return _re.sub(r'<[^>]+>', '', str(text)).strip()[:maxlen]

    message = (
        f"\U0001f6a8 <b>NEW EVENT{'S' if len(events) > 1 else ''} DETECTED!</b>\n"
        f"\U0001f3af <b>{len(events)} new Dubai Flea Market listing{'s' if len(events) > 1 else ''} just went live!</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
    )

    for i, event in enumerate(events, 1):
        title = _clean(event.get('title', 'Untitled'), 80)
        link = event.get('link', '')
        date_posted = _clean(event.get('date_posted', ''), 40)
        desc = _clean(event.get('description') or event.get('excerpt') or '', 150)
        categories = event.get('categories') or event.get('tags') or []
        if isinstance(categories, list):
            categories = ', '.join(str(c) for c in categories[:3])

        message += f"\n\U0001f4cd <b>Event {i}: {title}</b>\n"
        if date_posted:
            message += f"   \U0001f4c5 Posted: {date_posted}\n"
        if categories:
            message += f"   \U0001f3f7 Category: {categories}\n"
        if desc:
            raw_desc = str(event.get('description') or '')
            overflow = len(_re.sub(r'<[^>]+>', '', raw_desc).strip()) > 150
            message += f"   \U0001f4dd {desc}{'...' if overflow else ''}\n"
        message += f"   \U0001f517 <a href=\"{link}\">Open Event Page</a>\n"
        if i < len(events):
            message += "\n   \u2500 \u2500 \u2500 \u2500 \u2500 \u2500 \u2500 \u2500 \u2500\n"

    interval = CONFIG.get('check_interval_minutes', 15)
    message += (
        f"\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\u23f0 Detected: {format_multi_timezone(now)}\n"
        f"\U0001f50d Next check: in ~{interval} min\n"
        f"\U0001f4f1 Tap a link above to view full details!\n\n"
        f"\U0001f916 <i>Dubai Flea Market Tracker</i>"
    )

    console_log(f"📱 Sending Telegram notification for {len(events)} event(s)", "info")

    # Send to ALL chat IDs (env-configured + DB subscribers + admin)
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
    console_log(f"📱 Event notification sent to {success_count}/{len(all_ids)} chat(s)", "success" if success else "warning")
    if not success:
        log_activity(f"📱 Telegram failed for new events: {last_error}", "warning")
        notify_admin_alert(f"Telegram failed for new event alerts: {last_error}", "Telegram Alert Failure")
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
   • Current: {format_multi_timezone(now)}
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


def send_telegram_daily_summary() -> bool:
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

    # Late import to break circular dependency (events → notifications → events)
    from events import fetch_events
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
⏰ {format_multi_timezone(now)}

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


# ===== Email Sending =====

def send_email_gmail(subject, body, recipient, max_retries=3):
    """Send email via Gmail SMTP (may be blocked on cloud hosts like Render)."""
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

        except smtplib.SMTPException as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"SMTP error: {last_error}")
            console_log(f"⚠️ SMTP error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(3)
                continue
        except (OSError, socket.error) as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"Network error: {last_error}")
            console_log(f"⚠️ Network error (attempt {attempt}): {last_error}", "warning")
            if attempt < max_retries:
                time.sleep(5 * attempt)
                continue
        except Exception as e:
            last_error = str(e)[:50]
            set_last_smtp_error(f"Gmail error: {last_error}")
            console_log(f"❌ Gmail error: {last_error}", "error")
            break

    return False, last_error


def send_email_direct(subject, body, recipient):
    """Direct email send without queueing using Gmail SMTP."""
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
        now = datetime.now(timezone.utc)
        should_log = True
        if config.LAST_GMAIL_CONFIG_LOG_AT:
            delta = (now - config.LAST_GMAIL_CONFIG_LOG_AT).total_seconds()
            should_log = delta > 300

        if should_log:
            log_activity("Gmail not configured", "error")
            set_last_smtp_error("Gmail not configured")
            config.LAST_GMAIL_CONFIG_LOG_AT = now

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


# ===== Email Queue =====

def add_to_email_queue(subject, body, recipient, priority='normal'):
    """Add a failed email to the retry queue (database-backed)."""
    try:
        db_add_to_queue(subject, body, recipient, priority)
        config.EMAIL_QUEUE = db_get_queue()  # Refresh in-memory copy
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
            notify_admin_alert(
                f"📧 Email permanently failed after {MAX_EMAIL_AGE_HOURS}h of retries.\n"
                f"To: {mask_email(item['recipient'])}\n"
                f"Subject: {item['subject'][:50]}",
                "Email Expired"
            )
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
    config.EMAIL_QUEUE[:] = db_get_queue()


# ===== Notification Orchestration =====

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
    body += f"\n⏰ {format_multi_timezone()}"

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
    """Send heartbeat via Telegram to admin. Confirms bot is alive."""
    if not CONFIG['heartbeat_enabled']:
        return False

    # Heartbeat is Telegram-only (instant, free, reliable)
    result = send_telegram_heartbeat()
    return result


def send_daily_summary_email():
    """Send daily summary email."""
    # Send via Telegram first (instant, free, reliable)
    telegram_success = send_telegram_daily_summary()

    console_log("📊 Generating daily summary...", "info")
    now = datetime.now(timezone.utc)
    seen_data = load_seen_events()

    # Late import to break circular dependency (events → notifications → events)
    from events import fetch_events
    events = fetch_events()

    subject = f"📊 Dubai Flea Market Daily Summary - {now.strftime('%B %d, %Y')}"

    event_count = len(events) if events else 0
    seen_count = len(seen_data.get('event_ids', []))

    body = f"""
{'=' * 60}
📊 DAILY SUMMARY - {now.strftime('%A, %B %d, %Y')}
⏰ {format_multi_timezone(now)}
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
⏰ {format_multi_timezone(now)}
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
