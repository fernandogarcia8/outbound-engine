"""
Outbound Engine — Streamlit Web App

Run with:
  streamlit run app.py
"""

import sys
import os
import json

_ENGINE_DIR = os.path.join(os.path.dirname(__file__), "outbound_engine")
sys.path.insert(0, _ENGINE_DIR)

# ── Secret bootstrap ───────────────────────────────────────────────────────────
# On Streamlit Cloud: reads from st.secrets, writes credentials.json to /tmp.
# Locally: falls back to .env exactly as before.
import streamlit as st

_CLOUD_SECRET_KEYS = (
    "KUSTOMER_API_KEY_READ", "KUSTOMER_API_KEY_WRITE",
    "MARKETS_DRIVE_FOLDER_ID", "KUSTOMER_EMAIL_FROM_ADDRESS",
    "KUSTOMER_EMAIL_FROM_NAME", "KUSTOMER_SMS_FROM_1",
    "KUSTOMER_SMS_FROM_2", "KUSTOMER_SMS_FROM",
)

try:
    _using_cloud = "KUSTOMER_API_KEY_READ" in st.secrets
except Exception:
    _using_cloud = False

if _using_cloud:
    for _k in _CLOUD_SECRET_KEYS:
        try:
            os.environ[_k] = str(st.secrets[_k])
        except KeyError:
            pass
    if "gcp_service_account" in st.secrets:
        _creds_path = "/tmp/gcp_credentials.json"
        with open(_creds_path, "w") as _f:
            json.dump(dict(st.secrets["gcp_service_account"]), _f)
        os.environ["GOOGLE_SHEETS_CREDENTIALS_JSON"] = _creds_path
else:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ENGINE_DIR, ".env"))
    for _var in ("GOOGLE_SHEETS_CREDENTIALS_JSON",):
        _val = os.getenv(_var, "")
        if _val and not os.path.isabs(_val):
            os.environ[_var] = os.path.join(_ENGINE_DIR, _val)
from markets import get_markets
from import_split import import_and_split
from split_not_live import split_not_live
from classify_not_live import classify_not_live
from cross_list import detect_cross_list
from prep_churn import prep_churn
from prep_prospects import prep_prospects
from engine import run_campaign, send_from_drafts
from draft_prospects import generate_drafts
from seed_test_rows import seed_test_rows
from template_store import load_overrides, save_overrides
from templates import get_default_templates
from metrics import load_all_metrics
import pandas as pd


# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Outbound Engine",
    page_icon="🚤",
    layout="wide",
)

st.markdown("""
<style>
    /* Main content padding */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 860px;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #E0F0FB;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        padding: 0 20px;
        border-radius: 8px 8px 0 0;
        font-weight: 600;
        font-size: 0.9rem;
        color: #64748B;
    }
    .stTabs [aria-selected="true"] {
        background-color: #EFF8FF;
        color: #0EA5E9;
        border-bottom: 2px solid #0EA5E9;
    }

    /* Phase cards */
    .phase-card {
        border: 1px solid #BFDBFE;
        border-radius: 10px;
        padding: 1.1rem 1.4rem;
        margin-bottom: 1rem;
        background: #F0F9FF;
    }
    .phase-label {
        font-size: 1rem;
        font-weight: 600;
        color: #0C4A6E;
        margin-bottom: 0.15rem;
    }
    .phase-desc {
        font-size: 0.85rem;
        color: #0369A1;
        margin-bottom: 0;
    }

    /* Section labels */
    .section-label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #94A3B8;
        margin: 1.4rem 0 0.5rem 0;
    }

    /* Sidebar branding */
    .sidebar-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #0C4A6E;
        margin-bottom: 0;
    }
    .sidebar-sub {
        font-size: 0.78rem;
        color: #94A3B8;
        margin-top: 0;
    }

    /* Log output */
    .log-box {
        background: #0F172A;
        color: #CBD5E1;
        font-family: 'Courier New', monospace;
        font-size: 0.78rem;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        max-height: 360px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.5;
    }
</style>
""", unsafe_allow_html=True)


# ── Auth ────────────────────────────────────────────────────────────────────────
_AUTH_ENABLED = False
try:
    _AUTH_ENABLED = "auth" in st.secrets
except Exception:
    pass

# ── Market discovery ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_markets() -> dict:
    return get_markets()


@st.cache_data(ttl=1800, show_spinner=False)
def load_metrics_cached() -> dict:
    return load_all_metrics(load_markets())


# ── Sidebar ─────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<p class="sidebar-title">🚤 Outbound Engine</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-sub">Supply Team</p>', unsafe_allow_html=True)
    st.divider()

    MARKETS = load_markets()

    if not MARKETS:
        st.error("No markets found. Share a Google Sheet with the service account.")
        st.stop()

    market_key = st.selectbox(
        "Market",
        options=list(MARKETS.keys()),
        format_func=lambda k: MARKETS[k]["display_name"],
    )

    cfg         = MARKETS[market_key]
    market_name = cfg["display_name"]
    sheet_id    = cfg["sheet_id"]
    sheets      = cfg.get("sheets", {})

    bs_live      = sheets.get("bs_live",      "BS - Live")
    gmb_live     = sheets.get("gmb_live",     "GMB - Live")
    bs_not_live  = sheets.get("bs_not_live",  "BS - Not Live")
    bs_churn     = sheets.get("bs_churn",     "BS - Churn")
    gmb_not_live = sheets.get("gmb_not_live", "GMB - Not Live")
    prospects    = sheets.get("prospects",    "Prospects")

    st.divider()
    test_only = st.toggle("Test contacts only", value=False)
    if test_only:
        st.warning("Test mode ON — only rows where Notes = 'test' will be contacted.")

    st.divider()
    st.caption("Markets refresh every 5 min. Add a new market by sharing a Google Sheet with the service account and placing it in the Outbound Engine Drive folder.")

    if _AUTH_ENABLED:
        st.divider()
        if not st.session_state.get("logged_in"):
            st.markdown('<p class="section-label">Login</p>', unsafe_allow_html=True)
            _login_user = st.text_input("Username", placeholder="Username", label_visibility="collapsed", key="login_username")
            _login_pass = st.text_input("Password", placeholder="Password", type="password", label_visibility="collapsed", key="login_password")
            if st.button("Login", key="login_btn", use_container_width=True):
                _valid_user = st.secrets["auth"].get("username", "")
                _valid_pass = st.secrets["auth"].get("password", "")
                if _login_user == _valid_user and _login_pass == _valid_pass:
                    st.session_state["logged_in"] = True
                    st.session_state["auth_user"] = _login_user
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        else:
            st.caption(f"Logged in as **{st.session_state.get('auth_user', 'user')}**")
            if st.button("Logout", key="logout_btn", use_container_width=True):
                st.session_state["logged_in"] = False
                st.rerun()

_logged_in = not _AUTH_ENABLED or st.session_state.get("logged_in", False)


# ── Streaming helper ────────────────────────────────────────────────────────────

def make_log_runner(log_placeholder):
    lines = []
    def on_progress(msg: str):
        lines.append(msg)
        log_placeholder.markdown(
            f'<div class="log-box">' + "\n".join(lines) + "</div>",
            unsafe_allow_html=True,
        )
    return on_progress


# ── Page header ────────────────────────────────────────────────────────────────

st.markdown(f"## {market_name}")
st.caption("Select a tab to get started.")
if _AUTH_ENABLED and not _logged_in:
    st.info("🔒 Log in from the sidebar to enable all actions.")
st.markdown("")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_setup, tab_prep, tab_outreach, tab_messaging, tab_metrics = st.tabs(["📋  Setup", "🔍  Prep", "📨  Outreach", "✏️  Messaging", "📊  Metrics"])


# ══ TAB 1: Setup ═══════════════════════════════════════════════════════════════

with tab_setup:
    st.markdown("### Scrape Prospects")
    st.markdown(
        f"Prospect scraping uses the `/boat-charter-prospector` skill in Claude Code. "
        f"Run it once per market before triggering Phase 3 outreach."
    )
    st.markdown("")

    st.info(f"""
**Steps for {market_name}:**

1. Open Claude Code in this project directory
2. Run the `/boat-charter-prospector` skill
3. When prompted, enter market: **{market_name}**
4. Results will be written to the **Prospects** tab in the sheet
5. Review the tab, then go to **Prep** before running outreach
    """)

    st.markdown("")
    st.caption("Full automation of this step is coming in a future update.")


# ══ TAB 2: Prep ════════════════════════════════════════════════════════════════

with tab_prep:

    # ── Funnel Prep ─────────────────────────────────────────────────────────────
    st.markdown("### Funnel Prep")
    st.markdown(
        "Runs all detection and classification steps against the current sheet data. "
        "Run this once per new Snowflake export before triggering any outreach."
    )
    st.markdown("")

    st.markdown('<p class="section-label">Steps</p>', unsafe_allow_html=True)
    st.markdown("""
- **1 of 4 — Import & Split** Sheet1 into BS - Live, GMB - Live, BS - Not Live, BS - Churn, GMB - Not Live
- **2 of 4 — Classify** BS - Not Live rows by tier and assign action
- **3 of 4 — Detect** cross-list overlaps across BS - Live and GMB - Live
- **4 of 4 — Churn** classify deactivated rows by tier in BS - Churn
    """)

    st.markdown("")
    col1, col2, _ = st.columns([1, 1, 3])
    prep_dry  = col1.button("Dry Run",  key="prep_dry",  disabled=not _logged_in)
    prep_live = col2.button("Run Prep", key="prep_live", type="primary", disabled=not _logged_in)

    if prep_dry or prep_live:
        dry = prep_dry
        log_ph = st.empty()
        cb     = make_log_runner(log_ph)

        with st.status(f"{'[DRY RUN] ' if dry else ''}Running prep for {market_name}...", expanded=True) as status:
            st.write("**1 / 4** — Importing and splitting from Sheet1...")
            try:
                ri = import_and_split(
                    sheet_id=sheet_id,
                    raw_sheet="Sheet1",
                    bs_live_sheet=bs_live,
                    gmb_live_sheet=gmb_live,
                    bs_not_live_sheet=bs_not_live,
                    bs_churn_sheet=bs_churn,
                    gmb_not_live_sheet=gmb_not_live,
                    dry_run=dry,
                    on_progress=cb,
                )
                st.write(" · ".join(f"{tab}: {n}" for tab, n in ri.items()))
            except Exception as e:
                status.update(label="Import failed", state="error")
                st.error(str(e))
                st.stop()

            st.write("**2 / 4** — Classifying BS - Not Live...")
            r2 = classify_not_live(
                sheet_id=sheet_id, sheet_name=bs_not_live,
                dry_run=dry, on_progress=cb,
            )
            st.write(f"Classified: {r2.get('classified',0)} · Already set: {r2.get('skipped_already_set',0)}")

            st.write("**3 / 4** — Cross-list detection...")
            detect_cross_list(
                spreadsheet_id=sheet_id,
                bs_sheet_name=bs_live, gmb_sheet_name=gmb_live,
                churn_sheet_name=bs_churn, not_live_sheet_name=bs_not_live,
                dry_run=dry, on_progress=cb,
            )

            st.write("**4 / 4** — Churn classification...")
            rc = prep_churn(
                sheet_id=sheet_id,
                sheet_name=bs_churn,
                dry_run=dry,
                on_progress=cb,
            )
            st.write(
                f"Churn: {rc.get('tier1',0)} Tier 1 · "
                f"{rc.get('tier2',0)} Tier 2 · "
                f"{rc.get('unclassified',0)} unclassified"
            )

            status.update(label="Prep complete!", state="complete")

        if dry:
            st.info("Dry run complete — no changes written. Review the output, then click **Run Prep** to apply.")
        else:
            st.success(f"Prep complete for **{market_name}**. Review the sheet, then go to **Outreach**.")

    st.divider()

    # ── Prospects Prep ───────────────────────────────────────────────────────────
    st.markdown("### Prospects Prep")
    st.markdown(
        "Prepares only the **Prospects** tab. "
        "Adds tracking columns, applies dropdowns, then cross-checks every prospect "
        "against BS Live, GMB Live, BS Not Live, BS Churn, and Kustomer. "
        "Matched rows get a **Funnel Status** tag and are flagged **Manual Check** "
        "so you can review them before outreach. Net new rows stay as Prospect. "
        "Safe to run after Phases 1 and 2 are already done."
    )
    st.markdown("")

    col1p, col2p, _ = st.columns([1, 1, 3])
    prep_p_dry  = col1p.button("Dry Run",  key="prep_prospects_dry",  disabled=not _logged_in)
    prep_p_live = col2p.button("Run Prep", key="prep_prospects_live", type="primary", disabled=not _logged_in)

    if prep_p_dry or prep_p_live:
        dry = prep_p_dry
        log_ph = st.empty()
        cb     = make_log_runner(log_ph)

        with st.status(f"{'[DRY RUN] ' if dry else ''}Prepping Prospects tab for {market_name}...", expanded=True) as status:
            rp = prep_prospects(
                sheet_id=sheet_id,
                sheet_name=prospects,
                bs_live_sheet=bs_live,
                gmb_live_sheet=gmb_live,
                bs_not_live_sheet=bs_not_live,
                bs_churn_sheet=bs_churn,
                dry_run=dry,
                on_progress=cb,
            )
            status.update(label="Prospects prep complete!", state="complete")

        if dry:
            st.info(
                f"Dry run complete — {rp['filled']} rows would be set up · "
                f"{rp['net_new']} net new · {rp['matched']} already in funnel. "
                f"Click **Run Prep** to apply."
            )
        else:
            st.success(
                f"Done: **{rp['net_new']} net new** prospects (clear to contact) · "
                f"**{rp['matched']} already in funnel** (set to Manual Check — review before outreach). "
                f"Go to **Outreach → Phase 3**."
            )


# ══ TAB 3: Outreach ════════════════════════════════════════════════════════════

with tab_outreach:
    st.markdown("### Outreach")
    st.markdown("Run each phase in order. Review the sheet between phases.")
    st.markdown("")

    # ── Seed test rows (only shown when test mode is on) ───────────────────────
    if test_only:
        st.markdown('<p class="section-label">Test Setup</p>', unsafe_allow_html=True)

        from config import TEAM_MEMBERS as _TEAM_MEMBERS
        _member_names   = [m["first_name"] for m in _TEAM_MEMBERS]
        _selected_names = st.multiselect(
            "Seed contacts for",
            options=_member_names,
            default=_member_names,
            key="seed_members_select",
        )
        _members_to_seed = [m for m in _TEAM_MEMBERS if m["first_name"] in _selected_names]

        st.caption("Adds selected contacts as test rows to all sheet tabs. Skips any tab where they already exist.")
        seed_col1, seed_col2, _ = st.columns([1, 1, 4])
        seed_dry  = seed_col1.button("Preview",        key="seed_dry",  disabled=not _logged_in)
        seed_live = seed_col2.button("Seed test rows", key="seed_live", type="primary", disabled=not _logged_in)

        if seed_dry or seed_live:
            if not _members_to_seed:
                st.warning("Select at least one contact to seed.")
            else:
                log_ph = st.empty()
                cb     = make_log_runner(log_ph)
                with st.status(f"{'[DRY RUN] ' if seed_dry else ''}Seeding test rows for {market_name}...", expanded=True) as status:
                    results = seed_test_rows(
                        sheet_id=sheet_id,
                        bs_live=bs_live, gmb_live=gmb_live,
                        bs_not_live=bs_not_live, prospects=prospects,
                        dry_run=seed_dry, on_progress=cb,
                        members=_members_to_seed,
                    )
                    status.update(label="Done!", state="complete")
                total = sum(results.values())
                if seed_dry:
                    st.info(f"Preview complete — {total} row(s) would be added. Click **Seed test rows** to apply.")
                else:
                    st.success(f"{total} test row(s) added. Run outreach phases below with test mode on.")
        st.divider()

    phases = [
        {
            "num":   1,
            "label": "Phase 1 - Cross-List",
            "desc":  "BS - Live → Getmyboat pitch   ·   GMB - Live → Boatsetter pitch",
            "key":   "phase1",
        },
        {
            "num":   2,
            "label": "Phase 2 - Reactivate + Get Live",
            "desc":  "Reactivate + Get Live",
            "key":   "phase2",
        },
        {
            "num":   3,
            "label": "Phase 3 - Prospect",
            "desc":  "Cold outreach via Casey alias",
            "key":   "phase3",
        },
    ]

    for phase in phases:
        num = phase["num"]
        key = phase["key"]

        with st.expander(phase["label"]):

            # ── Phase 3 — draft flow ───────────────────────────────────────────
            if num == 3:
                st.markdown(
                    "Phase 3 uses a **review-before-send** flow. "
                    "Generate drafts first, review and edit them directly in the Google Sheet, "
                    "then come back and send."
                )
                st.markdown(
                    "<hr style='margin:0.6rem 0; border:none; border-top:1px solid #E2E8F0'>",
                    unsafe_allow_html=True,
                )

                # ── Step 1: Generate Drafts ────────────────────────────────────
                st.markdown("**Step 1 — Generate Drafts**")
                st.caption(
                    "Writes Draft Subject / Draft Email / Draft SMS columns to the Prospects tab. "
                    "No messages are sent. Edit any cell in the sheet before sending."
                )
                gcol1, gcol2, _ = st.columns([1, 1, 4])
                gen_dry  = gcol1.button("Dry Run",         key="p3_gen_dry",  disabled=not _logged_in)
                gen_live = gcol2.button("Generate Drafts", key="p3_gen_live", type="primary", disabled=not _logged_in)

                if gen_dry or gen_live:
                    log_ph = st.empty()
                    cb     = make_log_runner(log_ph)
                    dry    = gen_dry
                    label  = f"{'[DRY RUN] ' if dry else ''}Generating drafts for {market_name}..."
                    with st.status(label, expanded=True) as status:
                        result = generate_drafts(
                            sheet_id=sheet_id,
                            sheet_name=prospects,
                            market=market_name,
                            dry_run=dry,
                            test_only=test_only,
                            on_progress=cb,
                        )
                        status.update(label="Draft generation complete!", state="complete")
                    if dry:
                        st.info("Dry run complete — no changes made. Run without Dry Run to write drafts to the sheet.")
                    else:
                        st.success(
                            f"**{result['drafted']} draft(s)** written to the Prospects tab. "
                            f"Open the sheet, review the Draft Subject / Draft Email / Draft SMS columns, "
                            f"edit as needed, then click Send Drafts below."
                        )

                st.markdown(
                    "<hr style='margin:0.6rem 0; border:none; border-top:1px solid #E2E8F0'>",
                    unsafe_allow_html=True,
                )

                # ── Step 2: Send Initial Outreach (draft flow) ────────────────
                st.markdown("**Step 2 — Send Initial Outreach**")
                st.caption(
                    "Sends the T1 messages exactly as written in the draft columns. "
                    "Draft columns are kept as a record after sending."
                )
                s2c1, s2c2, _ = st.columns([1, 1.4, 4])
                s2_dry  = s2c1.button("Dry Run",      key=f"{key}_t1_dry",  disabled=not _logged_in)
                s2_live = s2c2.button("Send Initial", key=f"{key}_t1_live", type="primary", disabled=not _logged_in)

                if s2_live:
                    st.session_state[f"{key}_t1_confirm"] = True

                if st.session_state.get(f"{key}_t1_confirm"):
                    if test_only:
                        st.info(
                            f"Sending **Phase 3 — Initial** to **test contacts only** in "
                            f"**{market_name}**. Messages cannot be unsent."
                        )
                    else:
                        st.warning(
                            f"Sending **Phase 3 — Initial** to real contacts in "
                            f"**{market_name}**. Messages cannot be unsent."
                        )
                    cc1, cc2, _ = st.columns([1, 1, 4])
                    s2_confirmed = cc1.button("Confirm — Send", key=f"{key}_t1_confirmed", type="primary", disabled=not _logged_in)
                    s2_cancelled = cc2.button("Cancel",         key=f"{key}_t1_cancel",    disabled=not _logged_in)
                    if s2_cancelled:
                        st.session_state[f"{key}_t1_confirm"] = False
                        st.rerun()
                else:
                    s2_confirmed = False

                if s2_dry or s2_confirmed:
                    dry = s2_dry
                    if s2_confirmed:
                        st.session_state[f"{key}_t1_confirm"] = False
                    log_ph = st.empty()
                    cb     = make_log_runner(log_ph)
                    label  = f"{'[DRY RUN] ' if dry else ''}Phase 3 — Initial"
                    with st.status(f"Running {label}...", expanded=True) as status:
                        send_from_drafts(
                            market=market_name,
                            sheet_id=sheet_id,
                            sheet_name=prospects,
                            dry_run=dry,
                            test_only=test_only,
                            on_progress=cb,
                        )
                        status.update(label=f"{label} complete!", state="complete")
                    if dry:
                        st.info("Dry run complete — no messages sent.")
                    else:
                        st.success(f"**{label}** sent for **{market_name}**.")

                st.markdown(
                    "<hr style='margin:0.6rem 0; border:none; border-top:1px solid #E2E8F0'>",
                    unsafe_allow_html=True,
                )

                # ── Step 3: Follow-up 1 ────────────────────────────────────────
                st.markdown("**Step 3 — Follow-up 1**")
                st.caption(
                    "Sends T2 directly from templates on the same conversation thread as the initial. "
                    "Only contacts where Initial was sent and no reply received."
                )
                s3c1, s3c2, _ = st.columns([1, 1.4, 4])
                s3_dry  = s3c1.button("Dry Run",          key=f"{key}_fu1_dry",  disabled=not _logged_in)
                s3_live = s3c2.button("Send Follow-up 1", key=f"{key}_fu1_live", type="primary", disabled=not _logged_in)

                if s3_live:
                    st.session_state[f"{key}_fu1_confirm"] = True

                if st.session_state.get(f"{key}_fu1_confirm"):
                    if test_only:
                        st.info(f"Sending **Phase 3 — Follow-up 1** to **test contacts only** in **{market_name}**. Messages cannot be unsent.")
                    else:
                        st.warning(f"Sending **Phase 3 — Follow-up 1** to real contacts in **{market_name}**. Messages cannot be unsent.")
                    cc1, cc2, _ = st.columns([1, 1, 4])
                    s3_confirmed = cc1.button("Confirm — Send", key=f"{key}_fu1_confirmed", type="primary", disabled=not _logged_in)
                    s3_cancelled = cc2.button("Cancel",         key=f"{key}_fu1_cancel",    disabled=not _logged_in)
                    if s3_cancelled:
                        st.session_state[f"{key}_fu1_confirm"] = False
                        st.rerun()
                else:
                    s3_confirmed = False

                if s3_dry or s3_confirmed:
                    dry = s3_dry
                    if s3_confirmed:
                        st.session_state[f"{key}_fu1_confirm"] = False
                    log_ph = st.empty()
                    cb     = make_log_runner(log_ph)
                    label  = f"{'[DRY RUN] ' if dry else ''}Phase 3 — Follow-up 1"
                    with st.status(f"Running {label}...", expanded=True) as status:
                        run_campaign(
                            segment="prospect",
                            market=market_name,
                            sheet_id=sheet_id,
                            sheet_name=prospects,
                            dry_run=dry,
                            test_only=test_only,
                            min_touch=2,
                            max_touch=2,
                            require_approval=False,
                            on_progress=cb,
                        )
                        status.update(label=f"{label} complete!", state="complete")
                    if dry:
                        st.info("Dry run complete — no messages sent.")
                    else:
                        st.success(f"**{label}** sent for **{market_name}**.")

                st.markdown(
                    "<hr style='margin:0.6rem 0; border:none; border-top:1px solid #E2E8F0'>",
                    unsafe_allow_html=True,
                )

                # ── Step 4: Follow-up 2 ────────────────────────────────────────
                st.markdown("**Step 4 — Follow-up 2**")
                st.caption(
                    "Sends T3 directly from templates. "
                    "Only contacts where Follow-up 1 was sent and no reply received."
                )
                s4c1, s4c2, _ = st.columns([1, 1.4, 4])
                s4_dry  = s4c1.button("Dry Run",          key=f"{key}_fu2_dry",  disabled=not _logged_in)
                s4_live = s4c2.button("Send Follow-up 2", key=f"{key}_fu2_live", type="primary", disabled=not _logged_in)

                if s4_live:
                    st.session_state[f"{key}_fu2_confirm"] = True

                if st.session_state.get(f"{key}_fu2_confirm"):
                    if test_only:
                        st.info(f"Sending **Phase 3 — Follow-up 2** to **test contacts only** in **{market_name}**. Messages cannot be unsent.")
                    else:
                        st.warning(f"Sending **Phase 3 — Follow-ups 2** to real contacts in **{market_name}**. Messages cannot be unsent.")
                    cc1, cc2, _ = st.columns([1, 1, 4])
                    s4_confirmed = cc1.button("Confirm — Send", key=f"{key}_fu2_confirmed", type="primary", disabled=not _logged_in)
                    s4_cancelled = cc2.button("Cancel",         key=f"{key}_fu2_cancel",    disabled=not _logged_in)
                    if s4_cancelled:
                        st.session_state[f"{key}_fu2_confirm"] = False
                        st.rerun()
                else:
                    s4_confirmed = False

                if s4_dry or s4_confirmed:
                    dry = s4_dry
                    if s4_confirmed:
                        st.session_state[f"{key}_fu2_confirm"] = False
                    log_ph = st.empty()
                    cb     = make_log_runner(log_ph)
                    label  = f"{'[DRY RUN] ' if dry else ''}Phase 3 — Follow-up 2"
                    with st.status(f"Running {label}...", expanded=True) as status:
                        run_campaign(
                            segment="prospect",
                            market=market_name,
                            sheet_id=sheet_id,
                            sheet_name=prospects,
                            dry_run=dry,
                            test_only=test_only,
                            min_touch=3,
                            max_touch=3,
                            require_approval=False,
                            on_progress=cb,
                        )
                        status.update(label=f"{label} complete!", state="complete")
                    if dry:
                        st.info("Dry run complete — no messages sent.")
                    else:
                        st.success(f"**{label}** sent for **{market_name}**.")

            # ── Phases 1 + 2 — Initial / Follow-up 1 / Follow-up 2 ───────────
            else:
                _funnel_steps = [
                    {"label": "Initial",     "caption": "First outreach to eligible contacts.",                                      "min_touch": 1, "max_touch": 1},
                    {"label": "Follow-up 1", "caption": "Contacts where Initial was sent and no reply received.",                    "min_touch": 2, "max_touch": 2},
                    {"label": "Follow-up 2", "caption": "Contacts where Follow-up 1 was sent and no reply received.",               "min_touch": 3, "max_touch": 3},
                ]

                for si, step in enumerate(_funnel_steps):
                    step_label = step["label"]
                    min_t      = step["min_touch"]
                    max_t      = step["max_touch"]
                    skey       = f"{key}_s{min_t}"

                    st.markdown(f"**{step_label}**")
                    st.caption(step["caption"])

                    sc1, sc2, _ = st.columns([1, 1.4, 4])
                    s_dry  = sc1.button("Dry Run",            key=f"{skey}_dry",  disabled=not _logged_in)
                    s_live = sc2.button(f"Send {step_label}", key=f"{skey}_live", type="primary", disabled=not _logged_in)

                    if s_live:
                        st.session_state[f"{skey}_confirm"] = True

                    if st.session_state.get(f"{skey}_confirm"):
                        if test_only:
                            st.info(f"Sending **{phase['label']} — {step_label}** to **test contacts only** in **{market_name}**. Messages cannot be unsent.")
                        else:
                            st.warning(f"Sending **{phase['label']} — {step_label}** to real contacts in **{market_name}**. Messages cannot be unsent.")
                        cc1, cc2, _ = st.columns([1, 1, 4])
                        confirmed = cc1.button("Confirm — Send", key=f"{skey}_confirmed", type="primary", disabled=not _logged_in)
                        cancelled = cc2.button("Cancel",         key=f"{skey}_cancel",    disabled=not _logged_in)
                        if cancelled:
                            st.session_state[f"{skey}_confirm"] = False
                            st.rerun()
                    else:
                        confirmed = False

                    if s_dry or confirmed:
                        dry = s_dry
                        if confirmed:
                            st.session_state[f"{skey}_confirm"] = False
                        log_ph = st.empty()
                        cb     = make_log_runner(log_ph)

                        base = dict(
                            market=market_name, sheet_id=sheet_id,
                            dry_run=dry, test_only=test_only,
                            require_approval=False, on_progress=cb,
                            min_touch=min_t, max_touch=max_t,
                        )

                        label = f"{'[DRY RUN] ' if dry else ''}{phase['label']} — {step_label}"
                        with st.status(f"Running {label}...", expanded=True) as status:
                            if num == 1:
                                st.write("**1 / 2** — BS - Live → Getmyboat (email + SMS)")
                                run_campaign(segment="cross_list", sheet_name=bs_live, **base)
                                st.write("**2 / 2** — GMB - Live → Boatsetter (SMS only)")
                                run_campaign(segment="cross_list", sheet_name=gmb_live, sms_only=True, **base)
                            elif num == 2:
                                st.write("**1 / 2** — Reactivate")
                                run_campaign(segment="reactivate", sheet_name=bs_not_live, **base)
                                st.write("**2 / 2** — Get Live")
                                run_campaign(segment="get_live", sheet_name=bs_not_live, **base)
                            status.update(label=f"{label} complete!", state="complete")

                        if dry:
                            st.info("Dry run complete — no messages sent. Review the output, then click Send.")
                        else:
                            st.success(f"**{label}** sent for **{market_name}**.")

                    if si < len(_funnel_steps) - 1:
                        st.markdown(
                            "<hr style='margin:0.6rem 0; border:none; border-top:1px solid #E2E8F0'>",
                            unsafe_allow_html=True,
                        )


# ══ TAB 4: Messaging ═══════════════════════════════════════════════════════════

_SEGMENT_LABELS = {
    "reactivate_recent": "Reactivate — Recent (< 90 days inactive)",
    "reactivate_old":    "Reactivate — Old (90+ days / no date)",
    "get_live":          "Get Live",
    "cross_list_bs":     "Cross-List — BS Live → pitch Getmyboat",
    "cross_list_gmb":    "Cross-List — GMB Live → pitch Boatsetter",
    "prospect_fishing":  "Prospect — Fishing Charter",
    "prospect_rental":   "Prospect — Rental / Sailboat",
    "prospect_charter":  "Prospect — Charter / Tour / Watersports",
}

_TOUCH_LABELS_MSG = {1: "Touch 1 — Initial", 2: "Touch 2 — Follow-up 1", 3: "Touch 3 — Follow-up 2"}

with tab_messaging:
    st.markdown("### Message Templates")
    st.markdown(
        "View and customize the outreach copy for this market. "
        "The default templates are used unless you save an override here. "
        "Overrides are stored in the market's Google Sheet and applied automatically at send time."
    )
    st.markdown("")

    # ── Load overrides into session state (once per market per session) ────────
    _ovr_key = f"tmpl_overrides_{sheet_id}"
    if _ovr_key not in st.session_state:
        with st.spinner("Loading saved templates..."):
            try:
                st.session_state[_ovr_key] = load_overrides(sheet_id)
            except Exception:
                st.session_state[_ovr_key] = {}
    _overrides = st.session_state[_ovr_key]

    # Load defaults once (pure Python — no API call)
    _defaults = get_default_templates()

    # ── Selectors ─────────────────────────────────────────────────────────────
    sel_col1, sel_col2 = st.columns([3, 2])
    with sel_col1:
        sel_segment = st.selectbox(
            "Segment",
            options=list(_SEGMENT_LABELS.keys()),
            format_func=lambda k: _SEGMENT_LABELS[k],
            key="msg_segment",
        )
    with sel_col2:
        sel_touch = st.radio(
            "Touch",
            options=[1, 2, 3],
            format_func=lambda t: _TOUCH_LABELS_MSG[t],
            horizontal=True,
            key="msg_touch",
        )

    st.markdown("")

    _key_prefix   = f"{sel_segment}_t{sel_touch}"
    _sms_key      = f"{_key_prefix}_sms"
    _email_key    = f"{_key_prefix}_email"
    _subject_key  = f"{_key_prefix}_subject"

    _is_customized = any(k in _overrides for k in (_sms_key, _email_key, _subject_key))

    if _is_customized:
        st.success(f"Customized for **{market_name}** — this template overrides the default.")
    else:
        st.info("Using the default template. Edit and save below to customize for this market.")

    st.markdown("")

    # ── Subject ───────────────────────────────────────────────────────────────
    _subject_widget_key = f"msg_subject_{_key_prefix}"
    if _subject_widget_key not in st.session_state:
        st.session_state[_subject_widget_key] = _overrides.get(_subject_key, _defaults.get(_subject_key, ""))

    st.markdown('<p class="section-label">Email Subject</p>', unsafe_allow_html=True)
    new_subject = st.text_input(
        "Email Subject",
        key=_subject_widget_key,
        label_visibility="collapsed",
    )

    # ── SMS + Email side by side ───────────────────────────────────────────────
    st.markdown("")
    msg_col_sms, msg_col_email = st.columns(2)

    _sms_widget_key   = f"msg_sms_{_key_prefix}"
    _email_widget_key = f"msg_email_{_key_prefix}"

    if _sms_widget_key not in st.session_state:
        st.session_state[_sms_widget_key] = _overrides.get(_sms_key, _defaults.get(_sms_key, ""))
    if _email_widget_key not in st.session_state:
        st.session_state[_email_widget_key] = _overrides.get(_email_key, _defaults.get(_email_key, ""))

    with msg_col_sms:
        st.markdown('<p class="section-label">SMS Body</p>', unsafe_allow_html=True)
        new_sms = st.text_area(
            "SMS Body",
            key=_sms_widget_key,
            height=340,
            label_visibility="collapsed",
        )

    with msg_col_email:
        st.markdown('<p class="section-label">Email Body</p>', unsafe_allow_html=True)
        new_email = st.text_area(
            "Email Body",
            key=_email_widget_key,
            height=340,
            label_visibility="collapsed",
        )

    st.caption(
        "Available placeholders: `{greeting}` · `{market}` · `{rep}` · "
        "`{boat_noun}` · `{charter_name}` · `{name_ref}` · `{activity_ref}`"
    )
    st.markdown("")

    # ── Action buttons ────────────────────────────────────────────────────────
    btn_col1, btn_col2, _ = st.columns([1.4, 1.2, 4])

    with btn_col1:
        if st.button(f"Save for {market_name}", type="primary", key="msg_save", disabled=not _logged_in):
            _overrides[_sms_key]     = new_sms
            _overrides[_email_key]   = new_email
            _overrides[_subject_key] = new_subject
            st.session_state[_ovr_key] = _overrides
            try:
                save_overrides(sheet_id, _overrides)
                st.success("Saved!")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")

    with btn_col2:
        if _is_customized and st.button("Reset to default", key="msg_reset", disabled=not _logged_in):
            for _k in (_sms_key, _email_key, _subject_key):
                _overrides.pop(_k, None)
            # Reset widget state so textareas show the default on next render
            st.session_state[_sms_widget_key]     = _defaults.get(_sms_key, "")
            st.session_state[_email_widget_key]   = _defaults.get(_email_key, "")
            st.session_state[_subject_widget_key] = _defaults.get(_subject_key, "")
            st.session_state[_ovr_key] = _overrides
            try:
                save_overrides(sheet_id, _overrides)
                st.rerun()
            except Exception as e:
                st.error(f"Reset failed: {e}")


# ══ TAB 5: Metrics ═════════════════════════════════════════════════════════════

def _render_metrics_section(tot: dict, mkts: dict):
    """Renders summary cards + touch breakdown + by-market table for one category."""
    total_emails = sum(tot["emails"].values())
    total_sms    = sum(tot["sms"].values())
    contacted    = tot["contacted"]
    replied        = tot["replied"]
    reply_pct      = f"{replied / contacted * 100:.1f}%" if contacted else "—"

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Owners Contacted", contacted)
    mc2.metric("Reply Rate",       reply_pct)
    mc3.metric("Emails Sent",      total_emails)
    mc4.metric("SMS Sent",         total_sms)

    st.markdown("")

    if mkts:
        st.markdown("")
        mkt_rows = []
        for mkt_key, m in mkts.items():
            e = sum(m["emails"].values())
            s = sum(m["sms"].values())
            c = m["contacted"]
            r = m["replied"]
            mkt_rows.append({
                "Market":           m["display_name"],
                "Owners Contacted": c,
                "Emails":           e,
                "SMS":              s,
                "Total Messages":   e + s,
                "Replied":          r,
                "Reply Rate":       f"{r / c * 100:.1f}%" if c else "—",
            })
        st.dataframe(
            pd.DataFrame(mkt_rows).set_index("Market"),
            use_container_width=True,
        )


with tab_metrics:
    st.markdown("### Outreach Metrics")
    st.caption(
        "Excludes test rows. Fleet owners counted once regardless of boat count. "
        "Reply Rate = owners who replied / owners contacted (toggle 'Replied?' to TRUE in the sheet when an owner responds in Kustomer). "
        "Cached for 30 min — click Refresh to force a reload."
    )

    if st.button("🔄 Refresh", key="metrics_refresh", disabled=not _logged_in):
        load_metrics_cached.clear()
        st.rerun()

    with st.spinner("Loading metrics across all markets..."):
        _m = load_metrics_cached()

    # Clear stale cache if it holds the old single-dict format
    if "funnel" not in _m:
        load_metrics_cached.clear()
        st.rerun()

    _funnel   = _m["funnel"]
    _prospect = _m["prospect"]

    # ── Overall ────────────────────────────────────────────────────────────────
    _ft = _funnel["total"]
    _pt = _prospect["total"]
    _all_emails    = sum(_ft["emails"].values()) + sum(_pt["emails"].values())
    _all_sms       = sum(_ft["sms"].values())    + sum(_pt["sms"].values())
    _all_contacted = _ft["contacted"] + _pt["contacted"]
    _all_replied   = _ft["replied"]   + _pt["replied"]
    _all_reply_pct = f"{_all_replied / _all_contacted * 100:.1f}%" if _all_contacted else "—"

    st.markdown("#### Overall")
    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    ov1.metric("Owners Contacted", _all_contacted)
    ov2.metric("Reply Rate",       _all_reply_pct)
    ov3.metric("Emails Sent",      _all_emails)
    ov4.metric("SMS Sent",         _all_sms)
    ov5.metric("Total Messages",   _all_emails + _all_sms)

    st.divider()

    # ── Funnel Outreach ────────────────────────────────────────────────────────
    st.markdown("#### Funnel Outreach")
    st.caption("Existing owners with a prior relationship to Boatsetter or Getmyboat.")
    _render_metrics_section(_funnel["total"], _funnel["markets"])

    st.divider()

    # ── Prospect Outreach ──────────────────────────────────────────────────────
    st.markdown("#### Prospect Outreach")
    st.caption("Prospects tab — cold outreach to net new contacts with no prior Boatsetter or Getmyboat relationship.")
    _render_metrics_section(_prospect["total"], _prospect["markets"])
