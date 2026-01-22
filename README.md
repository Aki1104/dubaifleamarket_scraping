# Dubai Flea Market Event Notifier

Automatically get email notifications when new flea market events are posted on [dubai-fleamarket.com](https://dubai-fleamarket.com/events/).

> 👋 **New here?** Start with [START_HERE.md](START_HERE.md) for quick orientation!

---

## 🎯 The Problem This Solves

### The Struggle is Real:

**Before this system:**
- 😫 You have to manually refresh the website every 10-30 minutes
- ⏰ Events are posted at random times (sometimes early morning!)
- 🏃 Popular events sell out within **hours** or even **minutes**
- 💤 You miss events posted while you're sleeping or working
- 📱 Constantly checking your phone drains battery and wastes time
- 😤 Other vendors book their spots faster because they check more frequently

**The Pain:**
```
You: *Refreshes page for the 50th time today*
Website: No new events
You: *Takes a 2-hour break*
Website: *Posts new event at 2:47 PM*
You: *Checks again at 5:00 PM*
Website: Event posted! (But 80% of spots already taken)
You: 😭
```

### The Solution:

**With this automated system:**
- ✅ Checks for new events **every hour** (24/7, even while you sleep)
- ✅ Instant email notification when new events are posted
- ✅ **Competitive advantage** - You get notified within 60 minutes (or less!)
- ✅ Works even when your computer is off (runs on GitHub's servers)
- ✅ Free forever (uses GitHub Actions free tier)
- ✅ Can notify **multiple people** at once (your team, friends, family)

## 💪 Benefits & Why This Matters

### For Event Vendors:
1. **⏰ Time Saved:** No more manual refreshing - Save 2-3 hours per day
2. **🎯 Never Miss Events:** System monitors 24/7, even at 3am
3. **⚡ Faster Response:** Get notified within 1 hour instead of finding out hours later
4. **📈 Better Booking Success Rate:** Early notification = More available spots
5. **😌 Peace of Mind:** Stop obsessing over the website

### For Groups:
- **👥 Team Coordination:** Notify your entire vendor team instantly
- **🤝 Community Sharing:** Share notifications with friends/family who want to attend
- **📢 Group Chat Integration:** Forward email to WhatsApp/Telegram groups

### Real-World Impact:

| Scenario | Without System | With System |
|----------|---------------|-------------|
| Event posted at 2am | You find out at 9am (7 hrs late) | Email waiting when you wake up |
| Event posted during work | You check during lunch break | Instant notification (check during break) |
| Weekend event posted Friday | Might miss it if you forget to check | Automatic notification Friday evening |
| Popular location (Zabeel Park) | 100+ vendors competing, spots gone in 4 hours | You're among the first to know (within 1 hour) |

### Success Story Example:
```
📅 January 14, 2026 - 3:47 PM
🆕 New Event Posted: "Zabeel Park / Saturday 1 February"
📧 Your System Sends Email: 4:00 PM (13 minutes later)
✅ You Book Your Spot: 4:15 PM
🎉 Event Sells Out: 7:30 PM (You were among the first 40 vendors!)

WITHOUT the system:
❌ You check website: 6:00 PM (2 hours later)
😭 Only 15 spots remaining (high competition)
```

---

## 🚀 Quick Start

**Total Setup Time:** 15 minutes

📖 **Choose Your Guide:**
- **[QUICK_EDIT_REFERENCE.md](QUICK_EDIT_REFERENCE.md)** - Just show me what lines to edit! (fastest)
- **[SETUP_GUIDE.md](SETUP_GUIDE.md)** - Step-by-step with screenshots (most detailed)
- **[FILE_GUIDE.md](FILE_GUIDE.md)** - What does each file do?

**Quick Steps:**

1. **[Get Gmail App Password](#step-1-get-gmail-app-password)** (2 min)
2. **[Edit Configuration](#step-2-configure-the-script)** (1 min)
3. **[Test Locally](#step-3-test-locally)** (2 min)
4. **[Deploy to GitHub](#step-4-deploy-to-github-actions-automated)** (10 min)

---

### Step 1: Get Gmail App Password

1. Go to your Google Account settings
2. Enable **2-Factor Authentication** (required)
3. Go to https://myaccount.google.com/apppasswords
4. Create new app password for "Python Script"
5. Copy the 16-character code (e.g., `abcd efgh ijkl mnop`)

### Step 2: Configure the Script

Edit `event_tracker.py` (lines 36-38) and change:

```python
MY_EMAIL = "your_email@gmail.com"      # 👈 Your Gmail
MY_PASSWORD = "your_app_password_here" # 👈 16-char App Password from Step 1
TO_EMAIL = "your_email@gmail.com"      # 👈 Where to receive notifications
```

**💡 Notify Multiple People?** Use comma-separated emails:
```python
TO_EMAIL = "person1@gmail.com, person2@gmail.com, person3@gmail.com"
```

### Step 3: Test Locally

```bash
# Install dependencies
pip install requests

# Run the script
python event_tracker.py
```

You should see output like:
```
🔍 Checking for new events... [2026-01-14 12:00:00]
📂 Loaded 0 previously seen events
📥 Fetched 7 events from API
🆕 Found 7 new event(s):
   - Zabeel Park, Gate 1, Gate 2 / Sunday 1 February 2026
   - Al Khail Gate Park / Saturday 24 January 2026
   ...
✅ Email sent with 7 new event(s)
💾 Saved updated event list
```

### Step 4: Deploy to GitHub Actions (Automated)

1. **Create GitHub repository** and push your code:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/dubai-flea-market-notifier.git
   git push -u origin main
   ```

2. **Add secrets** to your GitHub repository:
   - Go to repo Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Add these three secrets:
     - `MY_EMAIL` = your Gmail address
     - `MY_PASSWORD` = your 16-character App Password
     - `TO_EMAIL` = email where you want notifications

3. **Enable GitHub Actions**:
   - Go to Actions tab
   - Enable workflows if prompted
   - The script will now run automatically every hour!

## 🔧 How It Works

```
┌─────────────────┐
│ GitHub Actions  │  Runs every hour
│  (Free Tier)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fetch API:     │  GET /wp-json/wp/v2/product
│  dubai-flea     │
│  market.com     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Compare with   │  Check event IDs
│  seen_events    │  in JSON file
│  .json          │
└────────┬────────┘
         │
    New event?
         │
    Yes  │  No
         ▼     └─────> Do nothing
┌─────────────────┐
│  Send email via │
│  Gmail SMTP     │
└─────────────────┘
```

## 📊 Event Data Structure

The API returns events like this:

```json
{
  "id": 7850,
  "title": {
    "rendered": "Zabeel Park, Gate 1, Gate 2 / Sunday 1 February 2026"
  },
  "date": "2026-01-12T14:24:07",
  "link": "https://dubai-fleamarket.com/product/zabeel-park-gate-1-gate-2-sunday-1-february-2026/"
}
```

We track events by their unique `id` field.

## 🔄 Customization

### Notify Multiple People (Email)

Simply edit `TO_EMAIL` in `event_tracker.py`:

```python
# Single person
TO_EMAIL = "you@gmail.com"

# Multiple people (comma-separated)
TO_EMAIL = "vendor1@gmail.com, vendor2@gmail.com, team@company.com"
```

Everyone in the list receives instant notifications! ✅

### Change Check Frequency

Edit `.github/workflows/check_events.yml` (line 40):

```yaml
schedule:
  - cron: '0 * * * *'  # Every hour (default)
  # - cron: '*/15 * * * *'  # Every 15 minutes (aggressive)
  # - cron: '0 9,17 * * *'  # 9am and 5pm daily (conservative)
```

**Recommendations:**
- **Every 15 min:** For highly competitive events (uses ~100 Actions minutes/day)
- **Every hour:** Balanced approach (uses ~2 Actions minutes/day) ⭐ Recommended
- **Twice daily:** For casual monitoring (uses <1 Action minute/day)

### Add WhatsApp Notifications (Advanced)

WhatsApp is **possible but requires extra setup**. Options:

#### Option 1: Twilio API (Easiest - Small Cost)
- **Cost:** ~$0.005 per message (~$0.15/month for 30 messages)
- **Setup Time:** 15 minutes
- **Reliability:** ⭐⭐⭐⭐⭐ Very stable
- **Guide:** See [SETUP_GUIDE.md](SETUP_GUIDE.md#-bonus-add-more-notification-methods)

**Quick Preview:**
```python
# Add to event_tracker.py after email is sent
from twilio.rest import Client

def send_whatsapp(message):
    client = Client("YOUR_TWILIO_SID", "YOUR_AUTH_TOKEN")
    client.messages.create(
        from_='whatsapp:+14155238886',
        to='whatsapp:+971501234567',  # Your number
        body=message
    )
```

#### Option 2: WhatsApp Business API (Free but Complex)
- **Cost:** Free (self-hosted)
- **Setup Time:** 2-3 hours
- **Reliability:** ⭐⭐⭐ Moderate (requires maintenance)
- **Best For:** Companies with technical resources

#### Option 3: Unofficial Bots (Not Recommended)
- ❌ Violates WhatsApp Terms of Service
- ❌ High risk of account ban
- ❌ Unreliable

**💡 Recommendation:** For most users, **email is the best option** - it's free, reliable, and instant. If you need WhatsApp, use Twilio (small cost but very reliable).

### Use Windows Task Scheduler Instead

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at desired time
4. Action: Start a program
   - Program: `python`
   - Arguments: `C:\path\to\event_tracker.py`
   - Start in: `C:\path\to\dubaifleamarket_scraping`

## 🐛 Troubleshooting

**"Authentication failed" error:**
- Make sure you're using App Password, not your regular Gmail password
- Check that 2FA is enabled on your Google account

**No email received:**
- Check spam folder
- Verify `TO_EMAIL` is correct
- Test with a simple print statement before the send_email() call

**GitHub Actions not running:**
- Check Actions tab for errors
- Verify secrets are added correctly (no extra spaces)
- Make sure workflow file is in `.github/workflows/` folder

## 📝 Files

- **`event_tracker.py`** - Main Python script that checks for events and sends emails (📝 **Edit lines 36-38**)
- **`seen_events.json`** - Database of previously seen events (auto-generated, prevents duplicates)
- **`.github/workflows/check_events.yml`** - GitHub Actions automation configuration (📝 **Edit line 47 for schedule**)
- **`requirements.txt`** - Python dependencies list
- **`.gitignore`** - Protects sensitive files from being uploaded to GitHub

**📚 Documentation:**
- **`README.md`** - This file (overview and benefits)
- **`QUICK_EDIT_REFERENCE.md`** - Exact lines to edit (fastest setup)
- **`SETUP_GUIDE.md`** - Detailed setup with screenshots and troubleshooting
- **`FILE_GUIDE.md`** - What each file does and where to find things
- **`HOW_IT_WORKS.md`** - Visual diagrams and architecture explanation

## 🎓 Learning Points

This project demonstrates:
- ✅ REST API consumption (better than web scraping!)
- ✅ JSON data handling
- ✅ Email automation with SMTP
- ✅ File I/O for state persistence
- ✅ CI/CD with GitHub Actions
- ✅ Environment variables for secrets

Perfect for your portfolio as a 4th-year student! 🚀

## 📜 License

Free to use and modify for personal projects.