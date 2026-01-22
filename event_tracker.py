"""
=============================================================================
📧 DUBAI FLEA MARKET EVENT TRACKER - event_tracker.py
=============================================================================

PURPOSE:
--------
This file is the MAIN SCRIPT that checks for new Dubai Flea Market events
and sends email notifications automatically.

WHAT IT DOES:
-------------
1. Fetches event data from dubai-fleamarket.com WordPress API
2. Compares new events with previously seen events (stored in seen_events.json)
3. Sends email notification when NEW events are detected
4. Updates the database to avoid sending duplicate notifications

WHY THIS MATTERS:
-----------------
Instead of refreshing the website every minute hoping to catch new events
before they sell out, this script monitors 24/7 and alerts you INSTANTLY
when a new event is posted - giving you a competitive advantage!

WHAT YOU NEED TO CHANGE:
-------------------------
- Lines 27-29: Add your Gmail email and App Password
(See README.md for setup instructions)

=============================================================================
"""

import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import os
import re
import html

# ===== LOAD ENVIRONMENT VARIABLES =====
# For local testing: Load from .env file if it exists
def load_env_file():
    """Load environment variables from .env file (for local development)"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

# Load .env file for local testing (GitHub Actions uses secrets instead)
load_env_file()

# ===== CONFIGURATION =====
API_URL = "https://dubai-fleamarket.com/wp-json/wp/v2/product?per_page=20"
DB_FILE = "seen_events.json"
STATUS_FILE = "tracker_status.json"  # Tracks daily summary timing

# Email configuration - Loaded securely from environment variables
# ⚠️ NEVER hardcode passwords in code files!
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# 🔐 SECURE: Credentials loaded from environment variables (not visible in code)
# For LOCAL testing: Create a .env file (see .env.example) or set system env vars
# For GITHUB ACTIONS: Add secrets in repo Settings → Secrets → Actions
MY_EMAIL = os.environ.get('MY_EMAIL', '')
MY_PASSWORD = os.environ.get('MY_PASSWORD', '')
TO_EMAIL = os.environ.get('TO_EMAIL', '')  # Can be comma-separated for multiple recipients

# Daily summary settings
DAILY_SUMMARY_ENABLED = os.environ.get('DAILY_SUMMARY_ENABLED', 'false').lower() == 'true'
DAILY_SUMMARY_HOUR = int(os.environ.get('DAILY_SUMMARY_HOUR', '9'))  # Default 9 AM UTC

# 🧪 Test mode - adds "sorry for test" message to emails
TEST_MODE = os.environ.get('TEST_MODE', 'false').lower() == 'true'


# ===== HELPER FUNCTIONS =====
def get_recipient_list():
    """Parse TO_EMAIL into a list of recipients."""
    if not TO_EMAIL:
        return []
    # Split by comma and clean up whitespace
    return [email.strip() for email in TO_EMAIL.split(',') if email.strip()]


def load_status():
    """Load tracker status (for daily summary timing)."""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {'last_daily_summary': None, 'total_checks': 0}


def save_status(status):
    """Save tracker status."""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)


def should_send_daily_summary():
    """Check if it's time to send the daily summary."""
    if not DAILY_SUMMARY_ENABLED:
        return False
    
    now = datetime.now(timezone.utc)
    current_hour = now.hour
    today_str = now.strftime('%Y-%m-%d')
    
    status = load_status()
    last_summary = status.get('last_daily_summary')
    
    # Send if: correct hour AND haven't sent today
    if current_hour == DAILY_SUMMARY_HOUR and last_summary != today_str:
        return True
    return False


def mark_daily_summary_sent():
    """Mark that daily summary was sent today."""
    status = load_status()
    status['last_daily_summary'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    status['total_checks'] = status.get('total_checks', 0) + 1
    save_status(status)


# ===== SECURITY FUNCTIONS =====
def sanitize_string(text):
    """
    Sanitize input string to prevent injection attacks.
    Removes/escapes potentially dangerous characters.
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ''
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    # Remove any potential SQL injection patterns (extra safety)
    dangerous_patterns = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|TRUNCATE)\b)',
        r'(--|;|\/\*|\*\/)',  # SQL comments
        r'(<script|<\/script|javascript:|on\w+\s*=)',  # XSS patterns
    ]
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text.strip()


def validate_url(url):
    """Validate that a URL is safe and from expected domain."""
    if not url or not isinstance(url, str):
        return False
    
    # Only allow URLs from the expected domain
    allowed_domains = ['dubai-fleamarket.com', 'www.dubai-fleamarket.com']
    
    try:
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Extract domain from URL
        domain = url.split('/')[2].lower()
        return any(domain == allowed or domain.endswith('.' + allowed) 
                   for allowed in allowed_domains)
    except (IndexError, AttributeError):
        return False


def validate_event_id(event_id):
    """Validate event ID is a safe integer."""
    try:
        # Ensure it's a valid integer (prevents injection via IDs)
        return isinstance(event_id, int) and event_id > 0
    except (TypeError, ValueError):
        return False


def load_seen_events():
    """Load the list of event IDs we've already seen"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return []


def save_seen_events(seen_events):
    """Save the updated list of seen event IDs"""
    with open(DB_FILE, 'w') as f:
        json.dump(seen_events, f, indent=2)


def fetch_events():
    """Fetch events from WordPress API"""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching events: {e}")
        return None


def extract_event_info(event):
    """Extract relevant information from event JSON with security validation."""
    # Validate event ID
    event_id = event.get('id')
    if not validate_event_id(event_id):
        print(f"⚠️ Skipping event with invalid ID: {event_id}")
        return None
    
    # Validate and sanitize URL
    link = event.get('link', '')
    if not validate_url(link):
        print(f"⚠️ Skipping event with invalid URL: {link}")
        return None
    
    # Sanitize text fields to prevent injection
    title = sanitize_string(event.get('title', {}).get('rendered', 'Unknown Event'))
    date_posted = sanitize_string(event.get('date', 'Unknown Date'))
    
    return {
        'id': event_id,
        'title': title,
        'date_posted': date_posted,
        'link': link  # Already validated
    }


def send_email(new_events):
    """Send email notification about new events to all recipients"""
    recipients = get_recipient_list()
    if not recipients:
        print("❌ No recipients configured")
        return False
    
    try:
        # Create email
        msg = MIMEMultipart('alternative')
        
        # Add test mode indicator to subject
        subject_prefix = "🧪 [TEST] " if TEST_MODE else ""
        msg['Subject'] = f"{subject_prefix}🎉 {len(new_events)} New Dubai Flea Market Event(s)!"
        msg['From'] = MY_EMAIL
        msg['To'] = ', '.join(recipients)  # Multiple recipients
        
        # Build email body
        email_body = ""
        
        # Add test mode warning at the top
        if TEST_MODE:
            now = datetime.now()
            email_body += "=" * 50 + "\n"
            email_body += "🧪 TEST EMAIL - Please Ignore\n"
            email_body += f"📅 Date: {now.strftime('%A, %B %d, %Y')}\n"
            email_body += f"🕐 Time: {now.strftime('%I:%M:%S %p')}\n"
            email_body += "\n⚠️ Sorry for the test email!\n"
            email_body += "   - MSBP, your dev 💻\n"
            email_body += "=" * 50 + "\n\n"
        
        email_body += f"🎯 {len(new_events)} new event(s) have been posted!\n\n"
        
        for event in new_events:
            email_body += f"📍 {event['title']}\n"
            email_body += f"🔗 {event['link']}\n"
            email_body += f"📅 Posted: {event['date_posted']}\n"
            email_body += "-" * 50 + "\n\n"
        
        email_body += "\n🤖 Sent automatically by Dubai Flea Market Tracker"
        if TEST_MODE:
            email_body += "\n🧪 This was a TEST run - not production"
        
        # Add plain text version
        text_part = MIMEText(email_body, 'plain')
        msg.attach(text_part)
        
        # Send email to all recipients
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MY_EMAIL, MY_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent to {len(recipients)} recipient(s): {', '.join(recipients)}")
        return True
    
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


def send_daily_summary(total_events, seen_count):
    """Send daily summary email when no new events found"""
    recipients = get_recipient_list()
    if not recipients:
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        
        # Add test mode indicator to subject
        subject_prefix = "🧪 [TEST] " if TEST_MODE else ""
        msg['Subject'] = f"{subject_prefix}📊 Dubai Flea Market Daily Summary - No New Events"
        msg['From'] = MY_EMAIL
        msg['To'] = ', '.join(recipients)
        
        now = datetime.now(timezone.utc)
        local_now = datetime.now()
        
        # Test mode header
        test_header = ""
        test_footer = ""
        if TEST_MODE:
            test_header = f"""
{'=' * 50}
🧪 TEST EMAIL - Please Ignore
📅 Date: {local_now.strftime('%A, %B %d, %Y')}
🕐 Time: {local_now.strftime('%I:%M:%S %p')}

⚠️ Sorry for the test email!
   - MSBP, your dev 💻
{'=' * 50}
"""
            test_footer = "\n🧪 This was a TEST run - not production"
        
        email_body = f"""{test_header}
📊 DAILY SUMMARY - {now.strftime('%A, %B %d, %Y')}
{'=' * 50}

✨ Status: No new events today

📈 Statistics:
   • Total events on website: {total_events}
   • Events you've already seen: {seen_count}
   • New events found: 0

💡 The tracker is running normally and monitoring for new events.
   You'll receive an instant notification when new events are posted!

🔗 Check manually: https://dubai-fleamarket.com

{'=' * 50}
🤖 Sent automatically by Dubai Flea Market Tracker{test_footer}
"""
        
        text_part = MIMEText(email_body, 'plain')
        msg.attach(text_part)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MY_EMAIL, MY_PASSWORD)
            server.send_message(msg)
        
        print(f"📊 Daily summary sent to {len(recipients)} recipient(s)")
        return True
    
    except Exception as e:
        print(f"❌ Error sending daily summary: {e}")
        return False


def main():
    """Main function to check for new events"""
    print(f"🔍 Checking for new events... [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    
    # Show test mode status
    if TEST_MODE:
        print("🧪 TEST MODE ENABLED - Emails will include test warning")
    
    # 🔐 Security check: Verify credentials are configured
    if not MY_EMAIL or not MY_PASSWORD or not TO_EMAIL:
        print("❌ ERROR: Email credentials not configured!")
        print("   Set environment variables: MY_EMAIL, MY_PASSWORD, TO_EMAIL")
        print("   For local testing, create a .env file (see .env.example)")
        print("   For GitHub Actions, add secrets in repo Settings → Secrets → Actions")
        return
    
    # Show recipient count
    recipients = get_recipient_list()
    print(f"📧 Sending to {len(recipients)} recipient(s)")
    
    # Load previously seen events
    seen_events = load_seen_events()
    print(f"📂 Loaded {len(seen_events)} previously seen events")
    
    # Fetch current events
    events = fetch_events()
    if events is None:
        print("❌ Failed to fetch events")
        return
    
    print(f"📥 Fetched {len(events)} events from API")
    
    # Find new events (with security validation)
    new_events = []
    for event in events:
        event_id = event.get('id')
        
        # Validate event ID before processing
        if not validate_event_id(event_id):
            print(f"⚠️ Skipping event with invalid ID")
            continue
            
        if event_id not in seen_events:
            event_info = extract_event_info(event)
            if event_info:  # Only add if validation passed
                new_events.append(event_info)
                seen_events.append(event_id)
    
    # Notify if new events found
    if new_events:
        print(f"🆕 Found {len(new_events)} new event(s):")
        for event in new_events:
            print(f"   - {event['title']}")
        
        # Send email notification
        if send_email(new_events):
            # Save updated list only if email was sent successfully
            save_seen_events(seen_events)
            print("💾 Saved updated event list")
    else:
        print("✨ No new events")
        
        # Check if it's time for daily summary
        if should_send_daily_summary():
            print("📊 Sending daily summary...")
            if send_daily_summary(len(events), len(seen_events)):
                mark_daily_summary_sent()
        else:
            if DAILY_SUMMARY_ENABLED:
                print(f"⏰ Daily summary scheduled for {DAILY_SUMMARY_HOUR}:00 UTC")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
