"""
All communication with the Kustomer API lives here.
Three API keys are used: read-only (lookups), write (conversations/send), create (new customers).
"""

import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from config import (
    KUSTOMER_BASE_URL,
    KUSTOMER_ASSIGNED_TEAM_ID,
    KUSTOMER_EMAIL_FROM_ADDRESS,
    KUSTOMER_EMAIL_FROM_NAME,
    KUSTOMER_SMS_FROM,
    CONVERSATION_NAMES,
)

load_dotenv()


class KustomerClient:
    def __init__(self):
        read_key   = os.getenv("KUSTOMER_API_KEY_READ")
        write_key  = os.getenv("KUSTOMER_API_KEY_WRITE")
        create_key = os.getenv("KUSTOMER_API_KEY_CREATE")

        if not read_key or not write_key:
            raise EnvironmentError(
                "KUSTOMER_API_KEY_READ and KUSTOMER_API_KEY_WRITE must be set in .env"
            )

        self._read_headers = {
            "Authorization": f"Bearer {read_key}",
            "Accept": "application/json",
        }
        self._write_headers = {
            "Authorization": f"Bearer {write_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._create_headers = {
            "Authorization": f"Bearer {create_key or write_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ── Customer lookup & creation ────────────────────────────────────────────

    def get_customer_by_email(self, email: str) -> dict | None:
        """Returns the customer dict from Kustomer if found by email, or None."""
        url = f"{KUSTOMER_BASE_URL}/customers/email={email}"
        response = requests.get(url, headers=self._read_headers, timeout=15)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json().get("data")

    def get_customer_by_phone(self, phone: str) -> dict | None:
        """Returns the customer dict from Kustomer if found by phone, or None."""
        url = f"{KUSTOMER_BASE_URL}/customers/phone={phone}"
        response = requests.get(url, headers=self._read_headers, timeout=15)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json().get("data")

    def create_customer(self, name: str, email: str = None, phone: str = None) -> dict:
        """Creates a new customer in Kustomer. Returns the created customer dict."""
        body = {"name": name}

        if email:
            body["emails"] = [{"email": email, "verified": True, "type": "other"}]
        if phone:
            body["phones"] = [{"phone": phone, "verified": True, "type": "other"}]

        response = requests.post(
            f"{KUSTOMER_BASE_URL}/customers",
            headers=self._create_headers,
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data")

    def get_or_create_customer(self, row: dict) -> str:
        """
        Resolves the Kustomer customer ID for an owner row.
        Priority: existing sheet ID → lookup by email → lookup by phone → create new.
        Returns the Kustomer ID string.
        """
        from config import COL_KUSTOMER_ID, COL_OWNER_EMAIL, COL_OWNER_PHONE, COL_FIRST_NAME, COL_LAST_NAME

        # If the sheet already has a Kustomer ID, use it directly
        existing_id = str(row.get(COL_KUSTOMER_ID) or "").strip()
        if existing_id:
            return existing_id

        email = str(row.get(COL_OWNER_EMAIL) or "").strip()
        phone = str(row.get(COL_OWNER_PHONE) or "").strip()

        customer = None

        if email:
            customer = self.get_customer_by_email(email)

        if not customer and phone:
            customer = self.get_customer_by_phone(phone)

        if customer:
            return customer["id"]

        # Not found anywhere — create a new one
        first = str(row.get(COL_FIRST_NAME) or "").strip()
        last  = str(row.get(COL_LAST_NAME)  or "").strip()
        name  = f"{first} {last}".strip() or "Unknown"

        customer = self.create_customer(name=name, email=email or None, phone=phone or None)
        return customer["id"]

    # ── Conversation & messaging ──────────────────────────────────────────────

    def create_conversation(
        self, customer_id: str, assigned_user_id: str, segment: str, market: str, name: str = None
    ) -> dict:
        """
        Creates a new conversation in Kustomer assigned to the given user and team.
        Returns the conversation dict.
        """
        tag = "supply_acq_" + market.lower().replace(" ", "_")

        body = {
            "name": name or CONVERSATION_NAMES.get(segment, "Boatsetter Outreach"),
            "customer": customer_id,
            "tags": ["outbound_engine", tag],
            "assignedTeams": [KUSTOMER_ASSIGNED_TEAM_ID],
            "assignedUsers": [assigned_user_id],
        }

        response = requests.post(
            f"{KUSTOMER_BASE_URL}/conversations",
            headers=self._write_headers,
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data")

    def send_email(
        self,
        customer_id: str,
        conversation_id: str,
        subject: str,
        body: str,
        to_email: str,
        to_name: str = "",
    ) -> dict:
        """
        Sends an outbound email draft attached to an existing conversation.
        Uses the shared supply team inbox as sender.
        """
        now = datetime.now(timezone.utc).isoformat()

        if subject.startswith("Re: "):
            subject = subject[4:]

        payload = {
            "body": body,
            "channel": "email",
            "conversation": conversation_id,
            "from": {
                "email": KUSTOMER_EMAIL_FROM_ADDRESS,
                "name": KUSTOMER_EMAIL_FROM_NAME,
            },
            "to": {"email": to_email, "name": to_name},
            "sendAt": now,
        }
        if subject:
            payload["subject"] = subject
        payload["payload"] = {
            "draftJs": {
                "blocks": [
                    {
                        "text": body,
                        "key": "block1",
                        "type": "unstyled",
                        "depth": 0,
                        "data": {},
                        "inlineStyleRanges": [],
                        "entityRanges": [],
                    }
                ],
                "entityMap": {},
            }
        }

        response = requests.post(
            f"{KUSTOMER_BASE_URL}/customers/{customer_id}/drafts",
            headers=self._write_headers,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data", {})

    def send_sms(
        self,
        customer_id: str,
        conversation_id: str,
        body: str,
        to_phone: str,
    ) -> dict:
        if to_phone and not to_phone.startswith("+"):
            to_phone = f"+{to_phone}"
        """
        Sends an outbound SMS draft attached to an existing conversation.
        Uses the shared supply team SMS number as sender.
        """
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "body": body,
            "channel": "sms",
            "conversation": conversation_id,
            "from": KUSTOMER_SMS_FROM,
            "to": to_phone,
            "sendAt": now,
            "payload": {
                "draftJs": {
                    "blocks": [
                        {
                            "text": body,
                            "key": "block1",
                            "type": "unstyled",
                            "depth": 0,
                            "data": {},
                            "inlineStyleRanges": [],
                            "entityRanges": [],
                        }
                    ],
                    "entityMap": {},
                }
            },
        }

        response = requests.post(
            f"{KUSTOMER_BASE_URL}/customers/{customer_id}/drafts",
            headers=self._write_headers,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("data", {})
