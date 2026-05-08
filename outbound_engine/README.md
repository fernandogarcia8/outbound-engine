# Boatsetter Outbound Engine

Sends personalized email and SMS to boat owners via Kustomer. Replaces the n8n workflow with a faster, more flexible Python tool.

---

## First-time setup (do this once)

### 1. Install Python dependencies

Open Terminal, navigate to this folder, then run:

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set up your .env file

Copy the example file:
```bash
cp .env.example .env
```

Then open `.env` and fill in the values:

- **KUSTOMER_API_KEY_READ** — your read-only Kustomer API key (for customer lookups)
- **KUSTOMER_API_KEY_WRITE** — your write Kustomer API key (for sending messages)
- **GOOGLE_SHEETS_CREDENTIALS_JSON** — path to your Google service account JSON file (see below)
- **KUSTOMER_SMS_FROM** — which SMS number to use (`+18554310490` or `+18559083869`)

### 3. Google Sheets credentials

This tool uses a **service account** to access Google Sheets. A service account is a special Google account for automated tools — not your personal Google login.

**Check if you already have one:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Select your project → "IAM & Admin" → "Service Accounts"
3. If you see one there, click it, go to "Keys" tab, and create a new JSON key
4. Download the JSON file and put it somewhere safe (e.g. `~/boatsetter-credentials.json`)
5. Set `GOOGLE_SHEETS_CREDENTIALS_JSON=~/boatsetter-credentials.json` in your `.env`

**If you don't have one yet:**
1. In Google Cloud Console → "IAM & Admin" → "Service Accounts" → "Create Service Account"
2. Give it a name like "outbound-engine"
3. After creating, go to "Keys" → "Add Key" → "JSON" → download
4. Enable the Google Sheets API: "APIs & Services" → "Enable APIs" → search "Google Sheets API" → Enable
5. Also enable the Google Drive API the same way

**Important:** For each Google Sheet you want to use, open the sheet, click "Share", and add the service account's email address (looks like `outbound-engine@your-project.iam.gserviceaccount.com`) as an **Editor**.

---

## Running a campaign

### Basic usage

```bash
python engine.py \
  --segment reactivate \
  --market "Panama City" \
  --sheet-id 1vOYXzqrgcD6p6Qmf9OjZRp08kdj9U5CfdSjYF0DHKAg \
  --sheet-name "BS - Not Live"
```

### Always do a dry run first

Add `--dry-run` to preview everything without sending a single message:

```bash
python engine.py \
  --segment reactivate \
  --market "Panama City" \
  --sheet-id 1vOYXzqrgcD6p6Qmf9OjZRp08kdj9U5CfdSjYF0DHKAg \
  --sheet-name "BS - Not Live" \
  --dry-run
```

The dry run shows you exactly who would be contacted, what message they'd receive, and who they'd be assigned to — without touching Kustomer or the sheet.

### All four segments

```bash
# Reactivate owners whose boats went inactive
python engine.py --segment reactivate --market "Panama City" --sheet-id <id> --sheet-name "BS - Not Live"

# Owners who listed but never went live
python engine.py --segment get_live --market "Panama City" --sheet-id <id> --sheet-name "BS - Not Live"

# Owners who need to relist
python engine.py --segment relist --market "Panama City" --sheet-id <id> --sheet-name "BS - Not Live"

# New prospects with no prior listing
python engine.py --segment prospect --market "Orlando" --sheet-id <id> --sheet-name "GMB - Live"
```

---

## What happens to the Google Sheet during a run

For every owner successfully contacted, the engine automatically updates:

| Column | What gets written |
|---|---|
| `Contact Status` | `Contacted` |
| `Kustomer ID` | Their Kustomer ID (if it wasn't already there) |
| `Email 1` | UTC timestamp of when the email was sent |
| `SMS 1` | UTC timestamp of when the SMS was sent |
| `KUSTOMER_CONVERSATION_ID` | Direct link to the conversation in Kustomer |

---

## Team member assignment (round-robin)

The engine cycles through Tyler → Fernando → Mandy → Tyler → ... and assigns each owner to the next person in line. This counter is saved in `round_robin_state.json` and survives between runs — so if Tyler was last in one run, Fernando goes first next run.

To reset the counter back to Tyler:
```bash
python -c "from round_robin import reset_counter; reset_counter()"
```

---

## Run logs

Every run creates a timestamped log file in the `logs/` folder:
```
logs/run_2026-05-04_14-23-00.log
```

The log records every action, every error, and a summary at the end.

---

## How to add a new segment

1. Open `config.py` — add the segment name to `SEGMENTS` and its expected sheet value to `SEGMENT_ACTIONS`
2. Open `templates.py` — add a new builder function following the same pattern as `_reactivate`, then add it to `_BUILDERS`
3. Optionally add a conversation name to `CONVERSATION_NAMES` in `config.py`

That's it — the rest of the engine picks it up automatically.

---

## How to change message templates

Open `templates.py`. Each segment has its own function (`_reactivate`, `_get_live`, `_prospect`). Edit the text inside those functions.

- `{greeting}` = "Hi John," or "Hi there," — auto-filled
- `{market}` = whatever you pass as `--market` — auto-filled

---

## How to add a new team member

Open `config.py` and add to the `TEAM_MEMBERS` list:

```python
{"name": "NewPerson", "kustomer_id": "their_kustomer_id_here"},
```

The round-robin picks them up automatically on the next run.

---

## Future web app

The core engine logic lives in the `run_campaign()` function inside `engine.py`. The CLI is just a thin wrapper around it. To add a web interface, you'd create one new file (e.g. `app.py` using FastAPI or Flask) that imports `run_campaign` and exposes it via a form — no changes to the existing code needed.
