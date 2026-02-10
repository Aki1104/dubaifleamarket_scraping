# 🎯 Project Goal

## Dubai Flea Market Event Tracker - Mission Statement

### Primary Objective

**Never miss a Dubai Flea Market event again!**

The goal of this project is to create an **automated monitoring system** that:

1. **Continuously watches** the Dubai Flea Market website (dubai-fleamarket.com) for new events
2. **Instantly notifies** you via Telegram when new events are posted
3. **Runs 24/7** without any manual intervention
4. **Provides a dashboard** to monitor the system's health and activity

---

## 🎯 Key Goals

### 1. **Real-Time Event Detection**
- Monitor the Dubai Flea Market API every 5 minutes (configurable)
- Detect new events the moment they're posted
- Track all seen events to avoid duplicate notifications

### 2. **Instant Notifications**
- **Primary**: Telegram Bot notifications (FREE, unlimited, instant)
- **Backup**: Email notifications via Gmail SMTP
- Admin-only messages for heartbeat/status (subscribers only get new events)

### 3. **24/7 Reliability**
- Hosted on Render.com (free tier)
- UptimeRobot keeps the app alive
- Automatic recovery from errors
- Watchdog thread restarts the checker if it dies

### 4. **Easy Management**
- Web-based admin dashboard
- Password-protected controls
- Real-time status monitoring
- Activity logs and console output
- Test buttons to verify everything works

---

## 📊 Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Uptime | 99%+ | ✅ Running |
| Detection Speed | < 5 min | ✅ 5 min checks |
| Notification Delivery | 100% | ✅ Telegram working |
| False Positives | 0% | ✅ Deduplication in place |

---

## 🚀 Future Goals

- [ ] Add more notification channels (WhatsApp, Discord)
- [ ] Event filtering by location or type
- [ ] Price/date range alerts
- [ ] Multi-website support (other flea markets)
- [ ] Mobile app integration

---

## 💡 Why This Matters

Dubai Flea Market events are popular and sell out quickly. By automating the monitoring process, you can:

- **Be the first to know** when new events are announced
- **Plan ahead** and never miss your favorite markets
- **Save time** - no more manually checking the website
- **Stay informed** with daily summaries and heartbeat updates

---

*Built with ❤️ for Dubai Flea Market enthusiasts*
