# Outbound Engine — Handoff Context

## Project location
```
/Users/fernandogarcia/Desktop/Claude/Outbound Engine/
├── controller.py           ← CLI entry point (use this instead of running scripts directly)
├── app.py                  ← Streamlit web app
├── markets.py              ← Dynamic market discovery (reads from Google Drive)
├── .streamlit/config.toml  ← App theme (light blue)
└── outbound_engine/
    ├── engine.py
    ├── cross_list.py
    ├── split_not_live.py
    ├── classify_not_live.py
    ├── market_discovery.py ← Drive folder scanner (handles shortcuts)
    ├── templates.py
    ├── segmentation.py
    ├── kustomer_client.py
    ├── sheets_connector.py
    ├── round_robin.py
    ├── logger.py
    ├── config.py
    ├── .env                ← API keys + MARKETS_DRIVE_FOLDER_ID
    └── credentials.json    ← Google service account
```

## What this is
A Python outreach engine for Boatsetter's supply team. Reads Google Sheets, sends email + SMS via Kustomer API, writes results back. Now has a Streamlit web app and a CLI controller. Markets auto-discovered from a Google Drive folder.

---

## How to run

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
2. `classify_not_live` — assigns Tier + Action to take + Contact Status to actionable rows
3. `detect_cross_list` — 5-layer + name-match detection, tags BS - Live and GMB - Live

---

## Market auto-discovery

Markets are discovered automatically from Google Drive at app startup (cached 5 min).

**To add a new market:**
1. Create a Google Sheet named after the market (e.g. "Panama City")
2. Share it with `outbound-engine@n8n-sheets-456321.iam.gserviceaccount.com` (Editor)
3. Place it (or a shortcut) in the "Outbound Engine" Drive folder:
   `https://drive.google.com/drive/u/0/folders/1jje4PAk8chx9pSbkjldhWsAqFQiCA4cf`
4. It appears in the web app dropdown automatically

Drive folder ID is set in `.env` as `MARKETS_DRIVE_FOLDER_ID=1jje4PAk8chx9pSbkjldhWsAqFQiCA4cf`.

Note: If you move an existing file into the folder, Drive creates a shortcut. The discovery code handles shortcuts correctly (resolves targetId).

**Required tab names inside each market sheet:**
`BS - Live` | `GMB - Live` | `BS - Not Live` | `BS - Churn` | `Prospects`

---

## Test mode

All outreach runs support a test mode that filters to rows where `Notes = "test"`.

In test mode, the eligibility and touch-timing checks are **bypassed entirely** — test contacts always receive Touch 1 regardless of prior send history. This means test contacts can be reused without resetting the sheet.

```bash
# CLI
python controller.py outreach --market savannah --phase 1 --test

# Web app
# Toggle "Test contacts only" in the sidebar before clicking Send
```

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
{"name": "Tyler",    "kustomer_id": "68233767cc5a45b13d77bef8"},
{"name": "Fernando", "kustomer_id": "63e13a6d7e5d1d84e78cacaa"},
```

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

Layer 6 (name match) catches same-person different-email cases. Notes include matched contact info for manual verification.

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

BS - Churn states (moved by split_not_live.py): `boatbound_denied`, `deactivated`, `deleted`, `incomplete`, `insurance_denied`, `pending_insurance`, `pending_survey`

---

## Active markets

### Savannah — "Savannah - Outbound" sheet
Sheet ID: `1TXflgydfFvtd1GuMAfyO5UDopQ5lCD22AMpRusK6vlU`

All test runs complete. **Live outreach has not been fired yet.**

| Sheet | Status |
|---|---|
| BS - Live | 11 Cross-List targets ready. Test run ✓ |
| GMB - Live | 0 targets (all are Dual Presence / Possible Dual Presence after name-match detection caught Keith Walston). Test run ✓ |
| BS - Not Live | 24 Reactivate + 11 Get Live ready. Test run ✓ |
| Prospects | 34 operators (28 GA / 6 SC). Dry run ✓ |
| BS - Churn | 202 rows. No outreach process yet. |

### Orlando — "Orlando Prospecting" sheet
Newly added to the Drive folder. Sheet is empty/fresh — no prep run yet.

---

## Web app deployment

**Live at:** https://supply-outbound-engine.streamlit.app

GitHub repo: https://github.com/fernandogarcia8/boatsetter-outbound-engine (private)

Secrets (API keys + GCP service account JSON) are stored in the Streamlit Cloud secrets manager — never committed to git. To update a secret, go to the app settings on share.streamlit.io.

Local dev still works unchanged — `streamlit run app.py` reads from `outbound_engine/.env`.

---

## What's pending / next steps

1. **Fire live outreach for Savannah** — all dry runs validated, ready to go
   - Phase 1: BS - Live (11 owners, email + SMS) — GMB - Live is 0 targets
   - Phase 2: BS - Not Live (24 reactivate + 11 get_live)
   - Phase 3: Prospects (34 operators)

2. **GitHub + Streamlit Cloud deployment** — set up permanent URL for Tyler

3. **Funnel detection for Prospects tab** — cross-reference 34 scraped operators against BS - Live, GMB - Live, BS - Not Live, BS - Churn before outreach. Discussed, not built yet.

4. **BS - Churn outreach** — no process yet. Opportunity in `pending_insurance`, `deactivated`, `deleted`.

5. **Orlando market** — sheet is in Drive folder, needs raw data + prep before outreach.

---

## What's working

- Google Sheets connection ✅
- Market auto-discovery from Drive folder ✅ (handles shortcuts)
- `controller.py` CLI (prep + outreach phases 1/2/3 + scrape instructions) ✅
- `app.py` Streamlit web app (sidebar market selector, tabs, test toggle, live log) ✅
- `cross_list.py` 6-layer detection including name matching ✅
- `split_not_live.py` ✅
- `classify_not_live.py` ✅
- `engine.py` all segments ✅
- Test mode (Notes="test", bypasses eligibility/timing) ✅
- Prospect templates — fishing / rental / charter variants, no em dashes ✅
- Deduplication by owner, boat noun (boat/boats/fleet) ✅
- Round-robin (Tyler + Fernando), persisted in `round_robin_state.json` ✅
- Independent email/SMS error handling ✅
- Multi-touch sequence (Touch 1/2/3, 2-day gap) ✅
