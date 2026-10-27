"""Durable intake and inventory. Market references are computed by the server."""

import csv
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
from uuid import uuid4

from cardscan.local_pricing.database import utc
from cardscan.local_pricing.importers import canonical_number
from cardscan.local_pricing.lookup import Lookup

OWNER = "local"
IDENTITY_KEYS = (
    "game",
    "product_id",
    "name",
    "set_name",
    "number",
    "language",
    "edition",
    "finish",
    "condition",
    "graded",
)


class AppError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def identity_key(fields):
    return sha256(
        json.dumps({k: fields.get(k) for k in IDENTITY_KEYS}, sort_keys=True).encode()
    ).hexdigest()


class Store:
    def __init__(self, db, owner=OWNER):
        self.db, self._owner = db, owner
        self.lookup = Lookup(db)

    @property
    def owner(self):
        from .principal import REQUEST_OWNER, current_owner

        return current_owner() if self._owner == REQUEST_OWNER else self._owner

    def session(self, value):
        with self.db.transaction() as c:
            old = c.execute(
                "SELECT owner_id FROM intake_sessions WHERE id=?", (str(value.id),)
            ).fetchone()
            if old and old[0] != self.owner:
                raise AppError("session_not_found", 404)
            c.execute(
                "INSERT INTO intake_sessions VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (str(value.id), self.owner, utc(), value.name),
            )
        return {"id": str(value.id), "name": value.name}

    def intake(self, id):
        with self.db.connect(readonly=True) as c:
            row = c.execute(
                "SELECT * FROM intake_cards WHERE id=? AND owner_id=?",
                (str(id), self.owner),
            ).fetchone()
            listing = c.execute(
                "SELECT id,revision,deleted_at FROM inventory_listings WHERE intake_id=? AND owner_id=?",
                (str(id), self.owner),
            ).fetchone()
        if not row:
            raise AppError("intake_not_found", 404)
        r = dict(row)
        r["fields"] = json.loads(r.pop("fields_json"))
        r["pricing"] = json.loads(r.pop("pricing_json")) if r["pricing_json"] else None
        r.update(
            saved=bool(listing),
            listing_id=listing["id"] if listing else None,
            listing_revision=listing["revision"] if listing else None,
        )
        return r

    def queue(self, limit=100, offset=0):
        with self.db.connect(readonly=True) as c:
            ids = [
                r[0]
                for r in c.execute(
                    "SELECT id FROM intake_cards WHERE owner_id=? ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                    (self.owner, limit, offset),
                )
            ]
            total = c.execute(
                "SELECT COUNT(*) FROM intake_cards WHERE owner_id=?", (self.owner,)
            ).fetchone()[0]
        return {
            "items": [self.intake(id) for id in ids],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def put_intake(self, id, value):
        id = str(id)
        fields = value.fields.model_dump()
        now = utc()
        with self.db.transaction() as c:
            if not c.execute(
                "SELECT 1 FROM intake_sessions WHERE id=? AND owner_id=?",
                (str(value.session_id), self.owner),
            ).fetchone():
                raise AppError("session_not_found", 404)
            for media in (value.front_id, value.back_id):
                if (
                    media
                    and not c.execute(
                        "SELECT 1 FROM app_media WHERE id=? AND owner_id=?",
                        (str(media), self.owner),
                    ).fetchone()
                ):
                    raise AppError("photo_not_found", 404)
            old = c.execute("SELECT * FROM intake_cards WHERE id=?", (id,)).fetchone()
            if old and old["owner_id"] != self.owner:
                raise AppError("intake_not_found", 404)
            if old and old["revision"] != value.expected_revision:
                raise AppError("intake_revision_conflict", 409)
            if not old and value.expected_revision != 0:
                raise AppError("intake_revision_conflict", 409)
            revision = old["revision"] + 1 if old else 1
            pricing = (
                old["pricing_json"]
                if old
                and identity_key(json.loads(old["fields_json"])) == identity_key(fields)
                and old["front_id"] == (str(value.front_id) if value.front_id else None)
                and old["back_id"] == (str(value.back_id) if value.back_id else None)
                else None
            )
            c.execute(
                """INSERT INTO intake_cards(id,owner_id,session_id,revision,fields_json,front_id,back_id,pricing_json,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,fields_json=excluded.fields_json,
                         front_id=excluded.front_id,back_id=excluded.back_id,pricing_json=excluded.pricing_json,updated_at=excluded.updated_at""",
                (
                    id,
                    self.owner,
                    str(value.session_id),
                    revision,
                    json.dumps(fields),
                    str(value.front_id) if value.front_id else None,
                    str(value.back_id) if value.back_id else None,
                    pricing,
                    old["created_at"] if old else now,
                    now,
                ),
            )
        return self.intake(id)

    def price(self, id, revision):
        intake = self.intake(id)
        if intake["revision"] != revision:
            raise AppError("intake_revision_conflict", 409)
        f = intake["fields"]
        if not f["product_id"] or not f["condition"]:
            raise AppError("confirm_card_and_condition", 422)
        card = self.lookup.product(f["product_id"])
        if not card:
            raise AppError("catalog_product_not_found", 404)
        # A model or UI cannot claim an unrelated product through an ID alone.
        with self.db.connect(readonly=True) as c:
            set_ok = c.execute(
                "SELECT 1 FROM set_aliases WHERE set_id=? AND alias=?",
                (card["set_id"], f["set_name"].casefold()),
            ).fetchone()
        if (
            canonical_number(f["number"]) != card["collector_number"]
            or not set_ok
            or f["name"].casefold() != card["name"].casefold()
        ):
            raise AppError("catalog_identity_mismatch", 422)
        if not f["finish"] or not f["language"]:
            result = {
                "status": "price_unavailable",
                "market_price": None,
                "warnings": ["Confirm language and finish to request an exact price."],
            }
        else:
            result = self.lookup.lookup(
                game=f["game"],
                set_name=f["set_name"],
                number=f["number"],
                language=f["language"],
                edition=f["edition"],
                finish=f["finish"],
                condition=f["condition"],
                graded=False,
                tcgplayer_product_id=f["product_id"],
            )
        result.update(
            identity_key=identity_key(f),
            looked_up_at=utc(),
            generic_references=card["generic_references"],
        )
        with self.db.transaction() as c:
            changed = c.execute(
                "UPDATE intake_cards SET pricing_json=? WHERE id=? AND owner_id=? AND revision=?",
                (json.dumps(result), str(id), self.owner, revision),
            ).rowcount
            if not changed:
                raise AppError("intake_revision_conflict", 409)
        return result

    def _listing_payload(self, value):
        intake = self.intake(value.intake_id)
        if intake["revision"] != value.intake_revision:
            raise AppError("intake_revision_conflict", 409)
        if not intake["front_id"] or not intake["back_id"]:
            raise AppError("front_and_back_required", 422)
        f = intake["fields"]
        if not all(
            f.get(k)
            for k in (
                "product_id",
                "name",
                "set_name",
                "number",
                "language",
                "condition",
            )
        ):
            raise AppError("confirm_card_details", 422)
        # Also validates the exact catalog selection even when the selling price is manual.
        self.price(value.intake_id, value.intake_revision)
        intake = self.intake(value.intake_id)
        snapshot = intake["pricing"]
        market = (
            snapshot
            if snapshot
            and snapshot.get("identity_key") == identity_key(f)
            and snapshot["status"] in ("exact_match", "stale_price")
            else None
        )
        title = f"{f['name']} · {f['number']} · {f['condition']}"
        description = f"{f['name']} from {f['set_name']}, card {f['number']}. {f['language']}; {f['edition'] or 'edition unspecified'}; {f['finish'] or 'finish unspecified'}. Raw card, {f['condition']}. Condition confirmed by the seller; photos show the actual card."
        return {
            **f,
            "item_name": value.item_name.strip() or title,
            "description": value.description.strip() or description,
            "sku": "TB-" + str(value.intake_id).replace("-", "").upper(),
            "provider_sku_id": market.get("provider_sku_id") if market else None,
            "market_reference": market,
            "listing_price": value.listing_price,
            "currency": "USD",
            "quantity": value.quantity,
            "front_image_id": intake["front_id"],
            "back_image_id": intake["back_id"],
            "notes": value.notes,
            "approved": True,
            "pricing_note": "Market reference and seller asking price are different. Shipping and taxes are not added.",
        }

    def save_listing(self, value, listing_id=None):
        payload = self._listing_payload(value)
        now = utc()
        id = str(listing_id or uuid4())
        with self.db.transaction() as c:
            current = c.execute(
                "SELECT revision FROM intake_cards WHERE id=? AND owner_id=?",
                (str(value.intake_id), self.owner),
            ).fetchone()
            if not current or current[0] != value.intake_revision:
                raise AppError("intake_revision_conflict", 409)
            old = c.execute(
                "SELECT * FROM inventory_listings WHERE intake_id=?",
                (str(value.intake_id),),
            ).fetchone()
            if listing_id:
                if (
                    not old
                    or old["id"] != str(listing_id)
                    or old["owner_id"] != self.owner
                    or old["deleted_at"]
                ):
                    raise AppError("listing_not_found", 404)
                if old["revision"] != value.expected_revision:
                    raise AppError("listing_revision_conflict", 409)
                id = old["id"]
                revision = old["revision"] + 1
            elif old:
                if (
                    old["owner_id"] == self.owner
                    and not old["deleted_at"]
                    and {
                        k: v
                        for k, v in json.loads(old["payload_json"]).items()
                        if k != "market_reference"
                    }
                    == {k: v for k, v in payload.items() if k != "market_reference"}
                ):
                    return self.listing(old["id"])
                raise AppError("intake_already_saved_edit_existing", 409)
            else:
                revision = 1
            c.execute(
                """INSERT INTO inventory_listings VALUES(?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET
                         revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (
                    id,
                    self.owner,
                    str(value.intake_id),
                    revision,
                    json.dumps(payload),
                    old["created_at"] if old else now,
                    now,
                ),
            )
            c.execute(
                "INSERT INTO inventory_versions(listing_id,revision,payload_json,created_at) VALUES(?,?,?,?)",
                (id, revision, json.dumps(payload), now),
            )
        return self.listing(id)

    def listing(self, id):
        with self.db.connect(readonly=True) as c:
            r = c.execute(
                "SELECT * FROM inventory_listings WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (str(id), self.owner),
            ).fetchone()
            publication = c.execute(
                "SELECT * FROM marketplace_publications WHERE listing_id=? AND owner_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                (str(id), self.owner),
            ).fetchone()
        if not r:
            raise AppError("listing_not_found", 404)
        out = dict(r)
        out["listing"] = json.loads(out.pop("payload_json"))
        out["publication"] = dict(publication) if publication else None
        if out["publication"] and out["publication"].get("response_json"):
            out["publication"]["response"] = json.loads(out["publication"].pop("response_json"))
        return out

    def record_publication(self, listing_id, event):
        with self.db.transaction() as c:
            owned = c.execute(
                "SELECT 1 FROM inventory_listings WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (str(listing_id), self.owner),
            ).fetchone()
            if not owned:
                raise AppError("listing_not_found", 404)
            c.execute(
                "INSERT INTO marketplace_publications VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event["id"], self.owner, str(listing_id), event["listing_revision"],
                    event["provider"], event.get("external_listing_id"), event["status"],
                    event.get("request_fingerprint"), json.dumps(event.get("response")) if event.get("response") is not None else None,
                    event.get("error"), event["created_at"],
                ),
            )
        return self.listing(listing_id)["publication"]

    def inventory(self, q="", condition=None, limit=50, offset=0):
        where = "owner_id=? AND deleted_at IS NULL AND instr(lower(payload_json),lower(?))>0"
        values = [self.owner, q]
        if condition:
            where += " AND json_extract(payload_json,'$.condition')=?"
            values.append(condition)
        with self.db.connect(readonly=True) as c:
            ids = [
                r[0]
                for r in c.execute(
                    "SELECT id FROM inventory_listings WHERE "
                    + where
                    + " ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                    (*values, limit, offset),
                )
            ]
            total = c.execute(
                "SELECT COUNT(*) FROM inventory_listings WHERE " + where, values
            ).fetchone()[0]
        return {
            "items": [self.listing(id) for id in ids],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def delete(self, id):
        with self.db.transaction() as c:
            if not c.execute(
                "UPDATE inventory_listings SET deleted_at=? WHERE id=? AND owner_id=? AND deleted_at IS NULL",
                (utc(), str(id), self.owner),
            ).rowcount:
                raise AppError("listing_not_found", 404)
        return {
            "deleted": True,
            "retention": "Intake, photos and listing audit remain in the local database.",
        }

    def export_csv(self):
        fields = [
            "item_name",
            "description",
            "sku",
            "game",
            "set_name",
            "number",
            "language",
            "edition",
            "finish",
            "condition",
            "listing_price",
            "currency",
            "quantity",
            "provider_sku_id",
            "front_image_id",
            "back_image_id",
            "notes",
        ]
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            fields + ["market_reference_usd", "market_source", "market_updated_at"]
        )
        with self.db.connect(readonly=True) as c:
            rows = list(
                c.execute(
                    "SELECT payload_json FROM inventory_listings WHERE owner_id=? AND deleted_at IS NULL ORDER BY id",
                    (self.owner,),
                )
            )

        def safe(value):
            text = "" if value is None else str(value)
            return (
                "'" + text
                if text.lstrip().startswith(("=", "+", "-", "@"))
                or text.startswith(("\t", "\r", "\n"))
                else text
            )

        for row in rows:
            r = json.loads(row[0])
            m = r.get("market_reference") or {}
            writer.writerow(
                [safe(r.get(k)) for k in fields]
                + [
                    safe(m.get("market_price")),
                    safe(m.get("source")),
                    safe(m.get("source_updated_at")),
                ]
            )
        return "\ufeff" + stream.getvalue()
