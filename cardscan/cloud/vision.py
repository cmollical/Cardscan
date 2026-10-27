"""Durable Firestore vision jobs dispatched to a private Cloud Run worker."""

from dataclasses import asdict
from decimal import Decimal
import json
import os
import re
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore, tasks_v2
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from cardscan.app.models import Assessment, CatalogGuidedIdentification, Identification
from cardscan.app.principal import owner_scope
from cardscan.app.store import AppError
from cardscan.app.vision import (
    Jobs,
    OpenAIVisionProvider,
    VisionSettings,
    checked_usage,
    combined_usage,
    usage_cost,
)
from cardscan.local_pricing.database import utc


class CloudTasksDispatcher:
    def __init__(self, client=None):
        self.client = client or tasks_v2.CloudTasksClient()
        self.project = os.environ["GOOGLE_CLOUD_PROJECT"]
        self.location = os.environ.get("TALLYBINDER_TASKS_LOCATION", "us-east1")
        self.queue = os.environ.get("TALLYBINDER_VISION_QUEUE", "tallybinder-vision")
        self.worker_url = os.environ["TALLYBINDER_VISION_WORKER_URL"].rstrip("/")
        self.service_account = os.environ["TALLYBINDER_TASKS_SERVICE_ACCOUNT"]

    def __call__(self, job_id):
        parent = self.client.queue_path(self.project, self.location, self.queue)
        task = {
            "name": self.client.task_path(
                self.project, self.location, self.queue, f"vision-{job_id}"
            ),
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.worker_url}/internal/tasks/vision/{quote(str(job_id), safe='')}",
                "headers": {"Content-Type": "application/json"},
                "oidc_token": {
                    "service_account_email": self.service_account,
                    "audience": self.worker_url,
                },
            },
        }
        try:
            self.client.create_task(parent=parent, task=task)
        except AlreadyExists:
            pass


def verify_task_identity(authorization, audience, service_account, *, request=None):
    """Verify a Google-signed OIDC token and its exact task-caller identity."""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise AppError("task_identity_required", 401)
    try:
        claims = id_token.verify_oauth2_token(
            authorization[len(prefix) :],
            request or GoogleRequest(),
            audience=audience,
        )
    except Exception:
        raise AppError("task_identity_invalid", 401) from None
    if claims.get("email") != service_account or claims.get("email_verified") is not True:
        raise AppError("task_identity_invalid", 403)
    return claims


class FirestoreJobs:
    def __init__(self, store, media, settings=None, provider=None, *, dispatcher=None):
        self.store = store
        self.db = store.db
        self.media = media
        self.client = store.client
        self.prefix = store.prefix
        self.settings = settings or VisionSettings.environment()
        self.provider = provider or OpenAIVisionProvider(self.settings)
        self.dispatcher = dispatcher

    def _jobs(self):
        return self.client.collection(f"{self.prefix}_vision_jobs")

    def _budgets(self):
        return self.client.collection(f"{self.prefix}_vision_budgets")

    def pause_reason(self):
        return None

    def available(self):
        return self.settings.enabled and (
            self.dispatcher is not None
            or not isinstance(self.provider, OpenAIVisionProvider)
            or self.provider.client is not None
            or bool(os.getenv("OPENAI_API_KEY"))
        )

    def _public(self, data):
        result = dict(data)
        result.pop("settings", None)
        intake = self.store.intake(result["intake_id"])
        result["stale_for_intake"] = intake["revision"] != result["intake_revision"]
        rows = [
            item.to_dict()
            for item in self._jobs()
            .where(filter=firestore.FieldFilter("owner_id", "==", self.store.owner))
            .stream()
            if item.to_dict().get("intake_id") == result["intake_id"]
        ]
        result["intake_estimated_cost_usd"] = str(
            sum(
                (Decimal(row["estimated_cost_usd"]) for row in rows if row.get("estimated_cost_usd") is not None),
                Decimal(0),
            )
        )
        result["intake_cost_complete"] = all(
            row.get("estimated_cost_usd") is not None for row in rows
        )
        result["intake_unknown_reserve_usd"] = str(
            sum(
                (Decimal(row["reserved_usd"]) for row in rows if row.get("estimated_cost_usd") is None),
                Decimal(0),
            )
        )
        return result

    def get(self, id):
        snapshot = self._jobs().document(str(id)).get()
        data = snapshot.to_dict() if snapshot.exists else None
        if not data or data.get("owner_id") != self.store.owner:
            raise AppError("job_not_found", 404)
        return self._public(data)

    def enqueue(self, id, value):
        if not self.settings.enabled:
            raise AppError("ai_disabled_use_manual_search", 503)
        intake = self.store.intake(id)
        if intake["revision"] != value.expected_revision:
            raise AppError("intake_revision_conflict", 409)
        if not intake["front_id"] or (value.kind == "condition" and not intake["back_id"]):
            raise AppError("required_photos_missing", 422)
        reserve = self.settings.reserve(value.kind)
        if reserve > Decimal(self.settings.per_job_limit):
            raise AppError("vision_per_job_reserve_exceeds_limit", 429)
        day = utc()[:10]
        job_id = str(
            uuid5(
                NAMESPACE_URL,
                f"tallybinder:{self.store.owner}:{id}:{value.kind}:{intake['revision']}",
            )
        )
        ref = self._jobs().document(job_id)
        budget_ref = self._budgets().document(f"{self.store.owner}-{day}")
        transaction = self.client.transaction()

        @firestore.transactional
        def create(txn):
            old = ref.get(transaction=txn)
            budget = budget_ref.get(transaction=txn)
            if old.exists:
                return False
            usage = budget.to_dict() if budget.exists else {"jobs": 0, "reserved_usd": "0"}
            total = Decimal(usage["reserved_usd"])
            if usage["jobs"] >= self.settings.daily_jobs or total + reserve > Decimal(self.settings.daily_limit):
                raise AppError("vision_daily_budget_exhausted", 429)
            now = utc()
            txn.create(
                ref,
                {
                    "id": job_id,
                    "owner_id": self.store.owner,
                    "intake_id": str(id),
                    "intake_revision": intake["revision"],
                    "kind": value.kind,
                    "status": "queued",
                    "model": self.settings.model,
                    "reserved_usd": str(reserve),
                    "estimated_cost_usd": None,
                    "usage": None,
                    "result": None,
                    "error": None,
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "settings": asdict(self.settings),
                },
            )
            txn.set(
                budget_ref,
                {
                    "owner_id": self.store.owner,
                    "day": day,
                    "jobs": usage["jobs"] + 1,
                    "reserved_usd": str(total + reserve),
                    "updated_at": now,
                },
            )
            return True

        new = create(transaction)
        return self.get(job_id), new

    def run(self, id):
        ref = self._jobs().document(str(id))
        transaction = self.client.transaction()

        @firestore.transactional
        def claim(txn):
            snapshot = ref.get(transaction=txn)
            data = snapshot.to_dict() if snapshot.exists else None
            if not data or data.get("status") != "queued":
                return None
            txn.update(ref, {"status": "running", "started_at": utc(), "error": None})
            return data

        job = claim(transaction)
        if not job:
            return False
        usage = None
        cost = None
        try:
            with owner_scope(job["owner_id"]):
                intake = self.store.intake(job["intake_id"])
                if intake["revision"] != job["intake_revision"]:
                    raise AppError("draft_changed_before_job_started", 409)
                paths = [self.media.file(intake["front_id"])]
                if job["kind"] == "condition":
                    paths.append(self.media.file(intake["back_id"]))
                settings = VisionSettings(**job["settings"])
                if settings.model != job["model"] or settings.reserve(job["kind"]) > Decimal(job["reserved_usd"]):
                    raise AppError("job_settings_reservation_mismatch", 409)
                provider = (
                    OpenAIVisionProvider(settings)
                    if isinstance(self.provider, OpenAIVisionProvider)
                    else self.provider
                )
                response = provider.research(job["kind"], paths)
                usages = [
                    checked_usage(
                        response, settings.max_input_tokens, settings.max_output_tokens
                    )
                ]
                usage = combined_usage(usages)
                cost = usage_cost(usage, settings)
                schema = Identification if job["kind"] == "identify" else Assessment
                result = schema.model_validate_json(response["result_text"]).model_dump()
                if job["kind"] == "identify":
                    result = Jobs.cross_reference(self, result)
                    guidance = Jobs.catalog_guidance(self, result)
                    if not result["catalog_candidates"] and guidance:
                        usage = None
                        cost = None
                        refinement = provider.resolve_set_codes(paths, guidance)
                        usages.append(
                            checked_usage(
                                refinement,
                                settings.refinement_max_input_tokens,
                                settings.refinement_max_output_tokens,
                            )
                        )
                        usage = combined_usage(usages)
                        cost = usage_cost(usage, settings)
                        resolution = CatalogGuidedIdentification.model_validate_json(
                            refinement["result_text"]
                        ).model_dump()
                        result = Jobs.apply_catalog_guidance(
                            self, result, guidance, resolution
                        )
                        result = Jobs.cross_reference(self, result)
                elif result["recommended_condition"] and re.search(
                    r"\b(?:condition (?:is |remains )?unknown|cannot (?:determine|assess) (?:the )?condition|insufficient (?:photo|image)(?:s| evidence)? to (?:determine|assess) (?:the )?condition)\b",
                    " ".join(result["observations"] + result["limitations"]),
                    re.I,
                ):
                    result["model_proposed_condition"] = result["recommended_condition"]
                    result["recommended_condition"] = None
                    result["limitations"].append("Contradictory condition proposal withheld; manual inspection required.")
                result["provenance"] = "AI photo interpretation; human confirmation required"
                result["limitations"] += ["Phone photos may miss surface damage, dents and other defects."]
                ref.update(
                    {
                        "status": "completed",
                        "result": result,
                        "usage": usage,
                        "estimated_cost_usd": cost,
                        "finished_at": utc(),
                    }
                )
        except Exception as exc:
            error = exc.code if isinstance(exc, AppError) else "vision_failed_" + type(exc).__name__
            ref.update(
                {
                    "status": "failed",
                    "error": error,
                    "usage": usage,
                    "estimated_cost_usd": cost,
                    "finished_at": utc(),
                }
            )
        return True
