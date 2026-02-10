# =============================================================================
# 🚀 RENDER + UPTIMEROBOT DEPLOYMENT GUIDE
# =============================================================================

## Why Move from GitHub Actions to Render?

### GitHub Actions Issues:
- ❌ Scheduled workflows can be delayed 5-60 minutes
- ❌ GitHub may skip runs during high load
- ❌ No real-time monitoring dashboard
- ❌ Limited to 2,000 minutes/month on free tier

### Render + UptimeRobot Benefits:
- ✅ True 24/7 uptime with UptimeRobot pinging
- ✅ Beautiful admin dashboard to monitor the bot
- ✅ Real-time logs and controls
- ✅ Toggle features on/off without code changes
- ✅ Free tier with 750 hours/month (enough for 24/7!)

---

## Step 1: Deploy to Render

### Option A: Quick Deploy (Recommended)

1. **Go to Render**: https://render.com
2. **Sign up/Login** with GitHub
3. **Create New Web Service**:
   - Connect your GitHub repo: `Aki1104/dubaifleamarket_scraping`
   - Render will auto-detect `render.yaml`

4. **Set Environment Variables** in Render Dashboard:
   - Go to your service → Environment
   - Add these secrets:
   
   | Key | Value |
   |-----|-------|
   | `MY_EMAIL` | your.email@gmail.com |
   | `MY_PASSWORD` | your-gmail-app-password |
   | `TO_EMAIL` | recipient@email.com |

5. **Deploy!** Click "Create Web Service"

### Option B: Manual Setup

1. **Create New Web Service** on Render
2. **Settings**:
   - **Build Command**: `pip install -r requirements-render.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2`
   - **Health Check Path**: `/health`
3. Add environment variables as shown above

---

## Step 2: Set Up UptimeRobot (Keep Service Alive)

Render's free tier "sleeps" after 15 minutes of inactivity.
UptimeRobot pings your service every 5 minutes to keep it awake!

1. **Go to UptimeRobot**: https://uptimerobot.com
2. **Sign up** (free account)
3. **Add New Monitor**:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Dubai Flea Market Tracker
   - **URL**: `https://your-render-url.onrender.com/health`
   - **Monitoring Interval**: 5 minutes

4. **Optional**: Set up alerts to notify you if the service goes down

---

## Step 3: Disable GitHub Actions (Optional)

Once Render is working, you can disable GitHub Actions:

1. Go to your repo → `.github/workflows/check_events.yml`
2. Add this at the top to disable:
   ```yaml
   # Disabled - now using Render for 24/7 monitoring
   # on:
   #   schedule:
   #     - cron: '*/15 * * * *'
   ```

Or delete the workflow file entirely.

---

## Dashboard Features

Your admin dashboard at `https://your-app.onrender.com/` includes:

### 📊 Stats Cards:
- Total checks performed
- Events tracked
- New events found
- Uptime counter

### ⏱️ Live Timers:
- Countdown to next event check
- Countdown to next heartbeat email

### 🎛️ Controls:
- Toggle tracker on/off
- Toggle heartbeat emails on/off
- Manual "Check Now" button
- Manual "Send Heartbeat" button
- Clear logs

### 📜 Activity Logs:
- Real-time log of all activities
- Color-coded by type (success/error/warning)

### 📅 Recent Events:
- Last 10 tracked events with links

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Admin dashboard |
| `/health` | GET | Health check (for UptimeRobot) |
| `/api/status` | GET | JSON status data |
| `/api/toggle/tracker` | POST | Toggle tracker on/off |
| `/api/toggle/heartbeat` | POST | Toggle heartbeat on/off |
| `/api/check-now` | POST | Trigger immediate check |
| `/api/send-heartbeat` | POST | Send heartbeat now |
| `/api/logs` | GET | Get activity logs |
| `/api/clear-logs` | POST | Clear logs |

---

## Troubleshooting

### Service keeps sleeping?
- Make sure UptimeRobot is set to 5-minute intervals
- Check UptimeRobot dashboard for failed pings

### Emails not sending?
- Verify MY_EMAIL and MY_PASSWORD in Render environment
- Make sure you're using a Gmail App Password, not regular password

### Events not being detected?
- Check the activity logs in the dashboard
- Verify the Dubai Flea Market API is accessible

---

## Cost Comparison

| Platform | Free Tier | Reliability | Dashboard |
|----------|-----------|-------------|-----------|
| GitHub Actions | 2,000 min/month | Medium (delays possible) | ❌ No |
| Render + UptimeRobot | 750 hrs/month | High | ✅ Yes |
| Railway | 500 hrs/month | High | ❌ No |
| Fly.io | 2,340 hrs/month | High | ❌ No |

**Recommendation**: Render + UptimeRobot is the best free option for this use case!

---

## Need Help?

- **Render Docs**: https://render.com/docs
- **UptimeRobot Docs**: https://uptimerobot.com/help
- **Gmail App Passwords**: https://myaccount.google.com/apppasswords
