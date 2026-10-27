"""Cloud compatibility and disaster recovery; synthetic photos, saved prices, no paid calls."""

from dataclasses import replace
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sqlite3
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from PIL import Image
from fastapi.testclient import TestClient
from cardscan.local_pricing.database import Database
from cardscan.local_pricing.cli import seed
from cardscan.local_pricing.api import create_app
from cardscan.app.security import COOKIE, CloudSettings, Security
from cardscan.app.media import MediaStore
from cardscan.app.models import SessionWrite, IntakeWrite, JobWrite
from cardscan.app.principal import REQUEST_OWNER, owner_scope
from cardscan.app.store import AppError, Store
from cardscan.app.vision import Jobs, VisionSettings
from cardscan.ops.backup import create, restore, digest
from cardscan.ops.daily import plan, run
from cardscan.ops.worker import serve, process_one, worker_lock

FIELDS = dict(
    game="pokemon",
    product_id=42382,
    name="Charizard",
    set_name="base set",
    number="4/102",
    language="english",
    edition="unlimited",
    finish="holo",
    condition="LP",
    graded=False,
)
CLOUD = {
    "TALLYBINDER_CLOUD": "true",
    "TALLYBINDER_ACCESS_TOKEN": "t" * 48,
    "TALLYBINDER_SESSION_SECRET": "s" * 48,
    "TALLYBINDER_ALLOWED_ORIGINS": "https://binder.example",
    "TALLYBINDER_JOB_MODE": "external",
}
HEAD = {"X-TallyBinder-Client": "web", "Origin": "https://binder.example"}


def synthetic_photo():
    out = BytesIO()
    Image.new("RGB", (300, 420), "green").save(out, "JPEG")
    return out.getvalue()


class CloudDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "data" / "database.sqlite")
        self.db.migrate()
        seed(self.db)
        self.media = self.root / "data" / "photos"
        self.media_store = MediaStore(self.db, self.media)
        self.photo = self.media_store.upload(synthetic_photo())["id"]
        self.store = Store(self.db)
        self.session = str(uuid4())
        self.store.session(SessionWrite(id=self.session))
        self.intake_id = str(uuid4())
        self.store.put_intake(
            self.intake_id,
            IntakeWrite(
                session_id=self.session,
                expected_revision=0,
                fields=FIELDS,
                front_id=self.photo,
                back_id=self.photo,
            ),
        )
        self.provider = Mock()
        self.provider.research.return_value = {
            "result_text": json.dumps(
                {
                    "candidates": [],
                    "observations": [],
                    "limitations": ["Synthetic fixture."],
                }
            ),
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }
        self.settings = VisionSettings(enabled=True)
        self.jobs = Jobs(self.store, self.media_store, self.settings, self.provider)

    def cloud_client(self):
        env = patch.dict(os.environ, CLOUD)
        env.start()
        self.addCleanup(env.stop)
        app = create_app(
            self.db.path,
            media_root=self.media,
            vision_settings=self.settings,
            vision_provider=self.provider,
        )
        client = TestClient(app, base_url="https://binder.example", headers=HEAD)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client, app

    def login(self, c):
        r = c.post(
            "/auth/login", json={"access_key": CLOUD["TALLYBINDER_ACCESS_TOKEN"]}
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r

    def config(self):
        with self.db.connect(readonly=True) as c:
            rows = c.execute(
                "SELECT provider,category_id,source_set_id FROM sync_state WHERE last_success_at IS NOT NULL"
            ).fetchall()
        scopes = {}
        for p, cat, g in rows:
            scopes.setdefault((int(cat), int(g)), []).append(p)
        return {
            "version": 1,
            "max_requests": 32,
            "sets": [
                {"category": a, "group": b, "providers": v}
                for (a, b), v in scopes.items()
            ],
        }

    def test_cloud_requires_secrets_https_and_external_worker(self):
        for change in (
            {"TALLYBINDER_ACCESS_TOKEN": ""},
            {"TALLYBINDER_SESSION_SECRET": "short"},
            {"TALLYBINDER_ALLOWED_ORIGINS": "http://binder.example"},
            {"TALLYBINDER_JOB_MODE": "background"},
            {"TALLYBINDER_ACCESS_TOKEN": "REPLACE_WITH_" + ("x" * 40)},
        ):
            with self.subTest(change=change), patch.dict(
                os.environ, {**CLOUD, **change}
            ):
                with self.assertRaises(ValueError):
                    CloudSettings.environment()

    def test_all_private_endpoints_include_catalog_and_photos_require_auth(self):
        c, _ = self.cloud_client()
        for url in (
            "/inventory",
            "/intake",
            "/media/" + self.photo,
            "/cards/search",
            "/prices/lookup",
            "/sync/status",
            "/docs",
            "/openapi.json",
        ):
            with self.subTest(url=url):
                self.assertEqual(c.get(url).status_code, 401)
        self.assertEqual(c.get("/health").status_code, 200)
        self.assertEqual(c.get("/app/config").json()["auth_mode"], "session")
        self.assertFalse(c.get("/app/config").json()["authenticated"])

    def test_secure_http_only_session_and_logout_and_no_key_leak(self):
        c, _ = self.cloud_client()
        r = self.login(c)
        cookie = r.headers["set-cookie"]
        for label in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
            self.assertIn(label, cookie)
        self.assertNotIn(CLOUD["TALLYBINDER_ACCESS_TOKEN"], cookie + r.text)
        self.assertEqual(c.get("/inventory").status_code, 200)
        self.assertTrue(c.get("/app/config").json()["authenticated"])
        self.assertIn(
            "no-store", c.get("/media/" + self.photo).headers["cache-control"]
        )
        self.assertEqual(c.post("/auth/logout").status_code, 200)
        self.assertEqual(c.get("/inventory").status_code, 401)

    def test_firebase_bearer_authenticates_config_with_verified_uid(self):
        env = {**CLOUD, "TALLYBINDER_FIREBASE_PROJECT_ID": "tallybinder"}
        with patch.dict(os.environ, env), patch(
            "cardscan.app.security.id_token.verify_firebase_token",
            return_value={"sub": "firebase-user-123", "exp": 9_999_999_999},
        ) as verify:
            app = create_app(
                self.db.path,
                media_root=self.media,
                vision_settings=self.settings,
                vision_provider=self.provider,
            )
            with TestClient(
                app,
                base_url="https://binder.example",
                headers={**HEAD, "Authorization": "Bearer signed-firebase-token"},
            ) as client:
                response = client.get("/app/config")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["auth_mode"], "firebase")
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(verify.call_args.kwargs["audience"], "tallybinder")

    def test_request_scoped_store_owner_isolated_and_restored(self):
        store = Store(self.db, owner=REQUEST_OWNER)
        alice_session = str(uuid4())
        bob_session = str(uuid4())
        with owner_scope("alice"):
            self.assertEqual(store.owner, "alice")
            store.session(SessionWrite(id=alice_session))
        with owner_scope("bob"):
            self.assertEqual(store.owner, "bob")
            store.session(SessionWrite(id=bob_session))
            with self.assertRaises(AppError):
                store.put_intake(
                    str(uuid4()),
                    IntakeWrite(
                        session_id=alice_session,
                        expected_revision=0,
                        fields=FIELDS,
                    ),
                )
        self.assertEqual(store.owner, "local")

    def test_session_expiry_tampering_and_access_key_rotation(self):
        with patch.dict(os.environ, CLOUD):
            settings = CloudSettings.environment()
        now = [100000]
        s = Security(settings, clock=lambda: now[0])
        cookie = s.cookie()
        from starlette.requests import Request

        def request(v):
            return Request(
                {"type": "http", "headers": [(b"cookie", (COOKIE + "=" + v).encode())]}
            )

        self.assertTrue(s.authenticated(request(cookie)))
        self.assertFalse(s.authenticated(request(cookie + "x")))
        now[0] += settings.session_seconds
        self.assertFalse(s.authenticated(request(cookie)))
        now[0] = 100000
        self.assertFalse(
            Security(
                replace(settings, token="new" * 20), clock=lambda: now[0]
            ).authenticated(request(cookie))
        )

    def test_csrf_origin_and_login_rate_limit_cannot_be_spoofed(self):
        c, _ = self.cloud_client()
        self.assertEqual(
            c.post(
                "/auth/login",
                json={"access_key": "x"},
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )
        self.assertEqual(
            c.post("/auth/login", json={"access_key": "é"}).status_code, 401
        )
        for i in range(9):
            self.assertEqual(
                c.post(
                    "/auth/login",
                    json={"access_key": "bad"},
                    headers={"X-Forwarded-For": str(i)},
                ).status_code,
                401,
            )
        self.assertEqual(
            c.post("/auth/login", json={"access_key": "bad"}).status_code, 429
        )

    def test_external_enqueue_returns_queued_without_api_attempt_and_survives_api_restart(
        self,
    ):
        c, app = self.cloud_client()
        self.login(c)
        r = c.post(
            "/intake/" + self.intake_id + "/jobs",
            json={"kind": "identify", "authorize_paid": True, "expected_revision": 1},
        )
        self.assertEqual(r.status_code, 200, r.text)
        id = r.json()["id"]
        self.assertEqual(self.jobs.get(id)["status"], "queued")
        self.provider.research.assert_not_called()
        with TestClient(
            create_app(
                self.db.path,
                media_root=self.media,
                vision_settings=self.settings,
                vision_provider=self.provider,
            )
        ):
            self.assertEqual(self.jobs.get(id)["status"], "queued")
        self.assertTrue(process_one(self.jobs))
        self.assertEqual(self.jobs.get(id)["status"], "completed")
        self.assertFalse(process_one(self.jobs))
        self.assertEqual(self.provider.research.call_count, 1)

    def test_worker_recovery_does_not_repeat_inflight_billable_request(self):
        first, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="identify", authorize_paid=True, expected_revision=1),
        )
        second, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="condition", authorize_paid=True, expected_revision=1),
        )
        with self.db.transaction() as c:
            c.execute(
                "UPDATE vision_jobs SET status='running' WHERE id=?", (first["id"],)
            )
        self.provider.research.return_value = {
            "result_text": json.dumps(
                {
                    "recommended_condition": None,
                    "observations": [],
                    "limitations": [],
                    "additional_photos_helpful": True,
                }
            ),
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }
        serve(
            self.db,
            self.media,
            once=True,
            provider=self.provider,
            settings=self.settings,
        )
        self.assertEqual(self.jobs.get(first["id"])["status"], "interrupted")
        self.assertEqual(self.jobs.get(second["id"])["status"], "completed")
        self.assertEqual(self.provider.research.call_count, 1)
        self.assertIsNone(self.jobs.get(first["id"])["estimated_cost_usd"])

    def test_worker_lock_and_global_ai_disable(self):
        with worker_lock(self.db):
            with self.assertRaises(RuntimeError):
                with worker_lock(self.db):
                    pass
        self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="identify", authorize_paid=True, expected_revision=1),
        )
        self.jobs.settings = replace(self.settings, enabled=False)
        self.assertFalse(process_one(self.jobs))
        self.provider.research.assert_not_called()

    def test_job_model_and_rates_are_frozen_across_configuration_changes(self):
        job, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="identify", authorize_paid=True, expected_revision=1),
        )
        self.jobs.settings = replace(self.settings, input_rate="7.5", output_rate="45")
        self.jobs.run(job["id"])
        r = self.jobs.get(job["id"])
        self.assertEqual(r["estimated_cost_usd"], "0.0012")
        self.jobs.run(job["id"])
        self.assertEqual(self.provider.research.call_count, 1)

    def test_backup_restore_preserves_inventory_prices_photos_and_provenance(self):
        from cardscan.app.models import ListingWrite

        listing = self.store.save_listing(
            ListingWrite(
                intake_id=self.intake_id,
                intake_revision=1,
                listing_price="500",
                quantity=2,
                approved=True,
            )
        )
        with self.db.connect(readonly=True) as c:
            before = [
                tuple(x) for x in c.execute("SELECT * FROM observations ORDER BY id")
            ]
        b = create(self.db, self.media, self.root / "backups")
        destination = self.root / "restored"
        r = restore(b["path"], destination)
        db = Database(destination / "database.sqlite")
        self.assertEqual(r["photos"], 1)
        with db.connect(readonly=True) as c:
            self.assertEqual(
                before,
                [tuple(x) for x in c.execute("SELECT * FROM observations ORDER BY id")],
            )
        self.assertEqual(
            Store(db).listing(listing["id"])["listing"]["listing_price"], "500.00"
        )
        self.assertEqual(
            MediaStore(db, destination / "photos").file(self.photo).read_bytes(),
            self.media_store.file(self.photo).read_bytes(),
        )
        with self.assertRaises(ValueError):
            restore(b["path"], destination)
        self.assertEqual(Path(b["path"]).stat().st_mode & 0o777, 0o600)

    def test_backup_missing_or_changed_photo_fails_without_complete_archive(self):
        path = self.media_store.file(self.photo)
        path.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            create(self.db, self.media, self.root / "bad-backups")
        self.assertFalse(list((self.root / "bad-backups").glob("*.tar")))

    def test_restore_rejects_traversal_and_tampering(self):
        archive = self.root / "evil.tar"
        with tarfile.open(archive, "w") as tar:
            data = b"bad"
            info = tarfile.TarInfo("../evil")
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
        with self.assertRaises(ValueError):
            restore(archive, self.root / "restored")
        self.assertFalse((self.root / "evil").exists())
        b = create(self.db, self.media, self.root / "backups")
        changed = self.root / "changed.tar"
        with tarfile.open(b["path"]) as original, tarfile.open(changed, "w") as target:
            for member in original:
                data = original.extractfile(member).read()
                if member.name.endswith(".jpg"):
                    data = b"x" * len(data)
                target.addfile(member, BytesIO(data))
        with self.assertRaises(ValueError):
            restore(changed, self.root / "restored")
        self.assertFalse((self.root / "restored").exists())

    def test_daily_plan_only_approved_existing_sets_and_request_budget(self):
        cfg = self.config()
        p = plan(self.db, cfg)
        self.assertEqual(p["max_requests"], 32)
        for change in (
            {**cfg, "max_requests": 65},
            {**cfg, "sets": cfg["sets"] * 4},
            {**cfg, "sets": [{"category": 3, "group": 999, "providers": ["tcgcsv"]}]},
            {**cfg, "sets": [{**cfg["sets"][0], "providers": ["invented"]}]},
        ):
            with self.assertRaises(ValueError):
                plan(self.db, change)
        path = self.root / "daily.json"
        path.write_text(json.dumps(cfg))
        with patch("cardscan.ops.daily.synchronize") as sync:
            self.assertFalse(run(self.db, path)["execute"])
            sync.assert_not_called()

    def test_daily_partial_failure_propagates_and_keeps_existing_dataset(self):
        cfg = self.config()
        path = self.root / "daily.json"
        path.write_text(json.dumps(cfg))
        before = digest(self.db.path)
        client = Mock()
        with patch(
            "cardscan.ops.daily.synchronize",
            return_value={"status": "partial_failure", "sets": []},
        ) as sync:
            result = run(self.db, path, execute=True, client=client)
            self.assertEqual(result["status"], "partial_failure")
            self.assertTrue(sync.call_args.kwargs["resume"])
        self.assertEqual(before, digest(self.db.path))

    def test_schema_5_migration_preserves_all_existing_history(self):
        with self.db.transaction() as c:
            before = [
                tuple(x) for x in c.execute("SELECT * FROM observations ORDER BY id")
            ]
            c.execute("DROP INDEX vision_execution_day")
            c.execute("ALTER TABLE vision_jobs DROP COLUMN started_at")
            c.execute("ALTER TABLE vision_jobs DROP COLUMN settings_json")
            c.execute("PRAGMA user_version=5")
        self.db.migrate()
        self.db.migrate()
        with self.db.connect(readonly=True) as c:
            self.assertEqual(
                before,
                [tuple(x) for x in c.execute("SELECT * FROM observations ORDER BY id")],
            )
        self.assertEqual(self.db.health()["schema_version"], 7)

    def test_cross_day_queued_authorizations_cannot_bypass_execution_day_spending_limit(
        self,
    ):
        from cardscan.local_pricing.database import utc

        spent, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="condition", authorize_paid=True, expected_revision=1),
        )
        queued, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="identify", authorize_paid=True, expected_revision=1),
        )
        with self.db.transaction() as c:
            c.execute(
                "UPDATE vision_jobs SET status='failed',estimated_cost_usd='4.99',started_at=? WHERE id=?",
                (utc(), spent["id"]),
            )
            c.execute(
                "UPDATE vision_jobs SET created_at='2020-01-01T00:00:00+00:00' WHERE id=?",
                (queued["id"],),
            )
        self.assertFalse(process_one(self.jobs))
        self.provider.research.assert_not_called()
        self.assertEqual(
            self.jobs.get(queued["id"])["error"], "execution_daily_budget_wait"
        )
        self.jobs.settings = replace(self.settings, daily_limit="10")
        self.assertTrue(process_one(self.jobs))
        self.assertEqual(self.provider.research.call_count, 1)

    def test_restore_quarantines_authorizations_and_blocks_all_ai_until_cost_review(
        self,
    ):
        from cardscan.app.store import AppError

        job, _ = self.jobs.enqueue(
            self.intake_id,
            JobWrite(kind="identify", authorize_paid=True, expected_revision=1),
        )
        backup = create(self.db, self.media, self.root / "backups")
        target = self.root / "restored"
        result = restore(backup["path"], target)
        self.assertEqual(result["quarantined_jobs"], 1)
        db = Database(target / "database.sqlite")
        jobs = Jobs(
            Store(db), MediaStore(db, target / "photos"), self.settings, self.provider
        )
        self.assertEqual(jobs.get(job["id"])["status"], "interrupted")
        self.assertTrue((target / ".ai-restore-hold").exists())
        self.assertFalse(process_one(jobs))
        with self.assertRaises(AppError):
            jobs.enqueue(
                self.intake_id,
                JobWrite(kind="condition", authorize_paid=True, expected_revision=1),
            )
        self.provider.research.assert_not_called()

    def test_restore_clearance_requires_explicit_review_and_does_not_call_ai(self):
        from contextlib import redirect_stdout, redirect_stderr
        from cardscan.ops.__main__ import main

        hold = self.db.path.parent / ".ai-restore-hold"
        hold.write_text("{}")
        argv = ["ops", "--db", str(self.db.path), "acknowledge-restore"]
        with patch("sys.argv", argv), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main()
        self.assertTrue(hold.exists())
        with patch("sys.argv", argv + ["--confirm-cost-review"]), redirect_stdout(
            StringIO()
        ):
            main()
        self.assertFalse(hold.exists())
        self.provider.research.assert_not_called()

    def test_health_is_not_ready_with_an_unmigrated_database(self):
        client, _ = self.cloud_client()
        with self.db.transaction() as c:
            c.execute("PRAGMA user_version=5")
        self.assertEqual(client.get("/health").status_code, 503)
