# Локальный backend протоколирования совещаний

Python 3.12 · FastAPI · Pydantic 2 · SQLAlchemy async · PostgreSQL · Alembic · faster-whisper large-v3 · pyannote community-1 · Ollama / Qwen3 · DOCX / PDF.

Отдельный backend, без frontend. React-приложение находится в корне этого репозитория. API предназначен для подключения React через HTTP; текущий демонстрационный frontend автоматически к нему не подключается.

## Быстрый запуск

Нужен Docker с Compose v2, свободное место для нескольких гигабайт моделей и достаточная память. Сборка и первое скачивание существенно дольше повторного запуска. По умолчанию используется CPU; Whisper large-v3 на CPU может обрабатывать запись медленнее её длительности.

1. Откройте терминал в `backend` и скопируйте `.env.example` в `.env` (`Copy-Item .env.example .env` в PowerShell, `cp .env.example .env` в Bash).
2. Примите условия модели [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) в своём аккаунте Hugging Face. Впишите read-token в `HF_TOKEN` внутри `.env`. Это необходимое условие скачивания gated-модели; приложение не может принять условия за пользователя.
3. Запустите одной командой:

```sh
docker compose up --build -d
```

Compose запускает PostgreSQL, применяет миграцию, скачивает модели отдельными initialization-сервисами, затем запускает API, Ollama и worker. Загрузка весов выполняется только при отсутствии подготовленной модели или изменении заданной ревизии. `api` может стать доступным раньше окончания скачивания: поступившие задания сохраняются в БД и дождутся worker.

- Swagger UI: <http://localhost:8000/docs>
- OpenAPI: <http://localhost:8000/openapi.json>
- Готовность БД: <http://localhost:8000/api/v1/health/ready>
- Наличие весов и модели Ollama: <http://localhost:8000/api/v1/health/models>

```sh
docker compose ps -a
docker compose logs -f bootstrap ollama-init worker
```

После первого скачивания удалите `HF_TOKEN` из `.env`. Условие доступа к pyannote и загрузка весов нужны один раз, обработка записей работает без токена. `health/models` проверяет доступность файлов и Ollama, но не проводит полноценное пробное распознавание.

Для остановки без удаления данных: `docker compose down`. Не добавляйте `-v`, если хотите сохранить записи, базу и модель Ollama.

## Приватность и offline

Аудио, видео, транскрипт, имена, summary и поручения обрабатываются локально. SDK облачных AI-сервисов не используется.

- `api`, `worker`, `db`, `migrate` и рабочий `ollama` подключены только к Docker-сети `runtime` с `internal: true`.
- Только `bootstrap` и `ollama-init` получают сеть для первоначального скачивания. Они **не монтируют хранилище записей и не подключаются к PostgreSQL**.
- Hugging Face offline-режим включён в worker; Whisper и pyannote загружаются по локальному пути. Отсутствие весов вызывает понятную ошибку, а не обращение к hosted inference.
- Телеметрия Hugging Face и pyannote отключена. Для Ollama задано `OLLAMA_NO_CLOUD=1`.
- LLM-клиент допускает только локальные адреса, проверяет DNS, соединяется с проверенным IP, игнорирует HTTP proxy из окружения и запрещает redirects. Перед передачей текста проверяет `/api/show` и отклоняет cloud aliases.
- В логах worker находятся UUID задания, этап и код ошибки; полный текст ответа LLM, запись и персональные данные не логируются приложением.

После подготовки образов и весов можно дополнительно изолировать initialization-сеть:

```sh
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build --pull never
```

Для air-gapped установки перенесите заранее собранные Docker-образы (`docker save` / `docker load`), каталог `models` **вместе с `provisioned.json`** и содержимое volume `ollama_models`. Ревизии и имена моделей в `.env` должны совпадать. Укажите конкретные commit SHA в `WHISPER_REVISION` и `DIARIZATION_REVISION`, если нужна воспроизводимая поставка весов.

При нативном запуске Python Docker-сетевая изоляция не действует: обеспечьте ограничения исходящего трафика на уровне ОС и отдельно задайте `OLLAMA_NO_CLOUD=1` серверу Ollama.

## Рабочий сценарий API

1. `POST /api/v1/meetings` принимает multipart: `file`, `title`, обязательную `meeting_date` с timezone offset, необязательную IANA `timezone` (по умолчанию `Asia/Almaty`). Ответ `202` содержит UUID.
2. Отдельный worker выполняет FFmpeg → Whisper → pyannote → сопоставление интервалов и сохраняет транскрипт. Статус станет `AWAITING_MAPPING`.
3. Добавьте участников, получите список спикеров и привяжите `SPEAKER_00` / `SPEAKER_01` к UUID участников.
4. Вызовите `POST /api/v1/meetings/{id}/analyze` с `{}`. Анализ будет выполнен локальной Qwen через Ollama, с уже привязанными именами. При сознательном пропуске mapping передайте `{"allow_unmapped": true}`. `UNKNOWN` не привязывается к одному человеку, поскольку может включать несколько голосов.
5. Ожидайте `COMPLETED`, получите summary и поручения, при необходимости исправьте поручения и выгрузите документы.

Пример загрузки в Bash; в Windows используйте `curl.exe` и команды одной строкой:

```sh
curl -X POST http://localhost:8000/api/v1/meetings \
  -F 'title=Обсуждение проекта' \
  -F 'meeting_date=2026-09-23T10:00:00+05:00' \
  -F 'timezone=Asia/Almaty' \
  -F 'file=@meeting.mp4;type=video/mp4'

curl http://localhost:8000/api/v1/meetings/MEETING_UUID
curl -X POST http://localhost:8000/api/v1/meetings/MEETING_UUID/participants \
  -H 'Content-Type: application/json' -d '{"name":"Айдар","position":"Аналитик"}'
curl http://localhost:8000/api/v1/meetings/MEETING_UUID/speakers
curl -X PATCH http://localhost:8000/api/v1/meetings/MEETING_UUID/speakers/SPEAKER_01 \
  -H 'Content-Type: application/json' -d '{"participant_id":"PARTICIPANT_UUID"}'
curl -X POST http://localhost:8000/api/v1/meetings/MEETING_UUID/analyze \
  -H 'Content-Type: application/json' -d '{}'
curl 'http://localhost:8000/api/v1/tasks?meeting_id=MEETING_UUID'
curl -X PATCH http://localhost:8000/api/v1/tasks/TASK_UUID \
  -H 'Content-Type: application/json' -d '{"status":"COMPLETED"}'
curl -o protocol.docx http://localhost:8000/api/v1/meetings/MEETING_UUID/exports/docx
curl -o protocol.pdf http://localhost:8000/api/v1/meetings/MEETING_UUID/exports/pdf
```

При заданном `API_KEY` добавляйте `X-API-Key: <значение>` ко всем `/api/v1` запросам, включая health. В Swagger поле `x-api-key` доступно в параметрах операций.

### Endpoints

| Метод | Путь `/api/v1/...` | Назначение |
|---|---|---|
| POST / GET | `meetings` | Загрузка / список встреч |
| GET | `meetings/{id}` | Статус, этап, метаданные STT, summary, topics, decisions |
| GET | `meetings/{id}/jobs` | Последние 100 заданий и коды ошибок |
| POST | `meetings/{id}/process` | Повтор распознавания после сбоя до сохранения транскрипта |
| POST | `meetings/{id}/analyze` | Первичный или повторный анализ без Whisper/pyannote |
| GET | `meetings/{id}/transcript` | Упорядоченные реплики с именами из текущего mapping |
| GET | `meetings/{id}/speakers` | Спикеры и привязки |
| PATCH | `meetings/{id}/speakers/{speaker_id}` | `participant_id`, допускает `null` для отвязки |
| POST / GET | `meetings/{id}/participants` | Создание / список участников |
| PATCH / DELETE | `meetings/{id}/participants/{participant_id}` | Изменение / удаление участника |
| GET | `tasks` | Список с фильтрами |
| GET / PATCH | `tasks/{id}` | Получение / редактирование поручения |
| GET | `meetings/{id}/exports/docx` и `.../pdf` | Генерация и скачивание итогового проекта протокола |
| GET | `health/live`, `health/ready`, `health/models` | Диагностика |

Списки встреч и поручений поддерживают `offset` и `limit` (максимум 200). Фильтры поручений: `status`, `meeting_id`, `responsible_id`, `deadline_from`, `deadline_to`; границы срока включительные, datetime обязательно содержит timezone offset.

PATCH поручения допускает `description`, `responsible_participant_id`, `deadline`, `priority`, `status`. `deadline` и `responsible_participant_id` могут быть `null`; обязательные поля — нет. Участник всегда принадлежит тому же совещанию, что дополнительно контролируется составным внешним ключом БД.

Статусы: `NEW`, `IN_PROGRESS`, `COMPLETED`, `OVERDUE`, `CANCELLED`. При завершении проставляется `completed_at`, при открытии заново — очищается. `OVERDUE` вычисляется при чтении и фильтрации от текущего момента для активных поручений; завершённые и отменённые не становятся просроченными. SQL-фильтры и ответы используют одну семантику. Срок без времени означает конец указанного дня в timezone совещания.

## Архитектура и восстановление

```text
app/api/             HTTP-валидация и ответы
app/schemas/         Pydantic-контракты API и structured output
app/models/          6 таблиц: meetings, participants, speakers, transcript_segments, tasks, jobs
app/repositories/    Запросы БД и проверки принадлежности
app/services/        Аудио, STT, diarization, merge, mapping, LLM, извлечение, экспорт
app/worker.py        Последовательный обработчик долговечной очереди
app/utils/           Сроки, проверка upload, безопасные коды ошибок
alembic/             Версионируемая схема БД
scripts/             Подготовка моделей и проверка экспорта
tests/               Unit, API, pipeline, PostgreSQL и экспорт
```

API не запускает тяжёлые модели внутри endpoint и не использует FastAPI BackgroundTasks для длительных заданий. Очередь хранится в PostgreSQL. Worker забирает задания через `FOR UPDATE SKIP LOCKED`, периодически продлевает lease; после аварийного завершения другой worker забирает истёкшее задание. Токен владельца проверяется перед записью результатов, чтобы старый worker не перезаписал новое выполнение. Уникальный partial index запрещает два активных задания на одну встречу. Число восстановлений ограничено `JOB_MAX_ATTEMPTS`.

Шаги имеют отдельные статусы `AUDIO_EXTRACTION`, `TRANSCRIPTION`, `DIARIZATION`, `ALIGNMENT`, `LOCAL_LLM_ANALYSIS`. При обычной ошибке сохраняется `FAILED` и безопасный код. Примеры: `WHISPER_MODEL_MISSING`, `DIARIZATION_MODEL_MISSING`, `NO_AUDIO_STREAM`, `AUDIO_DURATION_LIMIT`, `OLLAMA_MODEL_UNAVAILABLE`, `OLLAMA_ANALYSIS_FAILED`, `LLM_CONTEXT_LIMIT`.

API можно перезапускать независимо от worker. В одном worker выполняется одно задание; нативные вычисления идут вне event loop, heartbeat продолжает работать. Для одного GPU рекомендуется один worker. Модели освобождаются между этапами, чтобы уменьшить одновременный расход видеопамяти. Успешный анализ и поручения сохраняются одной транзакцией.

Изменение mapping не запускает STT: имена при чтении транскрипта подставляются SQL join. Анализ помечается `analysis_stale=true`; экспорт требует актуального анализа. Редактирование mapping, удаление участников и правка поручений во время активного задания дают `409`.

Повторный анализ не сбрасывает статусы, `completed_at` и ручные исправления. Точные повторные извлечения определяются по сегментам, цитате и описанию. Старые поручения не удаляются автоматически; `analysis_version` помогает увидеть их происхождение. Перефразированное моделью поручение может потребовать ручного устранения дубликата — ненужное поручение можно отменить через `CANCELLED`.

## RU / KK, спикеры и достоверность

Whisper использует `language=None`, `multilingual=True`, VAD и word timestamps. Язык не закреплён за русским. `detected_language` — общий первично определённый язык, а не гарантия одного языка всей записи; текст сохраняет исходный язык без принудительного перевода.

Для каждого слова/сегмента объединяются пересечения интервалов одного спикера и выбирается максимальная суммарная длительность. Дублирующиеся интервалы одного спикера не учитываются дважды. При отсутствии пересечения ставится `UNKNOWN`. Соседние слова одного спикера объединяются в читаемые реплики до 30 секунд. Используется exclusive diarization из community-1; одновременно говорящие люди в итоговом линейном транскрипте представлены одним выбранным спикером.

Ollama получает JSON Schema из Pydantic, `temperature=0`, `think=false`, `stream=false`. Ответ валидируется как JSON, без regex-разбора произвольного текста. Большой транскрипт разбивается на части с перекрытием; обработка не обрезает остаток записи молча. Summary частей объединяется в хронологическом порядке, поэтому для многочасовых встреч может получиться длиннее обычного краткого резюме.

У каждого поручения и решения проверяются существующие номера сегментов и дословная цитата. Неизвестные имена обнуляются; спикер не считается ответственным только потому, что он произнёс поручение. Вывод модели о сроке перепроверяется детерминированным парсером относительно локальной даты **самой встречи**. Поддержаны «завтра», «через неделю», «до пятницы», «25 сентября», «ертең», «жұмаға дейін», «келесі дүйсенбіге дейін» и другие формы из тестов. Неподдержанная или неоднозначная формулировка сохраняется в `deadline_raw`, а `deadline` остаётся `null`. Недостающую информацию можно заполнить PATCH.

Модельные результаты являются проектом протокола: наличие цитаты само по себе не доказывает правильность её интерпретации. Качество русского, казахского и переключения языков нужно измерить на реальных записях с вашей акустикой и терминологией. Код поддерживает эти режимы, но автоматические тесты бизнес-логики не заменяют замеры WER/DER и ручную проверку поручений.

## Хранение

В Compose записи находятся в named volume `meeting_storage`, веса Whisper/pyannote — в `./models`, веса Qwen — в `ollama_models`:

```text
storage/meetings/{uuid}/
  original/source.wav             # либо .mp3/.m4a/.mp4/.webm
  audio/{job_uuid}-{owner_uuid}/meeting.wav
  exports/protocol-{uuid}.docx
  exports/protocol-{uuid}.pdf
```

Исходное имя хранится только как метаданные. Каталоги и имена на диске создаёт приложение. Проверяются расширение, MIME, сигнатура контейнера и размер; FFprobe проверяет наличие аудио, FFmpeg преобразует в mono 16 kHz PCM s16le без `shell=True`. У upload есть ограничение тела запроса ещё при чтении multipart, включая запросы без `Content-Length`.

Каждая попытка worker пишет в отдельный каталог, каждый экспорт — в отдельный файл. Автоматической политики удаления в MVP нет: планируйте место и резервное копирование volumes и каталога моделей. Имена в PDF поддерживают русские и казахские символы благодаря встраиваемому DejaVu Sans; пользовательский текст экранируется перед передачей ReportLab.

## GPU

При наличии NVIDIA GPU, актуального драйвера и NVIDIA Container Toolkit:

```sh
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

Override устанавливает CUDA-вариант PyTorch, `AI_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16` и передаёт GPU worker и Ollama. CPU-образ использует CPU PyTorch и `int8`. Фактическая потребность в памяти зависит от длительности записи, модели Qwen и размера контекста; GPU-конфигурация требует проверки на целевом сервере.

## Нативная разработка и тесты

```sh
python3.12 -m venv .venv
# Windows: .venv\Scripts\Activate.ps1; Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check app tests scripts alembic
python -m ruff format --check app tests scripts alembic
```

По умолчанию тесты используют временный SQLite, без скачивания AI-моделей. Один тест конкурентного захвата заданий требует PostgreSQL. Для полного прогона задайте `TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/meetings_test`: каждый тест создаёт и удаляет только собственную схему `test_<uuid>`.

Проверка миграций на **отдельной тестовой БД**:

```sh
alembic upgrade head
alembic check
# Следующие две команды только на тестовой БД: downgrade удаляет таблицы приложения.
alembic downgrade base
alembic upgrade head
```

Для нативного API задайте `DATABASE_URL` в `.env`, примените `alembic upgrade head` и запустите `uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`. Для worker дополнительно установите `requirements-ai.txt`, FFmpeg/FFprobe, подготовьте модели и локальную Ollama; в отдельном терминале выполните `python -m app.worker`.

`python scripts/verify_exports.py` создаёт синтетические DOCX/PDF в `verification`. В Windows задайте `PDF_FONT_PATH=C:/Windows/Fonts/arial.ttf` и `PDF_BOLD_FONT_PATH=C:/Windows/Fonts/arialbd.ttf` или пути к DejaVu Sans. Реальные FFmpeg-тесты используют бинарник из `imageio-ffmpeg`; проверки FFprobe в них подменены, потому что этот пакет FFprobe не содержит.

Состояние проверок в этой среде описано в [VERIFICATION.md](VERIFICATION.md). Стек моделей и Docker запуск проверяются отдельно от тестов с подставными ответами моделей.

## Границы MVP

API по умолчанию публикуется только на `127.0.0.1`. Поддерживается общий `X-API-Key`, но нет пользователей, RBAC, SSO и разделения организаций. CORS не является авторизацией. Для предоставления доступа другим компьютерам настройте аутентификацию, HTTPS и сетевые ограничения под своё окружение.

В MVP нет потоковой записи, редактирования транскрипта, почтовых уведомлений и автоматического принятия протокола. Финальные решения и поручения должны проверяться человеком. Экспорт включает участников, summary, темы, решения, поручения, основания и полный транскрипт.

## Документация интеграций

- [faster-whisper: исходный API v1.2.1](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py) — multilingual и word timestamps.
- [pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) — локальная загрузка и exclusive diarization.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) — JSON Schema в `format`.
- [Ollama local-only mode](https://docs.ollama.com/faq) — отключение облачных функций.
