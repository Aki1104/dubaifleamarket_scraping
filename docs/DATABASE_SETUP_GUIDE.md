# 🗄️ Database Setup Guide for Dubai Flea Market Tracker

## Why Do We Need a Database?

Currently, our bot stores data in JSON files:
- `seen_events.json` - Events we've already seen
- `tracker_status.json` - Bot status and counters
- `activity_logs.json` - Activity history
- `email_history.json` - Email sending history

**The Problem:** When Render redeploys your app (which happens on every push or monthly restart), these files are **deleted** because Render uses ephemeral storage.

**Current "Solution":** We commit these files to GitHub, which causes spam commits.

**Better Solution:** Store data in a **cloud database** that persists forever.

---

## 📊 Database Options Comparison

| Feature | Supabase | Firebase | PlanetScale |
|---------|----------|----------|-------------|
| Free Tier | ✅ 500MB | ✅ 1GB | ✅ 5GB |
| Ease of Setup | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Python Support | ✅ Excellent | ✅ Good | ✅ Good |
| Type | PostgreSQL | NoSQL (Firestore) | MySQL |
| Best For | Our use case | Mobile apps | Large apps |

**I recommend Supabase** because:
1. It's the easiest to set up
2. Uses standard SQL (PostgreSQL)
3. Has an excellent Python library
4. Generous free tier (500MB = millions of events)

---

## 🚀 Part 1: Setting Up Supabase (Step-by-Step)

### Step 1: Create a Supabase Account

1. Go to [https://supabase.com](https://supabase.com)
2. Click **"Start your project"**
3. Sign up with **GitHub** (recommended) or email
4. Verify your email if needed

### Step 2: Create a New Project

1. Click **"New Project"**
2. Fill in:
   - **Name:** `dubai-flea-tracker` (or anything you want)
   - **Database Password:** Create a strong password (SAVE THIS!)
   - **Region:** Choose closest to you (e.g., `Singapore` for UAE)
3. Click **"Create new project"**
4. Wait 1-2 minutes for setup

### Step 3: Get Your API Keys

1. In your project dashboard, click **"Settings"** (gear icon) → **"API"**
2. You'll see two important values:
   - **Project URL:** `https://xxxxx.supabase.co`
   - **anon/public key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6...` (long string)
3. **Copy both** - you'll need them later

### Step 4: Create the Database Tables

1. Click **"SQL Editor"** in the left sidebar
2. Click **"New query"**
3. Paste this SQL code:

```sql
-- Table for storing seen events
CREATE TABLE seen_events (
    id BIGINT PRIMARY KEY,           -- Event ID from the API
    title TEXT NOT NULL,             -- Event title
    link TEXT,                       -- Event URL
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for tracker status/config
CREATE TABLE tracker_status (
    key TEXT PRIMARY KEY,            -- Setting name (e.g., 'total_checks')
    value TEXT,                      -- Setting value (stored as text, converted in code)
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for activity logs
CREATE TABLE activity_logs (
    id SERIAL PRIMARY KEY,           -- Auto-incrementing ID
    message TEXT NOT NULL,           -- Log message
    level TEXT DEFAULT 'info',       -- Log level (info, success, error, warning)
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for email history
CREATE TABLE email_history (
    id SERIAL PRIMARY KEY,
    recipient TEXT NOT NULL,
    subject TEXT,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for event statistics (for charts)
CREATE TABLE event_stats (
    id SERIAL PRIMARY KEY,
    stat_type TEXT NOT NULL,         -- 'daily' or 'hourly'
    period TEXT NOT NULL,            -- Date or hour string
    checks INTEGER DEFAULT 0,
    new_events INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stat_type, period)
);

-- Index for faster queries
CREATE INDEX idx_seen_events_id ON seen_events(id);
CREATE INDEX idx_activity_logs_timestamp ON activity_logs(timestamp);
CREATE INDEX idx_email_history_timestamp ON email_history(timestamp);
```

4. Click **"Run"** (or press Ctrl+Enter)
5. You should see "Success. No rows returned" - that's correct!

### Step 5: Verify Tables Were Created

1. Click **"Table Editor"** in the left sidebar
2. You should see 5 tables:
   - `seen_events`
   - `tracker_status`
   - `activity_logs`
   - `email_history`
   - `event_stats`

✅ **Supabase is now set up!**

---

## 🔧 Part 2: Understanding the Code Changes

### What is an API?

Think of an API like a **waiter in a restaurant**:
- You (the code) tell the waiter (API) what you want
- The waiter goes to the kitchen (database)
- The waiter brings back your food (data)

### How Supabase Python Library Works

```python
from supabase import create_client

# Connect to your database (like entering the restaurant)
supabase = create_client(
    "https://xxxxx.supabase.co",  # Restaurant address
    "eyJhbGc..."                   # Your reservation code
)

# READ data (like asking "what's on the menu?")
result = supabase.table("seen_events").select("*").execute()
# result.data = [{"id": 123, "title": "Event 1"}, {"id": 456, "title": "Event 2"}]

# INSERT data (like ordering food)
supabase.table("seen_events").insert({
    "id": 789,
    "title": "New Event",
    "link": "https://..."
}).execute()

# UPDATE data (like changing your order)
supabase.table("tracker_status").update({
    "value": "100"
}).eq("key", "total_checks").execute()

# DELETE data (like canceling an order)
supabase.table("seen_events").delete().eq("id", 789).execute()
```

### Common Operations Explained

| Operation | JSON File Way | Supabase Way |
|-----------|---------------|--------------|
| Load all events | `json.load(file)` | `table("seen_events").select("*").execute()` |
| Save new event | `json.dump(data, file)` | `table("seen_events").insert({...}).execute()` |
| Check if event exists | `event_id in data` | `table("seen_events").select("id").eq("id", event_id).execute()` |
| Count events | `len(data)` | `table("seen_events").select("id", count="exact").execute()` |

### Understanding the Syntax

```python
supabase.table("seen_events").select("*").eq("id", 123).execute()
#   │         │                │         │              │
#   │         │                │         │              └─ Run the query
#   │         │                │         └─ Filter: where id = 123
#   │         │                └─ Get all columns (*)
#   │         └─ From this table
#   └─ The database connection
```

It's like building a sentence:
- "From **seen_events** table, **select all columns** where **id equals 123**, and **execute** the query"

---

## 🔐 Part 3: Adding Supabase to Render

### Step 1: Add Environment Variables to Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click on your `dubaifleamarket_scraping` service
3. Go to **"Environment"** tab
4. Add these new variables:

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` (from Step 3 earlier) |
| `SUPABASE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6...` (your anon key) |

5. Click **"Save Changes"**

### Step 2: Update requirements.txt

Add this line to your `requirements.txt`:
```
supabase>=2.0.0
```

---

## 📝 Part 4: Code Changes Overview

Here's what will change in `app.py`:

### Before (JSON Files):
```python
# Loading seen events
def load_seen_events():
    try:
        with open('seen_events.json', 'r') as f:
            return json.load(f)
    except:
        return {"event_ids": [], "event_details": []}

# Saving seen events
def save_seen_events(data):
    with open('seen_events.json', 'w') as f:
        json.dump(data, f)
```

### After (Supabase):
```python
from supabase import create_client
import os

# Connect to Supabase (done once at startup)
supabase = create_client(
    os.environ.get('SUPABASE_URL'),
    os.environ.get('SUPABASE_KEY')
)

# Loading seen events
def load_seen_events():
    result = supabase.table("seen_events").select("*").execute()
    return {
        "event_ids": [e["id"] for e in result.data],
        "event_details": result.data
    }

# Saving a new seen event
def save_seen_event(event_id, title, link):
    supabase.table("seen_events").insert({
        "id": event_id,
        "title": title,
        "link": link
    }).execute()
```

### Key Differences:
1. **No file operations** - No `open()`, `read()`, `write()`
2. **Data persists forever** - Even after redeploys
3. **No more git commits** - Data lives in the cloud
4. **Slightly slower** - Network request vs local file (but negligible)

---

## 🎯 Part 5: What I'll Implement

When you're ready, I'll make these changes:

### Files to Modify:
1. **`app.py`** - Replace all JSON file operations with Supabase
2. **`requirements.txt`** - Add `supabase` package
3. **`.gitignore`** - Add JSON data files (they won't be needed anymore)

### New Functions:
```python
# Database connection
def get_supabase_client()

# Seen Events
def db_load_seen_events()      # Get all seen events
def db_save_seen_event()       # Save a new event
def db_check_event_exists()    # Check if event was seen
def db_remove_latest_event()   # For test notifications

# Tracker Status
def db_get_status()            # Get a status value
def db_set_status()            # Set a status value

# Activity Logs
def db_add_log()               # Add a log entry
def db_get_logs()              # Get recent logs
def db_clear_logs()            # Clear all logs

# Email History
def db_add_email_history()     # Record email sent
def db_get_email_history()     # Get email history

# Statistics
def db_record_stat()           # Record a statistic
def db_get_stats()             # Get stats for charts
```

### Fallback System:
I'll add a **fallback to JSON files** if Supabase isn't configured. This means:
- If you set up Supabase → Uses database
- If you don't → Falls back to JSON files (current behavior)

---

## ❓ Frequently Asked Questions

### Q: Is Supabase really free?
**A:** Yes! The free tier includes:
- 500MB database storage
- Unlimited API requests
- 2 free projects
- No credit card required

For our use case (a few hundred events), you'll never hit the limit.

### Q: What if Supabase goes down?
**A:** Supabase has 99.9% uptime. But I'll add error handling so if it's unreachable, the bot logs the error and continues (it just won't persist data temporarily).

### Q: Can I see my data?
**A:** Yes! Go to Supabase → Table Editor → Click any table to see/edit data directly.

### Q: How do I backup my data?
**A:** Supabase → Settings → Database → Download a full backup anytime.

### Q: Can I switch back to JSON files?
**A:** Yes, just remove the environment variables from Render. The fallback will kick in.

---

## 📋 Your Action Items

Before I implement the code changes, you need to:

- [ ] 1. Create Supabase account at [supabase.com](https://supabase.com)
- [ ] 2. Create a new project
- [ ] 3. Run the SQL to create tables (copy from Part 1, Step 4)
- [ ] 4. Get your Project URL and anon key
- [ ] 5. Add `SUPABASE_URL` and `SUPABASE_KEY` to Render environment variables
- [ ] 6. Tell me "Ready!" and I'll implement the code

---

## 🚀 Ready?

Once you've completed the setup steps above, just say **"Ready!"** and I'll:

1. Update `app.py` with Supabase integration
2. Add fallback system for local development
3. Update `requirements.txt`
4. Update `.gitignore`
5. Remove the git commit spam code
6. Test everything works

**Estimated time for you:** 10-15 minutes to set up Supabase
**Estimated time for me:** 5 minutes to implement code changes

---

*Created for the Dubai Flea Market Event Tracker project*
