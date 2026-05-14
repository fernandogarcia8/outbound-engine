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
from split_not_live import split_not_live
from classify_not_live import classify_not_live
from cross_list import detect_cross_list
from engine import run_campaign
from seed_test_rows import seed_test_rows
from template_store import load_overrides, save_overrides
from templates import get_default_templates


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


# ── Market discovery ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_markets() -> dict:
    return get_markets()


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

    bs_live     = sheets.get("bs_live",     "BS - Live")
    gmb_live    = sheets.get("gmb_live",    "GMB - Live")
    bs_not_live = sheets.get("bs_not_live", "BS - Not Live")
    bs_churn    = sheets.get("bs_churn",    "BS - Churn")
    prospects   = sheets.get("prospects",   "Prospects")

    st.divider()
    test_only = st.toggle("Test contacts only", value=False)
    if test_only:
        st.warning("Test mode ON — only rows where Notes = 'test' will be contacted.")

    st.divider()
    st.caption("Markets refresh every 5 min. Add a new market by sharing a Google Sheet with the service account and placing it in the Outbound Engine Drive folder.")


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
st.markdown("")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_setup, tab_prep, tab_outreach, tab_messaging = st.tabs(["📋  Setup", "🔍  Prep", "📨  Outreach", "✏️  Messaging"])


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
    st.markdown("### Prep")
    st.markdown(
        "Runs all detection and classification steps against the current sheet data. "
        "Run this once per new Snowflake export before triggering any outreach."
    )
    st.markdown("")

    st.markdown('<p class="section-label">Steps</p>', unsafe_allow_html=True)
    st.markdown("""
- **1 of 3 — Split** BS - Not Live into actionable vs churn rows
- **2 of 3 — Classify** actionable rows by tier and assign action
- **3 of 3 — Detect** cross-list overlaps across BS - Live and GMB - Live
    """)

    st.markdown("")
    col1, col2, _ = st.columns([1, 1, 3])
    prep_dry  = col1.button("Dry Run", key="prep_dry")
    prep_live = col2.button("Run Prep", key="prep_live", type="primary")

    if prep_dry or prep_live:
        dry = prep_dry
        log_ph = st.empty()
        cb     = make_log_runner(log_ph)

        with st.status(f"{'[DRY RUN] ' if dry else ''}Running prep for {market_name}...", expanded=True) as status:
            st.write("**1 / 3** — Splitting BS - Not Live...")
            r1 = split_not_live(
                sheet_id=sheet_id, source_sheet=bs_not_live,
                churn_sheet=bs_churn, dry_run=dry, on_progress=cb,
            )
            st.write(f"Split: {r1.get('kept',0)} kept · {r1.get('moved',0)} churn · {r1.get('unknown',0)} unknown")

            st.write("**2 / 3** — Classifying...")
            r2 = classify_not_live(
                sheet_id=sheet_id, sheet_name=bs_not_live,
                dry_run=dry, on_progress=cb,
            )
            st.write(f"Classified: {r2.get('classified',0)} · Already set: {r2.get('skipped_already_set',0)}")

            st.write("**3 / 3** — Cross-list detection...")
            detect_cross_list(
                spreadsheet_id=sheet_id,
                bs_sheet_name=bs_live, gmb_sheet_name=gmb_live,
                churn_sheet_name=bs_churn, not_live_sheet_name=bs_not_live,
                dry_run=dry, on_progress=cb,
            )
            status.update(label="Prep complete!", state="complete")

        if dry:
            st.info("Dry run complete — no changes written. Review the output, then click **Run Prep** to apply.")
        else:
            st.success(f"Prep complete for **{market_name}**. Review the sheet, then go to **Outreach**.")


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
        seed_dry  = seed_col1.button("Preview", key="seed_dry")
        seed_live = seed_col2.button("Seed test rows", key="seed_live", type="primary")

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

    touch_defs = [
        {"label": "Initial",      "note": "First outreach — send first",            "suffix": "t1"},
        {"label": "Follow-up 1",  "note": "Re-run 2+ days after Initial",           "suffix": "t2"},
        {"label": "Follow-up 2",  "note": "Re-run 2+ days after Follow-up 1",       "suffix": "t3"},
    ]

    for phase in phases:
        num = phase["num"]
        key = phase["key"]

        with st.expander(phase["label"]):
            for ti, tdef in enumerate(touch_defs):
                tkey        = f"{key}_{tdef['suffix']}"
                touch_label = tdef["label"]
                touch_note  = tdef["note"]

                lbl_col, dry_col, live_col, _ = st.columns([2.2, 1, 1.4, 2])
                lbl_col.markdown(
                    f"**{touch_label}** &nbsp;"
                    f"<span style='color:#94A3B8; font-size:0.8rem'>{touch_note}</span>",
                    unsafe_allow_html=True,
                )
                dry_btn  = dry_col.button("Dry Run",             key=f"{tkey}_dry")
                live_btn = live_col.button(f"Send {touch_label}", key=f"{tkey}_live", type="primary")

                # ── Confirmation gate ──────────────────────────────────────────
                if live_btn:
                    st.session_state[f"{tkey}_confirm"] = True

                if st.session_state.get(f"{tkey}_confirm"):
                    st.warning(
                        f"Sending **{phase['label']} — {touch_label}** to real contacts in "
                        f"**{market_name}**{'  (test contacts only)' if test_only else ''}. "
                        f"Messages cannot be unsent."
                    )
                    cc1, cc2, _ = st.columns([1, 1, 4])
                    confirmed = cc1.button("Confirm — Send", key=f"{tkey}_confirmed", type="primary")
                    cancelled = cc2.button("Cancel",         key=f"{tkey}_cancel")
                    if cancelled:
                        st.session_state[f"{tkey}_confirm"] = False
                        st.rerun()
                else:
                    confirmed = False

                if dry_btn or confirmed:
                    dry = dry_btn
                    if confirmed:
                        st.session_state[f"{tkey}_confirm"] = False
                    log_ph = st.empty()
                    cb     = make_log_runner(log_ph)

                    base = dict(
                        market=market_name, sheet_id=sheet_id,
                        dry_run=dry, test_only=test_only,
                        require_approval=False, on_progress=cb,
                    )

                    label = f"{'[DRY RUN] ' if dry else ''}{phase['label']} — {touch_label}"
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
                        elif num == 3:
                            st.write("**1 / 1** — Prospect (Casey alias)")
                            run_campaign(segment="prospect", sheet_name=prospects, **base)
                        status.update(label=f"{label} complete!", state="complete")

                    if dry:
                        st.info("Dry run complete — no messages sent. Review the output, then click Send.")
                    else:
                        st.success(f"**{label}** sent for **{market_name}**.")

                if ti < len(touch_defs) - 1:
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
        if st.button(f"Save for {market_name}", type="primary", key="msg_save"):
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
        if _is_customized and st.button("Reset to default", key="msg_reset"):
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
