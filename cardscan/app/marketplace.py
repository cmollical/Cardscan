"""Outbound marketplace publishing with an explicit, auditable boundary."""

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class MarketplaceSettings:
    url: str = ""
    token: str = ""
    access_token: str = ""
    storefront_url: str = ""
    provider: str = "tallybinder-demo-shop"

    @classmethod
    def environment(cls):
        value = cls(
            url=os.getenv("TALLYBINDER_MARKETPLACE_URL", "").strip(),
            token=os.getenv("TALLYBINDER_MARKETPLACE_TOKEN", "").strip(),
            access_token=os.getenv("TALLYBINDER_MARKETPLACE_ACCESS_TOKEN", "").strip(),
            storefront_url=os.getenv("TALLYBINDER_STOREFRONT_URL", "").strip(),
        )
        if value.url:
            parsed = urlsplit(value.url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Marketplace URL must be HTTPS without embedded credentials")
            if len(value.token) < 32:
                raise ValueError("Marketplace publish token must be at least 32 characters")
        return value


class MarketplacePublisher:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or MarketplaceSettings.environment()
        self.transport = transport

    def available(self):
        return bool(self.settings.url and self.settings.token)

    @staticmethod
    def payload(record):
        listing = record["listing"]
        return {
            "id": record["id"],
            "sku": listing["sku"],
            "title": listing["item_name"],
            "description": listing["description"],
            "price_cents": int(Decimal(listing["listing_price"]) * 100),
            "quantity": listing["quantity"],
            "condition": listing["condition"],
            "set_name": listing["set_name"],
            "collector_number": listing["number"],
            "language": listing["language"],
            "finish": listing.get("finish"),
            "rarity": listing.get("rarity"),
            "source_revision": record["revision"],
            "published_at": record["updated_at"],
        }

    def publish(self, record, front_image):
        payload = self.payload(record)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = {"Authorization": "Bearer " + self.settings.token}
        if self.settings.access_token:
            headers["OAI-Sites-Authorization"] = "Bearer " + self.settings.access_token
        with httpx.Client(transport=self.transport, timeout=30, follow_redirects=False) as client:
            response = client.post(
                self.settings.url,
                headers=headers,
                files={
                    "listing": (None, body, "application/json"),
                    "front_image": ("front.jpg", front_image, "image/jpeg"),
                },
            )
        response.raise_for_status()
        result = response.json()
        if result.get("external_listing_id") != record["id"] or result.get("status") != "published":
            raise ValueError("Unexpected marketplace response")
        result["request_fingerprint"] = sha256(body.encode() + front_image).hexdigest()
        return result
