"""Start a temporary real HTTP server against the configured, migrated database."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {**os.environ, "API_KEY": "local-smoke-key"}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False
        ) as client:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError("Uvicorn exited before startup")
                try:
                    response = client.get(
                        "/api/v1/health/ready", headers={"X-API-Key": "local-smoke-key"}
                    )
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("API did not become ready; check DATABASE_URL and migrations")
            assert client.get("/api/v1/meetings").status_code == 401
            assert (
                client.get("/api/v1/meetings", headers={"X-API-Key": "local-smoke-key"}).status_code
                == 200
            )
            assert client.get("/docs").status_code == 200
            schema = client.get("/openapi.json").json()
            assert "/api/v1/meetings/{meeting_id}/transcript" in schema["paths"]
            print(
                "PASS: real Uvicorn HTTP, PostgreSQL readiness, API-key protection, meetings list, Swagger/OpenAPI"
            )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
