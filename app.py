"""
=============================================================================
🌐 DUBAI FLEA MARKET ADMIN DASHBOARD - app.py
=============================================================================

PURPOSE:
--------
Flask web application that provides:
1. Admin dashboard to monitor the event tracker
2. Health endpoint for UptimeRobot to keep the service alive
3. Manual controls to trigger checks, enable/disable features
4. Real-time status and logs

DEPLOYMENT:
-----------
Deploy to Render.com (free tier) with UptimeRobot pinging /health every 5 min

=============================================================================
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
from datetime import datetime, timezone, timedelta
import json
import os
import threading
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html
import re

app = Flask(__name__)

# ===== CONFIGURATION =====
API_URL = "https://dubai-fleamarket.com/wp-json/wp/v2/product?per_page=20"

# File paths - use environment variable for Render compatibility
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(DATA_DIR, "seen_events.json")
STATUS_FILE = os.path.join(DATA_DIR, "tracker_status.json")
LOGS_FILE = os.path.join(DATA_DIR, "activity_logs.json")

# Email configuration from environment
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
MY_EMAIL = os.environ.get('MY_EMAIL', '')
MY_PASSWORD = os.environ.get('MY_PASSWORD', '')
TO_EMAIL = os.environ.get('TO_EMAIL', '')

# Feature toggles (can be changed via dashboard)
CONFIG = {
    'check_interval_minutes': int(os.environ.get('CHECK_INTERVAL', '15')),
    'heartbeat_enabled': os.environ.get('HEARTBEAT_ENABLED', 'true').lower() == 'true',
    'heartbeat_hours': int(os.environ.get('HEARTBEAT_HOURS', '3')),
    'heartbeat_email': os.environ.get('HEARTBEAT_EMAIL', 'steevenparubrub@gmail.com'),
    'tracker_enabled': True,
    'last_check': None,
    'next_check': None,
    'next_heartbeat': None,
    'total_checks': 0,
    'total_new_events': 0,
    'uptime_start': datetime.now(timezone.utc).isoformat()
}

# Activity logs (in-memory, persisted to file)
ACTIVITY_LOGS = []
MAX_LOGS = 100

# Background thread control
checker_thread = None
stop_checker = threading.Event()


# ===== HELPER FUNCTIONS =====
def log_activity(message, level="info"):
    """Add an activity log entry."""
    global ACTIVITY_LOGS
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'message': message,
        'level': level
    }
    ACTIVITY_LOGS.insert(0, entry)
    if len(ACTIVITY_LOGS) > MAX_LOGS:
        ACTIVITY_LOGS = ACTIVITY_LOGS[:MAX_LOGS]
    
    # Persist to file
    try:
        with open(LOGS_FILE, 'w') as f:
            json.dump(ACTIVITY_LOGS, f, indent=2)
    except:
        pass
    
    print(f"[{level.upper()}] {message}")


def load_logs():
    """Load activity logs from file."""
    global ACTIVITY_LOGS
    try:
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r') as f:
                ACTIVITY_LOGS = json.load(f)
    except:
        ACTIVITY_LOGS = []


def load_status():
    """Load tracker status."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        'last_daily_summary': None,
        'total_checks': 0,
        'last_heartbeat': None,
        'last_check_time': None
    }


def save_status(status):
    """Save tracker status."""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save status: {e}", "error")


def load_seen_events():
    """Load seen events."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {'event_ids': data, 'event_details': []}
                return data
        except:
            pass
    return {'event_ids': [], 'event_details': []}


def save_seen_events(seen_data):
    """Save seen events."""
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(seen_data, f, indent=2)
    except Exception as e:
        log_activity(f"Failed to save events: {e}", "error")


def sanitize_string(text):
    """Sanitize input string."""
    if not isinstance(text, str):
        return str(text) if text is not None else ''
    return html.escape(text).strip()


def validate_url(url):
    """Validate URL is from expected domain."""
    if not url or not isinstance(url, str):
        return False
    allowed_domains = ['dubai-fleamarket.com', 'www.dubai-fleamarket.com']
    try:
        if not url.startswith(('http://', 'https://')):
            return False
        domain = url.split('/')[2].lower()
        return any(domain == allowed or domain.endswith('.' + allowed) 
                   for allowed in allowed_domains)
    except:
        return False


def fetch_events():
    """Fetch events from API."""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log_activity(f"Failed to fetch events: {e}", "error")
        return None


def send_email(subject, body, to_email=None):
    """Send email notification."""
    if not MY_EMAIL or not MY_PASSWORD:
        log_activity("Email credentials not configured", "error")
        return False
    
    recipient = to_email or TO_EMAIL
    if not recipient:
        log_activity("No recipient email configured", "error")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = MY_EMAIL
        msg['To'] = recipient
        
        text_part = MIMEText(body, 'plain')
        msg.attach(text_part)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MY_EMAIL, MY_PASSWORD)
            server.sendmail(MY_EMAIL, recipient, msg.as_string())
        
        log_activity(f"Email sent to {recipient}", "success")
        return True
    except Exception as e:
        log_activity(f"Failed to send email: {e}", "error")
        return False


def send_new_event_email(events):
    """Send new event notification."""
    subject = f"🎉 {len(events)} New Dubai Flea Market Event(s)!"
    body = f"🎯 {len(events)} new event(s) have been posted!\n\n"
    
    for event in events:
        body += f"📍 {event['title']}\n"
        body += f"🔗 {event['link']}\n"
        body += f"📅 Posted: {event['date_posted']}\n"
        body += "-" * 50 + "\n\n"
    
    body += "\n🤖 Sent automatically by Dubai Flea Market Tracker"
    
    # Send to all TO_EMAIL recipients
    if TO_EMAIL:
        for email in TO_EMAIL.split(','):
            send_email(subject, body, email.strip())


def send_heartbeat():
    """Send heartbeat status email."""
    if not CONFIG['heartbeat_enabled']:
        return False
    
    now = datetime.now(timezone.utc)
    status = load_status()
    seen_data = load_seen_events()
    
    subject = f"💓 Bot Running OK - Check #{CONFIG['total_checks']} | {now.strftime('%H:%M')} UTC"
    
    body = f"""
{'=' * 60}
💓 DUBAI FLEA MARKET BOT - HEARTBEAT STATUS
{'=' * 60}

✅ STATUS: Bot is RUNNING and monitoring for new events!

📊 CURRENT STATS:
   • Check Number: #{CONFIG['total_checks']}
   • Current Time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}
   • Events Already Seen: {len(seen_data.get('event_ids', []))}
   • Total New Events Found: {CONFIG['total_new_events']}

⏰ TIMING INFO:
   • Check Interval: Every {CONFIG['check_interval_minutes']} minutes
   • Heartbeat Interval: Every {CONFIG['heartbeat_hours']} hours
   • Uptime Since: {CONFIG['uptime_start']}

🎯 WHAT THIS MEANS:
   The bot is actively running 24/7 on Render.
   You will receive an INSTANT email when a new event is posted!

🔗 Dashboard: Check your Render dashboard for logs
🔗 Manual Check: https://dubai-fleamarket.com

{'=' * 60}
🤖 Automated Heartbeat from Dubai Flea Market Tracker
{'=' * 60}
"""
    
    return send_email(subject, body, CONFIG['heartbeat_email'])


def check_for_events():
    """Main event checking logic."""
    log_activity("Starting event check...")
    CONFIG['last_check'] = datetime.now(timezone.utc).isoformat()
    CONFIG['total_checks'] += 1
    
    # Load seen events
    seen_data = load_seen_events()
    seen_ids = seen_data.get('event_ids', [])
    
    # Fetch current events
    events = fetch_events()
    if events is None:
        log_activity("Failed to fetch events from API", "error")
        return
    
    log_activity(f"Fetched {len(events)} events from API")
    
    # Find new events
    new_events = []
    for event in events:
        event_id = event.get('id')
        if not isinstance(event_id, int) or event_id <= 0:
            continue
        
        if event_id not in seen_ids:
            link = event.get('link', '')
            if not validate_url(link):
                continue
            
            event_info = {
                'id': event_id,
                'title': sanitize_string(event.get('title', {}).get('rendered', 'Unknown')),
                'date_posted': sanitize_string(event.get('date', 'Unknown')),
                'link': link
            }
            new_events.append(event_info)
            
            # Add to seen
            seen_data['event_ids'].append(event_id)
            seen_data.setdefault('event_details', []).append({
                **event_info,
                'first_seen': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            })
    
    if new_events:
        CONFIG['total_new_events'] += len(new_events)
        log_activity(f"🆕 Found {len(new_events)} NEW event(s)!", "success")
        
        # Send notification
        send_new_event_email(new_events)
        
        # Save updated seen events
        save_seen_events(seen_data)
    else:
        log_activity("✨ No new events")
    
    # Update status
    status = load_status()
    status['total_checks'] = CONFIG['total_checks']
    status['last_check_time'] = CONFIG['last_check']
    save_status(status)
    
    # Calculate next check time
    CONFIG['next_check'] = (datetime.now(timezone.utc) + 
                           timedelta(minutes=CONFIG['check_interval_minutes'])).isoformat()


def should_send_heartbeat():
    """Check if heartbeat is due."""
    if not CONFIG['heartbeat_enabled']:
        return False
    
    status = load_status()
    last_heartbeat = status.get('last_heartbeat')
    
    if not last_heartbeat:
        return True
    
    try:
        last_time = datetime.fromisoformat(last_heartbeat.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours_since = (now - last_time).total_seconds() / 3600
        return hours_since >= CONFIG['heartbeat_hours']
    except:
        return True


def background_checker():
    """Background thread that runs the event checker."""
    log_activity("🚀 Background checker started", "success")
    
    while not stop_checker.is_set():
        if CONFIG['tracker_enabled']:
            try:
                check_for_events()
                
                # Check heartbeat
                if should_send_heartbeat():
                    log_activity("💓 Sending heartbeat...")
                    if send_heartbeat():
                        status = load_status()
                        status['last_heartbeat'] = datetime.now(timezone.utc).isoformat()
                        save_status(status)
                        CONFIG['next_heartbeat'] = (datetime.now(timezone.utc) + 
                                                   timedelta(hours=CONFIG['heartbeat_hours'])).isoformat()
                        log_activity("💓 Heartbeat sent!", "success")
                
            except Exception as e:
                log_activity(f"Error in checker: {e}", "error")
        
        # Wait for next check
        stop_checker.wait(timeout=CONFIG['check_interval_minutes'] * 60)
    
    log_activity("Background checker stopped", "warning")


# ===== ROUTES =====
@app.route('/')
def dashboard():
    """Main dashboard page."""
    status = load_status()
    seen_data = load_seen_events()
    
    # Calculate times
    now = datetime.now(timezone.utc)
    
    # Time until next check
    next_check_in = "N/A"
    if CONFIG['next_check']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_check'].replace('Z', '+00:00'))
            diff = (next_dt - now).total_seconds()
            if diff > 0:
                mins = int(diff // 60)
                secs = int(diff % 60)
                next_check_in = f"{mins}m {secs}s"
            else:
                next_check_in = "Soon..."
        except:
            pass
    
    # Time until next heartbeat
    next_heartbeat_in = "N/A"
    if CONFIG['next_heartbeat']:
        try:
            next_dt = datetime.fromisoformat(CONFIG['next_heartbeat'].replace('Z', '+00:00'))
            diff = (next_dt - now).total_seconds()
            if diff > 0:
                hours = int(diff // 3600)
                mins = int((diff % 3600) // 60)
                next_heartbeat_in = f"{hours}h {mins}m"
            else:
                next_heartbeat_in = "Soon..."
        except:
            pass
    
    return render_template('dashboard.html',
        config=CONFIG,
        status=status,
        seen_count=len(seen_data.get('event_ids', [])),
        recent_events=seen_data.get('event_details', [])[-10:][::-1],
        logs=ACTIVITY_LOGS[:20],
        next_check_in=next_check_in,
        next_heartbeat_in=next_heartbeat_in,
        current_time=now.strftime('%Y-%m-%d %H:%M:%S UTC')
    )


@app.route('/health')
def health():
    """Health check endpoint for UptimeRobot."""
    return jsonify({
        'status': 'healthy',
        'tracker_enabled': CONFIG['tracker_enabled'],
        'total_checks': CONFIG['total_checks'],
        'last_check': CONFIG['last_check'],
        'uptime_start': CONFIG['uptime_start']
    })


@app.route('/api/status')
def api_status():
    """API endpoint for status data."""
    status = load_status()
    seen_data = load_seen_events()
    
    return jsonify({
        'config': CONFIG,
        'status': status,
        'seen_count': len(seen_data.get('event_ids', [])),
        'logs': ACTIVITY_LOGS[:20]
    })


@app.route('/api/toggle/<feature>', methods=['POST'])
def toggle_feature(feature):
    """Toggle a feature on/off."""
    if feature == 'tracker':
        CONFIG['tracker_enabled'] = not CONFIG['tracker_enabled']
        log_activity(f"Tracker {'enabled' if CONFIG['tracker_enabled'] else 'disabled'}", 
                    "success" if CONFIG['tracker_enabled'] else "warning")
    elif feature == 'heartbeat':
        CONFIG['heartbeat_enabled'] = not CONFIG['heartbeat_enabled']
        log_activity(f"Heartbeat {'enabled' if CONFIG['heartbeat_enabled'] else 'disabled'}",
                    "success" if CONFIG['heartbeat_enabled'] else "warning")
    
    return jsonify({'success': True, 'config': CONFIG})


@app.route('/api/check-now', methods=['POST'])
def check_now():
    """Trigger an immediate check."""
    log_activity("Manual check triggered", "info")
    
    # Run check in background to not block
    thread = threading.Thread(target=check_for_events)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Check triggered'})


@app.route('/api/send-heartbeat', methods=['POST'])
def send_heartbeat_now():
    """Send heartbeat immediately."""
    log_activity("Manual heartbeat triggered", "info")
    
    if send_heartbeat():
        status = load_status()
        status['last_heartbeat'] = datetime.now(timezone.utc).isoformat()
        save_status(status)
        return jsonify({'success': True, 'message': 'Heartbeat sent'})
    
    return jsonify({'success': False, 'message': 'Failed to send heartbeat'})


@app.route('/api/logs')
def get_logs():
    """Get activity logs."""
    return jsonify({'logs': ACTIVITY_LOGS})


@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    """Clear activity logs."""
    global ACTIVITY_LOGS
    ACTIVITY_LOGS = []
    log_activity("Logs cleared", "info")
    return jsonify({'success': True})


# ===== STARTUP =====
def start_background_checker():
    """Start the background checker thread."""
    global checker_thread
    if checker_thread is None or not checker_thread.is_alive():
        stop_checker.clear()
        checker_thread = threading.Thread(target=background_checker, daemon=True)
        checker_thread.start()


# Load existing logs on startup
load_logs()

# Start background checker when app starts
start_background_checker()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
