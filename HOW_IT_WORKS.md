# 🎨 How It Works - Visual Guide

Visual diagrams explaining how the Dubai Flea Market Event Notifier system works.

---

## 🔄 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     YOUR AUTOMATED SYSTEM                         │
└─────────────────────────────────────────────────────────────────┘

Step 1: SCHEDULE TRIGGER (Every Hour)
┌──────────────────┐
│  GitHub Actions  │  ⏰ Wakes up automatically
│   (Free Cloud)   │     "Time to check events!"
└────────┬─────────┘
         │
         │ Runs event_tracker.py
         ▼

Step 2: FETCH DATA FROM WEBSITE
┌──────────────────┐
│  API Request     │  📡 GET /wp-json/wp/v2/product
│  to dubai-flea   │     Returns JSON with all events
│  market.com      │
└────────┬─────────┘
         │
         │ Receives event data
         ▼
┌────────────────────────────────────────┐
│ Response: JSON Array                   │
│ [                                      │
│   {id: 7850, title: "Zabeel Park..."},│
│   {id: 7737, title: "Al Khail..."},   │
│   ...                                  │
│ ]                                      │
└────────┬───────────────────────────────┘
         │
         │ Parse JSON
         ▼

Step 3: COMPARE WITH HISTORY
┌──────────────────┐
│  seen_events     │  📂 Load previously seen IDs
│  .json           │     [7850, 7737, 7736, ...]
└────────┬─────────┘
         │
         │ Compare current vs. history
         ▼
    ╔═══════════╗
    ║ New Event?║
    ╚═══════════╝
         │
    ┌────┴────┐
    │         │
   YES       NO
    │         │
    │         └──────────> ✅ Do nothing
    │                         (Exit gracefully)
    ▼

Step 4: SEND NOTIFICATION
┌──────────────────┐
│  Gmail SMTP      │  📧 Send email via Google
│  smtp.gmail.com  │     To: your_email@gmail.com
└────────┬─────────┘
         │
         │ Email sent
         ▼
┌──────────────────┐
│  Your Inbox      │  🔔 NEW EVENT NOTIFICATION!
│  📱 Phone/PC     │     "Zabeel Park / Feb 1"
└──────────────────┘
         │
         │ User receives notification
         ▼
Step 5: UPDATE HISTORY
┌──────────────────┐
│  seen_events     │  💾 Add new event ID to list
│  .json           │     [7850, 7737, 7736, 7900] ← NEW
└────────┬─────────┘
         │
         │ Commit to GitHub
         ▼
┌──────────────────┐
│  GitHub Repo     │  🔄 Push updated file
│  (Your Account)  │     Next run will use new list
└──────────────────┘
```

---

## ⚡ The Competitive Advantage

### Traditional Method (Manual Checking):

```
You                     Website                Event Booking
│                          │                        │
├──[Check]─────────────────►                        │
│  "No events"            │                        │
│                          │                        │
│  ⏰ 30 min wait...      │                        │
│                          │                        │
├──[Check]─────────────────►                        │
│  "No events"            │                        │
│                          │                        │
│  ⏰ 30 min wait...      │                        │
│                          │                        │
│                          │  [New event posted!]  │
│                          │  2:47 PM              │
│                          │                        │
│  ⏰ Still waiting...    │                        │
│                          │                        ├─[Others booking]
│                          │                        ├─[50% taken]
├──[Check]─────────────────►                        ├─[70% taken]
│  "Oh! New event! 😱"    │                        │
│  5:00 PM (2h 13m late!) │                        │
│                          │                        │
├──[Try to book]───────────────────────────────────►│
│                          │                        ├─[85% taken]
│  "Only 15 spots left!"  │                        ✅ Booked (barely!)
└──────────────────────────────────────────────────┘

❌ RESULT: Stressful, late, limited options
```

### Automated Method (This System):

```
Your System             Website                Event Booking
│                          │                        │
├──[Auto Check]───────────►│                        │
│  "No events"            │                        │
│  ⏰ 1 hour wait...      │                        │
├──[Auto Check]───────────►│                        │
│  "No events"            │                        │
│  ⏰ 1 hour wait...      │                        │
│                          │  [New event posted!]  │
│                          │  2:47 PM              │
│  ⏰ 13 min wait...      │                        │
├──[Auto Check]───────────►│                        │
│  "NEW EVENT! 🎉"        │                        │
│  3:00 PM (13 min lag)   │                        │
│                          │                        │
├──[Email sent]           │                        │
📧 You receive email      │                        │
│  3:00 PM                │                        │
│                          │                        ├─[Few early birds]
You                        │                        ├─[15% taken]
├──[Read email]           │                        │
│  3:15 PM                │                        │
├──[Book your spot]──────────────────────────────►│
│                          │                        ✅ Booked! (plenty left)
│  "Great! 85 spots left!"│                        │
└──────────────────────────────────────────────────┘

✅ RESULT: Fast, stress-free, lots of options
```

**Time Saved:** 1 hour 58 minutes  
**Stress Reduced:** 100%  
**Available Spots:** 85 vs. 15

---

## 📊 Notification Flow

### Single Recipient:

```
┌─────────────────┐
│  New Event      │
│  Detected!      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Send Email     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  your@email.com │ 📧 Receives notification
└─────────────────┘
```

### Multiple Recipients:

```
┌─────────────────┐
│  New Event      │
│  Detected!      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Send Email     │
│  (To: List)     │
└────────┬────────┘
         │
         ├──────────────────┬──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ person1@      │  │ person2@      │  │ person3@      │
│ gmail.com     │  │ gmail.com     │  │ yahoo.com     │
└───────────────┘  └───────────────┘  └───────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
    📧 Notified        📧 Notified        📧 Notified
    (same time)        (same time)        (same time)
```

**Everyone gets notified instantly!**

---

## 🔐 Security Flow

### How Secrets Are Protected:

```
Local Development:
┌─────────────────┐
│  event_tracker  │  ← Contains actual password
│  .py            │     (stored on YOUR computer)
└─────────────────┘
         │
         │ Edit file
         ▼
❌ DO NOT commit passwords to GitHub!

GitHub Repository:
┌─────────────────┐
│  event_tracker  │  ← Password replaced with placeholder
│  .py (in repo)  │     MY_PASSWORD = "your_app_password_here"
└─────────────────┘
         ▲
         │ Push code (safe!)
         │
┌─────────────────┐
│  .gitignore     │  ← Protects sensitive files
└─────────────────┘

GitHub Secrets (Encrypted):
┌─────────────────────────────────┐
│  Settings → Secrets              │
│  ┌───────────────────────────┐  │
│  │ MY_EMAIL: ••••••••••      │  │ 🔒 Encrypted
│  │ MY_PASSWORD: ••••••••••   │  │ 🔒 Not visible in logs
│  │ TO_EMAIL: ••••••••••      │  │ 🔒 Safe storage
│  └───────────────────────────┘  │
└─────────────────────────────────┘
         │
         │ Injected at runtime only
         ▼
GitHub Actions Runner:
┌─────────────────┐
│  event_tracker  │  ← Uses secrets from environment
│  .py (running)  │     MY_EMAIL = ${{ secrets.MY_EMAIL }}
└─────────────────┘

🔒 Your password NEVER appears in:
   ✅ GitHub code
   ✅ Action logs
   ✅ Commit history
```

---

## 📈 Cost Comparison

### Free Solutions (Recommended):

```
┌──────────────────┐
│  Your System     │  💰 FREE
│  (GitHub Actions)│  ⭐⭐⭐⭐⭐ Reliability
│                  │  ✅ 2000 min/month free
│                  │  ✅ Runs 24/7
│                  │  ✅ No server maintenance
└──────────────────┘
```

### Paid Alternatives (For Comparison):

```
┌──────────────────┐
│  Dedicated Server│  💰 $5-10/month
│  (DigitalOcean)  │  ⭐⭐⭐⭐ Reliability
│                  │  ✅ Full control
│                  │  ❌ Requires maintenance
└──────────────────┘

┌──────────────────┐
│  Monitoring SaaS │  💰 $10-30/month
│  (Zapier, etc)   │  ⭐⭐⭐ Reliability
│                  │  ✅ Easy setup
│                  │  ❌ Limited customization
└──────────────────┘

┌──────────────────┐
│  Manual Checking │  💰 FREE (but...)
│  (You refreshing)│  ⭐⭐ Reliability
│                  │  ❌ Wastes 2-3 hrs/day
│                  │  ❌ Miss nighttime posts
│                  │  ❌ Stressful
└──────────────────┘
```

**Verdict:** GitHub Actions is the best value! ✅

---

## 🌐 WhatsApp Integration (Optional)

### Email Only (Current):

```
┌─────────────────┐
│  New Event      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Gmail SMTP     │ 📧
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Your Email     │ ✅ FREE, Instant
└─────────────────┘
```

### Email + WhatsApp (Via Twilio):

```
┌─────────────────┐
│  New Event      │
└────────┬────────┘
         │
         ├──────────────────┬────────────────┐
         │                  │                │
         ▼                  ▼                ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Gmail SMTP   │  │  Twilio API   │  │  Other Email  │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        ▼                  ▼                  ▼
    📧 Email           📱 WhatsApp        📧 Email
    (FREE)         ($0.005/msg)          (FREE)
```

**Pros:** Instant WhatsApp notification on phone  
**Cons:** Costs ~$0.15/month (30 messages)  
**Setup:** See [SETUP_GUIDE.md](SETUP_GUIDE.md#-bonus-add-more-notification-methods)

---

## ⏱️ Timing Scenarios

### Best Case (Hourly Checks):

```
Event Posted: 2:47 PM
Next Check:   3:00 PM (13 min later)
Email Sent:   3:00 PM
You Notified: 3:00 PM
You Book:     3:15 PM

⏰ Total Lag: 28 minutes (event to booking)
```

### Worst Case (Hourly Checks):

```
Event Posted: 2:01 PM
Next Check:   3:00 PM (59 min later)
Email Sent:   3:00 PM
You Notified: 3:00 PM
You Book:     3:15 PM

⏰ Total Lag: 1 hour 14 minutes (event to booking)
```

### With 15-Minute Checks:

```
Event Posted: 2:47 PM
Next Check:   3:00 PM (13 min later)
Email Sent:   3:00 PM

⏰ Max Lag: 15 minutes (guaranteed)
⚠️ Uses more GitHub Actions minutes
```

**Recommendation:** Hourly checks are sufficient for most users!

---

## 📱 Device Support

Your notifications work on **ALL devices** where you have email:

```
┌─────────────────┐
│  Gmail Server   │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┬──────────┐
    │         │          │          │          │
    ▼         ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│ 📱   │  │ 💻   │  │ ⌚    │  │ 📧   │  │ 🖥️   │
│Phone │  │Laptop│  │Watch │  │ iPad │  │Desktop│
└──────┘  └──────┘  └──────┘  └──────┘  └──────┘
 iPhone    MacBook   Apple    Tablet     PC
 Android   Windows   Samsung  Android    Linux
```

**You'll see notification on ALL logged-in devices!** 🎉

---

---

## 📊 Daily Summary Feature (NEW!)

### What It Does

Sends a daily digest email even when NO new events are found, showing:
- Statistics (total events, seen events, new events)
- List of all tracked events with details
- When you first saw each event

### Why It Matters

- **Peace of Mind:** Confirms the system is working
- **Event Reference:** See all tracked events in one email
- **Status Update:** Know what's being monitored

### Daily Summary Flow

```
┌────────────────────────────────────────────────────────┐
│  Daily Summary Check (Configured Time)                 │
└──────────────────┬─────────────────────────────────────┘
                   │
         ┌─────────▼─────────┐
         │ Current UTC Hour  │
         │ >= Scheduled Hour?│
         └─────────┬─────────┘
                   │
              ┌────┴────┐
              │         │
             YES       NO
              │         │
              │         └────> ⏰ Wait for next run
              ▼
    ┌─────────────────┐
    │ Already sent    │
    │ today?          │
    └────────┬────────┘
             │
        ┌────┴────┐
        │         │
       YES       NO
        │         │
        │         └────────> 📊 Send Summary
        ▼
    ✅ Skip (already sent)
```

### Timing Configuration

**Example Settings:**

| Setting | UTC Time | Philippines Time | Dubai Time |
|---------|----------|------------------|------------|
| Hour = 1 | 1:00 AM | 9:00 AM | 5:00 AM |
| Hour = 5 | 5:00 AM | 1:00 PM | 9:00 AM |
| Hour = 9 | 9:00 AM | 5:00 PM | 1:00 PM |
| Hour = 13 | 1:00 PM | 9:00 PM | 5:00 PM |

**Time Zones:**
- **UTC** = Universal Time
- **Philippines** = UTC + 8 hours
- **Dubai** = UTC + 4 hours

### Sample Daily Summary Email

```
📊 DAILY SUMMARY - Saturday, January 25, 2026
==================================================

✨ Status: No new events today

📈 Statistics:
   • Total events on website: 3
   • Events you've already seen: 5
   • New events found: 0

📋 TRACKED EVENTS (Most Recent 5):
--------------------------------------------------

1. 📍 Zabeel Park / Saturday 1 February
   📅 Posted: 2026-01-15
   🔗 https://dubai-fleamarket.com/events/zabeel-park-feb-1
   👀 First seen: 2026-01-15 10:45 UTC

2. 📍 Al Khail Gate / Friday 31 January
   📅 Posted: 2026-01-10
   🔗 https://dubai-fleamarket.com/events/al-khail-jan-31
   👀 First seen: 2026-01-10 14:30 UTC

3. 📍 Times Square Center / Saturday 25 January
   📅 Posted: 2026-01-05
   🔗 https://dubai-fleamarket.com/events/times-square-jan-25
   👀 First seen: 2026-01-05 08:15 UTC

--------------------------------------------------

💡 The tracker is running normally and monitoring for new events.
   You'll receive an instant notification when new events are posted!

🔗 Check manually: https://dubai-fleamarket.com

==================================================
🤖 Sent automatically by Dubai Flea Market Tracker
```

### Technical Improvement: Timing Fix

**Problem:** GitHub Actions cron schedules can be delayed by 5-30 minutes  
**Old Behavior:** Only sent if run happened at EXACT scheduled hour  
**Result:** Daily summaries often missed due to timing delays

**Solution:** Time-window based triggering

```python
# ❌ OLD (Unreliable)
if current_hour == DAILY_SUMMARY_HOUR and last_summary != today_str:
    return True

# ✅ NEW (Robust)
if last_summary == today_str:
    return False  # Already sent today
if current_hour >= DAILY_SUMMARY_HOUR:
    return True  # Send on first run at/after scheduled hour
```

**Benefits:**
- ✅ Works even with GitHub Actions delays
- ✅ Sends once per day, no duplicates
- ✅ More reliable delivery
- ✅ Catches missed windows

---

## 🔄 Event Data Storage Evolution

### Old Format (Event IDs Only)

```json
[7850, 7737, 7736, 7761, 7379]
```

**Limitations:**
- No event details for reference
- Can't show event names in summaries
- No date tracking

### New Format (Event Details + IDs)

```json
{
  "event_ids": [7850, 7737, 7736, 7761, 7379],
  "event_details": [
    {
      "id": 7850,
      "title": "Zabeel Park / Saturday 1 February",
      "date_posted": "2026-01-15T10:30:00",
      "link": "https://dubai-fleamarket.com/events/...",
      "first_seen": "2026-01-15 10:45 UTC"
    }
  ]
}
```

**Benefits:**
- ✅ Rich event details for summaries
- ✅ Historical reference
- ✅ Tracks when you first saw each event
- ✅ Backward compatible with old format
- ✅ Auto-limits to 50 most recent events

---

**Visual Guide Complete!** For code-level details, see [FILE_GUIDE.md](FILE_GUIDE.md)
