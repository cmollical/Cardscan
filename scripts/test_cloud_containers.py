"""Local Docker contract test: synthetic photos, saved prices, AI off, no public deployment."""

import argparse
from hashlib import sha256
from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import uuid4
import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cardscan.local_pricing.database import Database
from cardscan.local_pricing.cli import seed

DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]


def docker(*args):
    return subprocess.check_output(
        DOCKER + list(args), text=True, stderr=subprocess.STDOUT
    ).strip()


def check(value, message):
    if not value:
        raise AssertionError(message)


def photo():
    out = BytesIO()
    Image.new("RGB", (300, 420), "green").save(out, "JPEG")
    return out.getvalue()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-image", default="tallybinder-api:cloud-test")
    p.add_argument("--frontend-image", default="tallybinder-frontend:cloud-test")
    args = p.parse_args()
    suffix = uuid4().hex[:10]
    network = "tb-test-" + suffix
    api = "tb-api-" + suffix
    frontend = "tb-front-" + suffix
    worker = "tb-worker-" + suffix
    started = []
    key = "synthetic-test-key-" + suffix + "x" * 40
    secret = "synthetic-session-key-" + suffix + "s" * 40
    with TemporaryDirectory(prefix="tb-container-test-") as tmp:
        root = Path(tmp)
        data = root / "data"
        data.mkdir()
        db = Database(data / "database.sqlite")
        db.migrate()
        seed(db)
        with db.connect(readonly=True) as c:
            history = c.execute("SELECT count(*) FROM observations").fetchone()[0]
        docker("network", "create", network)
        try:
            docker(
                "run",
                "--rm",
                "--user",
                "0:0",
                "-v",
                str(data) + ":/data",
                args.api_image,
                "python",
                "-c",
                'import os;[(os.chown(os.path.join(p,n),10001,10001)) for p,ds,fs in os.walk("/data") for n in ds+fs];os.chown("/data",10001,10001)',
            )

            def start_api():
                docker(
                    "run",
                    "-d",
                    "--name",
                    api,
                    "--network",
                    network,
                    "--network-alias",
                    "api",
                    "-p",
                    "127.0.0.1::8000",
                    "--read-only",
                    "--tmpfs",
                    "/tmp:size=64m",
                    "-v",
                    str(data) + ":/data",
                    "-e",
                    "TALLYBINDER_CLOUD=true",
                    "-e",
                    "TALLYBINDER_DB=/data/database.sqlite",
                    "-e",
                    "TALLYBINDER_MEDIA_DIR=/data/photos",
                    "-e",
                    "TALLYBINDER_JOB_MODE=external",
                    "-e",
                    "TALLYBINDER_AI_ENABLED=false",
                    "-e",
                    "TALLYBINDER_ALLOWED_ORIGINS=https://binder.example",
                    "-e",
                    "TALLYBINDER_ACCESS_TOKEN=" + key,
                    "-e",
                    "TALLYBINDER_SESSION_SECRET=" + secret,
                    args.api_image,
                )
                if api not in started:
                    started.append(api)

            start_api()
            docker(
                "run",
                "-d",
                "--name",
                worker,
                "--network",
                network,
                "--read-only",
                "--tmpfs",
                "/tmp:size=32m",
                "-v",
                str(data) + ":/data",
                "-e",
                "TALLYBINDER_DB=/data/database.sqlite",
                "-e",
                "TALLYBINDER_MEDIA_DIR=/data/photos",
                "-e",
                "TALLYBINDER_AI_ENABLED=false",
                args.api_image,
                "python",
                "-m",
                "cardscan.ops.worker",
            )
            started.append(worker)
            docker(
                "run",
                "-d",
                "--name",
                frontend,
                "--network",
                network,
                "-p",
                "127.0.0.1::3000",
                "--read-only",
                "--tmpfs",
                "/tmp:size=32m",
                args.frontend_image,
            )
            started.append(frontend)
            port = json.loads(docker("inspect", frontend))[0]["NetworkSettings"][
                "Ports"
            ]["3000/tcp"][0]["HostPort"]
            base = "http://127.0.0.1:" + port + "/api/backend"
            with httpx.Client(timeout=20) as client:

                def wait():
                    for _ in range(60):
                        try:
                            if client.get(base + "/health").status_code == 200:
                                return
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.5)
                    diagnostic = subprocess.run(
                        DOCKER
                        + [
                            "exec",
                            api,
                            "python",
                            "-c",
                            "from cardscan.local_pricing.database import Database;print(Database('/data/database.sqlite').health())",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    print(diagnostic.stdout + diagnostic.stderr, file=sys.stderr)
                    raise AssertionError("Local container health failed")

                wait()

                def worker_ready():
                    for _ in range(20):
                        ready = subprocess.run(
                            DOCKER
                            + [
                                "exec",
                                worker,
                                "python",
                                "-c",
                                "from pathlib import Path;import time;assert time.time()-float(Path('/data/database.sqlite.vision.heartbeat').read_text())<10",
                            ],
                            capture_output=True,
                        )
                        if ready.returncode == 0:
                            return
                        time.sleep(0.25)
                    raise AssertionError("Worker heartbeat unavailable")

                worker_ready()
                docker("restart", "--time", "10", worker)
                worker_ready()
                check(
                    client.get(base + "/inventory").status_code == 401,
                    "Anonymous inventory exposed",
                )
                headers = {
                    "X-TallyBinder-Client": "web",
                    "Origin": "https://binder.example",
                }
                login = client.post(
                    base + "/auth/login", headers=headers, json={"access_key": key}
                )
                check(login.status_code == 200, "Login failed")
                check(
                    "HttpOnly" in login.headers["set-cookie"]
                    and "Secure" in login.headers["set-cookie"],
                    "Cookie flags lost in Next proxy",
                )
                # Local plain HTTP cannot establish browser Secure-cookie behavior; explicitly
                # forward the returned cookie to test proxy header transport only.
                headers["Cookie"] = login.headers["set-cookie"].split(";", 1)[0]
                session = str(uuid4())
                intake = str(uuid4())
                check(
                    client.post(
                        base + "/intake/sessions", headers=headers, json={"id": session}
                    ).status_code
                    == 200,
                    "Session failed",
                )
                uploaded = client.post(
                    base + "/media/upload",
                    headers=headers,
                    files={"file": ("synthetic.jpg", photo(), "image/jpeg")},
                )
                check(uploaded.status_code == 200, "Photo upload failed")
                media = uploaded.json()["id"]
                padded = photo()
                padded += b"\0" * (7_900_000 - len(padded))
                large = client.post(
                    base + "/media/upload",
                    headers=headers,
                    files={"file": ("synthetic-padded.jpg", padded, "image/jpeg")},
                )
                check(
                    large.status_code == 200,
                    "7.9 MB upload did not traverse the local Next proxy",
                )
                fields = dict(
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
                check(
                    client.put(
                        base + "/intake/" + intake,
                        headers=headers,
                        json={
                            "session_id": session,
                            "expected_revision": 0,
                            "fields": fields,
                            "front_id": media,
                            "back_id": media,
                        },
                    ).status_code
                    == 200,
                    "Draft failed",
                )
                price = client.post(
                    base + "/intake/" + intake + "/price?revision=1", headers=headers
                )
                check(
                    Decimal(price.json()["market_price"]) == Decimal("527.70")
                    and price.json()["provider_sku_id"] == "2999653",
                    "Exact dated SKU mismatch",
                )
                created = client.post(
                    base + "/inventory",
                    headers=headers,
                    json={
                        "intake_id": intake,
                        "intake_revision": 1,
                        "listing_price": "500",
                        "quantity": 2,
                        "approved": True,
                    },
                )
                check(created.status_code == 200, "Inventory creation failed")
                listing = created.json()["id"]
                image_hash = sha256(
                    client.get(base + "/media/" + media, headers=headers).content
                ).hexdigest()
                check(
                    "500.00"
                    in client.get(base + "/inventory/export.csv", headers=headers).text,
                    "CSV missing listing",
                )
                docker("restart", "--time", "90", api)
                wait()
                check(
                    client.get(base + "/inventory/" + listing, headers=headers).json()[
                        "listing"
                    ]["quantity"]
                    == 2,
                    "Inventory lost on restart",
                )
                docker("rm", "-f", api)
                start_api()
                wait()
                check(
                    client.get(base + "/inventory/" + listing, headers=headers).json()[
                        "listing"
                    ]["listing_price"]
                    == "500.00",
                    "Inventory lost on container replacement",
                )
                check(
                    sha256(
                        client.get(base + "/media/" + media, headers=headers).content
                    ).hexdigest()
                    == image_hash,
                    "Photo lost on replacement",
                )
                result = json.loads(
                    docker(
                        "exec",
                        api,
                        "python",
                        "-m",
                        "cardscan.ops",
                        "backup",
                        "--destination",
                        "/data/test-backups",
                    )
                )
                restored = json.loads(
                    docker(
                        "exec",
                        api,
                        "python",
                        "-m",
                        "cardscan.ops",
                        "restore",
                        "--archive",
                        result["path"],
                        "--destination",
                        "/data/restored",
                    )
                )
                check(restored["photos"] == 1, "Backup photo missing")
                count = int(
                    docker(
                        "exec",
                        api,
                        "python",
                        "-c",
                        'import sqlite3; c=sqlite3.connect("/data/restored/database.sqlite"); print(c.execute("SELECT count(*) FROM observations").fetchone()[0])',
                    )
                )
                check(count == history, "Restored price history changed")
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "local_only": True,
                            "api_image": args.api_image,
                            "frontend_image": args.frontend_image,
                            "checks": [
                                "private_auth",
                                "worker_restart_heartbeat_AI_disabled",
                                "Next_cookie_forwarding_headers",
                                "image_upload_7_9_MB",
                                "exact_SKU",
                                "inventory_CSV",
                                "API_restart_persistence",
                                "container_replacement_persistence",
                                "photo_persistence",
                                "backup_restore_history",
                            ],
                            "historical_rows_preserved": history,
                            "paid_AI_calls": 0,
                        },
                        indent=2,
                    )
                )
        except BaseException:
            for name in started:
                logs = subprocess.run(
                    DOCKER + ["logs", "--tail", "30", name],
                    capture_output=True,
                    text=True,
                )
                print(name + " logs:\n" + logs.stdout + logs.stderr, file=sys.stderr)
            raise
        finally:
            for name in reversed(started):
                subprocess.run(DOCKER + ["rm", "-f", name], capture_output=True)
            subprocess.run(
                DOCKER
                + [
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    "-v",
                    str(data) + ":/data",
                    args.api_image,
                    "python",
                    "-c",
                    f'import os; [(os.chown(os.path.join(p,n),{os.getuid()},{os.getgid()})) for p,ds,fs in os.walk("/data") for n in ds+fs];os.chown("/data",{os.getuid()},{os.getgid()})',
                ],
                capture_output=True,
            )
            subprocess.run(DOCKER + ["network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
