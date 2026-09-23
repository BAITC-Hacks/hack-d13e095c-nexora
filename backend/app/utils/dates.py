import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def aware_utc(value: datetime) -> datetime:
    # SQLite test adapter returns naive UTC. PostgreSQL uses timestamptz.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def end_of_day(value: date, timezone: str) -> datetime:
    return datetime.combine(value, time(23, 59, 59), ZoneInfo(timezone)).astimezone(UTC)


WEEKDAYS = {
    "понедельник": 0,
    "вторник": 1,
    "сред": 2,
    "четверг": 3,
    "пятниц": 4,
    "суббот": 5,
    "воскресень": 6,
    "дүйсенбі": 0,
    "сейсенбі": 1,
    "сәрсенбі": 2,
    "бейсенбі": 3,
    "жұма": 4,
    "сенбі": 5,
    "жексенбі": 6,
}
MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
    "қаңтар": 1,
    "ақпан": 2,
    "наурыз": 3,
    "сәуір": 4,
    "мамыр": 5,
    "маусым": 6,
    "шілде": 7,
    "тамыз": 8,
    "қыркүйек": 9,
    "қазан": 10,
    "қараша": 11,
    "желтоқсан": 12,
}


def parse_deadline(raw: str | None, meeting_date: datetime, timezone: str) -> date | None:
    """Resolve supported RU/KK expressions from the meeting's local date, never server today.

    Unknown/ambiguous forms stay null even if an LLM suggests a date.
    """
    if not raw:
        return None
    reference = aware_utc(meeting_date).astimezone(ZoneInfo(timezone)).date()
    text = raw.strip().lower().replace("ё", "е")
    for phrase, days in (
        ("послезавтра", 2),
        ("бүрсігүні", 2),
        ("завтра", 1),
        ("ертең", 1),
        ("сегодня", 0),
        ("бүгін", 0),
    ):
        if re.search(rf"\b{phrase}\b", text):
            return reference + timedelta(days=days)
    if "через неделю" in text or "бір аптадан кейін" in text:
        return reference + timedelta(days=7)
    relative = re.search(r"через\s+(\d+)\s+(день|дня|дней)|(?P<kk>\d+)\s+күннен кейін", text)
    if relative:
        days_text = relative.group(1) or relative.group("kk")
        if len(days_text) > 4 or int(days_text) > 3650:
            return None
        try:
            return reference + timedelta(days=int(days_text))
        except OverflowError:
            return None
    # Longest first prevents 'сенбі' matching 'дүйсенбі'.
    for name in sorted(WEEKDAYS, key=len, reverse=True):
        if name in text:
            weekday = WEEKDAYS[name]
            if "келесі" in text or "следующ" in text:
                return reference + timedelta(days=7 - reference.weekday() + weekday)
            return reference + timedelta(days=(weekday - reference.weekday()) % 7)
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    numeric = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    try:
        if iso:
            return date(*map(int, iso.groups()))
        if numeric:
            day, month, year = map(int, numeric.groups())
            return date(year, month, day)
        for month_name, month in MONTHS.items():
            match = re.search(rf"\b(\d{{1,2}})\s+{month_name}\w*(?:\s+(\d{{4}}))?", text)
            if match:
                # Missing year means the year of the meeting, no invented rollover.
                return date(int(match.group(2) or reference.year), month, int(match.group(1)))
    except ValueError:
        return None
    return None
