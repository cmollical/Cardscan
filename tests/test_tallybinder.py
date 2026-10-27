"""TallyBinder application tests. Photos and vision replies are synthetic, no paid calls."""

from copy import deepcopy
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from PIL import Image
from fastapi.testclient import TestClient
from cardscan.local_pricing.database import Database
from cardscan.local_pricing.cli import seed
from cardscan.local_pricing.api import create_app
from cardscan.app.models import Assessment, Identification
from cardscan.app.vision import VisionSettings, OpenAIVisionProvider
from cardscan.app.marketplace import MarketplaceSettings

HEADERS = {"X-TallyBinder-Client": "web"}


class FakeMarketplace:
    settings = MarketplaceSettings(
        url="https://shop.example/api/publish",
        token="x" * 32,
        storefront_url="https://shop.example",
    )

    def available(self):
        return True

    def publish(self, record, front_image):
        assert front_image.startswith(b"\xff\xd8")
        return {
            "provider": self.settings.provider,
            "external_listing_id": record["id"],
            "status": "published",
            "published_at": "2026-10-27T00:00:00+00:00",
            "request_fingerprint": "a" * 64,
        }
FIELDS = dict(
    game="pokemon",
    product_id=42382,
    name="Charizard",
    set_name="base set",
    number="4/102",
    language="english",
    edition="unlimited",
    finish="holo",
    rarity=None,
    condition="LP",
    graded=False,
    notes="",
)


def jpeg(color="green", size=(300, 420)):
    out = BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


def ai_response(result):
    return dict(
        result_text=json.dumps(result),
        usage={"input_tokens": 1000, "output_tokens": 100},
        schema=Assessment,
    )


class TallyBinderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / "app.sqlite")
        self.db.migrate()
        seed(self.db)
        self.provider = Mock()
        self.settings = VisionSettings(enabled=True)
        self.app = create_app(
            self.db.path,
            media_root=Path(self.tmp.name) / "photos",
            vision_settings=self.settings,
            vision_provider=self.provider,
            marketplace=FakeMarketplace(),
        )
        self.client = TestClient(self.app, headers=HEADERS)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.session = str(uuid4())
        self.assertEqual(
            self.client.post("/intake/sessions", json={"id": self.session}).status_code,
            200,
        )
        self.front = self.photo("green")
        self.back = self.photo("blue")

    def photo(self, color):
        r = self.client.post(
            "/media/upload",
            files={"file": ("untrusted-name.jpg", jpeg(color), "image/jpeg")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def intake(self, fields=None, id=None, front=True, back=True):
        id = id or str(uuid4())
        r = self.client.put(
            "/intake/" + id,
            json={
                "session_id": self.session,
                "expected_revision": 0,
                "fields": fields or FIELDS,
                "front_id": self.front if front else None,
                "back_id": self.back if back else None,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def listing(self, intake, **changes):
        return {
            "intake_id": intake["id"],
            "intake_revision": intake["revision"],
            "listing_price": "500.00",
            "quantity": 1,
            "approved": True,
            **changes,
        }

    def test_upload_metadata_stripping_generated_names_and_content_dedup(self):
        self.assertEqual(self.photo("green"), self.front)
        r = self.client.get("/media/" + self.front)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["cache-control"], "no-store")
        im = Image.open(BytesIO(r.content))
        self.assertEqual(im.format, "JPEG")
        self.assertFalse(im.getexif())
        files = list((Path(self.tmp.name) / "photos").glob("*.jpg"))
        self.assertEqual(len(files), 2)
        self.assertTrue(all("untrusted-name" not in p.name for p in files))

    def test_upload_limits_formats_dimensions_and_path_validation(self):
        self.assertEqual(
            self.client.post(
                "/media/upload", files={"file": ("bad.svg", b"<svg/>", "image/svg+xml")}
            ).status_code,
            415,
        )
        self.assertEqual(
            self.client.post(
                "/media/upload",
                files={"file": ("tiny.jpg", jpeg(size=(30, 40)), "image/jpeg")},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/media/upload",
                content=b"x",
                headers={
                    **HEADERS,
                    "Content-Length": "10000000",
                    "Content-Type": "application/octet-stream",
                },
            ).status_code,
            413,
        )
        self.assertEqual(self.client.get("/media/not-a-uuid").status_code, 422)
        self.assertEqual(self.client.get("/media/" + str(uuid4())).status_code, 404)

    def test_exact_price_condition_override_and_stale_price(self):
        d = self.intake()
        r = self.client.post("/intake/" + d["id"] + "/price", params={"revision": 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["market_price"], "527.7")
        self.assertEqual(r.json()["provider_sku_id"], "2999653")
        changed = {**FIELDS, "condition": "MP"}
        updated = self.client.put(
            "/intake/" + d["id"],
            json={
                "session_id": self.session,
                "expected_revision": 1,
                "fields": changed,
                "front_id": self.front,
                "back_id": self.back,
            },
        ).json()
        self.assertIsNone(updated["pricing"])
        self.assertEqual(
            self.client.post(
                "/intake/" + d["id"] + "/price", params={"revision": 2}
            ).json()["market_price"],
            "364.73",
        )
        self.assertEqual(
            self.client.post(
                "/intake/" + d["id"] + "/price", params={"revision": 1}
            ).status_code,
            409,
        )
        with patch(
            "cardscan.local_pricing.lookup.utc",
            return_value="2027-01-01T00:00:00+00:00",
        ):
            result = self.client.post(
                "/intake/" + d["id"] + "/price", params={"revision": 2}
            ).json()
        self.assertEqual(result["status"], "stale_price")

    def test_missing_price_generic_separate_and_manual_selling_price(self):
        fields = {
            **FIELDS,
            "product_id": 509703,
            "name": "Charmander",
            "set_name": "obsidian flames",
            "number": "26/197",
            "condition": "HP",
            "edition": "standard",
            "finish": "non-holo",
        }
        d = self.intake(fields)
        r = self.client.post(
            "/intake/" + d["id"] + "/price", params={"revision": 1}
        ).json()
        self.assertIsNone(r["market_price"])
        self.assertTrue(r["generic_references"])
        result = self.client.post(
            "/inventory", json=self.listing(d, listing_price="0.10")
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()["listing"]["market_reference"])
        self.assertEqual(result.json()["listing"]["listing_price"], "0.10")

    def test_missing_finish_returns_catalog_backed_choices(self):
        with self.db.transaction() as connection:
            row = dict(
                connection.execute(
                    "SELECT * FROM skus WHERE provider_sku_id='2999653'"
                ).fetchone()
            )
            row.pop("id")
            row["provider_sku_id"] = "finish-choice-test"
            row["finish"] = "reverse holo"
            connection.execute(
                "INSERT INTO skus(" + ",".join(row) + ") VALUES(" +
                ",".join("?" for _ in row) + ")",
                tuple(row.values()),
            )
        draft = self.intake({**FIELDS, "finish": None})
        result = self.client.post(
            "/intake/" + draft["id"] + "/price", params={"revision": 1}
        ).json()
        self.assertEqual(result["status"], "variant_selection_required")
        self.assertEqual(result["required_fields"], ["finish"])
        self.assertEqual(result["available_finishes"], ["holo", "reverse holo"])
        self.assertEqual(
            result["warnings"], ["Choose finish to request an exact price."]
        )

    def test_approved_listing_publishes_with_audited_result(self):
        d = self.intake()
        saved = self.client.post("/inventory", json=self.listing(d)).json()
        result = self.client.post(f"/inventory/{saved['id']}/publish")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["status"], "published")
        self.assertEqual(result.json()["external_listing_id"], saved["id"])
        record = self.client.get(f"/inventory/{saved['id']}").json()
        self.assertEqual(record["publication"]["status"], "published")
        self.assertEqual(record["publication"]["request_fingerprint"], "a" * 64)

    def test_wrong_product_number_language_edition_finish_never_substitute(self):
        d = self.intake({**FIELDS, "number": "4/130"})
        self.assertEqual(
            self.client.post(
                "/intake/" + d["id"] + "/price", params={"revision": 1}
            ).status_code,
            422,
        )
        for field, value in [
            ("language", "japanese"),
            ("edition", "first edition"),
            ("finish", "reverse holo"),
        ]:
            d = self.intake({**FIELDS, field: value})
            r = self.client.post(
                "/intake/" + d["id"] + "/price", params={"revision": 1}
            ).json()
            self.assertIsNone(r["market_price"])
            self.assertEqual(r["status"], "not_found")

    def test_optimistic_revision_conflicts_and_duplicate_intake_prevention(self):
        d = self.intake()
        r = self.client.put(
            "/intake/" + d["id"],
            json={"session_id": self.session, "expected_revision": 0, "fields": FIELDS},
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.get("/intake").json()["total"], 1)

    def test_photos_required_and_unowned_photo_rejected(self):
        d = self.intake(back=False)
        self.assertEqual(
            self.client.post("/inventory", json=self.listing(d)).status_code, 422
        )
        self.assertEqual(
            self.client.put(
                "/intake/" + str(uuid4()),
                json={
                    "session_id": self.session,
                    "fields": FIELDS,
                    "front_id": str(uuid4()),
                },
            ).status_code,
            404,
        )

    def test_inventory_listing_template_duplicate_prevention_and_price_persistence(
        self,
    ):
        d = self.intake()
        body = self.listing(d, notes="Seller notes", quantity=2)
        a = self.client.post("/inventory", json=body)
        self.assertEqual(a.status_code, 200, a.text)
        row = a.json()
        b = self.client.post("/inventory", json=body)
        self.assertEqual(b.status_code, 200, b.text)
        self.assertEqual(row["id"], b.json()["id"])
        payload = row["listing"]
        self.assertEqual(payload["listing_price"], "500.00")
        self.assertEqual(payload["market_reference"]["market_price"], "527.7")
        self.assertIn("Charizard", payload["description"])
        self.assertTrue(payload["sku"].startswith("TB-"))
        self.assertEqual(payload["quantity"], 2)
        with Database(self.db.path).connect(readonly=True) as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM inventory_listings").fetchone()[0], 1
            )
        self.assertTrue(self.client.get("/intake/" + d["id"]).json()["saved"])
        self.assertEqual(
            self.client.post(
                "/inventory", json=self.listing(d, listing_price="1")
            ).status_code,
            409,
        )

    def test_inventory_edit_delete_search_filter_and_audit(self):
        d = self.intake()
        row = self.client.post("/inventory", json=self.listing(d)).json()
        edited = self.client.put(
            "/inventory/" + row["id"],
            json=self.listing(
                d,
                expected_revision=1,
                listing_price="480.50",
                item_name="My Charizard",
                quantity=3,
            ),
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["revision"], 2)
        self.assertEqual(
            self.client.get("/inventory?q=My%20Charizard&condition=LP").json()["total"],
            1,
        )
        self.assertEqual(self.client.get("/inventory?condition=NM").json()["total"], 0)
        self.assertEqual(self.client.delete("/inventory/" + row["id"]).status_code, 422)
        self.assertEqual(
            self.client.delete("/inventory/" + row["id"] + "?confirm=true").status_code,
            200,
        )
        self.assertEqual(self.client.get("/inventory").json()["total"], 0)
        self.assertEqual(self.client.get("/inventory/" + row["id"]).status_code, 404)
        with self.db.connect(readonly=True) as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM inventory_versions").fetchone()[0], 2
            )

    def test_csv_formula_protection_and_market_asking_price_separation(self):
        d = self.intake()
        self.client.post(
            "/inventory",
            json=self.listing(
                d, item_name="=BADFORMULA()", listing_price="500.01", notes="@unsafe"
            ),
        )
        csv = self.client.get("/inventory/export.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("'=BADFORMULA()", csv.text)
        self.assertIn("'@unsafe", csv.text)
        self.assertIn("500.01", csv.text)
        self.assertIn("527.7", csv.text)
        self.assertIn("provider_sku_id", csv.text)
        self.assertNotIn(self.tmp.name, csv.text)

    def test_listing_input_validation_and_no_client_supplied_market_price(self):
        d = self.intake()
        for value in ["-1", "NaN", "USD 5", "1.234", "1e3"]:
            self.assertEqual(
                self.client.post(
                    "/inventory", json=self.listing(d, listing_price=value)
                ).status_code,
                422,
            )
        self.assertEqual(
            self.client.post(
                "/inventory", json=self.listing(d, market_price="99999")
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                "/inventory", json=self.listing(d, approved=False)
            ).status_code,
            422,
        )

    def test_batch_durable_queue_and_error_isolation(self):
        one = self.intake()
        two = self.intake({**FIELDS, "condition": "NM"})
        bad = str(uuid4())
        self.assertEqual(self.client.get("/intake?limit=1").json()["total"], 2)
        self.assertEqual(self.client.get("/intake/" + bad).status_code, 404)
        self.assertEqual(
            self.client.get("/intake/" + one["id"]).json()["fields"]["condition"], "LP"
        )
        self.assertEqual(
            self.client.get("/intake/" + two["id"]).json()["fields"]["condition"], "NM"
        )
        self.assertEqual(self.provider.research.call_count, 0)

    def test_security_origin_and_custom_header_and_no_admin_sync(self):
        self.assertEqual(
            self.client.post(
                "/intake/sessions",
                json={"id": str(uuid4())},
                headers={"X-TallyBinder-Client": ""},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/intake/sessions",
                json={"id": str(uuid4())},
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post("/sync").status_code, 404)
        with patch.dict(os.environ, {"TALLYBINDER_ACCESS_TOKEN": "test-only-token"}):
            with TestClient(
                create_app(self.db.path, media_root=Path(self.tmp.name) / "photos")
            ) as c:
                self.assertEqual(c.get("/inventory").status_code, 401)
                self.assertEqual(
                    c.get(
                        "/inventory",
                        headers={"Authorization": "Bearer test-only-token"},
                    ).status_code,
                    200,
                )
                self.assertNotIn("test-only-token", c.get("/app/config").text)

    def test_mock_ai_identification_cross_references_catalog_but_never_approves(self):
        result = {
            "readings": [
                dict(
                    name="Charizard",
                    set_code="base set",
                    collector_number="4/102",
                    language="english",
                    edition="first edition",
                    finish="holo",
                    rarity=None,
                )
            ],
            "observations": [
                "Name Charizard is visible at the top.",
                "Collector number 4/102 and set code base set are visible at the bottom.",
            ],
            "limitations": ["Synthetic test, not real identification."],
            "recommended_condition": "LP",
            "condition_observations": ["Synthetic edge wear."],
            "condition_limitations": ["Synthetic photos."],
            "additional_photos_helpful": False,
        }
        self.provider.research.return_value = ai_response(result)
        d = self.intake()
        job = self.client.post(
            "/intake/" + d["id"] + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        ).json()
        state = self.client.get("/jobs/" + job["id"]).json()
        self.assertEqual(state["status"], "completed")
        self.assertGreater(len(state["result"]["catalog_candidates"]), 0)
        self.assertFalse(state["result"]["catalog_candidates"][0]["approved"])
        self.assertTrue(state["result"]["catalog_candidates"][0]["issues"])
        self.assertEqual(self.client.get("/intake/" + d["id"]).json()["fields"], FIELDS)
        self.assertEqual(self.provider.research.call_count, 1)
        self.assertEqual(len(self.provider.research.call_args.args[1]), 2)
        self.assertEqual(state["result"]["recommended_condition"], "LP")
        self.assertEqual(state["estimated_cost_usd"], "0.0012")
        self.assertEqual(state["intake_estimated_cost_usd"], "0.0012")
        self.assertTrue(state["intake_cost_complete"])

    def test_catalog_guided_set_code_reread_uses_dynamic_database_codes(self):
        with self.db.transaction() as connection:
            game_id = connection.execute(
                "SELECT id FROM games WHERE name='pokemon'"
            ).fetchone()[0]
            set_id = connection.execute(
                "INSERT INTO sets(game_id,name) VALUES(?,?)",
                (game_id, "Synthetic dynamic set"),
            ).lastrowid
            connection.execute(
                "INSERT INTO set_aliases(set_id,alias,provenance) VALUES(?,?,?)",
                (set_id, "asc", "synthetic dynamic provider metadata"),
            )
            connection.execute(
                "INSERT INTO products(game_id,set_id,name,collector_number,tcgplayer_product_id) VALUES(?,?,?,?,?)",
                (game_id, set_id, "Drampa", "176/217", "9999998"),
            )
        self.provider.research.return_value = ai_response(
            {
                "readings": [
                    dict(
                        name="Drampa",
                        set_code="ASCE",
                        collector_number="176/217",
                        language=None,
                        edition=None,
                        finish=None,
                        rarity=None,
                    )
                ],
                "observations": [
                    "The name Drampa is visible near the top.",
                    "The bottom collector line shows 176/217 beside ASCE.",
                ],
                "limitations": [],
                "recommended_condition": "LP",
                "condition_observations": ["Synthetic edge wear."],
                "condition_limitations": [],
                "additional_photos_helpful": False,
            }
        )
        self.provider.resolve_set_codes.return_value = ai_response(
            {
                "resolutions": [
                    {
                        "reading_index": 0,
                        "selected_set_code": "asc",
                        "observation": "The printed set code is ASC; the adjacent EN language mark is separate.",
                    }
                ],
                "limitations": [],
            }
        )
        draft = self.intake()
        job = self.client.post(
            "/intake/" + draft["id"] + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        ).json()
        state = self.client.get("/jobs/" + job["id"]).json()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(state["result"]["catalog_candidates"]), 1)
        candidate = state["result"]["catalog_candidates"][0]
        self.assertEqual(candidate["claim"]["raw_set_code"], "ASCE")
        self.assertEqual(candidate["claim"]["set_code"], "asc")
        self.assertIn("catalog_guided_set_code_reread", candidate["issues"])
        guidance = self.provider.resolve_set_codes.call_args.args[1]
        self.assertEqual(guidance[0]["candidate_set_codes"], ["asc"])
        self.assertEqual(state["estimated_cost_usd"], "0.0024")
        self.assertFalse(candidate["approved"])

    def test_ai_matches_zero_padded_visible_collector_number(self):
        with self.db.transaction() as connection:
            game_id = connection.execute(
                "SELECT id FROM games WHERE name='pokemon'"
            ).fetchone()[0]
            set_id = connection.execute(
                "INSERT INTO sets(game_id,name) VALUES(?,?)",
                (game_id, "ME04: Chaos Rising"),
            ).lastrowid
            connection.execute(
                "INSERT INTO set_aliases(set_id,alias,provenance) VALUES(?,?,?)",
                (set_id, "cri", "synthetic provider metadata"),
            )
            connection.execute(
                "INSERT INTO products(game_id,set_id,name,collector_number,tcgplayer_product_id) VALUES(?,?,?,?,?)",
                (game_id, set_id, "Flaaffy", "28/86", "9999997"),
            )
        self.provider.research.return_value = ai_response(
            {
                "readings": [
                    dict(
                        name="Flaaffy",
                        set_code="CRI EN",
                        collector_number="028/086",
                        language=None,
                        edition=None,
                        finish=None,
                        rarity=None,
                    )
                ],
                "observations": [
                    "Card name Flaaffy is visible at the top.",
                    "Collector line 028/086 and set code CRI EN are visible at the bottom.",
                ],
                "limitations": [],
                "recommended_condition": "LP",
                "condition_observations": ["Synthetic edge wear."],
                "condition_limitations": [],
                "additional_photos_helpful": False,
            }
        )
        draft = self.intake()
        job = self.client.post(
            "/intake/" + draft["id"] + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        ).json()
        state = self.client.get("/jobs/" + job["id"]).json()
        self.assertEqual(state["status"], "completed")
        self.assertEqual(len(state["result"]["catalog_candidates"]), 1)
        candidate = state["result"]["catalog_candidates"][0]
        self.assertEqual(candidate["card"]["name"], "Flaaffy")
        self.assertEqual(candidate["card"]["collector_number"], "28/86")
        self.assertEqual(candidate["claim"]["collector_number"], "028/086")
        self.assertEqual(candidate["claim"]["raw_set_code"], "CRI EN")
        self.assertEqual(candidate["claim"]["set_code"], "CRI")
        self.assertEqual(candidate["claim"]["language"], "english")
        self.assertIn("adjacent_language_mark_separated", candidate["issues"])
        self.assertEqual(state["result"]["unmatched_claims"], [])

    def test_ai_name_only_or_internally_unsupported_claim_is_not_clickable(self):
        result = {
            "readings": [
                dict(
                    name="Drampa",
                    set_code="Obsidian Flames",
                    collector_number="161/197",
                    language="english",
                    edition=None,
                    finish=None,
                    rarity=None,
                )
            ],
            "observations": [
                "Card name visible as Drampa.",
                "The top-right HP value is 130.",
                "Set code appears to be ASC.",
            ],
            "limitations": [],
            "recommended_condition": None,
            "condition_observations": [],
            "condition_limitations": ["Synthetic photo is insufficient."],
            "additional_photos_helpful": True,
        }
        self.provider.research.return_value = ai_response(result)
        draft = self.intake()
        job = self.client.post(
            "/intake/" + draft["id"] + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        ).json()
        state = self.client.get("/jobs/" + job["id"]).json()
        self.assertEqual(state["result"]["catalog_candidates"], [])
        self.assertIn(
            "collector_number_not_supported_by_observation",
            state["result"]["unmatched_claims"][0]["issues"],
        )
        self.assertTrue(any("no selectable printing" in value.lower() for value in state["result"]["limitations"]))

    def test_mock_ai_condition_human_override_stale_results_and_idempotent_jobs(self):
        self.provider.research.return_value = ai_response(
            {
                "recommended_condition": "NM",
                "observations": ["Synthetic corner view"],
                "limitations": ["Synthetic photos."],
                "additional_photos_helpful": True,
            }
        )
        d = self.intake()
        body = {"kind": "condition", "authorize_paid": True, "expected_revision": 1}
        job = self.client.post("/intake/" + d["id"] + "/jobs", json=body).json()
        again = self.client.post("/intake/" + d["id"] + "/jobs", json=body).json()
        self.assertEqual(job["id"], again["id"])
        self.assertEqual(self.provider.research.call_count, 1)
        self.assertEqual(
            self.client.get("/intake/" + d["id"]).json()["fields"]["condition"], "LP"
        )
        self.client.put(
            "/intake/" + d["id"],
            json={
                "session_id": self.session,
                "expected_revision": 1,
                "fields": {**FIELDS, "condition": "MP"},
                "front_id": self.front,
                "back_id": self.back,
            },
        )
        self.assertTrue(
            self.client.get("/jobs/" + job["id"]).json()["stale_for_intake"]
        )

    def test_ai_errors_do_not_leak_secrets_and_unknown_cost_reserve_is_held(self):
        self.provider.research.side_effect = TimeoutError("SECRET_SHOULD_NOT_LEAK")
        d = self.intake()
        r = self.client.post(
            "/intake/" + d["id"] + "/jobs",
            json={"kind": "condition", "authorize_paid": True, "expected_revision": 1},
        ).json()
        job = self.client.get("/jobs/" + r["id"])
        self.assertEqual(job.json()["status"], "failed")
        self.assertIsNone(job.json()["estimated_cost_usd"])
        self.assertFalse(job.json()["intake_cost_complete"])
        self.assertEqual(job.json()["intake_unknown_reserve_usd"], "0.309")
        self.assertNotIn("SECRET_SHOULD_NOT_LEAK", job.text)
        self.assertEqual(self.provider.research.call_count, 1)

    def test_invalid_ai_structured_response_still_accounts_completed_usage(self):
        self.provider.research.return_value = ai_response({"not_the_schema": True})
        d = self.intake()
        job = self.client.post(
            "/intake/" + d["id"] + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        ).json()
        result = self.client.get("/jobs/" + job["id"]).json()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["estimated_cost_usd"], "0.0012")

    def test_ai_disabled_without_payment_authorization_or_configuration(self):
        d = self.intake()
        self.assertEqual(
            self.client.post(
                "/intake/" + d["id"] + "/jobs",
                json={
                    "kind": "identify",
                    "authorize_paid": False,
                    "expected_revision": 1,
                },
            ).status_code,
            422,
        )
        with TestClient(
            create_app(
                self.db.path,
                media_root=Path(self.tmp.name) / "photos",
                vision_settings=VisionSettings(enabled=False),
            )
        ) as c:
            self.assertEqual(
                c.post(
                    "/intake/" + d["id"] + "/jobs",
                    headers=HEADERS,
                    json={
                        "kind": "identify",
                        "authorize_paid": True,
                        "expected_revision": 1,
                    },
                ).status_code,
                503,
            )
        self.assertEqual(self.provider.research.call_count, 0)

    def test_ai_budget_guards_and_interrupted_jobs_not_auto_retried(self):
        d = self.intake()
        self.app.state.jobs.settings = VisionSettings(enabled=True, daily_limit="0.01")
        self.assertEqual(
            self.client.post(
                "/intake/" + d["id"] + "/jobs",
                json={
                    "kind": "identify",
                    "authorize_paid": True,
                    "expected_revision": 1,
                },
            ).status_code,
            429,
        )
        self.app.state.jobs.settings = VisionSettings(enabled=True)
        from cardscan.app.models import JobWrite

        job, _ = self.app.state.jobs.enqueue(
            d["id"], JobWrite(kind="identify", authorize_paid=True, expected_revision=1)
        )
        self.app.state.jobs.recover()
        self.assertEqual(self.app.state.jobs.get(job["id"])["status"], "interrupted")
        self.assertEqual(self.provider.research.call_count, 0)

    def test_official_sdk_request_mock_images_no_tools_and_structured_schema(self):
        client = Mock()
        client.responses.create.return_value = {
            "status": "completed",
            "usage": {"input_tokens": 1000, "output_tokens": 100},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "readings": [],
                                    "observations": [],
                                    "limitations": [],
                                    "recommended_condition": None,
                                    "condition_observations": [],
                                    "condition_limitations": [],
                                    "additional_photos_helpful": True,
                                }
                            ),
                        }
                    ],
                }
            ],
        }
        provider = OpenAIVisionProvider(self.settings, client)
        provider.research("identify", [self.app.state.media.file(self.front)])
        args = client.responses.create.call_args.kwargs
        self.assertEqual(args["tools"], [])
        self.assertFalse(args["store"])
        self.assertTrue(args["text"]["format"]["strict"])
        prompt = args["input"][0]["content"][0]["text"]
        self.assertIn("Never use HP", prompt)
        self.assertIn("exact short set code", prompt)
        self.assertIn("TCGplayer Card Conditioning Standards", prompt)
        self.assertIn("NM permits up to 3 points; LP up to 6", prompt)
        self.assertIn("Surface wear/whitening exposing cardstock", prompt)
        self.assertIn("do not count glare", prompt)
        self.assertIn("Every downgrade below NM", prompt)
        self.assertTrue(
            args["input"][0]["content"][1]["image_url"].startswith(
                "data:image/jpeg;base64,"
            )
        )
        client.responses.create.return_value["output"][0]["content"][0]["text"] = json.dumps(
            {
                "resolutions": [
                    {
                        "reading_index": 0,
                        "selected_set_code": "asc",
                        "observation": "ASC is visible beside the collector number.",
                    }
                ],
                "limitations": [],
            }
        )
        provider.resolve_set_codes(
            [self.app.state.media.file(self.front)],
            [
                {
                    "reading_index": 0,
                    "name": "Drampa",
                    "collector_number": "176/217",
                    "raw_set_code": "ASCE",
                    "candidate_set_codes": ["asc"],
                    "catalog_card_ids": [1],
                }
            ],
        )
        refined = client.responses.create.call_args.kwargs
        self.assertEqual(
            refined["max_output_tokens"], self.settings.refinement_max_output_tokens
        )
        self.assertEqual(refined["tools"], [])
        refinement_prompt = refined["input"][0]["content"][0]["text"]
        self.assertIn('"candidate_set_codes":["asc"]', refinement_prompt)
        self.assertIn("must not be appended", refinement_prompt)

    def test_contradictory_ai_condition_is_withheld_and_preserved_for_review(self):
        self.provider.research.return_value = ai_response(
            {
                "recommended_condition": "NM",
                "observations": ["Condition is unknown."],
                "limitations": [],
                "additional_photos_helpful": True,
            }
        )
        d = self.intake()
        job = self.client.post(
            "/intake/" + d["id"] + "/jobs",
            json={"kind": "condition", "authorize_paid": True, "expected_revision": 1},
        ).json()
        result = self.client.get("/jobs/" + job["id"]).json()["result"]
        self.assertIsNone(result["recommended_condition"])
        self.assertEqual(result["model_proposed_condition"], "NM")
        self.assertEqual(
            self.client.get("/intake/" + d["id"]).json()["fields"]["condition"], "LP"
        )
