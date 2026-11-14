# Creator Assistant

An AI executive assistant for social media creators: deals and barter tracking, schedule with clash
detection, cab/porter booking with approval, invoices with payment links, brand outreach, and chat or
voice in English, Hindi and Marathi. Works on web and Telegram.

## What is real and what is a demo stub

| Area | Status |
|---|---|
| Auth (JWT access + refresh, bcrypt, rate limits, audit log, per-user data isolation) | Real |
| Deals, barter stages, calendar with clash detection, contacts, invoices (PDF) | Real |
| Agent with tool calling and human approval for bookings | Real |
| LLM | `mock` rule-based brain by default; set `LLM_PROVIDER=openai_compat` for a real model |
| Voice to text | Real with `faster-whisper` (optional install) |
| Telegram bot (text, voice, approve/reject buttons, reminders) | Real, needs a bot token |
| Payments | Razorpay payment link if test keys are set, otherwise a UPI link |
| Cab and porter booking | **Mock provider** plus Uber and Google Maps deep links. Replace `app/services/logistics.py` with a partner API |
| Gmail: connect, read brand emails, classify, draft replies, save drafts to Gmail, add to deals | Real, needs Google credentials (see Gmail setup) |
| Google Calendar two-way sync, event suggestions from emails | Real, needs the Calendar API enabled (see Calendar setup) |
| Follow-up reminders (you owe a reply / brand is silent), nudge drafts | Real |
| Instagram data | **Not built.** Needs a Meta app review |
| Translation | Uses the LLM. Swap in IndicTrans2 in `app/services/translate.py` |

## Quick start (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then set SECRET_KEY
python -m scripts.seed                                 # demo user: demo@example.com / demo12345
uvicorn app.main:app --reload
```

Open http://localhost:8000 (web app) or http://localhost:8000/docs (API docs).

Try in the chat: `Add a barter deal with Mamaearth`, `list deals`,
`Book a cab from Panvel to Bandra tomorrow at 4 pm`, `create invoice for deal 3`,
`suggest brands`, `draft a pitch to Nykaa`.

## Use a real free LLM

Local with Ollama:
```bash
ollama pull llama3.1
# .env
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
```
Hosted free tiers (Groq, Gemini, OpenRouter): use the base URLs in `.env.example` and put your key in
`LLM_API_KEY`. Pick a model that supports tool calling.

## Gmail setup

What it does: reads your inbox, keeps only brand-related emails (paid collab, barter, negotiation, payment,
event invite), summarises them, pulls out brand, amount and deliverables, and writes a draft reply. You can
edit the draft and save it to your Gmail Drafts folder, or turn the email into a deal with one click.

Safety choices built in:
- The app **never sends email**. It only creates drafts (no `gmail.send` scope).
- Emails classified as unrelated are **not stored**. Email bodies and OAuth tokens are **encrypted at rest**.
- Email text is treated as untrusted. The model that reads it has no tools, so a malicious email cannot trigger actions.
- Disconnect revokes the Google token and deletes the saved emails.

Setup:
1. Go to https://console.cloud.google.com, create a project, and enable the **Gmail API**.
2. OAuth consent screen: choose External, add yourself under **Test users**.
3. Credentials: create an **OAuth client ID** of type Web application. Add the redirect URI
   `http://localhost:8000/gmail/callback`.
4. Put the client ID and secret in `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) and set `FERNET_KEY`
   (command is in `.env.example`) so tokens stay decryptable across restarts.
5. Restart, open the **Inbox** tab, click **Connect Gmail**.

Before a public launch: Google treats `gmail.readonly` and `gmail.compose` as restricted scopes, so you will
need app verification and a security assessment. In Testing mode you are limited to listed test users and
refresh tokens expire after about a week. Check Google's current policy before planning your launch date.

In chat you can say: `check my inbox`, `draft a reply to email 3`. With the Celery worker running, new collab
and payment emails are checked every 10 minutes and sent to you on Telegram.

## Google Calendar setup

1. Google Cloud Console: enable the **Google Calendar API** for the same project you use for Gmail.
2. OAuth consent screen, Data access: add the scope `https://www.googleapis.com/auth/calendar.events`.
3. Restart the app, open **Schedule**, click **Connect Google Calendar** and approve. This asks Google for
   the extra permission, so existing Gmail users must do it once.

What it does:
- New events (from chat, the API, or accepted email suggestions) are created in Google Calendar with a 30 minute reminder.
- **Sync now** (and the background job) imports your Google events so clash detection sees your whole day.
  All-day entries are skipped. Events edited or cancelled in Google are updated here.
- Events imported from Google are never deleted from Google when you remove them here.
- When a brand email mentions a shoot, meeting or deadline date, a suggestion appears in **Schedule**.
  Nothing is added until you click **Add to calendar**.
- If Google reports a missing permission, Schedule shows a clear message and the Connect button returns.

## Follow-up reminders

The app reads Gmail thread metadata (sender and time only) for saved brand emails from the last 45 days.
- **You owe a reply**: the brand wrote last and `REPLY_AFTER_DAYS` (default 2) have passed.
- **Waiting on brand**: you wrote last and `FOLLOWUP_AFTER_DAYS` (default 3) have passed.
- Replies you send from Gmail itself are noticed, so nothing needs to be logged by hand.
- Actions in Inbox, Follow-ups: draft a reply or nudge, save it to Gmail drafts (never sent), snooze 2 days, or mark done.
- A dismissed thread stays quiet until it changes. Closed deals are skipped.
- With Telegram linked you get a reminder, repeated at most every 2 days.
- Nudge wording lives in `nudge_template` in `app/services/email_ai.py`. Edit it to change your tone.
- In chat: `any follow-ups pending?`, `sync my calendar`.

Job alerts, `noreply` senders and platform notifications (Indeed, LinkedIn, Google and similar) are filtered out.
Use **Clean up** in the Inbox to remove ones saved earlier.

## Background jobs

Option 1, no extra software: set `BACKGROUND_JOBS=true` in `.env`. The API runs reminders every minute,
Gmail and calendar sync every 10 minutes, and follow-up checks about every 3 hours.

Option 2, Celery (production): `celery -A app.worker.celery worker -B -l info`. Do not enable both at once.

## Creator profile and personalization

Open **Profile & preferences** from the account menu (top right, or More on a phone).
- Fill in your details: display name, handle, niche, bio, city, creator type, languages, currency, payment defaults.
- **Social accounts** are added by hand (handle, link, follower count). There is no OAuth, so numbers are as you enter them.
- **Creator type** (Influencer, YouTuber, Gamer, Streamer, Podcaster, Blogger, Other) changes the wording and shortcuts, for example
  Deals becomes Sponsorships. Every feature stays available to every type. Edit `app/services/personas.py` to change the wording.
- The assistant gets your creator type, niche, channels, city, languages, currency and bio. Your **phone, email, pickup location,
  UPI ID and GSTIN are never sent to the AI model**.
- Payment terms and invoice notes are printed on new invoice PDFs. Invoices are still created in rupees until the invoice redesign.

New tables `creator_profiles` and `social_accounts` are created automatically at startup. Existing tables are not altered.

## Voice

```bash
pip install -r requirements-ml.txt     # faster-whisper, downloads the model on first use
```
The mic button in the web app and voice notes in Telegram then work. Use `WHISPER_MODEL=medium` for
better Hindi and Marathi accuracy on a stronger machine.

## Telegram

1. Create a bot with @BotFather and put the token in `.env` as `TELEGRAM_BOT_TOKEN`.
2. `python -m bot.telegram_bot`
3. In the web app click **Link Telegram**, then send `/link CODE` to the bot.

## Reminders (Celery + Redis)

```bash
celery -A app.worker.celery worker -B -l info
```
Sends a Telegram reminder 30 minutes before events and one day before content due dates.

## Docker (Postgres + Redis + API + worker)

```bash
cp .env.example .env
docker compose up --build
docker compose --profile telegram up bot     # optional bot
```

## Tests

```bash
pytest -q
```

## Project layout

```
app/
  main.py            FastAPI app, serves the web UI at /app
  models.py          Users, deals, events, invoices, bookings, pending actions, audit log
  security.py        JWT, bcrypt, token encryption, audit helper
  routers/           auth, deals, events, contacts, invoices, agent, voice, outreach, gmail
  services/
    agent.py         LLM loop, tool execution, approval flow
    tools.py         Tools the LLM can call
    llm.py           OpenAI-compatible client and mock brain
    logistics.py     Cab and porter (mock + deep links)
    payments.py      Razorpay link or UPI link
    invoice_pdf.py   Invoice PDFs
    outreach.py      Brand matching and pitch drafts (data/brands.csv)
    speech.py        faster-whisper
    gmail_client.py  Gmail REST calls and OAuth
    gmail_sync.py    Sync, draft, add-to-deal, disconnect
    email_ai.py      Noise filter, classification, reply and nudge drafts
    email_dates.py   Finds shoot, meeting and deadline dates in emails
    suggestions.py   Stores date suggestions found in emails
    calendar_client.py  Google Calendar REST calls
    calendar_sync.py    Push, pull, reconcile events; accept suggestions
    followups.py     Thread follow-up tracking and nudges
  jobs.py            Scheduled work (reminders, syncs, follow-up cycle)
  background.py      In-process scheduler (BACKGROUND_JOBS=true)
  worker.py          Celery wrappers for the same jobs
  timeutil.py        India time helpers
bot/telegram_bot.py  Telegram interface
web/index.html       Dashboard and chat
tests/               API smoke tests
```

## Next steps

1. Connect a real LLM (Ollama or Groq) so Hindi and Marathi sentences are understood in full.
2. Fix voice (`pip install -r requirements-ml.txt`).
3. Real logistics partner API.
4. pgvector memory for past conversations and brand history.
5. Media kit PDF generator and contract templates.
6. Replace `create_all` with Alembic migrations before storing real user data.
7. Production checklist: strong `SECRET_KEY`, HTTPS, restricted CORS, privacy policy and consent for
   inbox access (DPDP Act).
