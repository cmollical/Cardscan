"""Firestore-backed mutable app state with SQLite-backed pricing reads."""

import csv
from io import StringIO
import os
from uuid import NAMESPACE_URL, uuid5

from cardscan.app.store import AppError, Store, identity_key, missing_variant_result
from cardscan.local_pricing.database import utc
from cardscan.local_pricing.importers import canonical_number


class FirestoreStore(Store):
    """Store intake/inventory state in Firestore, leaving catalog reads in SQLite."""

    def __init__(self, pricing_db, client=None, owner="local", prefix=None):
        super().__init__(pricing_db, owner=owner)
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
        self.client = client
        self.prefix = prefix or os.getenv("TALLYBINDER_FIRESTORE_PREFIX", "tallybinder")

    def _collection(self, name):
        return self.client.collection(f"{self.prefix}_{name}")

    def _owner_documents(self, name):
        from google.cloud.firestore_v1.base_query import FieldFilter

        return list(
            self._collection(name)
            .where(filter=FieldFilter("owner_id", "==", self.owner))
            .stream()
        )

    def _listing_id(self, intake_id):
        return str(uuid5(NAMESPACE_URL, f"tallybinder:{self.owner}:{intake_id}"))

    def session(self, value):
        ref = self._collection("sessions").document(str(value.id))
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            old = ref.get(transaction=txn)
            if old.exists and old.to_dict().get("owner_id") != self.owner:
                raise AppError("session_not_found", 404)
            if not old.exists:
                txn.create(
                    ref,
                    {
                        "id": str(value.id),
                        "owner_id": self.owner,
                        "created_at": utc(),
                        "name": value.name,
                    },
                )

        write(transaction)
        return {"id": str(value.id), "name": value.name}

    def intake(self, id):
        id = str(id)
        snapshot = self._collection("intakes").document(id).get()
        if not snapshot.exists:
            raise AppError("intake_not_found", 404)
        result = snapshot.to_dict()
        if result.get("owner_id") != self.owner or result.get("deleted_at"):
            raise AppError("intake_not_found", 404)
        listing = self._collection("listings").document(self._listing_id(id)).get()
        listing_data = listing.to_dict() if listing.exists else None
        active = bool(listing_data and not listing_data.get("deleted_at"))
        result.update(
            saved=active,
            listing_id=listing_data["id"] if active else None,
            listing_revision=listing_data["revision"] if active else None,
        )
        return result

    def queue(self, limit=100, offset=0):
        rows = [
            x.to_dict()
            for x in self._owner_documents("intakes")
            if not x.to_dict().get("deleted_at")
        ]
        rows.sort(key=lambda x: (x["updated_at"], x["id"]), reverse=True)
        selected = rows[offset : offset + limit]
        return {
            "items": [self.intake(row["id"]) for row in selected],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    def delete_intake(self, id):
        id = str(id)
        ref = self._collection("intakes").document(id)
        listing_ref = self._collection("listings").document(self._listing_id(id))
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            current = ref.get(transaction=txn)
            listing = listing_ref.get(transaction=txn)
            data = current.to_dict() if current.exists else None
            listing_data = listing.to_dict() if listing.exists else None
            if (
                not data
                or data.get("owner_id") != self.owner
                or data.get("deleted_at")
            ):
                raise AppError("intake_not_found", 404)
            if listing_data and not listing_data.get("deleted_at"):
                raise AppError("intake_has_inventory_listing", 409)
            txn.update(ref, {"deleted_at": utc()})

        write(transaction)
        return {"deleted": True}

    def put_intake(self, id, value):
        id = str(id)
        session_ref = self._collection("sessions").document(str(value.session_id))
        media_refs = [
            self._collection("media").document(str(x))
            for x in (value.front_id, value.back_id)
            if x
        ]
        ref = self._collection("intakes").document(id)
        transaction = self.client.transaction()
        fields = value.fields.model_dump()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            session = session_ref.get(transaction=txn)
            media = [x.get(transaction=txn) for x in media_refs]
            old = ref.get(transaction=txn)
            if not session.exists or session.to_dict().get("owner_id") != self.owner:
                raise AppError("session_not_found", 404)
            if any(
                not item.exists or item.to_dict().get("owner_id") != self.owner
                for item in media
            ):
                raise AppError("photo_not_found", 404)
            previous = old.to_dict() if old.exists else None
            if previous and previous.get("deleted_at"):
                raise AppError("intake_not_found", 404)
            if previous and previous.get("owner_id") != self.owner:
                raise AppError("intake_not_found", 404)
            if previous and previous["revision"] != value.expected_revision:
                raise AppError("intake_revision_conflict", 409)
            if not previous and value.expected_revision != 0:
                raise AppError("intake_revision_conflict", 409)
            now = utc()
            front = str(value.front_id) if value.front_id else None
            back = str(value.back_id) if value.back_id else None
            pricing = None
            if (
                previous
                and identity_key(previous["fields"]) == identity_key(fields)
                and previous.get("front_id") == front
                and previous.get("back_id") == back
            ):
                pricing = previous.get("pricing")
            txn.set(
                ref,
                {
                    "id": id,
                    "owner_id": self.owner,
                    "session_id": str(value.session_id),
                    "revision": previous["revision"] + 1 if previous else 1,
                    "fields": fields,
                    "front_id": front,
                    "back_id": back,
                    "pricing": pricing,
                    "created_at": previous["created_at"] if previous else now,
                    "updated_at": now,
                },
            )

        write(transaction)
        return self.intake(id)

    def price(self, id, revision):
        intake = self.intake(id)
        if intake["revision"] != revision:
            raise AppError("intake_revision_conflict", 409)
        fields = intake["fields"]
        if not fields["product_id"] or not fields["condition"]:
            raise AppError("confirm_card_and_condition", 422)
        card = self.lookup.product(fields["product_id"])
        if not card:
            raise AppError("catalog_product_not_found", 404)
        with self.db.connect(readonly=True) as connection:
            set_ok = connection.execute(
                "SELECT 1 FROM set_aliases WHERE set_id=? AND alias=?",
                (card["set_id"], fields["set_name"].casefold()),
            ).fetchone()
        if (
            canonical_number(fields["number"]) != card["collector_number"]
            or not set_ok
            or fields["name"].casefold() != card["name"].casefold()
        ):
            raise AppError("catalog_identity_mismatch", 422)
        if not fields["finish"] or not fields["language"]:
            result = missing_variant_result(card, fields)
        else:
            result = self.lookup.lookup(
                game=fields["game"],
                set_name=fields["set_name"],
                number=fields["number"],
                language=fields["language"],
                edition=fields["edition"],
                finish=fields["finish"],
                condition=fields["condition"],
                graded=False,
                tcgplayer_product_id=fields["product_id"],
            )
        result.update(
            identity_key=identity_key(fields),
            looked_up_at=utc(),
            generic_references=card["generic_references"],
        )
        ref = self._collection("intakes").document(str(id))
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            current = ref.get(transaction=txn)
            data = current.to_dict() if current.exists else None
            if not data or data.get("owner_id") != self.owner:
                raise AppError("intake_not_found", 404)
            if data["revision"] != revision:
                raise AppError("intake_revision_conflict", 409)
            txn.update(ref, {"pricing": result})

        write(transaction)
        return result

    def save_listing(self, value, listing_id=None):
        payload = self._listing_payload(value)
        expected_id = self._listing_id(str(value.intake_id))
        if listing_id and str(listing_id) != expected_id:
            raise AppError("listing_not_found", 404)
        ref = self._collection("listings").document(expected_id)
        intake_ref = self._collection("intakes").document(str(value.intake_id))
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            intake = intake_ref.get(transaction=txn)
            old = ref.get(transaction=txn)
            intake_data = intake.to_dict() if intake.exists else None
            previous = old.to_dict() if old.exists else None
            if (
                not intake_data
                or intake_data.get("owner_id") != self.owner
                or intake_data["revision"] != value.intake_revision
            ):
                raise AppError("intake_revision_conflict", 409)
            if listing_id:
                if not previous or previous.get("deleted_at"):
                    raise AppError("listing_not_found", 404)
                if previous["revision"] != value.expected_revision:
                    raise AppError("listing_revision_conflict", 409)
                revision = previous["revision"] + 1
            elif previous:
                old_payload = {
                    k: v
                    for k, v in previous["listing"].items()
                    if k != "market_reference"
                }
                new_payload = {
                    k: v for k, v in payload.items() if k != "market_reference"
                }
                if not previous.get("deleted_at") and old_payload == new_payload:
                    return False
                raise AppError("intake_already_saved_edit_existing", 409)
            else:
                revision = 1
            now = utc()
            record = {
                "id": expected_id,
                "owner_id": self.owner,
                "intake_id": str(value.intake_id),
                "revision": revision,
                "listing": payload,
                "created_at": previous["created_at"] if previous else now,
                "updated_at": now,
                "deleted_at": None,
            }
            txn.set(ref, record)
            txn.set(
                ref.collection("versions").document(str(revision)),
                {"revision": revision, "listing": payload, "created_at": now},
            )
            return True

        write(transaction)
        return self.listing(expected_id)

    def listing(self, id):
        from google.cloud.firestore_v1.base_query import FieldFilter

        snapshot = self._collection("listings").document(str(id)).get()
        data = snapshot.to_dict() if snapshot.exists else None
        if not data or data.get("owner_id") != self.owner or data.get("deleted_at"):
            raise AppError("listing_not_found", 404)
        publications = list(
            self._collection("publications")
            .where(filter=FieldFilter("owner_id", "==", self.owner))
            .stream()
        )
        events = [x.to_dict() for x in publications if x.to_dict().get("listing_id") == str(id)]
        events.sort(key=lambda x: (x["created_at"], x["id"]), reverse=True)
        data["publication"] = events[0] if events else None
        return data

    def record_publication(self, listing_id, event):
        listing = self._collection("listings").document(str(listing_id)).get()
        data = listing.to_dict() if listing.exists else None
        if not data or data.get("owner_id") != self.owner or data.get("deleted_at"):
            raise AppError("listing_not_found", 404)
        self._collection("publications").document(event["id"]).create(
            {**event, "owner_id": self.owner, "listing_id": str(listing_id)}
        )
        return event

    def inventory(self, q="", condition=None, limit=50, offset=0):
        rows = [x.to_dict() for x in self._owner_documents("listings")]
        query = q.casefold()
        rows = [
            row
            for row in rows
            if not row.get("deleted_at")
            and query in str(row.get("listing", {})).casefold()
            and (not condition or row.get("listing", {}).get("condition") == condition)
        ]
        rows.sort(key=lambda x: (x["updated_at"], x["id"]), reverse=True)
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }

    def delete(self, id):
        ref = self._collection("listings").document(str(id))
        transaction = self.client.transaction()

        from google.cloud import firestore

        @firestore.transactional
        def write(txn):
            old = ref.get(transaction=txn)
            data = old.to_dict() if old.exists else None
            if not data or data.get("owner_id") != self.owner or data.get("deleted_at"):
                raise AppError("listing_not_found", 404)
            txn.update(ref, {"deleted_at": utc(), "updated_at": utc()})

        write(transaction)
        return {
            "deleted": True,
            "retention": "Intake, photos and listing audit remain in private cloud storage.",
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

        def safe(value):
            text = "" if value is None else str(value)
            return (
                "'" + text
                if text.lstrip().startswith(("=", "+", "-", "@"))
                or text.startswith(("\t", "\r", "\n"))
                else text
            )

        rows = [x.to_dict() for x in self._owner_documents("listings")]
        rows = [row for row in rows if not row.get("deleted_at")]
        rows.sort(key=lambda x: x["id"])
        for row in rows:
            listing = row["listing"]
            market = listing.get("market_reference") or {}
            writer.writerow(
                [safe(listing.get(k)) for k in fields]
                + [
                    safe(market.get("market_price")),
                    safe(market.get("source")),
                    safe(market.get("source_updated_at")),
                ]
            )
        return "\ufeff" + stream.getvalue()
