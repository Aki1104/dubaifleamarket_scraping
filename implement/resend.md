# Resend implementation plan

## Overview
Resend is a transactional email provider with a simple HTTP API. We will use it as a replacement or fallback to Gmail SMTP on Render.

## Proposed approach
- Add an API key in `.env` (for example: `RESEND_API_KEY`).
- Create a small helper in `app.py` to send emails via Resend.
- Switch email delivery logic to prefer Resend when the key is present.
- Keep Gmail SMTP as a fallback if needed.

## Steps to implement
1. Create a Resend account and generate an API key.
2. Add the API key to Render environment variables.
3. Add a send function using the Resend REST API.
4. Wire the new send function into the existing email flow.
5. Verify delivery using a test email.

## Notes
- Resend offers a free tier with a daily limit.
- Using a dedicated transactional provider improves deliverability on Render.
