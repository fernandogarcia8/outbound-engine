"""
Assigns team members to outreach conversations in fair round-robin order.
The current position is saved in round_robin_state.json so the counter
survives between runs — if Tyler was last, next run starts with Fernando.
"""

import json
import os

from config import TEAM_MEMBERS

STATE_FILE = os.path.join(os.path.dirname(__file__), "round_robin_state.json")


def _load_index() -> int:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return int(json.load(f).get("index", 0))
        except (json.JSONDecodeError, ValueError):
            pass
    return 0


def _save_index(index: int) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump({"index": index}, f)


def get_next_assignee() -> dict:
    """
    Returns the next team member dict: {"name": ..., "kustomer_id": ...}
    and advances the counter by one for the next call.
    """
    index = _load_index()
    assignee = TEAM_MEMBERS[index % len(TEAM_MEMBERS)]
    _save_index(index + 1)
    return assignee


def reset_counter() -> None:
    """Resets the round-robin counter back to the first team member."""
    _save_index(0)


def peek_next_assignee() -> dict:
    """Returns who would be assigned next without advancing the counter."""
    index = _load_index()
    return TEAM_MEMBERS[index % len(TEAM_MEMBERS)]
