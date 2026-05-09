# Boatsetter Outbound Engine

A Python + Streamlit outreach engine for Boatsetter's supply team. Reads boat owner data from Google Sheets (sourced from Snowflake), segments it, sends personalized email and SMS via the Kustomer API, and writes results back to the sheet. Replaces a fragile n8n workflow.

**Live app:** https://supply-outbound-engine.streamlit.app
**GitHub:** https://github.com/fernandogarcia8/outbound-engine (private)

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Architecture Overview](#architecture-overview)
3. [How to Run](#how-to-run)
4. [Markets & Auto-Discovery](#markets--auto-discovery)
5. [Outreach Phases & Touch Sequence](#outreach-phases--touch-sequence)
6. [Prep Pipeline](#prep-pipeline)
7. [Segmentation Logic](#segmentation-logic)
8. [Message Templates](#message-templates)
9. [Kustomer Integration](#kustomer-integration)
10. [Google Sheets Integration](#google-sheets-integration)
11. [Test Mode](#test-mode)
12. [Cross-List Detection](#cross-list-detection)
13. [BS - Not Live Classification](#bs---not-live-classification)
14. [Configuration](#configuration)
15. [Active Markets](#active-markets)
16. [What's Working / Pending](#whats-working--pending)

---

## Project Structure

```
/
├── app.py                        ← Streamlit web app (primary interface)
├── controller.py                 ← CLI entry point (alternative to web app)
├── markets.py                    ← Auto-discovers markets from Google Drive
├── requirements.txt
├── .streamlit/
│   └── config.toml               ← App theme
└── outbound_engine/
    ├── engine.py                 ← Core orchestrator — runs outreach campaigns
    ├── templates.py              ← All message copy (email + SMS per segment/touch)
    ├── segmentation.py           ← Eligibility logic — determines touch # per row
    ├── kustomer_client.py        ← Kustomer API wrapper (lookup, create, send)
    ├── sheets_connector.py       ← Google Sheets read/write wrapper
    ├── cross_list.py             ← 6-layer cross-list detection (runs during Prep)
    ├── split_not_live.py         ← Splits BS-Not-Live into actionable vs churn
    ├── classify_not_live.py      ← Assigns Tier + Action + Contact Status
    ├── seed_test_rows.py         ← Seeds Tyler + Fernando as test rows in all tabs
    ├── market_discovery.py       ← Scans Drive folder, resolves shortcuts
    ├── round_robin.py            ← Tyler ↔ Fernando assignment, persisted to JSON
    ├── logger.py                 ← File logger + RunSummary
    ├── config.py                 ← All constants, column names, team members
    ├── .env                      ← API keys (local only, never committed)
    └── credentials.json          ← GCP service account (local only, never committed)
```

---

## Architecture Overview

```
Snowflake export
      ↓
Google Sheets (one sheet per market, multiple tabs)
      ↓
Prep pipeline (split → classify → detect cross-list)
      ↓
engine.py  ←  segmentation.py (filter eligible rows + assign touch #)
      ↓             ↓
templates.py    round_robin.py (assign rep)
      ↓
Kustomer API (create customer → create conversation → send email/SMS)
      ↓
Google Sheets (write timestamps, Kustomer ID, conversation link)
```

**Streamlit app (`app.py`)** wraps the entire pipeline in a web UI. The app runs on Streamlit Cloud and reads secrets from the Streamlit secrets manager (locally it falls back to `.env`).

---

## How to Run

### Local development

```bash
cd "/Users/fernandogarcia/Desktop/Claude/Outbound Engine"
source outbound_engine/venv/bin/activate
streamlit run app.py
# Opens at http://localhost:8501
```

### Deployed app

Lives at https://supply-outbound-engine.streamlit.app. Deploys automatically from the `main` branch of the GitHub repo. Secrets (API keys + GCP service account) are stored in Streamlit Cloud's secrets manager — never in code.

### CLI (alternative to web app)

```bash
python controller.py prep     --market savannah [--dry-run]
python controller.py outreach --market savannah --phase 1 [--dry-run] [--yes] [--test]
python controller.py outreach --market savannah --phase 2 [--dry-run] [--yes] [--test]
python controller.py outreach --market savannah --phase 3 [--dry-run] [--yes] [--test]
```

`--market` accepts partial names (`savannah` matches "Savannah - Outbound").

---

## Markets & Auto-Discovery

Markets are discovered automatically from a Google Drive folder at app startup (cached 5 min).

**Drive folder:** `https://drive.google.com/drive/u/0/folders/1jje4PAk8chx9pSbkjldhWsAqFQiCA4cf`

### Adding a new market

1. Create a Google Sheet named `<Location> - Outbound` (e.g. "Tampa Bay - Outbound")
2. Add tabs: `BS - Live` | `GMB - Live` | `BS - Not Live` | `BS - Churn` | `Prospects`
3. Share with `outbound-engine@n8n-sheets-456321.iam.gserviceaccount.com` (Editor)
4. Place the sheet (or a shortcut) in the Drive folder above
5. It appears in the app dropdown within 5 minutes

### Naming convention

Whatever comes before `- Outbound` is used verbatim as the market name in message copy.

| Sheet name | Copy says |
|---|---|
| `Savannah - Outbound` | Savannah |
| `Tampa Bay - Outbound` | Tampa Bay |
| `Houston and nearby - Outbound` | Houston and nearby |

---

## Outreach Phases & Touch Sequence

### Three phases, run in order

| Phase | Segment(s) | Source tab(s) | Channel |
|---|---|---|---|
| **Phase 1 — Cross-List** | `cross_list` | BS - Live → Getmyboat pitch | Email + SMS |
| | | GMB - Live → Boatsetter pitch | SMS only |
| **Phase 2 — Reactivate + Get Live** | `reactivate`, `get_live` | BS - Not Live | Email + SMS |
| **Phase 3 — Prospect** | `prospect` | Prospects | Email + SMS |

### Three-touch sequence per contact

Each phase runs a 3-touch sequence. The engine determines which touch each contact is ready for based on timestamps in the sheet.

| Touch | Label | Condition |
|---|---|---|
| Touch 1 | Initial | `Contact Status = Pending Outreach`, no prior sends |
| Touch 2 | Follow-up 1 | `Contact Status = Contacted`, Touch 1 sent ≥ 2 days ago, no reply |
| Touch 3 | Follow-up 2 | `Contact Status = Contacted`, Touch 2 sent ≥ 2 days ago, no reply |

In the web app, each phase shows three rows (Initial / Follow-up 1 / Follow-up 2) with separate Dry Run and Send buttons. All call the same `run_campaign()` — the engine automatically selects the right touch per contact.

A contact is skipped entirely if `Replied? = true`.

---

## Prep Pipeline

Prep must be run once per new Snowflake data export, before any outreach. The web app Prep tab runs these three steps in sequence:

### Step 1 — Split (`split_not_live.py`)

Scans `BS - Not Live` and moves rows with churn-state `BOAT_LISTING_STATE` values to `BS - Churn`.

Churn states: `blocked`, `boatbound_denied`, `deactivated`, `deleted`, `incomplete`, `insurance_denied`, `pending_insurance`, `pending_survey`

### Step 2 — Classify (`classify_not_live.py`)

Assigns `Tier`, `Action to take`, and `Contact Status` to remaining rows in `BS - Not Live`.

| Tier | BOAT_LISTING_STATE | Condition | Action |
|---|---|---|---|
| Tier 1 | `approved` | No LAST_LIVE date | Get Live |
| Tier 1 | `approved` | Has LAST_LIVE date | Reactivate |
| Tier 2 | `pending_review`, `survey_received` | Created ≥ 2023-01-01 | Get Live |
| Tier 3 | `pending_review`, `survey_received` | Created < 2023-01-01 | Get Live |
| Rehab | `corrections_needed` | — | Check (no outreach) |

### Step 3 — Cross-List Detection (`cross_list.py`)

Runs 6-layer detection across `BS - Live` and `GMB - Live`. Adds outreach tracking columns and color-coded dropdowns to both tabs.

See [Cross-List Detection](#cross-list-detection) for full detail.

---

## Segmentation Logic

`segmentation.py` — `filter_eligible_rows()` returns `(row, touch_number)` pairs.

A row is eligible if:
- Has email or phone
- `Replied?` ≠ `true`
- `Action to take` matches the segment's expected value (from `SEGMENT_ACTIONS` in config)
- Touch timing rules are met (see three-touch table above)

**Deduplication:** Multiple rows for the same owner (matched by email, fallback phone) are collapsed into one. The `_boat_count` field is set so templates can use "your boat" / "your boats" / "your fleet".

---

## Message Templates

All copy lives in `templates.py`. `get_messages()` is the single entry point — returns `{sms_body, email_body, email_subject}`.

### Signing

| Segment | Signed as |
|---|---|
| `reactivate`, `get_live`, `cross_list` | Real rep name (round-robin assignee) |
| `prospect` | "Casey" alias |

### Variants

**Reactivate:** `recent` (< 90 days inactive) or `old` (≥ 90 days / no date)

**Cross-list:** `bs` (sheet starts with "BS" → rep from Boatsetter, pitching Getmyboat) or `gmb` (sheet starts with "GMB" → rep from Getmyboat, pitching Boatsetter)

**Prospect:** auto-detected from `Type` column
| Variant | Trigger |
|---|---|
| `fishing` | Type contains "fishing" |
| `rental` | Type contains "rental" or "sailboat" |
| `charter` | Everything else (tours, eco, sunset, watersports, yacht) |

Business name from `Charter Name` column is injected into prospect templates.

### SMS formatting

All SMS bodies follow this structure (blank lines between each section):
```
Hi [Name],

[Rep] from [Platform] here.

[Pitch body]

[CTA question]

- [Rep]
```

### Copy rules

- No em dashes anywhere — they signal AI-generated content
- Market name auto-injected from sheet name (strips `- Outbound` suffix)
- Greeting auto-built from `OWNER_FIRST_NAME` column; falls back to "Hi there,"

---

## Kustomer Integration

**Two API keys** (both required):
- `KUSTOMER_API_KEY_READ` — lookups only
- `KUSTOMER_API_KEY_WRITE` — create customers, conversations, send messages

### Send flow per contact

1. **Resolve Kustomer ID** — check sheet → lookup by email → lookup by phone → create new customer
2. **Create conversation** — assigned to rep + supply team (`assignedTeams: ["69b1d655010fbbf86a5557d6"]`)
3. **Send email** — `POST /v1/customers/{id}/drafts` with `channel: "email"` (if email available and not SMS-only mode)
4. **Send SMS** — same endpoint with `channel: "sms"` (if phone available)
5. **Write back to sheet** — timestamps, Kustomer ID, conversation link

Email and SMS are sent in independent try/except blocks so one failure doesn't block the other.

**Email from:** `{"email": "supplyteam@boatsetter.com", "name": "Boatsetter Supply Team"}`
**SMS from:** `+18554310490` (configurable via `KUSTOMER_SMS_FROM` env var)
**Phone normalization:** `send_sms()` auto-prepends `+` if missing (E.164 format)

### Conversation tags

Auto-generated per run: `outbound_engine` + `supply_acq_<market_snake_case>`

---

## Google Sheets Integration

`sheets_connector.py` wraps gspread with a service account.

**Important:** Phone numbers from `get_all_records()` come back as integers — always `str()` cast before use. `append_row()` uses `value_input_option="RAW"` to prevent Sheets from interpreting `+` prefixes as formula operators.

### Columns written during outreach

| Column | Written when |
|---|---|
| `Kustomer ID` | First send (if not already in sheet) |
| `Contact Status` | Set to `Contacted` on Touch 1 |
| `Email 1` / `SMS 1` | Timestamp of Touch 1 send |
| `Email 2` / `SMS 2` | Timestamp of Touch 2 send |
| `Email 3` / `SMS 3` | Timestamp of Touch 3 send |
| `KUSTOMER_CONVERSATION_ID` | Link to conversation in Kustomer |

Row matching: by `OWNER_EMAIL` first, fallback to `OWNER_PHONE_NUMBER`.
Timestamp format written to sheet: `YYYY-MM-DD`.

---

## Test Mode

Toggle "Test contacts only" in the sidebar. In test mode:
- Only rows where `Notes = "test"` are processed
- Eligibility and touch-timing checks are **bypassed** — test contacts always get Touch 1
- Lets you rerun test outreach without resetting the sheet

### Seeding test rows

With test mode on, go to the Outreach tab → Test Setup → click **Seed test rows**. Adds Tyler and Fernando to all sheet tabs automatically. Idempotent — skips any tab where they already exist.

| Tab | Tyler's row | Fernando's row |
|---|---|---|
| BS - Live | Cross-List · Pending Outreach | Cross-List · Pending Outreach |
| GMB - Live | Cross-List · Pending Outreach | Cross-List · Pending Outreach |
| BS - Not Live | Reactivate · Pending Outreach | Get Live · Pending Outreach |
| Prospects | Prospect | Prospect |

Kustomer ID is left blank when seeded — the engine fills it at send time via `get_or_create_customer()`.

### Confirmation gate

Live sends (non-dry-run) require a second "Confirm — Send" click after the initial send button. Dry runs skip this.

---

## Cross-List Detection

`cross_list.py` — runs during Prep Step 3. Scans `BS - Live` and `GMB - Live` against all other tabs.

| Layer | Match type | Result written |
|---|---|---|
| L1 | Email vs BS - Live | `Dual Presence` |
| L2 | Phone vs BS - Live | `Dual Presence` |
| L3 | Email/phone vs BS - Churn | `Already on BS Funnel` + state + admin URL |
| L4 | Email/phone vs BS - Not Live | `Already on BS Funnel` + state |
| L5 | Kustomer lookup | `Possible Dual Presence` or `Cross-List` |
| L6 | Name match vs BS - Churn / BS - Not Live | `Already on BS Funnel` (name match, verify before outreach) |

### Dropdowns added to BS - Live and GMB - Live during Prep

**Action to take:** Cross-List (blue) · Skip (gray) · Manual Check (peach)

**Contact Status (BS - Live):** Pending Outreach · Contacted · Interested · Cross-List WIP · Not Interested · Win · Dual Presence (gray) · Possible Dual Presence (orange)

**Contact Status (GMB - Live):** same as BS - Live + Already on BS Funnel (salmon)

---

## BS - Not Live Classification

Handled by `classify_not_live.py` during Prep Step 2.

| Tier | BOAT_LISTING_STATE | Condition | Action assigned |
|---|---|---|---|
| Tier 1 | `approved` | `LAST_LIVE` empty | Get Live |
| Tier 1 | `approved` | `LAST_LIVE` not empty | Reactivate |
| Tier 2 | `pending_review`, `survey_received` | Created ≥ 2023-01-01 | Get Live |
| Tier 3 | `pending_review`, `survey_received` | Created < 2023-01-01 | Get Live |
| Rehab | `corrections_needed` | — | Check (no outreach sent) |

The `Reactivate` action uses a `recent` message variant when `BOAT_LISTING_LAST_LIVE_ON_SITE_AT` is within 90 days.

---

## Configuration

`config.py` — central config file. Key settings:

```python
TOUCH_GAP_DAYS = 2             # days between outreach touches
REACTIVATE_RECENT_DAYS = 90    # days threshold for "recent" reactivate variant

TEAM_MEMBERS = [
    {"name": "Tyler",    "kustomer_id": "...", "email": "tbrick@boatsetter.com",   "phone": "+16128503633"},
    {"name": "Fernando", "kustomer_id": "...", "email": "fernando@boatsetter.com", "phone": "+528116892533"},
]
```

**To add a team member:** append to `TEAM_MEMBERS` with their `name`, `kustomer_id`, `email`, and `phone`.

**Prospect sheet column overrides** — prospect sheets use different column names than Snowflake-sourced sheets. Mapped in `SEGMENT_COLUMN_OVERRIDES`:
- `Email` → `OWNER_EMAIL`
- `Phone Number` → `OWNER_PHONE_NUMBER`
- `Owner Name` → `OWNER_FIRST_NAME` (engine splits on first space to get last name)

### Environment variables (`.env` / Streamlit secrets)

| Variable | Purpose |
|---|---|
| `KUSTOMER_API_KEY_READ` | Read-only Kustomer key (lookups) |
| `KUSTOMER_API_KEY_WRITE` | Write Kustomer key (send messages) |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Path to GCP service account JSON |
| `MARKETS_DRIVE_FOLDER_ID` | Google Drive folder ID for market discovery |
| `KUSTOMER_EMAIL_FROM_ADDRESS` | Outbound email address |
| `KUSTOMER_EMAIL_FROM_NAME` | Outbound email display name |
| `KUSTOMER_SMS_FROM` | Outbound SMS number (E.164) |

---

## Active Markets

| Market | Sheet name | Status |
|---|---|---|
| **Savannah** | `Savannah - Outbound` | All test runs done. Live outreach not yet fired. 11 cross-list targets, 35 BS-Not-Live, 34 prospects. |
| **Houston** | `Houston and nearby - Outbound` | Prep done. Outreach not fired. |
| **Orlando** | `Orlando Prospecting` | In Drive folder. Empty/fresh — no prep or outreach yet. |

---

## What's Working / Pending

### Working

- Google Sheets connection + market auto-discovery from Drive (handles shortcuts)
- Streamlit web app — live at https://supply-outbound-engine.streamlit.app
- CLI controller (`prep`, `outreach`, `scrape` commands)
- Cross-list detection (6 layers including name matching)
- Prep pipeline (split → classify → detect) with colored dropdowns
- Engine: all segments, 3-touch sequence, 2-day gap enforcement
- Test mode with seed button (idempotent)
- Round-robin rep assignment, persisted in `round_robin_state.json`
- Confirmation gate before live sends
- Independent email/SMS error handling
- Deduplication by owner, boat noun scaling (boat/boats/fleet)
- Prospect templates — fishing / rental / charter variants

### Pending / Not Yet Built

1. **Fire live Savannah outreach** — all validation done, ready
2. **Funnel detection for Prospects tab** — cross-reference scraped operators against existing BS/GMB sheets before outreach (discussed, not built)
3. **BS - Churn outreach** — no process yet; opportunity in `pending_insurance`, `deactivated`, `deleted`
4. **Orlando** — needs raw Snowflake data + prep before outreach
