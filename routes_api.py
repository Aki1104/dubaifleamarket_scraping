"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — API Routes
=============================================================================
"""

import csv
import json
import smtplib
import socket
import threading
import time
from io import StringIO
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import request, jsonify, Response

import config
from config import (
    app, CONFIG, API_DIAGNOSTICS,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS, TELEGRAM_ADMIN_CHAT_ID,
    MY_EMAIL, MY_PASSWORD, TO_EMAIL,
    SMTP_SERVER, SMTP_PORT, SMTP_USE_IPV4,
    CHECK_HISTORY,
    EMAIL_RETRY_INTERVALS,
)
from utils import (
    rate_limit, require_admin, require_password,
    console_log, log_activity, log_admin_action,
    sanitize_string, validate_email, validate_url, mask_email,
    format_timestamp, parse_iso_timestamp,
    format_multi_timezone, format_multi_timezone_date,
    get_smtp_connection, set_last_smtp_error,
)
from state import (
    load_seen_events, save_seen_events,
    load_status, save_status,
    load_event_stats, record_stat,
    load_email_history,
    load_theme_settings, save_theme_settings,
    load_recipient_status, save_recipient_status,
    get_all_recipients, get_recipients,
    load_tracked_events, get_latest_event_summary,
    save_email_queue, build_email_queue_payload,
    mark_daily_summary_sent,
)
from notifications import (
    send_telegram, send_telegram_heartbeat, send_telegram_daily_summary,
    send_telegram_new_events, send_new_event_email,
    send_email, send_email_gmail,
    send_heartbeat, send_daily_summary_email,
    process_email_queue, notify_admin_alert,
    get_admin_chat_id,
)
from events import fetch_events, check_for_events
from db import (
    db_set_notification_setting, db_get_all_notification_settings,
    db_add_subscriber, db_remove_subscriber, db_toggle_subscriber,
    db_get_subscribers, db_get_active_subscriber_ids, db_get_subscriber_count,
    db_get_queue, db_remove_from_queue, db_clear_queue, db_clear_logs,
    validate_chat_id, mask_chat_id,
)


# ===== Tracked Events =====

@app.route('/api/events')
@rate_limit
@require_admin
def api_events():
    events = load_tracked_events()
    return jsonify({'events': events})


# ===== Status / Diagnostics =====

@app.route('/api/public-stats')
@rate_limit
def api_public_stats():
    """Public-safe stats for the landing page — no sensitive internal data."""
    seen_data = load_seen_events()

    # Build recent events (safe public fields only)
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
                'link': event.get('link') or event.get('url'),
            })

    # Safe console feed — only msg + time_short, no internal diagnostics
    safe_console = [
        {'msg': entry.get('msg', ''), 'time_short': entry.get('time_short', '')}
        for entry in config.SYSTEM_CONSOLE[:10]
        if isinstance(entry, dict) and entry.get('msg')
    ]

    return jsonify({
        'total_checks': CONFIG.get('total_checks', 0),
        'emails_sent': CONFIG.get('emails_sent', 0),
        'seen_count': len(seen_data.get('event_ids', [])),
        'email_queue_count': len(config.EMAIL_QUEUE),
        'latest_event': get_latest_event_summary(),
        'recent_events': recent_events,
        'visitor_stats': {
            'last_24h': len(config.VISITOR_LOG),
        },
        'console': safe_console,
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
        'logs': config.ACTIVITY_LOGS[:20],
        'next_check_seconds': next_check_seconds,
        'next_heartbeat_seconds': next_heartbeat_seconds,
        'email_queue_count': len(config.EMAIL_QUEUE),
        'latest_event': get_latest_event_summary(),
        'recent_events': recent_events,
        'visitor_stats': {
            'total': config.VISITOR_TOTAL,
            'last_24h': len(config.VISITOR_LOG)
        }
    })


@app.route('/api/console')
@rate_limit
@require_admin
def api_console():
    """API endpoint for system console logs."""
    return jsonify({
        'console': config.SYSTEM_CONSOLE[:100],
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
            'pending_count': len(config.EMAIL_QUEUE),
            'high_priority': len([e for e in config.EMAIL_QUEUE if e.get('priority') == 'high']),
            'items': config.EMAIL_QUEUE[:10]  # Show first 10 for debugging
        },
        'console_entries': len(config.SYSTEM_CONSOLE),
        'activity_log_entries': len(config.ACTIVITY_LOGS)
    })


# ===== Test & Diagnostic Actions =====

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
    config.SYSTEM_CONSOLE = []
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


# ===== Feature Toggles & Settings =====

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


# ===== Recipient Management =====

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


# ===== Telegram Subscriber Management =====

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


# ===== Manual Actions =====

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


# ===== Email Testing =====

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
    subject = "🧪 Test Email - Dubai Flea Market Tracker"
    body = f"""
{'=' * 60}
🧪 TEST EMAIL
{'=' * 60}

✅ This is a test email from Dubai Flea Market Tracker!

If you received this, your email configuration is working.

📊 SYSTEM INFO:
   • Sent at: {format_multi_timezone_date(now)}

🎯 You will receive instant notifications when new events are posted!

{'=' * 60}
🤖 Dubai Flea Market Tracker
{'=' * 60}
"""

    if send_email(subject, body, email):
        return jsonify({'success': True, 'message': 'Test email sent'})

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
        subject = "🧪 Test Email - Dubai Flea Market Tracker"
        body = f"""
{'=' * 60}
🧪 TEST EMAIL - Bulk Test
{'=' * 60}

✅ This is a test email from Dubai Flea Market Tracker!

📧 Testing all {len(recipients)} configured recipients.

📊 Sent at: {format_multi_timezone_date(now)}

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
📅 {format_multi_timezone_date()}
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
    """Remove latest event from DB and trigger a real 'new event' notification."""
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
    seen_data['event_ids'] = event_ids[:-1]
    seen_data['event_details'] = event_details[:-1]

    # Save the modified database
    save_seen_events(seen_data)
    console_log(f"✅ TEST NEW EVENT: Event removed from database ({len(event_ids)-1} events remaining)", "success")

    # Now trigger an immediate event check
    console_log("🔄 TEST NEW EVENT: Triggering immediate API check...", "info")

    try:
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


# ===== Telegram Testing =====

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

📅 {format_multi_timezone_date(now)}

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
📅 {format_multi_timezone_date(now)}

🌐 <b>Fetched from:</b> dubai-fleamarket.com
📊 <b>Events on site:</b> {len(events)} total

━━━━━━━━━━━━━━━━━━━━━━
<b>📍 Sample Events (First {len(test_events)}):</b>
━━━━━━━━━━━━━━━━━━━━━━
"""

        for i, event in enumerate(test_events, 1):
            raw_title = event.get('title', 'Untitled')
            if isinstance(raw_title, dict):
                raw_title = raw_title.get('rendered', 'Untitled')
            title = sanitize_string(str(raw_title), 60)
            link = event.get('link', '#')
            raw_date = event.get('date', '') or event.get('date_posted', '')
            date = format_timestamp(raw_date) if raw_date else 'Unknown'
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


# ===== Email Queue Management =====

@app.route('/api/retry-queue', methods=['POST'])
@rate_limit
@require_admin
def retry_email_queue():
    """Manually process the email retry queue."""
    before = len(config.EMAIL_QUEUE)
    process_email_queue()
    after = len(config.EMAIL_QUEUE)
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
    cleared = len(config.EMAIL_QUEUE)
    config.EMAIL_QUEUE = []
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
    removed = False
    for item in config.EMAIL_QUEUE[:]:
        if item.get('id') == item_id:
            config.EMAIL_QUEUE.remove(item)
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
    target = None
    for item in config.EMAIL_QUEUE:
        if item.get('id') == item_id:
            target = item
            break
    if not target:
        return jsonify({'success': False, 'message': 'Item not found'}), 404

    success, error = send_email_gmail(target.get('subject', ''), target.get('body', ''), target.get('recipient', ''), max_retries=1)
    if success:
        config.EMAIL_QUEUE.remove(target)
        save_email_queue()
        log_admin_action('email_queue_retry', f"id={item_id} success")
        return jsonify({'success': True, 'message': 'Email sent'})

    target['attempts'] = target.get('attempts', 0) + 1
    target['last_error'] = error or 'Send failed'
    target['next_retry'] = (datetime.now(timezone.utc) + timedelta(minutes=EMAIL_RETRY_INTERVALS[-1])).isoformat()
    save_email_queue()
    log_admin_action('email_queue_retry', f"id={item_id} failed")
    return jsonify({'success': False, 'message': 'Send failed'})


# ===== Theme =====

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


# ===== Live Events / History =====

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


# ===== Logs =====

@app.route('/api/logs')
@rate_limit
@require_admin
def get_logs():
    """Get activity logs."""
    return jsonify({'logs': config.ACTIVITY_LOGS})


@app.route('/api/clear-logs', methods=['POST'])
@rate_limit
@require_password
def clear_logs():
    """Clear activity logs - requires password."""
    config.ACTIVITY_LOGS = []
    try:
        db_clear_logs()
    except Exception as e:
        console_log(f"⚠️ Failed to clear DB logs: {e}", "warning")
    log_activity("🗑️ Logs cleared", "info")
    console_log("🗑️ Activity logs cleared by admin", "info")
    return jsonify({'success': True})


# ===== Statistics =====

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
        stats = config.EVENT_STATS['daily'].get(day, {'checks': 0, 'new_events': 0, 'emails_sent': 0})
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
        stats = config.EVENT_STATS['hourly'].get(hour, {'checks': 0, 'new_events': 0})
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


# ===== Export =====

@app.route('/api/export-logs')
@rate_limit
@require_admin
def export_logs():
    """Export activity logs as JSON or CSV."""
    format_type = request.args.get('format', 'json')
    console_log(f"📤 Exporting logs as {format_type.upper()}", "info")

    if format_type == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Timestamp', 'Level', 'Message'])

        for log in config.ACTIVITY_LOGS:
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
        return Response(
            json.dumps(config.ACTIVITY_LOGS, indent=2),
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
        return Response(
            json.dumps(events, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment;filename=tracked_events.json'}
        )


# ===== Search & Notifications =====

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


# ===== Consolidated Polling =====

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

    checker_alive = config.checker_thread is not None and config.checker_thread.is_alive()

    return jsonify({
        'config': CONFIG,
        'status': status,
        'seen_count': len(seen_data.get('event_ids', [])),
        'next_check_seconds': next_check_seconds,
        'next_heartbeat_seconds': next_heartbeat_seconds,
        'checker_running': checker_alive,
        'email_queue': build_email_queue_payload(limit=10),
        'latest_event': get_latest_event_summary(),
        'logs': config.ACTIVITY_LOGS[:20],
        'console': config.SYSTEM_CONSOLE[:100],
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
            'total': config.VISITOR_TOTAL,
            'last_24h': len(config.VISITOR_LOG)
        },
        'timestamp': now.isoformat()
    })
