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
    ├── engine.py
    ├── cross_list.py
    ├── split_not_live.py
    ├── classify_not_live.py
    ├── seed_test_rows.py   ← Seeds team members as test rows (per-person selection)
    ├── template_store.py   ← Loads/saves per-market template overrides from _templates tab
    ├── market_discovery.py ← Drive folder scanner (handles shortcuts)
    ├── templates.py
    ├── segmentation.py
    ├── kustomer_client.py
    ├── sheets_connector.py
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

## Prep (run before outreach, once per new data export)

Prep runs three steps in sequence:
1. `split_not_live` — splits BS - Not Live into actionable vs BS - Churn by BOAT_LISTING_STATE
2. `classify_not_live` — assigns Tier + Action + Contact Status + outreach columns to actionable rows
3. `detect_cross_list` — 6-layer detection, tags BS - Live and GMB - Live, adds outreach columns + colored dropdowns to both tabs

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

In test mode, eligibility and touch-timing checks are **bypassed entirely** — test contacts always receive Touch 1 regardless of prior send history.

**Seeding test rows (web app):**
1. Toggle "Test contacts only" on in the sidebar
2. Go to the Outreach tab — a "Test Setup" section appears
3. Click **Seed test rows** — adds Tyler and Fernando to all sheet tabs automatically
   - BS - Not Live: Tyler → Reactivate, Fernando → Get Live (tests both variants)
   - All other tabs: both → Cross-List or Prospect
4. Idempotent — skips tabs where they already exist

**Kustomer ID in test rows:** Left blank when seeded. The engine looks up and fills it at send time via `get_or_create_customer()`.

```bash
# CLI
python controller.py outreach --market savannah --phase 1 --test
```

**Confirmation gate (web app):** Live sends require a second confirmation click after "Send Phase X". Dry runs skip this.

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

## Per-market template overrides (template_store.py + ✏️ Messaging tab)

The web app has a **Messaging** tab (4th tab) that lets you edit copy per market. On save, overrides are written to a `_templates` tab in the market's Google Sheet (auto-created). The engine loads these at campaign start and applies them field by field — unoverridden fields fall back to the hardcoded defaults in `templates.py`. No behavior change for markets with no overrides.

Supported placeholders: `{greeting}` · `{market}` · `{rep}` · `{boat_noun}` · `{charter_name}` · `{name_ref}` · `{activity_ref}`

---

## Test mode — per-person seeding

In the Test Setup section (Outreach tab, test mode on), a multiselect lets you choose which team members to seed (defaults to all). Action assignments in BS - Not Live (Tyler → Reactivate, Fernando → Get Live) are fixed per person regardless of who is selected.

To test individually without re-seeding: just clear the `Notes = "test"` value from the other person's row in the sheet — the engine skips any row where Notes ≠ "test".

---

## Templates (templates.py)

### No em dashes anywhere in user-facing copy
All em dashes were removed — they signal AI-generated content. Use periods or plain hyphens instead.

### Prospect variants (auto-detected from `Type` column)
| Variant | Trigger |
|---|---|
| `fishing` | Type contains "fishing" |
| `rental` | Type contains "rental" or "sailboat" |
| `charter` | Everything else (tours, eco, sunset, watersports, yacht) |

Business name from `Charter Name` column is injected into prospect templates.

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

## Active markets

### Savannah — "Savannah - Outbound" sheet
Sheet ID: `1TXflgydfFvtd1GuMAfyO5UDopQ5lCD22AMpRusK6vlU`

All test runs complete. **Live outreach has not been fired yet.**

| Tab | Status |
|---|---|
| BS - Live | 11 Cross-List targets ready. Test run ✓ |
| GMB - Live | 0 targets (all Dual Presence / Possible Dual Presence after name-match detection). Test run ✓ |
| BS - Not Live | 24 Reactivate + 11 Get Live ready. Test run ✓ |
| Prospects | 34 operators (28 GA / 6 SC). Dry run ✓ |
| BS - Churn | 202 rows. No outreach process yet. |

### Houston — "Houston and nearby - Outbound" sheet
Prep run complete. Outreach not yet fired.

### Orlando — "Orlando Prospecting" sheet
In Drive folder. Sheet is empty/fresh — no prep run yet.

---

## What's pending / next steps

1. **Fire live outreach for Savannah** — all dry runs validated, ready to go
   - Phase 1: BS - Live (11 owners, email + SMS) — GMB - Live is 0 targets
   - Phase 2: BS - Not Live (24 reactivate + 11 get_live)
   - Phase 3: Prospects (34 operators)

2. **Prospect scraping automation** — currently manual via `/boat-charter-prospector` skill in Claude Code. To automate: call Anthropic API with the skill as system prompt, back `WebSearch` with Tavily/Serper API, back `WebFetch` with Python requests, write results directly to the Prospects tab. Main challenge: long-running (10-30 min) so Streamlit needs background threading. Discussed, not built.

3. **Funnel detection for Prospects tab** — cross-reference scraped operators against BS - Live, GMB - Live, BS - Not Live, BS - Churn before outreach. Discussed, not built yet.

4. **BS - Churn outreach** — no process yet. Opportunity in `pending_insurance`, `deactivated`, `deleted`.

5. **Orlando market** — sheet is in Drive folder, needs raw data + prep before outreach.

---

## What's working

- Google Sheets connection ✅
- Market auto-discovery from Drive folder ✅ (handles shortcuts, strips display name suffixes)
- `controller.py` CLI (prep + outreach phases 1/2/3 + scrape instructions) ✅
- `app.py` Streamlit web app ✅ — live at https://supply-outbound-engine.streamlit.app
- `cross_list.py` 6-layer detection including name matching ✅
- Cross-list prep adds outreach columns + colored dropdowns to BS-Live and GMB-Live ✅
- `split_not_live.py` ✅ (handles `blocked` state → BS-Churn)
- `classify_not_live.py` ✅
- `engine.py` all segments ✅
- **Per-market message template overrides** ✅ — Messaging tab, stored in `_templates` Sheet tab
- Test mode (Notes="test", bypasses eligibility/timing) ✅
- Seed test rows with per-person selection ✅ (Outreach tab, test mode only)
- Confirmation gate before live sends ✅
- Prospect templates — fishing / rental / charter variants, no em dashes ✅
- Deduplication by owner, boat noun (boat/boats/fleet) ✅
- Round-robin (Tyler + Fernando), persisted in `round_robin_state.json` ✅
- Independent email/SMS error handling ✅
- Multi-touch sequence (Touch 1/2/3, 2-day gap) ✅
