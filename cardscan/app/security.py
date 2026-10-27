"""Firebase identity, legacy owner sessions and bounded request rates."""

from collections import OrderedDict, deque
from dataclasses import dataclass
from hashlib import sha256
import hmac
import os
import secrets
import threading
import time
from urllib.parse import urlsplit
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = "__Host-tallybinder"


@dataclass(frozen=True)
class CloudSettings:
    production: bool
    token: str
    secret: str
    origins: tuple[str, ...]
    firebase_project_id: str = ""
    session_seconds: int = 43200

    @classmethod
    def environment(cls):
        production = os.getenv("TALLYBINDER_CLOUD", "false").lower() == "true"
        token = os.getenv("TALLYBINDER_ACCESS_TOKEN", "")
        secret = os.getenv("TALLYBINDER_SESSION_SECRET", "")
        firebase_project_id = os.getenv("TALLYBINDER_FIREBASE_PROJECT_ID", "").strip()
        origins = tuple(
            x.strip()
            for x in os.getenv(
                "TALLYBINDER_ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000,https://localhost:3000,https://127.0.0.1:3000",
            ).split(",")
            if x.strip()
        )
        mode = os.getenv("TALLYBINDER_JOB_MODE", "background")
        if mode not in ("background", "external"):
            raise ValueError("Invalid job mode")
        if production:
            if (
                min(len(token), len(secret)) < 32
                or token == secret
                or any(x.startswith(("REPLACE_", "YOUR_")) for x in (token, secret))
            ):
                raise ValueError(
                    "Cloud requires distinct strong access and session secrets"
                )
            if not origins or any(
                urlsplit(x).scheme != "https"
                or not urlsplit(x).hostname
                or "*" in x
                or urlsplit(x).path not in ("", "/")
                or x.endswith("/")
                for x in origins
            ):
                raise ValueError(
                    "Cloud requires exact HTTPS origins without trailing slash"
                )
            if mode != "external":
                raise ValueError("Cloud requires the durable external vision worker")
        return cls(production, token, secret, origins, firebase_project_id)


class Security:
    def __init__(self, settings, clock=time.time):
        self.settings, self.clock = settings, clock
        self.buckets = OrderedDict()
        self.firebase_cache = OrderedDict()
        self.lock = threading.Lock()

    def _firebase_principal(self, token):
        digest = sha256(token.encode()).hexdigest()
        now = self.clock()
        with self.lock:
            cached = self.firebase_cache.get(digest)
            if cached and cached[0] > now:
                self.firebase_cache.move_to_end(digest)
                return cached[1]
        claims = id_token.verify_firebase_token(
            token,
            GoogleRequest(),
            audience=self.settings.firebase_project_id,
        )
        uid = claims.get("sub")
        expires = claims.get("exp")
        if not isinstance(uid, str) or not uid or not isinstance(expires, (int, float)):
            raise ValueError("Invalid Firebase identity")
        with self.lock:
            self.firebase_cache[digest] = (min(float(expires), now + 300), uid)
            self.firebase_cache.move_to_end(digest)
            while len(self.firebase_cache) > 256:
                self.firebase_cache.popitem(last=False)
        return uid

    def principal(self, request, *, allow_bearer=True):
        token = self.settings.token
        authorization = request.headers.get("authorization", "")
        bearer = authorization[7:] if authorization.startswith("Bearer ") else ""
        if allow_bearer and bearer:
            if token and hmac.compare_digest(bearer.encode(), token.encode()):
                return "local"
            if self.settings.firebase_project_id:
                try:
                    return self._firebase_principal(bearer)
                except Exception:
                    return None
        if not token and not self.settings.firebase_project_id:
            return "local" if not self.settings.production else None
        if not self.settings.production:
            return None
        value = request.cookies.get(COOKIE, "")
        try:
            issued, nonce, signature = value.split(".")
            age = self.clock() - int(issued)
            expected = self.sign(issued + "." + nonce)
            valid = (
                0 <= age < self.settings.session_seconds
                and len(nonce) == 32
                and hmac.compare_digest(expected, signature)
            )
            return "local" if valid else None
        except (ValueError, OverflowError):
            return None

    def authenticated(self, request, *, allow_bearer=True):
        return self.principal(request, allow_bearer=allow_bearer) is not None

    def sign(self, value):
        key = (
            self.settings.secret
            + "\0"
            + sha256(self.settings.token.encode()).hexdigest()
        ).encode()
        return hmac.new(key, value.encode(), sha256).hexdigest()

    def cookie(self):
        value = str(int(self.clock())) + "." + secrets.token_hex(16)
        return value + "." + self.sign(value)

    def allowed(self, key, limit):
        now = self.clock()
        with self.lock:
            bucket = self.buckets.setdefault(key, deque())
            self.buckets.move_to_end(key)
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            while len(self.buckets) > 256:
                self.buckets.popitem(last=False)
        return True


class CloudGuard(BaseHTTPMiddleware):
    def __init__(self, app, security):
        super().__init__(app)
        self.security = security

    async def dispatch(self, request, call_next):
        s = self.security
        if not s.settings.production:
            return await call_next(request)
        path = request.url.path
        public = path in ("/health", "/app/config", "/auth/login")
        internal = path.startswith("/internal/tasks/vision/")
        principal = None if internal else s.principal(request)
        if not public and not internal and principal is None:
            return JSONResponse(
                {"detail": {"code": "sign_in_required"}},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        if not internal and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-tallybinder-client") != "web":
                return JSONResponse(
                    {"detail": {"code": "client_header_required"}}, status_code=403
                )
            origin = request.headers.get("origin")
            if origin and origin not in s.settings.origins:
                return JSONResponse(
                    {"detail": {"code": "origin_not_allowed"}}, status_code=403
                )
        # Identity-scoped limits cannot be evaded with a spoofed forwarded IP.
        kind = (
            "login"
            if path == "/auth/login"
            else (
                "internal"
                if internal
                else "upload"
                if path == "/media/upload"
                else "public" if public else "private"
            )
        )
        limit = {
            "login": 10,
            "upload": 120,
            "internal": 120,
            "public": 240,
            "private": 1800,
        }[kind]
        rate_key = kind if kind in ("login", "internal", "public") else f"{kind}:{principal}"
        if not s.allowed(rate_key, limit):
            return JSONResponse(
                {"detail": {"code": "request_rate_limited"}},
                status_code=429,
                headers={"Retry-After": "60", "Cache-Control": "no-store"},
            )
        if principal is not None:
            request.state.owner_id = principal
        from .principal import owner_scope

        with owner_scope(principal or "local"):
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie, Authorization, Origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_key: str = Field(min_length=1, max_length=256)


def configure(app):
    settings = CloudSettings.environment()
    security = Security(settings)
    app.state.security = security
    app.add_middleware(CloudGuard, security=security)

    @app.post("/auth/login")
    def login(value: Login):
        if not settings.production:
            return JSONResponse(
                {"detail": {"code": "cloud_sessions_not_enabled"}}, status_code=503
            )
        if not hmac.compare_digest(value.access_key.encode(), settings.token.encode()):
            return JSONResponse(
                {"detail": {"code": "invalid_access_key"}}, status_code=401
            )
        response = JSONResponse({"authenticated": True})
        response.set_cookie(
            COOKIE,
            security.cookie(),
            max_age=settings.session_seconds,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.post("/auth/logout")
    def logout():
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(
            COOKIE, path="/", secure=True, httponly=True, samesite="strict"
        )
        return response
