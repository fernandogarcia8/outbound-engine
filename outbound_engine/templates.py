"""
Message templates for each outreach segment.

Signing:
  - reactivate / get_live : real rep name (round-robin assignee)
  - prospect              : "Casey" alias
  - cross_list            : real rep name (round-robin assignee)

Reactivate variants:
  - "recent" (< 90 days since last live) : boat recently went inactive
  - "old"    (>= 90 days, or no date)    : boat hasn't been live in a while
"""

from config import COL_FIRST_NAME


def _greeting(row: dict) -> str:
    first_name = (row.get(COL_FIRST_NAME) or "").strip().title()
    return f"Hi {first_name}," if first_name else "Hi there,"


def _location(row: dict, market: str) -> str:
    """
    Returns the most specific location string available for this row.
    Prospects use the 'Location' column; funnel rows use 'BOAT_CITY'.
    Strips trailing state abbreviation ("Savannah, GA" → "Savannah").
    Falls back to market (DMA name) if neither is populated.
    """
    for col in ("Location", "BOAT_CITY"):
        val = (row.get(col) or "").strip()
        if val:
            # Strip marina/suffix after " — " (e.g. "Savannah, GA — Savannah Marina" → "Savannah, GA")
            if " — " in val:
                val = val.split(" — ")[0].strip()
            # Strip ", ST" state abbreviation (e.g. "Savannah, GA" → "Savannah")
            if ", " in val:
                city, state = val.rsplit(", ", 1)
                if len(state) == 2 and state.isalpha():
                    val = city
            return val
    return market


def _boat_noun(count: int) -> str:
    """Returns the right noun based on how many boats the owner has."""
    if count >= 3:
        return "your fleet"
    if count == 2:
        return "your boats"
    return "your boat"


# ── Touch 1 templates ──────────────────────────────────────────────────────────

def _reactivate_recent(greeting: str, market: str, assignee_name: str = "the team", **_) -> dict:
    sms_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter.\n\n"
        f"I saw your boat is currently inactive. Demand in {market} is strong right now and I'd love "
        f"to get it back live to send bookings your way.\n\n"
        f"Want help getting it back live?"
    )
    email_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter. Noticed your boat recently went inactive and "
        f"wanted to check in.\n\n"
        f"Demand in {market} is picking up right now and we would love to get your boat back "
        f"live so we can send bookings your way.\n\n"
        f"Is there anything holding it back?\n\n"
        f"Best,\n{assignee_name}"
    )
    return {
        "sms_body":      sms_body,
        "email_body":    email_body,
        "email_subject": "Quick check want to get your boat back live?",
    }


def _reactivate_old(greeting: str, market: str, assignee_name: str = "the team", **_) -> dict:
    sms_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter.\n\n"
        f"I noticed your boat hasn't been live in a while. Demand in {market} is strong right now "
        f"and we would love to get it back live to send bookings your way.\n\n"
        f"Do you still have it?"
    )
    email_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter. I noticed your boat has been inactive for a "
        f"while and wanted to see if you'd like to reactivate it.\n\n"
        f"Demand in {market} is strong right now and we would love to get it active again to "
        f"send bookings your way.\n\n"
        f"Do you still have it available?\n\n"
        f"Best,\n{assignee_name}"
    )
    return {
        "sms_body":      sms_body,
        "email_body":    email_body,
        "email_subject": "Is your boat still available?",
    }


def _get_live(greeting: str, market: str, assignee_name: str = "the team", **_) -> dict:
    sms_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter.\n\n"
        f"I came across your listing and saw it never went live. Demand in {market} is strong right "
        f"now and we can help get it live quickly if you still have the boat.\n\n"
        f"Do you still have it?\n\n"
        f"Best, {assignee_name}"
    )
    email_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Boatsetter. I came across your listing and saw it never "
        f"went live.\n\n"
        f"Demand in {market} is strong right now and we would love to get your boat active to "
        f"send bookings your way.\n\n"
        f"Do you still have the boat?\n\n"
        f"Best, {assignee_name}"
    )
    return {
        "sms_body":      sms_body,
        "email_body":    email_body,
        "email_subject": "Is your boat still available?",
    }


def _prospect_variant(row: dict) -> str:
    """Returns 'fishing' or 'charter' based on the operator's Type column."""
    op_type = (row.get("Type") or "").lower()
    if "fishing" in op_type:
        return "fishing"
    return "charter"


# ── Prospect data helpers ──────────────────────────────────────────────────────

_BOAT_TYPE_KEYWORDS = [
    "catamaran", "pontoon", "sailboat", "sail boat", "skiff", "trawler",
    "yacht", "trimaran", "houseboat", "bowrider", "kayak",
]
# Generic descriptions that add no personality — skip them
_BOAT_TYPE_SKIP = ["multi", "multiple", "fleet", "vessel", "center console", "fishing boat"]


def _boat_ref(row: dict) -> str:
    """
    Returns a specific boat type noun (e.g. 'catamaran') if the Boat Type field
    has something meaningful. Returns '' for generic/fleet descriptions.
    """
    raw = (row.get("Boat Type") or "").lower().strip()
    if not raw:
        return ""
    for skip in _BOAT_TYPE_SKIP:
        if skip in raw:
            return ""
    for keyword in _BOAT_TYPE_KEYWORDS:
        if keyword in raw:
            # Normalise "sail boat" → "sailboat"
            return keyword.replace("sail boat", "sailboat")
    return ""


def _activities(row: dict) -> str:
    """
    Formats Activities/Events/Services as a readable list (up to 3 items).
    'Inshore, offshore, gulf stream fishing' → 'inshore, offshore, and gulf stream fishing'
    """
    raw   = (row.get("Activities/Events/Services") or "").strip()
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()][:3]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{parts[0]}, {parts[1]}, and {parts[2]}"


_BOOKING_PLATFORMS = {
    "fareharbor":  "FareHarbor",
    "fare harbor": "FareHarbor",
    "bookeo":      "Bookeo",
    "rezdy":       "Rezdy",
    "checkfront":  "Checkfront",
    "xola":        "Xola",
    "peek":        "Peek Pro",
    "regiondo":    "Regiondo",
}


def _booking_context(row: dict) -> str:
    """
    Returns a single sentence for operators already on a known booking platform,
    positioning Boatsetter as an additive channel. Returns '' otherwise.
    """
    software = (row.get("Booking Software") or "").lower().strip()
    if not software:
        return ""
    for key, display in _BOOKING_PLATFORMS.items():
        if key in software:
            return (
                f"Since you're already on {display}, adding Boatsetter is a "
                f"straightforward new demand channel -- no changes to your existing setup.\n\n"
            )
    return ""


def _in_loc(name: str, location: str) -> str:
    """
    Returns ' in {location}' unless the location is already evident from the
    business name -- avoids 'Tybee Island Watersports in Tybee Island'.
    """
    if not location:
        return ""
    if location.lower() in name.lower():
        return ""
    return f" in {location}"


def _prospect(greeting: str, market: str, row: dict = None, assignee_name: str = "the team", **_) -> dict:
    row          = row or {}
    charter_name = (row.get("Charter Name") or "").strip()
    name         = charter_name or "your operation"
    variant      = _prospect_variant(row)
    activities   = _activities(row)
    boat         = _boat_ref(row)
    loc_ref      = _in_loc(name, market)
    rep          = assignee_name

    # Build the activity observation line
    if activities and boat:
        activity_line = f"saw you run {activities} out of your {boat}{loc_ref}"
    elif activities:
        activity_line = f"saw you run {activities}{loc_ref}"
    elif boat:
        activity_line = f"saw you have a {boat}{loc_ref}"
    else:
        activity_line = f"saw you're operating{loc_ref}"

    if variant == "fishing":
        sms_body = (
            f"{greeting}\n\n"
            f"Came across {name}, {activity_line}. We're working with fishing guides in {market} "
            f"to help bring more bookings their way through Boatsetter + Getmyboat.\n\n"
            f"It's free to list and we can handle the setup for you.\n\n"
            f"Open to it?\n\n"
            f"- {rep}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{rep} from Boatsetter here. I came across {name} and {activity_line}.\n\n"
            f"We're working with fishing guides in {market} to help bring more bookings their way "
            f"by listing them across both Boatsetter and Getmyboat.\n\n"
            f"It's free to list, you stay in control of pricing and availability, and our team "
            f"can handle the setup for you.\n\n"
            f"The goal is simple, bring you incremental trips without adding extra work.\n\n"
            f"Would you be open to getting set up?\n\n"
            f"Best, {rep}"
        )
        subject = "Quick question about your charter"

    else:  # charter + rental merged
        sms_body = (
            f"{greeting}\n\n"
            f"Came across {name}, {activity_line}. We're helping operators in {market} get more "
            f"bookings and fill open days through Boatsetter + Getmyboat.\n\n"
            f"It's free to list and we can handle the setup.\n\n"
            f"Open to it?\n\n"
            f"- {rep}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{rep} from Boatsetter here. I came across {name} and {activity_line}.\n\n"
            f"We're working with operators in {market} to help bring in more bookings and fill "
            f"open availability by listing them across both Boatsetter and Getmyboat.\n\n"
            f"It's free to list, you stay in control of pricing and availability, and our team "
            f"can handle the setup for you.\n\n"
            f"The goal is simple, help you capture more demand without adding extra work.\n\n"
            f"Would you be open to getting set up?\n\n"
            f"Best, {rep}"
        )
        subject = "Quick question about your business"

    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


def _cross_list_bs(
    greeting: str, market: str, assignee_name: str = "the team",
    boat_count: int = 1, **_
) -> dict:
    """BS - Live owners: from Boatsetter, inviting them to also list on Getmyboat."""
    noun = _boat_noun(boat_count)

    sms_body = (
        f"{greeting}\n\n"
        f"{assignee_name} from Boatsetter here.\n\n"
        f"With the Boatsetter + Getmyboat merger, we can now list {noun} on both platforms to "
        f"capture more bookings in {market}.\n"
        f"Calendars will sync across both platforms.\n\n"
        f"We handle setup and calendars sync.\n\n"
        f"Are you open to a quick chat?\n\n"
        f"- {assignee_name}"
    )
    email_body = (
        f"{greeting}\n\n"
        f"I wanted to reach out regarding your account. As you may have heard, Boatsetter "
        f"and Getmyboat have merged, list your boat on both platforms to help capture "
        f"additional bookings in {market}. Demand is strong right now.\n\n"
        f"There's no cost to list, calendars will sync to avoid double bookings, and our "
        f"team can handle most of the setup.\n\n"
        f"You'd just need to create and verify your Getmyboat account and add payout details. "
        f"We'll take care of the rest.\n\n"
        f"Want us to get this set up for you?\n\n"
        f"Best,\n{assignee_name}"
    )
    subject = (
        f"Get {noun} listed on Getmyboat too in {market}"
        if boat_count == 1
        else f"Get listed on Getmyboat too in {market}"
    )
    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


def _cross_list_gmb(greeting: str, market: str, assignee_name: str = "the team", **_) -> dict:
    """GMB - Live owners: from Getmyboat, inviting them to also list on Boatsetter."""
    sms_body = (
        f"{greeting}\n\n"
        f"{assignee_name} from Getmyboat here.\n\n"
        f"With the Getmyboat + Boatsetter merge, we can now get you listed on both platforms "
        f"with synced calendars to help drive more demand in {market} this season.\n\n"
        f"Would you be open to a quick call this week to walk through it?\n\n"
        f"- {assignee_name}"
    )
    email_body = (
        f"{greeting}\n\n"
        f"{assignee_name} here from Getmyboat. I wanted to reach out because with the recent "
        f"Getmyboat + Boatsetter merger, we can now get you listed on both platforms simultaneously.\n\n"
        f"What this means for you:\n"
        f"- Synced calendars across both platforms (no double bookings)\n"
        f"- More exposure across Getmyboat and Boatsetter's combined audience\n"
        f"- More bookings coming your way this season in {market}\n\n"
        f"It's a quick setup and the potential upside is significant.\n\n"
        f"Would you be open to a quick call this week to walk through it?\n\n"
        f"Best,\n{assignee_name}\nGetmyboat | Boatsetter"
    )
    return {
        "sms_body":      sms_body,
        "email_body":    email_body,
        "email_subject": f"Get listed on both Boatsetter & Getmyboat in {market}",
    }


# ── Follow-up templates (Touch 2 + 3) ─────────────────────────────────────────

def _bs_followup(
    greeting: str, market: str, touch: int, assignee_name: str = "the team", **_
) -> dict:
    """Touch 2 and 3 for reactivate and get_live (real rep name)."""
    if touch == 2:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here from Boatsetter.\n\n"
            f"Just following up on my last message. Demand in {market} is strong right now and "
            f"we'd love to get your boat live to send bookings your way.\n\n"
            f"Is it still available?"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here from Boatsetter. Just wanted to follow up on my previous message.\n\n"
            f"Demand is looking strong right now and we'd love to get your boat live to capture bookings.\n\n"
            f"Is it still available?\n\n"
            f"Best,\n{assignee_name}"
        )
        subject = "Following up on your listing - is it still available?"
    else:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here, one last follow-up from Boatsetter.\n\n"
            f"If you're still interested in listing your boat in {market}, "
            f"just reply here and I'll get you set up.\n\n"
            f"Cheers!"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here, wanted to follow up one last time.\n\n"
            f"If you still have your boat and want to get it live in {market}, I'm happy to "
            f"help make it quick and easy.\n\n"
            f"If now's not the right time, no worries at all.\n\n"
            f"Best, {assignee_name}"
        )
        subject = "Last follow-up from Boatsetter"

    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


def _prospect_followup(greeting: str, market: str, touch: int, row: dict = None, assignee_name: str = "the team", **_) -> dict:
    """Touch 2 and 3 for prospect segment."""
    row     = row or {}
    variant = _prospect_variant(row)
    rep     = assignee_name
    subject = (
        "Re: Quick question about your charter"
        if variant == "fishing" else
        "Re: Quick question about your business"
    )

    if touch == 2:
        sms_body = (
            f"{greeting}\n\n"
            f"{rep} again from Boatsetter. Just following up on my last message. We're getting "
            f"operators in {market} live across Boatsetter + Getmyboat to bring in more bookings. "
            f"I think you'd be a perfect fit.\n\n"
            f"Want me to get this started for you?\n\n"
            f"- {rep}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{rep} from Boatsetter here, just following up on my last note.\n\n"
            f"We're currently getting operators in {market} set up across Boatsetter + Getmyboat "
            f"to bring in more bookings. Demand is strong right now.\n\n"
            f"It's quick to set up and we can handle most of it for you.\n\n"
            f"Would you like me to get this started?\n\n"
            f"Best,\n{rep}"
        )
    else:
        sms_body = (
            f"{greeting}\n\n"
            f"If you want help getting more bookings, I can get everything set up across "
            f"Boatsetter + Getmyboat.\n\n"
            f"If not, all good 👍\n\n"
            f"- {rep}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{rep} here, just one last follow-up.\n\n"
            f"If you'd like to try getting more bookings through Boatsetter + Getmyboat, it's "
            f"free to list and easy to get started. I can help set everything up. If not, no "
            f"worries at all.\n\n"
            f"Best, {rep}"
        )

    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


def _cross_list_bs_followup(
    greeting: str, market: str, assignee_name: str, touch: int, **_
) -> dict:
    """Touch 2 and 3 for BS - Live cross_list (Boatsetter → Getmyboat)."""
    if touch == 2:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} from Boatsetter.\n\n"
            f"Just wanted to circle back on getting your boat live on Getmyboat too. "
            f"We're prioritizing active owners to help them with the setup.\n\n"
            f"Want us to get this started for you?\n\n"
            f"- {assignee_name}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"Just wanted to follow up here.\n\n"
            f"We're currently getting a number of owners in {market} set up on Getmyboat to "
            f"capture additional demand, and it's been a quick win so far.\n\n"
            f"Happy to handle the setup for you. You'd just need to create your account and "
            f"add payout details.\n\n"
            f"Would you like us to get this started?\n\n"
            f"Best,\n{assignee_name}"
        )
        subject = f"Following up on the Getmyboat listing in {market}"
    else:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} from Boatsetter.\n\n"
            f"One last follow-up on the Getmyboat opportunity. If timing isn't right, no worries, "
            f"just reply whenever you're ready.\n\n"
            f"- {assignee_name}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"Just one last follow-up from me.\n\n"
            f"If now isn't the right time to get set up on Getmyboat, no worries at all. "
            f"Just reply when you're ready and we'll make it happen.\n\n"
            f"Thank you!\n{assignee_name}"
        )
        subject = "Last follow-up on the Getmyboat listing"

    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


def _cross_list_gmb_followup(
    greeting: str, market: str, assignee_name: str, touch: int, **_
) -> dict:
    """Touch 2 and 3 for GMB - Live cross_list (Getmyboat → Boatsetter)."""
    if touch == 2:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} from Getmyboat here.\n\n"
            f"Just wanted to follow up. We're prioritizing active owners in {market} to get set up "
            f"on Boatsetter to capture additional demand.\n\n"
            f"Would you be open to a quick call to walk through it?\n\n"
            f"- {assignee_name}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here from Getmyboat. Following up on cross-listing your boat "
            f"on Boatsetter.\n\n"
            f"We're finishing getting active owners set up so they can enjoy demand on both "
            f"platforms. Quick setup, synced calendars (no double bookings), more exposure in "
            f"{market}.\n\n"
            f"Are you available for a quick call this week?\n\n"
            f"Best,\n{assignee_name}\nGetmyboat | Boatsetter"
        )
        subject = f"Following up on Boatsetter x Getmyboat in {market}"
    else:
        sms_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here from Getmyboat, last follow-up from me.\n\n"
            f"If you'd like to get set up on Boatsetter to capture more bookings in {market}, "
            f"happy to walk you through it.\n\n"
            f"Just let me know!\n\n"
            f"- {assignee_name}"
        )
        email_body = (
            f"{greeting}\n\n"
            f"{assignee_name} here. This is my last follow-up on the Boatsetter opportunity "
            f"in {market}.\n\n"
            f"If the timing isn't right, no worries at all. But if you'd like to explore it, "
            f"just reply and I'll get everything set up for you.\n\n"
            f"Best,\n{assignee_name}\nGetmyboat | Boatsetter"
        )
        subject = "Last follow-up on Boatsetter x Getmyboat"

    return {"sms_body": sms_body, "email_body": email_body, "email_subject": subject}


# ── Routing ────────────────────────────────────────────────────────────────────

_TOUCH1_BUILDERS = {
    "reactivate": _reactivate_old,   # "recent" variant handled in get_messages()
    "get_live":   _get_live,
    "prospect":   _prospect,
    "cross_list": _cross_list_bs,    # default; "gmb" variant handled in get_messages()
}


def _render_template(text: str, **subs) -> str:
    """Substitutes {placeholder} tokens in a template override string."""
    for k, v in subs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def get_default_templates() -> dict[str, str]:
    """
    Returns all template defaults as format strings with {placeholder} tokens.
    Used by the UI editor to show baseline copy and as fallback when a partial
    override exists (e.g. only SMS is overridden — email falls back to this).

    Keys follow the pattern:  {segment_key}_t{touch}_{channel}
    Channels: sms, email, subject
    """
    d: dict[str, str] = {}

    def _add(prefix: str, msgs: dict) -> None:
        d[f"{prefix}_sms"]     = msgs["sms_body"]
        d[f"{prefix}_email"]   = msgs["email_body"]
        d[f"{prefix}_subject"] = msgs["email_subject"]

    # ── Touch 1 ───────────────────────────────────────────────────────────────
    _add("reactivate_recent_t1", _reactivate_recent(
        greeting="{greeting}", market="{market}", assignee_name="{rep}"))
    _add("reactivate_old_t1", _reactivate_old(
        greeting="{greeting}", market="{market}", assignee_name="{rep}"))
    _add("get_live_t1", _get_live(
        greeting="{greeting}", market="{market}", assignee_name="{rep}"))
    _add("cross_list_bs_t1", _cross_list_bs(
        greeting="{greeting}", market="{market}", assignee_name="{rep}", boat_count=1))
    _add("cross_list_gmb_t1", _cross_list_gmb(
        greeting="{greeting}", market="{market}", assignee_name="{rep}"))

    for variant in ("fishing", "charter"):
        _add(f"prospect_{variant}_t1", _prospect(
            greeting="{greeting}", market="{market}", assignee_name="{rep}",
            row={
                "Type": variant,
                "Charter Name": "{charter_name}",
                "Activities/Events/Services": "{activities}",
                "Boat Type": "",
            },
        ))

    # ── Touch 2 & 3 ───────────────────────────────────────────────────────────
    for touch in (2, 3):
        for seg in ("reactivate_recent", "reactivate_old", "get_live"):
            _add(f"{seg}_t{touch}", _bs_followup(
                greeting="{greeting}", market="{market}", assignee_name="{rep}", touch=touch))

        _add(f"cross_list_bs_t{touch}", _cross_list_bs_followup(
            greeting="{greeting}", market="{market}", assignee_name="{rep}", touch=touch))
        _add(f"cross_list_gmb_t{touch}", _cross_list_gmb_followup(
            greeting="{greeting}", market="{market}", assignee_name="{rep}", touch=touch))

        for variant in ("fishing", "charter"):
            _add(f"prospect_{variant}_t{touch}", _prospect_followup(
                greeting="{greeting}", market="{market}", assignee_name="{rep}", touch=touch,
                row={"Type": variant},
            ))

    return d


def get_messages(
    segment: str,
    row: dict,
    market: str,
    assignee_name: str = "the team",
    touch: int = 1,
    variant: str | None = None,
    market_overrides: dict | None = None,
) -> dict:
    """
    Returns {"sms_body": ..., "email_body": ..., "email_subject": ...}.

    variant:
      reactivate — "recent" (< 90 days inactive) or None/"old"
      cross_list — "bs" (Boatsetter → Getmyboat) or "gmb" (Getmyboat → Boatsetter)

    market_overrides:
      Dict of {template_key: content} loaded from the market's _templates tab.
      Any matching key replaces the corresponding field in the result.
    """
    if segment not in _TOUCH1_BUILDERS:
        raise ValueError(
            f"Unknown segment '{segment}'. Valid: {list(_TOUCH1_BUILDERS.keys())}"
        )

    greeting   = _greeting(row)
    boat_count = int(row.get("_boat_count") or 1)
    location   = _location(row, market)

    # Compute segment key used for override lookup
    if segment == "reactivate":
        _seg_key = f"reactivate_{variant or 'old'}"
    elif segment == "cross_list":
        _seg_key = f"cross_list_{variant or 'bs'}"
    elif segment == "prospect":
        _seg_key = f"prospect_{_prospect_variant(row)}"
    else:
        _seg_key = segment  # "get_live"

    # Run the default template function
    if touch == 1:
        if segment == "reactivate" and variant == "recent":
            result = _reactivate_recent(
                greeting=greeting, market=location, assignee_name=assignee_name,
                boat_count=boat_count, row=row,
            )
        elif segment == "cross_list" and variant == "gmb":
            result = _cross_list_gmb(
                greeting=greeting, market=location, assignee_name=assignee_name,
                boat_count=boat_count, row=row,
            )
        else:
            result = _TOUCH1_BUILDERS[segment](
                greeting=greeting, market=location, assignee_name=assignee_name,
                boat_count=boat_count, row=row,
            )
    elif segment == "cross_list":
        if variant == "gmb":
            result = _cross_list_gmb_followup(
                greeting=greeting, market=location, assignee_name=assignee_name, touch=touch, row=row,
            )
        else:
            result = _cross_list_bs_followup(
                greeting=greeting, market=location, assignee_name=assignee_name, touch=touch, row=row,
            )
    elif segment == "prospect":
        result = _prospect_followup(greeting=greeting, market=location, touch=touch, row=row, assignee_name=assignee_name)
    else:
        result = _bs_followup(
            greeting=greeting, market=location, touch=touch, assignee_name=assignee_name
        )

    # Apply market-specific overrides (field by field — partial overrides are supported)
    if market_overrides:
        charter_name = (row.get("Charter Name") or "").strip()
        subs = {
            "greeting":     greeting,
            "market":       location,
            "rep":          assignee_name,
            "boat_noun":    _boat_noun(boat_count),
            "charter_name": charter_name,
            "activities":   _activities(row),
            "boat_type":    _boat_ref(row),
            "name_ref": (
                f"I came across {charter_name}" if charter_name
                else "I came across your operation"
            ),
            "activity_ref": (
                f", including {_activities(row)}," if _activities(row) else ""
            ),
        }
        key_prefix = f"{_seg_key}_t{touch}"
        for field, result_key in (
            ("sms",     "sms_body"),
            ("email",   "email_body"),
            ("subject", "email_subject"),
        ):
            override = market_overrides.get(f"{key_prefix}_{field}")
            if override:
                result[result_key] = _render_template(override, **subs)

    return result
