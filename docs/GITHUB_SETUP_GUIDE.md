# 🚀 GitHub Actions Setup Guide

This guide walks you through deploying the Dubai Flea Market Event Tracker to GitHub Actions for 24/7 automated monitoring.

---

## 📋 Prerequisites

Before you begin, make sure you have:
- [ ] A GitHub account
- [ ] Git installed on your computer
- [ ] A Gmail account with App Password (see below)

---

## 🔐 Step 1: Get Gmail App Password

Gmail requires an "App Password" for scripts to send emails (your regular password won't work).

### 1.1 Enable 2-Factor Authentication
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Click **"2-Step Verification"**
3. Follow the steps to enable it

### 1.2 Generate App Password
1. Go to [App Passwords](https://myaccount.google.com/apppasswords)
2. Select app: **"Mail"**
3. Select device: **"Other (Custom name)"** → Enter "Dubai Flea Market Tracker"
4. Click **"Generate"**
5. **Copy the 16-character password** (looks like: `abcd efgh ijkl mnop`)
6. Save it somewhere safe - you'll need it for GitHub secrets!

---

## 📤 Step 2: Push Code to GitHub

### 2.1 Create a New Repository
1. Go to [GitHub](https://github.com) and sign in
2. Click the **"+"** icon → **"New repository"**
3. Name it: `dubai-fleamarket-tracker` (or any name you prefer)
4. Set to **Private** (recommended - keeps your project hidden)
5. **DON'T** initialize with README (we already have files)
6. Click **"Create repository"**

### 2.2 Push Your Local Code
Open PowerShell/Terminal in your project folder and run:

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - Dubai Flea Market Tracker"

# Add your GitHub repository as remote (replace with YOUR repo URL)
git remote add origin https://github.com/YOUR_USERNAME/dubai-fleamarket-tracker.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## 🔑 Step 3: Add GitHub Secrets (IMPORTANT!)

Secrets store your sensitive data (email, password) securely. GitHub encrypts them and they're never visible in logs.

### 3.1 Navigate to Secrets
1. Go to your repository on GitHub
2. Click **"Settings"** (tab at the top)
3. In the left sidebar, click **"Secrets and variables"** → **"Actions"**
4. Click **"New repository secret"**

### 3.2 Add Required Secrets

Add these secrets one by one:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `MY_EMAIL` | Your Gmail address | `yourname@gmail.com` |
| `MY_PASSWORD` | Your 16-char App Password | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | Recipients (comma-separated) | `email1@gmail.com,email2@gmail.com` |

### 3.3 Add Optional Secrets (Recommended)

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `DAILY_SUMMARY_ENABLED` | `true` or `false` | Get daily "system working" emails |
| `DAILY_SUMMARY_HOUR` | `0` to `23` | Hour in UTC to send summary |

**Time Zone Reference:**
| UTC Hour | Dubai Time (UTC+4) |
|----------|-------------------|
| `5` | 9:00 AM |
| `8` | 12:00 PM |
| `12` | 4:00 PM |
| `17` | 9:00 PM |

---

## ▶️ Step 4: Enable GitHub Actions

### 4.1 Verify Workflow File
Make sure `.github/workflows/check_events.yml` exists in your repository.

### 4.2 Enable Actions (if needed)
1. Go to your repository
2. Click **"Actions"** tab
3. If prompted, click **"I understand my workflows, go ahead and enable them"**

### 4.3 Test Manually (Recommended!)
1. Go to **"Actions"** tab
2. Click **"Check Dubai Flea Market Events"** in the left sidebar
3. Click **"Run workflow"** dropdown (right side)
4. Click the green **"Run workflow"** button
5. Wait ~30 seconds, then refresh the page
6. Click on the running workflow to see logs
7. Check your email!

---

## ⏰ Step 5: Configure Check Frequency (Optional)

The default is every 15 minutes. To change it:

### Edit `.github/workflows/check_events.yml`

Find this section:
```yaml
schedule:
  - cron: '*/15 * * * *'  # Every 15 minutes
```

**Timing Options:**
| Cron Expression | Frequency | Monthly Minutes* |
|-----------------|-----------|------------------|
| `'*/5 * * * *'` | Every 5 min | ❌ 4,320 (exceeds free tier) |
| `'*/15 * * * *'` | Every 15 min | ✅ 1,440 |
| `'*/30 * * * *'` | Every 30 min | ✅ 720 |
| `'0 * * * *'` | Every hour | ✅ 360 |

*GitHub Free Tier: 2,000 minutes/month

---

## ✅ Step 6: Verify Everything Works

### Check the Actions Tab
- ✅ **Green checkmark** = Success
- ❌ **Red X** = Failed (click to see error logs)

### Common Issues & Fixes

| Problem | Solution |
|---------|----------|
| "Email credentials not configured" | Double-check secrets are named exactly: `MY_EMAIL`, `MY_PASSWORD`, `TO_EMAIL` |
| "Authentication failed" | Regenerate Gmail App Password, make sure 2FA is enabled |
| "No recipients configured" | Check `TO_EMAIL` secret has valid email addresses |
| Workflow not running | Go to Actions tab, enable workflows if prompted |

---

## 🔧 Step 7: Ongoing Maintenance

### View Run History
1. Go to **Actions** tab
2. See all past runs with status

### Check Logs
1. Click on any workflow run
2. Click **"check-events"** job
3. Expand steps to see detailed output

### Update Recipients
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click on `TO_EMAIL`
3. Click **"Update"**
4. Enter new comma-separated list

### Disable Temporarily
1. Go to **Actions** tab
2. Click **"Check Dubai Flea Market Events"**
3. Click **"..."** menu → **"Disable workflow"**

---

## 📊 Understanding the Files

| File | Purpose | Committed to GitHub? |
|------|---------|---------------------|
| `event_tracker.py` | Main script | ✅ Yes |
| `check_events.yml` | Automation schedule | ✅ Yes |
| `seen_events.json` | Tracks seen events | ✅ Yes (auto-updated) |
| `tracker_status.json` | Daily summary timing | ✅ Yes (auto-updated) |
| `.env` | Local credentials | ❌ No (gitignored) |
| `.env.example` | Template for others | ✅ Yes |

---

## 💡 Pro Tips

### 1. Test Before Going Live
- Run workflow manually first
- Check emails arrive correctly
- Verify all recipients receive them

### 2. Monitor First Few Days
- Check Actions tab daily for first week
- Ensure no failures

### 3. Keep App Password Secure
- Never share it
- Never commit it to code
- Regenerate if compromised

### 4. Free Tier Limits
- 2,000 minutes/month
- Every 15 min = ~1,440 minutes ✅
- Every 5 min = ~4,320 minutes ❌

---

## 🆘 Need Help?

### Check Workflow Logs
Most issues can be diagnosed by reading the error messages in the Actions logs.

### Common Error Messages

**"smtplib.SMTPAuthenticationError"**
→ App Password is wrong or 2FA not enabled

**"No module named 'requests'"**
→ Check `requirements.txt` exists with `requests` listed

**"Permission denied" on git push**
→ Workflow needs write permissions (check step below)

### Enable Workflow Write Permissions (if needed)
1. Go to **Settings** → **Actions** → **General**
2. Scroll to **"Workflow permissions"**
3. Select **"Read and write permissions"**
4. Click **Save**

---

## ✨ You're All Set!

Once configured, the tracker will:
- ✅ Check for new events every 15 minutes
- ✅ Send instant email when new events are posted
- ✅ Send daily summary (if enabled)
- ✅ Run 24/7 even when your computer is off
- ✅ Keep your credentials secure

**Happy event hunting! 🎉**

---

*Created by MSBP - Dubai Flea Market Event Tracker*
