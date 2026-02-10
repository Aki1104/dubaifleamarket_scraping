# 📋 Quick Reference: Lines to Edit

**Last Updated:** January 14, 2026

This document shows you **EXACTLY** which lines to edit to get started. No confusion, no guessing!

---

## 🎯 Step 1: Edit Email Configuration

### File: `event_tracker.py`

**Location:** Lines 36-40

**What to change:**

```python
# BEFORE (Default - Won't Work!)
MY_EMAIL = "your_email@gmail.com"  
MY_PASSWORD = "your_app_password_here"  
TO_EMAIL = "your_email@gmail.com"

# AFTER (Your Actual Details)
MY_EMAIL = "yourname@gmail.com"                    # ← Your Gmail
MY_PASSWORD = "abcd efgh ijkl mnop"                 # ← 16-char App Password
TO_EMAIL = "yourname@gmail.com"                     # ← Where to receive emails
```

### 💡 Optional: Notify Multiple People

```python
# Single recipient
TO_EMAIL = "you@gmail.com"

# Multiple recipients (add as many as you want!)
TO_EMAIL = "person1@gmail.com, person2@gmail.com, person3@gmail.com"
```

---

## ⏰ Step 2: Change Check Frequency (Optional)

### File: `.github/workflows/check_events.yml`

**Location:** Line 47 (inside the `schedule:` section)

**What to change:**

```yaml
# BEFORE (Default - Every 15 Minutes)
schedule:
  - cron: '*/15 * * * *'  # Every 15 minutes (96 checks/day)

# AFTER - Choose ONE of these options:

# Option A: Keep current (every 15 minutes - RECOMMENDED)
- cron: '*/15 * * * *'  # 96x/day, ~1,440 min/month ✅

# Option B: Every 30 minutes (more conservative)
- cron: '*/30 * * * *'  # 48x/day, ~720 min/month

# Option C: Every hour (very conservative)
- cron: '0 * * * *'  # 24x/day, ~360 min/month

# Option D: Every 5 minutes (TOO FREQUENT - exceeds free tier!)
# - cron: '*/5 * * * *'  # 288x/day, ~4,320 min/month ❌

# Option E: Specific times (9am, 12pm, 6pm, 9pm daily)
- cron: '0 9,12,18,21 * * *'  # 4x/day
```

**💡 Free Tier Limit:** GitHub Actions provides 2,000 minutes/month free
- Each run takes ~30-60 seconds
- Every 15 min = 1,440 minutes/month ✅ SAFE
- Every 5 min = 4,320 minutes/month ❌ EXCEEDS LIMIT

**Recommendation:** Keep default (`*/15 * * * *`) for fast notifications ⚡

---

## 🔑 Step 3: Add GitHub Secrets

**Location:** GitHub Repository → Settings → Secrets and variables → Actions

**Secrets to add:**

| Secret Name | Value | Example |
|-------------|-------|---------|
| `MY_EMAIL` | Your Gmail address | `yourname@gmail.com` |
| `MY_PASSWORD` | Your 16-char App Password | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | Notification email(s) | `yourname@gmail.com` or multiple |

### How to Add:
1. Go to your GitHub repo
2. Click **Settings** (top menu)
3. Sidebar → **Secrets and variables** → **Actions**
4. Click **"New repository secret"** (green button)
5. Enter name (e.g., `MY_EMAIL`)
6. Enter value (e.g., `yourname@gmail.com`)
7. Click **"Add secret"**
8. Repeat for all 3 secrets

---

## 📊 Summary: What Needs Your Attention

| File | Lines | What to Edit | Required? |
|------|-------|--------------|-----------|
| `event_tracker.py` | 36-38 | Email & password | ✅ YES |
| `.github/workflows/check_events.yml` | 47 | Schedule frequency | ⭐ Optional |
| GitHub Settings | N/A | Add 3 secrets | ✅ YES |
| `requirements.txt` | N/A | Nothing | ❌ No changes needed |
| `.gitignore` | N/A | Nothing | ❌ No changes needed |

---

## ✅ Verification Checklist

Before running:

### Local Testing:
- [ ] Edited `event_tracker.py` lines 36-38 with your email
- [ ] Obtained Gmail App Password (16 characters)
- [ ] Installed Python `requests` library (`pip install requests`)
- [ ] Ran `python event_tracker.py` successfully
- [ ] Received test email

### GitHub Deployment:
- [ ] Created GitHub repository
- [ ] Pushed code to GitHub (`git push`)
- [ ] Added all 3 secrets to GitHub Settings
- [ ] Enabled GitHub Actions
- [ ] Manually triggered workflow (to test)
- [ ] Workflow completed successfully (green checkmark)

---

## 🆘 Common Mistakes & Fixes

| Mistake | How to Fix |
|---------|-----------|
| Used regular Gmail password instead of App Password | Generate App Password at https://myaccount.google.com/apppasswords |
| Typo in email address | Double-check spelling in line 36 |
| Forgot to add GitHub secrets | Go to Settings → Secrets → Add all 3 |
| Used wrong secret names | Must be exactly `MY_EMAIL`, `MY_PASSWORD`, `TO_EMAIL` |
| `.github/workflows/` folder in wrong location | Must be in repo root: `.github/workflows/check_events.yml` |

---

## 🎯 Quick Copy-Paste Template

Save time! Copy this template and fill in your details:

```python
# ===== Paste this into event_tracker.py (lines 36-38) =====
MY_EMAIL = "PASTE_YOUR_EMAIL_HERE"
MY_PASSWORD = "PASTE_YOUR_16_CHAR_APP_PASSWORD_HERE"
TO_EMAIL = "PASTE_NOTIFICATION_EMAIL_HERE"
```

```yaml
# ===== Paste this into check_events.yml (line 47) =====
# Choose ONE option:
- cron: '*/15 * * * *'     # Every 15 minutes (RECOMMENDED - 1,440 min/month)
# - cron: '*/30 * * * *'   # Every 30 minutes (conservative)
# - cron: '0 * * * *'      # Every hour (very conservative)
# - cron: '*/5 * * * *'    # Every 5 minutes (EXCEEDS FREE TIER!)
```

---

## 📞 Need More Help?

- **How to get App Password:** See [SETUP_GUIDE.md](SETUP_GUIDE.md#2a-enable-2-factor-authentication)
- **GitHub setup details:** See [SETUP_GUIDE.md](SETUP_GUIDE.md#4a-create-github-repository)
- **Error troubleshooting:** See [SETUP_GUIDE.md](SETUP_GUIDE.md#-common-errors)
- **File purposes:** See [FILE_GUIDE.md](FILE_GUIDE.md)

---

**That's it!** Only 2 files to edit + 3 GitHub secrets = Working automated system! 🚀
