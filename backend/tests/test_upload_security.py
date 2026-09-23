from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.helpers import PREFIX, WAV_HEADER, upload


@pytest.mark.parametrize(
    ("filename", "mime", "data", "expected"),
    [
        ("a.exe", "audio/wav", WAV_HEADER, 415),
        ("a.wav", "text/plain", WAV_HEADER, 415),
        ("a.wav", "audio/wav", b"<script>fake</script>", 415),
        ("a.wav", "audio/wav", b"", 422),
        ("a.wav", "audio/wav", WAV_HEADER + b"a" * (1024 * 1024), 413),
        ("a.mp3", "audio/mpeg", b"ID3" + b"a" * 30, 202),
        ("a.m4a", "audio/mp4", b"\0\0\0\x20ftypM4A ", 202),
        ("a.mp4", "video/mp4", b"\0\0\0\x20ftypisom", 202),
        ("a.webm", "video/webm", b"\x1a\x45\xdf\xa3test", 202),
    ],
    ids=["extension", "mime", "header", "empty", "oversize", "mp3", "m4a", "mp4", "webm"],
)
async def test_upload_validation(env, filename, mime, data, expected):
    response = await upload(env, filename, data, mime)
    assert response.status_code == expected, response.text
    if expected != 202:
        assert list(env["settings"].storage_dir.rglob("source.*")) == []


async def test_filename_is_never_used_as_storage_path(env):
    response = await upload(env, filename="../../escape.wav")
    assert response.status_code == 202
    paths = list(env["settings"].storage_dir.rglob("source.wav"))
    assert len(paths) == 1 and response.json()["id"] in str(paths[0])
    assert response.json()["original_filename"] == "escape.wav"


@pytest.mark.parametrize(
    "field,value",
    [("meeting_date", "2026-09-23T10:00:00"), ("timezone", "Mars/Base"), ("title", "   ")],
)
async def test_invalid_metadata(env, field, value):
    assert (await upload(env, **{field: value})).status_code == 422


async def test_api_key_protects_data(env):
    env["settings"].api_key = "test-secret"
    assert (await env["client"].get(PREFIX + "/meetings")).status_code == 401
    assert (
        await env["client"].get(PREFIX + "/meetings", headers={"X-API-Key": "wrong"})
    ).status_code == 401
    assert (
        await env["client"].get(PREFIX + "/meetings", headers={"X-API-Key": "test-secret"})
    ).status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com",
        "http://8.8.8.8:11434",
        "http://ollama.com",
        "http://user:pass@localhost:11434",
        "http://169.254.169.254",
        "http://localhost/path",
    ],
)
def test_external_ollama_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_url=url)


def test_cloud_model_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_model="qwen3:cloud")


async def test_streaming_upload_without_content_length_is_bounded(env):
    async def chunks():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.wav"\r\nContent-Type: audio/wav\r\n\r\n'
        for _ in range(20):
            yield b"x" * 65536
        yield b"\r\n--boundary--\r\n"

    response = await env["client"].post(
        PREFIX + "/meetings",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 413, response.text


def test_compose_data_services_have_no_egress():
    import yaml

    compose = yaml.safe_load(Path("docker-compose.yml").read_text())
    assert compose["networks"]["runtime"]["internal"] is True
    for service in ("api", "worker", "db", "ollama", "migrate"):
        assert compose["services"][service]["networks"] == ["runtime"]
        assert "HF_TOKEN" not in compose["services"][service].get("environment", {})
    for service in ("bootstrap", "ollama-init"):
        assert not any(
            "meeting_storage" in volume for volume in compose["services"][service]["volumes"]
        )
    assert compose["services"]["ollama"]["environment"]["OLLAMA_NO_CLOUD"] == "1"
