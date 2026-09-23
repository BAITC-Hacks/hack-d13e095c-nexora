"""Generate a synthetic RU/KK fixture for local visual QA; no meeting data is used."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services.export_service import ExportService  # noqa: E402


def main():
    settings = Settings()
    snapshot = {
        "title": "Жоба барысы — обсуждение проекта",
        "meeting_date": "2026-09-23 10:00",
        "timezone": "Asia/Almaty",
        "summary": "Обсудили ход проекта и подготовку отчёта. Айдар подтвердил выполнение поручения.",
        "topics": ["Ход проекта", "Отчётность"],
        "decisions": ["Подготовить отчёт к пятнице."],
        "analysis_version": 1,
        "participants": [
            {"name": "Ерлан", "position": "Руководитель"},
            {"name": "Айдар", "position": "Аналитик"},
        ],
        "tasks": [
            {
                "description": "Подготовить отчёт по проекту",
                "responsible_name": "Айдар",
                "assigned_by": "Ерлан",
                "deadline": "25.09.2026 23:59:59 +05:00",
                "status": "NEW",
                "priority": "normal",
                "confidence": 0.95,
                "source_quote": "Айдар, подготовь отчёт до пятницы.",
                "analysis_version": 1,
            }
        ],
        "transcript": [
            {
                "start": 0,
                "end": 4,
                "speaker_id": "SPEAKER_00",
                "speaker_name": "Ерлан",
                "text": "Айдар, подготовь отчёт до пятницы.",
            },
            {
                "start": 5,
                "end": 8,
                "speaker_id": "SPEAKER_01",
                "speaker_name": "Айдар",
                "text": "Жақсы, дайындаймын. Ә Ғ Қ Ң Ө Ұ Ү Һ І.",
            },
        ],
    }
    directory = Path("verification")
    directory.mkdir(exist_ok=True)
    service = ExportService(settings)
    for extension in ("pdf", "docx"):
        path = directory / f"sample-protocol.{extension}"
        path.write_bytes(getattr(service, extension)(snapshot))
        print(path.resolve())


if __name__ == "__main__":
    main()
