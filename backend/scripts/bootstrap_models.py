"""Provision public/gated weights. This service has NO mount of meeting data."""

import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download


def download(repo: str, path: Path, revision: str, token: str | None, marker: str):
    manifest = path / "provisioned.json"
    expected = {"repository": repo, "revision": revision}
    if (
        manifest.is_file()
        and (path / marker).is_file()
        and json.loads(manifest.read_text()) == expected
    ):
        print(f"Model already provisioned: {repo}")
        return
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        raise SystemExit(
            f"Model is not provisioned for {repo}@{revision}; download it before offline startup."
        )
    if repo.startswith("pyannote/") and not token:
        raise SystemExit("Set HF_TOKEN in .env after accepting the community-1 model conditions.")
    snapshot_download(repo_id=repo, revision=revision, local_dir=path, token=token)
    if not (path / marker).is_file():
        raise SystemExit(f"Incomplete model snapshot: {repo}")
    manifest.write_text(json.dumps(expected), encoding="utf-8")
    # Runtime containers use uid=10001 and mount these files read-only.
    for item in path.rglob("*"):
        item.chmod(0o755 if item.is_dir() else 0o644)
    path.chmod(0o755)
    print(f"Model provisioned: {repo}")


if __name__ == "__main__":
    root = Path(os.environ.get("MODEL_ROOT", "/models"))
    token = os.environ.get("HF_TOKEN") or None
    download(
        "pyannote/speaker-diarization-community-1",
        root / "diarization",
        os.environ.get("DIARIZATION_REVISION", "main"),
        token,
        "config.yaml",
    )
    download(
        os.environ.get("WHISPER_REPO", "Systran/faster-whisper-large-v3"),
        root / "whisper",
        os.environ.get("WHISPER_REVISION", "main"),
        token,
        "model.bin",
    )
