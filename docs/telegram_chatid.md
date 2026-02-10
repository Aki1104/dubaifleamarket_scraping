# 📱 How to Get Your Telegram Chat ID

This guide shows you how to get the **Chat ID** you need for the `TELEGRAM_CHAT_IDS` and `TELEGRAM_ADMIN_CHAT_ID` environment variables.

---

## Method 1: Using @userinfobot (Easiest)

1. Open Telegram
2. Search for **@userinfobot**
3. Start a chat and send any message
4. The bot will reply with your **Chat ID** (a number like `123456789`)

---

## Method 2: Using @RawDataBot

1. Open Telegram
2. Search for **@RawDataBot**
3. Start a chat and send any message
4. Look for the `"id"` field under `"chat"` in the response

---

## Method 3: Using the Telegram Bot API (After Creating Your Bot)

### Step 1: Create your bot with @BotFather (if not done already)

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts to name your bot
4. Copy the **Bot Token** (looks like `1234567890:ABCdefGhIjKlMnOpQrStUvWxYz`)

### Step 2: Send a message to your bot

1. Search for your new bot by its username
2. Click **Start** and send any message (e.g., "hello")

### Step 3: Get your Chat ID from the API

Open this URL in your browser (replace `YOUR_BOT_TOKEN` with your actual token):

```
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
```

Example:
```
https://api.telegram.org/bot1234567890:ABCdefGhIjKlMnOpQrStUvWxYz/getUpdates
```

### Step 4: Find the chat ID in the response

Look for the `"chat"` object in the JSON response:

```json
{
  "result": [
    {
      "message": {
        "chat": {
          "id": 123456789,    <-- THIS IS YOUR CHAT ID
          "first_name": "Your Name",
          "type": "private"
        }
      }
    }
  ]
}
```

The number next to `"id"` is your **Chat ID**.

---

## Method 4: Getting a Group Chat ID

If you want to send messages to a **group chat**:

1. Add your bot to the group
2. Send a message in the group
3. Visit: `https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates`
4. Find the group chat — its ID will be a **negative number** (e.g., `-1001234567890`)

---

## Setting Up Environment Variables

Once you have your chat ID(s), set the environment variables:

| Variable | Purpose | Example |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Your bot's API token from @BotFather | `1234567890:ABCdef...` |
| `TELEGRAM_CHAT_IDS` | Comma-separated IDs for event alerts (all subscribers) | `123456789,987654321` |
| `TELEGRAM_ADMIN_CHAT_ID` | Single ID for admin-only messages (heartbeat, errors) | `123456789` |

### In your `.env` file:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIjKlMnOpQrStUvWxYz
TELEGRAM_CHAT_IDS=123456789,987654321
TELEGRAM_ADMIN_CHAT_ID=123456789
```

### In Render Dashboard:
1. Go to your service → **Environment**
2. Add each variable as a key-value pair
3. Click **Save Changes** — the service will restart automatically

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `getUpdates` returns empty `"result": []` | Send a message to the bot first, then try again |
| Bot doesn't respond | Make sure you clicked **Start** in the bot chat |
| Group chat ID not showing | Remove and re-add the bot to the group, then send a message |
| Error 401 Unauthorized | Your bot token is invalid — get a new one from @BotFather |
| Error 403 Forbidden | The bot was blocked or removed from the chat |

---

## Quick Reference

```
Bot Token  →  @BotFather → /newbot
Chat ID    →  @userinfobot or getUpdates API
Group ID   →  Negative number from getUpdates
Admin ID   →  Your personal chat ID only
```
