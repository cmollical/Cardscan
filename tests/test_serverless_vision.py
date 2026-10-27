"""Serverless vision queue tests use synthetic images and never call OpenAI."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from cardscan.app.models import JobWrite
from cardscan.app.vision import VisionSettings
from cardscan.cloud.vision import CloudTasksDispatcher, FirestoreJobs


class Snapshot:
    def __init__(self, data):
        self.data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self.data) if self.data is not None else None


class Document:
    def __init__(self, collection, id):
        self.collection, self.id = collection, id

    def get(self, transaction=None):
        return Snapshot(self.collection.data.get(self.id))

    def update(self, value):
        self.collection.data[self.id].update(value)


class Query:
    def __init__(self, collection):
        self.collection = collection

    def stream(self):
        return [Snapshot(value) for value in self.collection.data.values()]


class Collection:
    def __init__(self):
        self.data = {}

    def document(self, id):
        return Document(self, id)

    def where(self, **kwargs):
        return Query(self)


class Transaction:
    def create(self, ref, value):
        if ref.id in ref.collection.data:
            raise RuntimeError("already exists")
        ref.collection.data[ref.id] = dict(value)

    def set(self, ref, value):
        ref.collection.data[ref.id] = dict(value)

    def update(self, ref, value):
        ref.collection.data[ref.id].update(value)


class Client:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, Collection())

    def transaction(self):
        return Transaction()


class Store:
    owner = "local"
    prefix = "test"

    def __init__(self, intake):
        self.client = Client()
        self.value = intake
        self.lookup = Mock()
        self.lookup.search.return_value = {"items": []}

    def intake(self, id):
        return dict(self.value)


class Media:
    def __init__(self, path):
        self.path = path

    def file(self, id):
        return self.path


class ServerlessVisionTests(unittest.TestCase):
    def test_firestore_job_is_idempotent_budgeted_and_runs_once(self):
        with TemporaryDirectory() as tmp:
            photo = Path(tmp) / "photo.jpg"
            photo.write_bytes(b"synthetic")
            intake_id = str(uuid4())
            store = Store(
                {
                    "id": intake_id,
                    "revision": 1,
                    "front_id": str(uuid4()),
                    "back_id": str(uuid4()),
                }
            )
            provider = Mock()
            provider.research.return_value = {
                "result_text": json.dumps(
                    {"candidates": [], "observations": [], "limitations": []}
                ),
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            }
            jobs = FirestoreJobs(
                store,
                Media(photo),
                VisionSettings(enabled=True),
                provider,
                dispatcher=Mock(),
            )
            value = JobWrite(kind="identify", authorize_paid=True, expected_revision=1)
            with patch("cardscan.cloud.vision.firestore.transactional", lambda fn: fn):
                first, new = jobs.enqueue(intake_id, value)
                duplicate, duplicate_new = jobs.enqueue(intake_id, value)
                self.assertTrue(jobs.run(first["id"]))
                self.assertFalse(jobs.run(first["id"]))
            self.assertTrue(new)
            self.assertFalse(duplicate_new)
            self.assertEqual(first["id"], duplicate["id"])
            result = jobs.get(first["id"])
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["estimated_cost_usd"], "0.0012")
            self.assertEqual(provider.research.call_count, 1)

    def test_dispatcher_uses_private_oidc_target_and_deterministic_task(self):
        client = Mock()
        client.queue_path.return_value = "queue"
        client.task_path.return_value = "task"
        env = {
            "GOOGLE_CLOUD_PROJECT": "project",
            "TALLYBINDER_VISION_WORKER_URL": "https://worker.example/",
            "TALLYBINDER_TASKS_SERVICE_ACCOUNT": "tasks@example.iam.gserviceaccount.com",
        }
        with patch.dict(os.environ, env):
            CloudTasksDispatcher(client)("job-id")
        call = client.create_task.call_args.kwargs
        request = call["task"]["http_request"]
        self.assertEqual(call["parent"], "queue")
        self.assertEqual(request["url"], "https://worker.example/tasks/vision/job-id")
        self.assertEqual(request["oidc_token"]["audience"], "https://worker.example")
        self.assertEqual(
            request["oidc_token"]["service_account_email"],
            "tasks@example.iam.gserviceaccount.com",
        )


if __name__ == "__main__":
    unittest.main()
