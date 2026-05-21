# Outbound Engine — Handoff Context

## Project location
```
/Users/fernandogarcia/Desktop/Claude/Outbound Engine/
├── controller.py           ← CLI entry point (alternative to web app)
├── app.py                  ← Streamlit web app (primary interface)
├── markets.py              ← Dynamic market discovery (reads from Google Drive)
├── requirements.txt        ← Python dependencies (used by Streamlit Cloud)
├── .streamlit/config.toml  ← App theme (light blue)
└── outbound_engine/
    ├── engine.py           ← Core orchestrator + send_from_drafts()
    ├── cross_list.py
    ├── split_not_live.py
    ├── classify_not_live.py
    ├── prep_prospects.py   ← Prospects tab prep: columns, dropdowns + funnel detection
    ├── draft_prospects.py  ← Generates Draft Subject/Email/SMS columns before Phase 3 send
    ├── seed_test_rows.py   ← Seeds team members as test rows (per-person selection)
    ├── template_store.py   ← Loads/saves per-market template overrides from _templates tab
    ├── market_discovery.py ← Drive folder scanner (handles shortcuts)
    ├── templates.py        ← All message copy — prospect templates redesigned this session
    ├── segmentation.py
    ├── kustomer_client.py
    ├── sheets_connector.py
    ├── metrics.py          ← Aggregates outreach metrics across all markets/tabs
    ├── round_robin.py
    ├── logger.py
    ├── config.py
    ├── .env                ← API keys + MARKETS_DRIVE_FOLDER_ID (local only)
    └── credentials.json    ← Google service account (local only)
```

## What this is
A Python outreach engine for Boatsetter's supply team. Reads Google Sheets, sends email + SMS via Kustomer API, writes results back. Has a Streamlit web app (primary) and a CLI controller. Markets auto-discovered from a Google Drive folder.

---

## Web app

**Live at:** https://supply-outbound-engine.streamlit.app

GitHub repo: https://github.com/fernandogarcia8/outbound-engine (private)

Secrets (API keys + GCP service account JSON) are stored in the Streamlit Cloud secrets manager — never committed to git. To update a secret, go to the app settings on share.streamlit.io.

Local dev still works unchanged — `streamlit run app.py` reads from `outbound_engine/.env`.

---

## How to run locally

### Start the web app
```bash
cd "/Users/fernandogarcia/Desktop/Claude/Outbound Engine"
source outbound_engine/venv/bin/activate
streamlit run app.py
# Opens at http://localhost:8501
```

### CLI controller (alternative to web app)
```bash
cd "/Users/fernandogarcia/Desktop/Claude/Outbound Engine"
source outbound_engine/venv/bin/activate

python controller.py prep     --market savannah [--dry-run]
python controller.py outreach --market savannah --phase 1 [--dry-run] [--yes] [--test]
python controller.py outreach --market savannah --phase 2 [--dry-run] [--yes] [--test]
python controller.py outreach --market savannah --phase 3 [--dry-run] [--yes] [--test]
python controller.py scrape   --market savannah   # prints prospecting skill instructions
```

`--market` accepts partial names (e.g. `savannah` matches "Savannah - Outbound").

---

## Outreach phases (in order)

| Phase | What it does | Segments |
|---|---|---|
| **Phase 1 — Cross-List** | BS - Live → Getmyboat pitch (email + SMS) · GMB - Live → Boatsetter pitch (SMS only) | `cross_list` |
| **Phase 2 — BS - Not Live** | Reactivate (< 90 days inactive) + Get Live | `reactivate`, `get_live` |
| **Phase 3 — Prospect** | Cold outreach via Casey alias | `prospect` |

---

## Prep (two separate sections in the Prep tab)

### Funnel Prep (run once per new Snowflake export, before Phases 1 + 2)
Runs three steps in sequence:
1. `split_not_live` — splits BS - Not Live into actionable vs BS - Churn by BOAT_LISTING_STATE
2. `classify_not_live` — assigns Tier + Action + Contact Status + outreach columns to actionable rows
3. `detect_cross_list` — 6-layer detection, tags BS - Live and GMB - Live, adds outreach columns + colored dropdowns to both tabs

### Prospects Prep (run before Phase 3, safe to run after Phases 1 + 2)
`prep_prospects.py` — only touches the Prospects tab. Two steps in one click:
1. **Column setup** — ensures tracking columns exist, sets `Action to take = "Prospect"` and `Contact Status = "Pending Outreach"` for new rows, applies dropdowns
2. **Funnel detection** — cross-checks every prospect against all funnel tabs + Kustomer API, writes a `Funnel Status` tag per row

Detection layers (first match wins):

| Layer | Checks | Result |
|---|---|---|
| L1+2 | BS - Live email + phone | `BS Active` |
| L3+4 | GMB - Live email + phone | `GMB Active` |
| L5+6 | BS - Not Live email + phone | `BS Funnel` + listing state in Notes |
| L7+8 | BS - Churn email + phone | `BS Funnel` + listing state in Notes |
| L9 | Kustomer API lookup | `In Kustomer` |
| — | No match anywhere | `Net New` |

**Funnel Status dropdown:** Net New (green) · BS Active (blue) · GMB Active (purple) · BS Funnel (yellow) · In Kustomer (peach)

Matched rows → `Action to take` flipped to `Manual Check` (engine skips them). Net New rows → Action stays `Prospect`.
Rows already set to `Skip` by the user are never overwritten.

**Re-run behavior:** currently re-runs detection on all rows and overwrites `Funnel Status`, `Notes`, and `Action to take` for matched rows. If you manually promoted a matched row back to `Prospect` after review, re-running would flip it back to `Manual Check`. A future improvement would skip rows that already have a `Funnel Status`.

---

## Multi-touch sequence

Each phase supports three touches (Initial → Follow-up 1 → Follow-up 2). The web app shows three buttons per phase; each button runs the full engine and the engine decides which touch each contact gets based on their current state:

| Touch | Condition |
|---|---|
| Touch 1 | Contact Status = "Pending Outreach", no prior sends |
| Touch 2 | Status = "Contacted", Email 1 or SMS 1 has a timestamp, no T2 sent yet, no reply |
| Touch 3 | Status = "Contacted", Email 2 or SMS 2 has a timestamp, no T3 sent yet, no reply |

**No minimum time gap between touches.** You control timing by deciding when to click Follow-up 1 / Follow-up 2. Run them whenever you're ready — the next day or a week later.

Timestamps are written back to the sheet in `Email 1` / `SMS 1` / `Email 2` / `SMS 2` / `Email 3` / `SMS 3` columns.

---

## Market naming convention

The Google Sheet name controls what appears in message copy. Whatever comes before `- Outbound` is used as the market name in templates.

| Sheet name | Copy says |
|---|---|
| `Houston and nearby - Outbound` | Houston and nearby |
| `Tampa Bay - Outbound` | Tampa Bay |
| `Savannah - Outbound` | Savannah |

**Always name sheets:** `<copy-ready location> - Outbound`

---

## Market auto-discovery

Markets are discovered automatically from Google Drive at app startup (cached 5 min).

**To add a new market:**
1. Create a Google Sheet named `<Location> - Outbound` (e.g. "Tampa Bay - Outbound")
2. Add tabs: `BS - Live` | `GMB - Live` | `BS - Not Live` | `BS - Churn` | `Prospects`
3. Share the sheet with `outbound-engine@n8n-sheets-456321.iam.gserviceaccount.com` (Editor)
4. Place it (or a shortcut) in the "Outbound Engine" Drive folder:
   `https://drive.google.com/drive/u/0/folders/1jje4PAk8chx9pSbkjldhWsAqFQiCA4cf`
5. It appears in the web app dropdown automatically (within 5 min)

Note: If you move an existing file into the folder, Drive creates a shortcut. The discovery code handles shortcuts correctly (resolves targetId).

---

## Test mode

All outreach runs support a test mode that filters to rows where `Notes = "test"`.

In test mode, eligibility checks are **bypassed entirely** — test contacts always receive Touch 1 regardless of prior send history. Deduplication still runs — if an owner has multiple test rows, they get one message with the correct noun (boat / boats / fleet).

**Seeding test rows (web app):**
1. Toggle "Test contacts only" on in the sidebar
2. Go to the Outreach tab — a "Test Setup" section appears
3. Click **Seed test rows** — adds Tyler and Fernando to all sheet tabs automatically
   - BS - Not Live: Tyler → Reactivate, Fernando → Get Live (tests both variants)
   - All other tabs: both → Cross-List or Prospect
4. Idempotent — skips tabs where they already exist, reports row number of the existing row

**Kustomer ID in test rows:** Left blank when seeded. The engine looks up and fills it at send time via `get_or_create_customer()`.

```bash
# CLI
python controller.py outreach --market savannah --phase 1 --test
```

**Confirmation gate (web app):** Live sends require a second confirmation click. Dry runs skip this.

---

## Critical technical details

### Kustomer API
- **Send messages:** `POST /v1/customers/{id}/drafts` (email AND SMS use same endpoint)
- **Email from:** `{"email": "supplyteam@boatsetter.com", "name": "Boatsetter Supply Team"}`
- **SMS from:** `+18554310490` (configurable in `.env` as `KUSTOMER_SMS_FROM`)
- **Conversations:** include `assignedTeams: ["69b1d655010fbbf86a5557d6"]`
- **Two API keys:** `KUSTOMER_API_KEY_READ` (lookups) and `KUSTOMER_API_KEY_WRITE` (send)
- **Phone normalization:** `send_sms()` auto-prepends `+` if missing (E.164)

### Google Sheets
- Phone numbers from `get_all_records()` come back as integers — always `str()` cast
- Rows matched on `OWNER_EMAIL` first, fallback `OWNER_PHONE_NUMBER`
- Date written to sheet: `YYYY-MM-DD`
- Prospect sheets use different column names (`Email`, `Phone Number`, `Owner Name`) — normalized automatically via `SEGMENT_COLUMN_OVERRIDES` in `config.py`
- **Rate limiting:** `SheetsConnector` and `template_store` both use `BackOffHTTPClient` (gspread 6.x) which auto-retries on 429s with exponential backoff
- **Fleet owners:** `update_row` updates ALL rows matching the owner's email/phone in a single batch call — Contact Status, timestamps, Kustomer link all stay in sync across every boat row

### Team members (config.py) — Tyler + Fernando only (Casey is prospect alias only)
```python
{"name": "Tyler",    "kustomer_id": "68233767cc5a45b13d77bef8", "email": "tbrick@boatsetter.com",   "phone": "+16128503633"},
{"name": "Fernando", "kustomer_id": "63e13a6d7e5d1d84e78cacaa", "email": "fernando@boatsetter.com", "phone": "+528116892533"},
```
Email and phone are used only for seeding test rows — not for outreach assignment.

---

## Cross-list detection (cross_list.py)

Six-layer matching when running prep on BS - Live / GMB - Live:

| Layer | Match type | Result |
|---|---|---|
| L1 | Email vs BS - Live | `Dual Presence` |
| L2 | Phone vs BS - Live | `Dual Presence` |
| L3 | Email/phone vs BS - Churn | `Already on BS Funnel` + state + admin URL |
| L4 | Email/phone vs BS - Not Live | `Already on BS Funnel` + state |
| L5 | Kustomer lookup | `Possible Dual Presence` or `Cross-List` |
| L6 | Name match vs BS - Churn / BS - Not Live | `Already on BS Funnel` + "(name match, verify before outreach)" note |

Prep also adds outreach tracking columns and colored dropdowns to both Live tabs:

**Action to take:** Cross-List (blue) · Skip (gray) · Manual Check (peach)

**Contact Status (BS - Live):** Pending Outreach · Contacted · Interested · Cross-List WIP · Not Interested · Win · Dual Presence · Possible Dual Presence

**Contact Status (GMB - Live):** same + Already on BS Funnel

---

## Skip option (all tabs)

Every "Action to take" dropdown includes a **Skip** option (gray). Setting a row to Skip excludes it from all outreach — the engine only processes rows whose action exactly matches the segment (Cross-List / Reactivate / Get Live / Prospect).

| Tab | When Skip dropdown appears |
|---|---|
| BS - Live / GMB - Live | After prep (cross_list.py) |
| BS - Not Live | After prep (classify_not_live.py) |
| Prospects | After first live Phase 3 run (engine.py applies it) |

---

## Per-market template overrides (template_store.py + ✏️ Messaging tab)

The web app has a **Messaging** tab (4th tab) that lets you edit copy per market. On save, overrides are written to a `_templates` tab in the market's Google Sheet (auto-created). The engine loads these at campaign start and applies them field by field — unoverridden fields fall back to the hardcoded defaults in `templates.py`.

Supported placeholders: `{greeting}` · `{market}` · `{rep}` · `{boat_noun}` · `{charter_name}` · `{name_ref}` · `{activity_ref}`

**Important:** Saved overrides in `_templates` are independent of code changes. If you update copy in `templates.py`, any market with a saved override for that template will still show the old text — update the override manually in the Messaging tab.

---

## Metrics tab (📊 Metrics)

The 5th tab aggregates outreach performance across all markets. Data is read directly from the sheets, cached 30 min, with a manual Refresh button.

**What it shows:**
- Overall: Emails Sent, SMS Sent, Owners Contacted, Reply Rate
- Touch breakdown table (T1 / T2 / T3 × email / SMS)
- Contact Status distribution
- Per-market table (Emails, SMS, Contacted, Interested, Wins, Replied, Reply Rate)

**How it works:**
- Deduplicates by owner email/phone — fleet owners count once regardless of boat count
- Filters out test rows (`Notes = "test"`)
- Normalizes minor status casing differences
- Counts T1 from `Email 1` / `SMS 1`, T2 from `Email 2` / `SMS 2`, T3 from `Email 3` / `SMS 3`
- Numbers shown are totals across ALL markets combined

**Reply Rate** requires manually toggling `Replied?` to `TRUE` in the sheet when an owner responds in Kustomer. Everything else is automatic.

---

## Templates (templates.py)

### No em dashes anywhere in user-facing copy
All em dashes removed — they signal AI-generated content. Use `--` (double hyphen) instead.

### Brand name: always "Getmyboat" (not "GetMyBoat")

### Prospect variants (auto-detected from `Type` column)
| Variant | Trigger |
|---|---|
| `fishing` | Type contains "fishing" |
| `charter` | Everything else (rental, tours, eco, sunset, watersports, yacht) |

Rental was merged into charter — both get booking-focused copy.

### Prospect signing
Prospects are signed with **real rep names (Tyler or Fernando)** — round-robin, same as funnel segments. The "Casey" alias is gone.

Rep is assigned at `Generate Drafts` time and saved in `Draft Assignee ID`. At send time, that saved ID is used so the body copy and Kustomer assignment always match. For T2/T3 follow-ups, the same rep from T1 is reused.

### Location personalization (`_location()`)
- Prospects: reads `Location` column
- Funnel rows: reads `BOAT_CITY` column
- Strips trailing state abbreviation: "Savannah, GA" → "Savannah"
- Strips marina suffix: "Savannah, GA — Savannah Marina" → "Savannah"
- Falls back to market DMA name if both columns empty
- `_in_loc(name, location)` skips `" in {location}"` if the city is already in the business name (avoids "Tybee Island Watersports in Tybee Island")

### Prospect data helpers
- **`_activities(row)`** — formats `Activities/Events/Services` as "X, Y, and Z" (up to 3). Used in the activity observation line.
- **`_boat_ref(row)`** — extracts a specific boat type noun (catamaran, skiff, pontoon, sailboat, etc.) from `Boat Type`. Returns `""` for generic descriptions like "multi-vessel fleet" or "center console".
- **`_booking_context(row)`** — if `Booking Software` is a known platform (FareHarbor, Bookeo, Rezdy, etc.), returns one sentence positioning Boatsetter as an additive channel.

All three helpers are also exposed as `{activities}`, `{boat_type}` placeholders in the per-market template override system.

### Reactivate variants
- `recent` — LAST_LIVE_ON_SITE_AT < 90 days ago
- `old` — ≥ 90 days or no date

### Cross-list variants
- `bs` — sheet name starts with "BS" → rep from Boatsetter, pitching Getmyboat
- `gmb` — sheet name starts with "GMB" → rep from Getmyboat, pitching Boatsetter

---

## BS - Not Live tier logic (classify_not_live.py)

| Tier | BOAT_LISTING_STATE | Condition | Action |
|---|---|---|---|
| Tier 1 | `approved` | LAST_LIVE empty | Get Live |
| Tier 1 | `approved` | LAST_LIVE not empty | Reactivate |
| Tier 2 | `pending_review`, `survey_received` | CREATED_AT ≥ 2023-01-01 | Get Live |
| Tier 3 | `pending_review`, `survey_received` | CREATED_AT < 2023-01-01 | Get Live |
| Rehab | `corrections_needed` | — | Check (no outreach, manual review) |

BS - Churn states (moved by split_not_live.py): `blocked`, `boatbound_denied`, `deactivated`, `deleted`, `incomplete`, `insurance_denied`, `pending_insurance`, `pending_survey`

---

## Phase 3 — Prospect outreach flow

Phase 3 has 4 steps in the web app:

```
Step 1 — Generate Drafts  →  Step 2 — Send Initial  →  Step 3 — Follow-up 1  →  Step 4 — Follow-up 2
```

### Step 1 — Generate Drafts (`draft_prospects.py`)
Only generates T1 (initial outreach) drafts. Writes four columns to the Prospects tab:

| Column | Contents |
|---|---|
| `Draft Subject` | Email subject line |
| `Draft Email` | Full email body |
| `Draft SMS` | Full SMS body |
| `Draft Assignee ID` | Kustomer ID of assigned rep (used at send time) |

Nothing is sent. Drafts stay in the sheet permanently as a send record.

### Step 2 — Send Initial (`engine.send_from_drafts()`)
Sends exactly what is in the draft columns. Writes timestamps to `Email 1` / `SMS 1`. Rep assignment is read from `Draft Assignee ID` so the email/SMS body and the Kustomer assignment always match. The Kustomer conversation title is set to the `Draft Subject` value.

### Step 3 — Follow-up 1 (`engine.run_campaign(min_touch=2, max_touch=2)`)
Sends T2 directly from templates — no draft review. Replies on the same Kustomer conversation as T1. Email subject falls back to `Draft Subject` column (same as T1). Same rep as T1 is reused.

### Step 4 — Follow-up 2 (`engine.run_campaign(min_touch=3, max_touch=3)`)
Sends T3 directly from templates. Same threading and rep behaviour as Follow-up 1.

---

## What's working

- Google Sheets connection ✅
- Market auto-discovery from Drive folder ✅ (handles shortcuts, strips display name suffixes)
- `controller.py` CLI (prep + outreach phases 1/2/3 + scrape instructions) ✅
- `app.py` Streamlit web app ✅ — live at https://supply-outbound-engine.streamlit.app
- `cross_list.py` 6-layer detection including name matching ✅
- Cross-list prep adds outreach columns + colored dropdowns to BS-Live and GMB-Live ✅
- `split_not_live.py` ✅
- `classify_not_live.py` ✅
- `engine.py` all segments ✅
- **Fleet owner deduplication** ✅ — one message per owner with correct noun (boat/boats/fleet); all matching rows updated in one batch call
- **Rate limiting handled** ✅ — BackOffHTTPClient auto-retries on 429s; no more mid-run crashes
- **Skip option on all tabs** ✅ — set Action to "Skip" to exclude any owner from outreach
- **Per-market message template overrides** ✅ — Messaging tab, stored in `_templates` Sheet tab
- **Metrics tab** ✅ — 5th tab, aggregates sends/replies/status across all markets, 30-min cache
- **Multi-touch sequence** ✅ — no minimum time gap; T2/T3 eligible as soon as prior touch is sent
- Test mode (Notes="test", uses real eligibility logic on test rows — T2/T3 test runs work correctly) ✅
- Seed test rows with per-person selection ✅ — shows row number when contact already exists
- Confirmation gate before live sends ✅
- Deduplication by owner, boat noun (boat/boats/fleet) ✅
- Round-robin (Tyler + Fernando), persisted in `round_robin_state.json` ✅
- Independent email/SMS error handling ✅
- **Prospects Prep** ✅ — dedicated prep for Prospects tab only (safe post-Phase 1+2): column setup + funnel detection, `Funnel Status` column, Manual Check for matched rows
- **Prospect draft flow** ✅ — 4-step: Generate Drafts → Send Initial → Follow-up 1 → Follow-up 2; T1 via draft review, T2/T3 via templates; each step targets exactly one touch
- **Funnel phases (1+2) step flow** ✅ — separate Initial / Follow-up 1 / Follow-up 2 buttons; each targets exactly one touch (min_touch=max_touch)
- **Follow-up conversation threading** ✅ — T2/T3 reply on the same Kustomer thread as T1 (confirmed working); email subject reused from `Draft Subject` column for prospects
- **Prospect templates** ✅ — real rep names (Tyler/Fernando), fishing/charter variants, city-level location, activities/boat type/booking software personalization
- **Rep consistency across touches** ✅ — same rep used for T1/T2/T3; saved in `Draft Assignee ID` (prospects) and `Assigned Rep ID` (funnel)
- **Location personalization** ✅ — city-level for all segments; strips state suffix + marina suffix; avoids city repetition in business names
- **Cross-list email subjects** ✅ — BS variant: "Get more bookings by listing on Getmyboat too"; GMB variant: "Get more bookings by listing on Boatsetter too"; consistent across all touches

---

## Known gaps / not yet built

- **Prospect scraping automation** — currently manual via `/boat-charter-prospector` skill in Claude Code
- **Prospects Prep re-run idempotency** — re-running overwrites `Funnel Status`/`Notes`/`Action` for matched rows even if manually reviewed; future fix: skip rows that already have a `Funnel Status`
- **BS - Churn outreach** — no process yet; opportunity in `pending_insurance`, `deactivated`, `deleted`
