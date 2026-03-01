"""
=============================================================================
🌐 DUBAI FLEA MARKET TRACKER — Page Routes (HTML)
=============================================================================
"""

from datetime import datetime, timezone, timedelta
from flask import render_template, request, session, redirect, url_for, jsonify

import config
from config import (
    app, CONFIG,
    CHECK_HISTORY,
)
from utils import (
    rate_limit, require_admin,
    console_log, sanitize_string, mask_email,
    format_timestamp, format_hour_offset, parse_iso_timestamp,
    record_visit, safe_next_url, verify_password,
    log_admin_action, get_client_ip,
    _generate_csrf_token, _validate_csrf_token,
)
from state import (
    load_seen_events, load_status,
    load_recipient_status, load_theme_settings,
    load_email_history, get_all_recipients,
    get_latest_event_summary, build_email_queue_payload,
)


@app.route('/')
def index():
    """Client-facing landing page."""
    from config import CONFIG, VISITOR_LOG
    from state import load_seen_events
    now = datetime.now(timezone.utc)
    record_visit()
    seen_data = load_seen_events()
    return render_template(
        'index.html',
        current_year=now.year,
        total_checks=CONFIG.get('total_checks', 0),
        emails_sent=CONFIG.get('emails_sent', 0),
        seen_count=len(seen_data.get('event_ids', [])),
        visitors_24h=len(VISITOR_LOG),
    )


@app.route('/login', methods=['GET', 'POST'])
@rate_limit
def admin_login():
    """Admin login page with CSRF protection."""
    if request.method == 'GET':
        next_url = safe_next_url(request.args.get('next'))
        csrf_token = _generate_csrf_token()
        return render_template('admin_login.html', error=None, next=next_url, csrf_token=csrf_token)

    # Validate CSRF token
    if not _validate_csrf_token():
        console_log(f"🚫 CSRF validation failed from {get_client_ip()[:15]}", "warning")
        next_url = safe_next_url(request.form.get('next'))
        csrf_token = _generate_csrf_token()
        return render_template('admin_login.html', error='Invalid request. Please try again.', next=next_url, csrf_token=csrf_token)

    password = request.form.get('password', '')
    next_url = safe_next_url(request.form.get('next'))

    if verify_password(password):
        session.permanent = True
        session['admin_logged_in'] = True
        session['admin_logged_in_at'] = datetime.now(timezone.utc).isoformat()
        log_admin_action('admin_login', f"{request.method} {request.path}")
        return redirect(next_url)

    csrf_token = _generate_csrf_token()
    return render_template('admin_login.html', error='Invalid password', next=next_url, csrf_token=csrf_token)


@app.route('/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin')
@app.route('/dashboard')
@rate_limit
@require_admin
def dashboard():
    """Admin dashboard page."""
    status = load_status()
    seen_data = load_seen_events()
    tracked_events_table = seen_data.get('event_details', [])[-50:][::-1]
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

    uptime_str = "Just started"
    try:
        start = parse_iso_timestamp(CONFIG['uptime_start'])
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
    except Exception:
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
        tracked_events_table=tracked_events_table,
        live_events=live_events,
        logs=config.ACTIVITY_LOGS[:50],
        all_recipients=all_recipients,
        recipient_status=recipient_status,
        mask_email=mask_email,
        format_timestamp=format_timestamp,
        format_hour_offset=format_hour_offset,
        email_queue=config.EMAIL_QUEUE,
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
    checker_alive = config.checker_thread is not None and config.checker_thread.is_alive()

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


@app.route('/api/health')
def api_health():
    """Health check endpoint for uptime monitoring."""
    return jsonify({
        'status': 'healthy',
        'uptime_start': CONFIG['uptime_start'],
        'total_checks': CONFIG['total_checks'],
        'tracker_enabled': CONFIG['tracker_enabled'],
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
