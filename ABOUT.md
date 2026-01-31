# 📖 About This Project

## Dubai Flea Market Event Tracker

### What is it?

This is an **automated event monitoring bot** that watches the Dubai Flea Market website and sends you instant notifications when new events are posted. It runs 24/7 in the cloud and requires zero manual intervention.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLOUD (Render.com)                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                        Flask App                             │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │ Background  │  │   Admin     │  │   Notification      │  │ │
│  │  │  Checker    │→ │  Dashboard  │  │     Engine          │  │ │
│  │  │  (5 min)    │  │  (Web UI)   │  │  (Telegram/Email)   │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                                         │
         ▼                                         ▼
┌─────────────────┐                    ┌─────────────────────┐
│  Dubai Flea     │                    │    Telegram Bot     │
│  Market API     │                    │    @MSBP_dubai...   │
└─────────────────┘                    └─────────────────────┘
```

---

## 🔧 Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | Python 3.11 + Flask | Web server & API |
| Frontend | HTML/CSS/JS | Admin dashboard |
| Hosting | Render.com (Free) | 24/7 cloud hosting |
| Notifications | Telegram Bot API | Instant free messages |
| Keep-Alive | UptimeRobot | Prevents Render spin-down |
| Data Storage | JSON files | Event tracking & config |

---

## 📱 Notification Types

### For Everyone (Subscribers)
- 🆕 **New Events** - Sent when new events are posted on the website

### For Admin Only
- 💓 **Heartbeat** - Periodic "bot is alive" status updates
- 📊 **Daily Summary** - Daily recap of bot activity
- 🧪 **Test Messages** - Manual tests from the dashboard

---

## 🖥️ Admin Dashboard Features

### Monitoring
- ✅ Real-time bot status (Running/Stopped)
- ⏱️ Countdown timers to next check & heartbeat
- 📈 Event statistics chart (daily/hourly)
- 📋 Activity log with timestamps
- 🖥️ System console output

### Controls
- ▶️ Start/Stop tracker
- 🔄 Force check now
- 📧 Send test notifications
- ⚙️ Configure settings (intervals, recipients)
- 🔍 Search tracked events
- 📥 Export logs (JSON/CSV)

### Appearance
- 🌙 Dark/Light theme toggle
- 📱 Mobile responsive design
- 🔔 Browser notifications

---

## 🔐 Security

- 🔑 Password-protected admin actions
- 🚫 Rate limiting (100 requests/minute)
- 🔒 Environment variables for sensitive data
- 👤 Admin-only Telegram chat ID for status messages

---

## 📁 File Structure

```
dubaifleamarket_scraping/
├── app.py                 # Main Flask application (2500+ lines)
├── requirements.txt       # Python dependencies
├── seen_events.json       # Database of tracked events
├── tracker_status.json    # Bot status & settings
├── templates/
│   └── dashboard.html     # Admin dashboard UI
├── static/
│   ├── dashboard.css      # Dashboard styles
│   └── dashboard.js       # Dashboard logic
├── GOAL.md               # Project goals
├── ABOUT.md              # This file
├── README.md             # Quick start guide
└── ... (other docs)
```

---

## 🌐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Your Telegram bot token |
| `TELEGRAM_CHAT_IDS` | ✅ | Comma-separated chat IDs for notifications |
| `TELEGRAM_ADMIN_CHAT_ID` | ⭐ | Your chat ID for admin-only messages |
| `ADMIN_PASSWORD` | ✅ | Password for dashboard actions |
| `MY_EMAIL` | ❌ | Gmail address (backup) |
| `MY_PASSWORD` | ❌ | Gmail app password (backup) |

---

## 📊 How It Works

1. **Every 5 minutes**, the bot checks the Dubai Flea Market API
2. **Compares** the events against previously seen events
3. **If new events found**, sends Telegram notification to all subscribers
4. **Saves** new events to the database to prevent duplicates
5. **Every few hours**, sends heartbeat to admin confirming bot is alive
6. **Daily**, sends summary report to admin

---

## 🚀 Deployment

This project is designed to run on **Render.com's free tier**:

1. Connect GitHub repo to Render
2. Set environment variables
3. Deploy!
4. Set up UptimeRobot to ping the `/api/health` endpoint

The bot will run 24/7 automatically!

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 2026 | Initial release with email notifications |
| 2.0 | Jan 2026 | Added Telegram Bot integration |
| 2.1 | Jan 2026 | Added admin-only messages, removed SendGrid |
| 2.2 | Jan 2026 | Added real API Telegram test |

---

## 👨‍💻 Author

Built by a Dubai Flea Market enthusiast who got tired of manually checking for new events!

---

## 📄 License

MIT License - Feel free to modify and use for your own projects!

---

*Last updated: January 2026*
