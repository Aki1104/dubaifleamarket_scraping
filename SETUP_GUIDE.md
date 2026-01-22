# 🛠️ Quick Setup Guide - Lines You Need to Edit

This guide shows you **EXACTLY** which lines to change to get your event notifier working.

---

## 📝 Step 1: Edit `event_tracker.py`

**Open:** `event_tracker.py`

### Find These Lines (Around Line 36-38):

```python
MY_EMAIL = "your_email@gmail.com"  # 👈 CHANGE THIS
MY_PASSWORD = "your_app_password_here"  # 👈 CHANGE THIS
TO_EMAIL = "your_email@gmail.com"  # 👈 CHANGE THIS
```

### Change Them To:

```python
MY_EMAIL = "yourname@gmail.com"  # Your actual Gmail
MY_PASSWORD = "abcd efgh ijkl mnop"  # Your 16-char App Password from Step 2
TO_EMAIL = "yourname@gmail.com"  # Where you want notifications
```

### 💡 Want to Notify Multiple People?

Change `TO_EMAIL` to a comma-separated list:

```python
TO_EMAIL = "person1@gmail.com, person2@gmail.com, person3@gmail.com"
```

---

## 🔑 Step 2: Get Gmail App Password

### 2A. Enable 2-Factor Authentication

1. Go to: https://myaccount.google.com/security
2. Find "2-Step Verification"
3. Click "Get Started" and follow instructions
4. **Important:** You must complete this before Step 2B!

### 2B. Generate App Password

1. Go to: https://myaccount.google.com/apppasswords
2. You'll see "App passwords" section
3. Click "Select app" → Choose "Mail" or "Other"
4. Type: "Python Event Notifier"
5. Click "Generate"
6. Copy the **16-character code** (looks like: `abcd efgh ijkl mnop`)
7. Paste this into `MY_PASSWORD` in Step 1

**Screenshot Guide:**
```
┌─────────────────────────────────────┐
│ Google Account                      │
├─────────────────────────────────────┤
│ App passwords                       │
│                                     │
│ Select app: Mail ▼                 │
│ Select device: Other (Custom name) │
│                                     │
│ [Generate]                         │
│                                     │
│ Your app password:                  │
│ ┌─────────────────────────────┐   │
│ │ abcd efgh ijkl mnop         │   │
│ └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## 🧪 Step 3: Test Locally

Open PowerShell/Terminal in project folder:

```powershell
# Install required library
pip install requests

# Run the script
python event_tracker.py
```

### ✅ Expected Output (Success):

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

### ❌ Common Errors:

| Error | Solution |
|-------|----------|
| `Authentication failed` | Use App Password (16 chars), not regular password |
| `Invalid credentials` | Check MY_EMAIL is correct Gmail address |
| `Connection refused` | Check internet connection |
| `No module named 'requests'` | Run: `pip install requests` |

---

## 🚀 Step 4: Deploy to GitHub (Automated 24/7)

### 4A. Create GitHub Repository

1. Go to: https://github.com/new
2. Repository name: `dubai-flea-market-notifier`
3. Choose "Public" or "Private" (both work)
4. **DO NOT** initialize with README (we already have one)
5. Click "Create repository"

### 4B. Push Your Code

```powershell
# Initialize git (if not already)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Dubai Flea Market Notifier"

# Connect to GitHub (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/dubai-flea-market-notifier.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### 4C. Add GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** (top menu)
3. Left sidebar → **Secrets and variables** → **Actions**
4. Click **"New repository secret"** (green button)

Add these **3 secrets**:

| Name | Value | Example |
|------|-------|---------|
| `MY_EMAIL` | Your Gmail address | `yourname@gmail.com` |
| `MY_PASSWORD` | Your 16-char App Password | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | Where to send notifications | `yourname@gmail.com` OR `email1@gmail.com, email2@gmail.com` |

**Screenshot:**
```
┌────────────────────────────────────────┐
│ Actions secrets / New secret           │
├────────────────────────────────────────┤
│ Name *                                 │
│ ┌────────────────────────────────┐    │
│ │ MY_EMAIL                       │    │
│ └────────────────────────────────┘    │
│                                        │
│ Secret *                               │
│ ┌────────────────────────────────┐    │
│ │ yourname@gmail.com             │    │
│ └────────────────────────────────┘    │
│                                        │
│ [Add secret]                          │
└────────────────────────────────────────┘
```

### 4D. Enable GitHub Actions

1. Go to **Actions** tab in your repository
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. You should see "Check Dubai Flea Market Events" workflow
4. Click **"Run workflow"** → **"Run workflow"** (to test immediately)

---

## ⚙️ Step 5: Customize Check Frequency (Optional)

**Open:** `.github/workflows/check_events.yml`

**Find Line 47:**

```yaml
- cron: '*/15 * * * *'  # Every 15 minutes (default)
```

**Change To:**

| Frequency | Cron Expression | Description | Monthly Usage |
|-----------|----------------|-------------|---------------|
| Every 15 minutes (default) | `*/15 * * * *` | Fast notifications ⚡ | ~1,440 min ✅ |
| Every 30 minutes | `*/30 * * * *` | Balanced (48 checks/day) | ~720 min |
| Every hour | `0 * * * *` | Conservative (24 checks/day) | ~360 min |
| Every 2 hours | `0 */2 * * *` | Very conservative (12 checks/day) | ~180 min |
| 9am, 12pm, 6pm, 9pm | `0 9,12,18,21 * * *` | Strategic times (4 checks/day) | ~60 min |
| Every 5 minutes | `*/5 * * * *` | **TOO FREQUENT** ❌ | ~4,320 min ⚠️ |

**💡 Pro Tip:** Free tier = 2,000 minutes/month. Each run takes ~30-60 seconds.
- ✅ Every 15 min = 1,440 minutes/month (SAFE)
- ❌ Every 5 min = 4,320 minutes/month (EXCEEDS LIMIT)

**Recommendation:** Keep default (every 15 minutes) for best balance between speed and free tier usage.

---

## 📱 BONUS: Add More Notification Methods

### ✅ Multiple Emails (Easy - Already Supported!)

Just edit `TO_EMAIL` to include multiple addresses:

```python
TO_EMAIL = "you@gmail.com, friend@gmail.com, family@yahoo.com"
```

Everyone in the list gets the email when new events are posted!

---

### 📱 WhatsApp Notifications (Advanced - Requires Extra Setup)

WhatsApp is **possible** but more complex. Here are your options:

#### Option 1: Twilio (Easiest - Costs $)
- **Cost:** ~$0.005 per message
- **Setup:** 15 minutes
- **Reliability:** Very high
- **Steps:**
  1. Sign up: https://www.twilio.com/whatsapp
  2. Get API credentials
  3. Add this to `event_tracker.py`:
  
  ```python
  from twilio.rest import Client
  
  def send_whatsapp(message):
      client = Client("YOUR_ACCOUNT_SID", "YOUR_AUTH_TOKEN")
      client.messages.create(
          from_='whatsapp:+14155238886',  # Twilio sandbox
          to='whatsapp:+971501234567',  # Your number with country code
          body=message
      )
  ```

#### Option 2: Unofficial WhatsApp API (Free but Risky)
- **Cost:** Free
- **Risk:** WhatsApp might ban your number
- **Reliability:** Medium
- **Libraries:** `pywhatkit`, `selenium-based bots`
- **Not Recommended:** Violates WhatsApp Terms of Service

#### Option 3: WhatsApp Business API (Official but Complex)
- **Cost:** Free (self-hosted) or paid (cloud)
- **Setup:** Very complex, requires business verification
- **Best For:** Companies, not individuals

#### Recommendation:
For a student project, **stick with email** - it's free, reliable, and professional. If you really need WhatsApp, use Twilio for testing (they give free trial credit).

---

## ✅ Verification Checklist

Before going live, check:

- [ ] `event_tracker.py` has your correct email and App Password
- [ ] You tested locally and received an email
- [ ] Code is pushed to GitHub
- [ ] All 3 secrets are added to GitHub (MY_EMAIL, MY_PASSWORD, TO_EMAIL)
- [ ] GitHub Actions is enabled
- [ ] You manually triggered the workflow and it succeeded
- [ ] `seen_events.json` was created (locally or in repo)

---

## 🆘 Need Help?

**Error in local testing?**
- Check the "Common Errors" table in Step 3

**GitHub Actions failing?**
- Go to Actions tab → Click failed run → Check error logs
- Most common: Forgot to add secrets or typo in secret names

**No email received?**
- Check spam folder
- Verify TO_EMAIL is correct
- Make sure first run found "new" events (won't send if no new events)

**Want to force a notification?**
- Delete `seen_events.json` file
- Run script again - it will treat all events as "new"

---

## 🎯 What's Next?

Once setup is complete:
1. Your script checks every 15 minutes (or your custom schedule)
2. When a new event is posted, you get an email within 15 minutes (or less if you customized frequency)
3. You book your spot before others who are manually refreshing!
4. You can turn off your computer - GitHub Actions runs in the cloud 24/7

**Competitive Advantage:** While others check manually every 30 minutes, your system checks automatically and notifies you instantly - even at 3am! 🚀
