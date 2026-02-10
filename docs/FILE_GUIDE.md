# 📁 Project File Structure

Quick reference for what each file does in this project.

---

## Core Files (You Need to Edit These)

### 📄 `event_tracker.py`
**Purpose:** Main Python script that does all the work  
**What it does:**
- Fetches events from dubai-fleamarket.com API
- Compares with previously seen events
- Sends email notifications for new events
- Saves event history to prevent duplicates

**Lines you need to edit:** 36-38 (email configuration)

---

### 📄 `.github/workflows/check_events.yml`
**Purpose:** Automation configuration for GitHub Actions  
**What it does:**
- Tells GitHub to run your script automatically
- Runs every hour (or your custom schedule)
- Safely stores your email credentials
- Updates the event database after each run

**Lines you need to edit:** 40 (schedule frequency)  
**What else:** Add secrets in GitHub Settings (MY_EMAIL, MY_PASSWORD, TO_EMAIL)

---

## Auto-Generated Files (Don't Edit These)

### 📄 `seen_events.json`
**Purpose:** Database of event IDs we've already seen  
**What it does:**
- Stores list of event IDs: `[7850, 7737, 7736, ...]`
- Prevents sending duplicate notifications
- Created automatically when script first runs
- Updated after each check

**Format:**
```json
[
  7850,
  7737,
  7736,
  7761,
  7636,
  7379
]
```

**⚠️ Warning:** Don't edit manually! The script manages this automatically.

---

## Documentation Files (Read These)

### 📄 `README.md`
**Purpose:** Project overview and quick start guide  
**What it contains:**
- Problem this solves (why you need this)
- Benefits and real-world impact
- Quick setup instructions
- How the system works
- Customization options

**Read this:** If you want to understand the "big picture"

---

### 📄 `SETUP_GUIDE.md`
**Purpose:** Step-by-step setup instructions  
**What it contains:**
- Exact lines to edit with screenshots
- How to get Gmail App Password
- Detailed GitHub deployment steps
- Troubleshooting common errors
- Multiple email & WhatsApp setup

**Read this:** When you're actually setting it up

---

### 📄 `FILE_GUIDE.md` (This File)
**Purpose:** Quick reference for project structure  
**What it contains:**
- What each file does
- Which files to edit vs. leave alone
- Where to find specific information

**Read this:** When you forget what a file does

---

## Configuration Files

### 📄 `requirements.txt`
**Purpose:** Lists Python libraries needed  
**Contents:**
```
requests==2.31.0
```
**Used by:** `pip install -r requirements.txt` command

---

### 📄 `.gitignore`
**Purpose:** Tells Git which files NOT to upload to GitHub  
**What it hides:**
- `seen_events.json` (your local database)
- `.env` files (if you add them later)
- Python cache files (`__pycache__/`)
- IDE config files

**Why:** Prevents accidentally committing sensitive data or junk files

---

## Folder Structure

```
dubaifleamarket_scraping/
│
├── 📄 event_tracker.py          ← Main script (EDIT THIS)
├── 📄 seen_events.json          ← Event database (auto-generated)
├── 📄 requirements.txt          ← Python dependencies
├── 📄 .gitignore                ← Git ignore rules
│
├── 📄 README.md                 ← Project overview
├── 📄 SETUP_GUIDE.md            ← Step-by-step setup
├── 📄 FILE_GUIDE.md             ← This file
│
└── 📁 .github/
    └── 📁 workflows/
        └── 📄 check_events.yml  ← GitHub Actions config (EDIT LINE 40)
```

---

## Which Files Go Where?

### ✅ Upload to GitHub:
- `event_tracker.py`
- `.github/workflows/check_events.yml`
- `requirements.txt`
- `.gitignore`
- `README.md`
- `SETUP_GUIDE.md`
- `FILE_GUIDE.md`

### ❌ DON'T Upload to GitHub:
- `seen_events.json` (local only, gets synced by GitHub Actions)
- `.env` (if you create one for local testing)
- Any file with passwords or API keys

### 🤖 Auto-Created by GitHub Actions:
- `seen_events.json` (synced to repo by workflow)

---

## Quick Action Guide

| I Want To... | Edit This File | Line(s) |
|--------------|---------------|---------|
| Change my email | `event_tracker.py` | 36-38 |
| Add multiple email recipients | `event_tracker.py` | 38 |
| Change check frequency | `.github/workflows/check_events.yml` | 40 |
| See what events were seen | `seen_events.json` | All (view only) |
| Reset notification history | Delete `seen_events.json` | N/A |
| Add GitHub secrets | GitHub Settings → Secrets | N/A |
| Test locally | Run `python event_tracker.py` | N/A |

---

## Need More Help?

- **General overview:** Read `README.md`
- **Setup instructions:** Read `SETUP_GUIDE.md`
- **File purpose:** Read this file (`FILE_GUIDE.md`)
- **Code questions:** Read comments in `event_tracker.py`
- **GitHub Actions issues:** Check `.github/workflows/check_events.yml` comments

---

**Last Updated:** January 14, 2026  
**Project:** Dubai Flea Market Event Notifier  
**Version:** 1.0
