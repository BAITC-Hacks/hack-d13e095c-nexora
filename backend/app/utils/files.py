from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import HTTPException, UploadFile

from app.config import Settings

MIME_TYPES = {
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "video/mp4"},
    ".mp4": {"video/mp4", "audio/mp4"},
    ".webm": {"video/webm", "audio/webm"},
}


def meeting_directory(settings: Settings, meeting_id: UUID) -> Path:
    return settings.storage_dir.resolve() / "meetings" / str(meeting_id)


def signature_matches(extension: str, header: bytes) -> bool:
    if extension == ".wav":
        return header[:4] in {b"RIFF", b"RF64"} and header[8:12] == b"WAVE"
    if extension == ".mp3":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224
        )
    if extension in {".mp4", ".m4a"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    return extension == ".webm" and header.startswith(b"\x1a\x45\xdf\xa3")


async def save_upload(
    upload: UploadFile, meeting_id: UUID, settings: Settings
) -> tuple[Path, int, str]:
    filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(filename).suffix.lower()
    mime = (upload.content_type or "").split(";", 1)[0].lower()
    if extension not in MIME_TYPES or mime not in MIME_TYPES[extension]:
        raise HTTPException(415, "Unsupported extension or MIME type")
    limit = settings.max_upload_mb * 1024 * 1024
    if upload.size is not None and upload.size > limit:
        raise HTTPException(413, "Upload exceeds MAX_UPLOAD_MB")
    directory = meeting_directory(settings, meeting_id)
    for child in ("original", "audio", "exports"):
        (directory / child).mkdir(parents=True, exist_ok=True)
    destination = directory / "original" / f"source{extension}"
    size = 0
    try:
        async with aiofiles.open(destination, "xb") as output:
            while chunk := await upload.read(1024 * 1024):
                if size == 0 and not signature_matches(extension, chunk[:32]):
                    raise HTTPException(415, "File header does not match the declared media format")
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Upload exceeds MAX_UPLOAD_MB")
                await output.write(chunk)
        if size == 0:
            raise HTTPException(422, "Empty media file")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return destination, size, filename[:255]
