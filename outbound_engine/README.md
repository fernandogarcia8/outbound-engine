# Boatsetter Outbound Engine

Sends personalized email and SMS to boat owners via Kustomer. Replaces the n8n workflow. Primary interface is a Streamlit web app; CLI available as an alternative.

**Live app:** https://supply-outbound-engine.streamlit.app

---

## First-time local setup (do this once)

```bash
cd outbound_engine
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then create `.env` in this folder with:

```
KUSTOMER_API_KEY_READ=...
KUSTOMER_API_KEY_WRITE=...
GOOGLE_SHEETS_CREDENTIALS_JSON=credentials.json
MARKETS_DRIVE_FOLDER_ID=1jje4PAk8chx9pSbkjldhWsAqFQiCA4cf
KUSTOMER_EMAIL_FROM_ADDRESS=supplyteam@boatsetter.com
KUSTOMER_EMAIL_FROM_NAME=Boatsetter Supply Team
KUSTOMER_SMS_FROM=+18554310490
```

Place `credentials.json` (Google service account) in this same folder.

---

## Running the web app

```bash
cd "/Users/fernandogarcia/Desktop/Claude/Outbound Engine"
source outbound_engine/venv/bin/activate
streamlit run app.py
# Opens at http://localhost:8501
```

---

## Outreach phases

| Phase | What it does |
|---|---|
| **Phase 1 — Cross-List** | BS - Live → Getmyboat pitch (email + SMS) · GMB - Live → Boatsetter pitch (SMS only) |
| **Phase 2 — BS - Not Live** | Reactivate (< 90 days inactive) + Get Live |
| **Phase 3 — Prospect** | Cold outreach via Casey alias |

Always run **Prep** before outreach on any new data export.

---

## Prep steps (run in order)

1. **Split** — moves BS - Not Live churn rows to BS - Churn tab
2. **Classify** — assigns Tier, Action, Contact Status to BS - Not Live rows
3. **Cross-list detection** — tags BS - Live and GMB - Live rows; adds outreach columns and colored dropdowns to both tabs

---

## What gets written to the sheet during outreach

| Column | Written when |
|---|---|
| `Contact Status` | Updated to `Contacted` after send |
| `Kustomer ID` | Filled in at send time via Kustomer lookup |
| `Email 1` / `SMS 1` | Timestamp of first touch |
| `Email 2` / `SMS 2` | Timestamp of second touch (2-day gap) |
| `Email 3` / `SMS 3` | Timestamp of third touch |
| `KUSTOMER_CONVERSATION_ID` | Link to the conversation in Kustomer |

---

## Test mode

Toggle "Test contacts only" in the sidebar to run outreach only on rows where `Notes = "test"`. Bypasses eligibility and timing checks — safe to reuse test rows without resetting.

**Seeding test rows:** With test mode on, go to the Outreach tab and click **Seed test rows**. Adds Tyler and Fernando to all sheet tabs automatically. Idempotent — skips tabs where they already exist.

---

## Adding a new market

1. Create a Google Sheet named `<Location> - Outbound` (e.g. "Tampa Bay - Outbound")
2. Add tabs: `BS - Live` | `GMB - Live` | `BS - Not Live` | `BS - Churn` | `Prospects`
3. Share with `outbound-engine@n8n-sheets-456321.iam.gserviceaccount.com` (Editor)
4. Place the sheet (or a shortcut) in the Outbound Engine Drive folder
5. It appears in the app dropdown within 5 minutes

The `- Outbound` suffix is automatically stripped when injecting the market name into message copy.

---

## Team members (config.py)

```python
TEAM_MEMBERS = [
    {"name": "Tyler",    "kustomer_id": "68233767cc5a45b13d77bef8", "email": "tbrick@boatsetter.com",   "phone": "+16128503633"},
    {"name": "Fernando", "kustomer_id": "63e13a6d7e5d1d84e78cacaa", "email": "fernando@boatsetter.com", "phone": "+528116892533"},
]
```

Round-robin assignment cycles Tyler → Fernando → Tyler → ... and persists in `round_robin_state.json` between runs.

Email and phone are used only for seeding test rows — not for outreach assignment.

To add a new team member, add an entry with their `name`, `kustomer_id`, `email`, and `phone`.

---

## Message templates (templates.py)

All copy lives in `templates.py`. Each segment has its own builder function. Variables available in all templates:
- `{greeting}` — "Hi John," or "Hi there," (auto-filled from name)
- `{market}` — the market name (auto-filled)
- `{noun}` — "your boat" / "your boats" / "your fleet" (auto-filled from dedup count)

No em dashes in any copy — they signal AI-generated content.

---

## BS - Not Live churn states

Rows with these `BOAT_LISTING_STATE` values are moved to BS - Churn during Split:
`blocked` · `boatbound_denied` · `deactivated` · `deleted` · `incomplete` · `insurance_denied` · `pending_insurance` · `pending_survey`

---

## Run logs

Every outreach run creates a timestamped log in `logs/`:
```
logs/run_2026-05-08_14-23-00.log
```
