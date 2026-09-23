from datetime import timedelta
from uuid import UUID

from app.db.base import utcnow
from app.models import Task, TranscriptSegment
from app.models.briefing import ConferenceBriefing
from app.models.conference import Conference
from app.models.enums import TaskStatus
from app.schemas.briefing import BriefingAnalysis
from app.services.briefing_service import BriefingProcessor, inputs, validate_items

BASE = "/api/v1/conferences"
OLD = "Решили выпускать продукт в пятницу. Вопрос бюджета отложили до ответа финансистов."
NEW = "Выпуск перенесли на понедельник. Новый риск: поставщик остановил поставку."


async def room(env, title="Проект"):
    r = await env["client"].post(
        BASE, json={"title": title, "name": "Организатор", "consent": True}
    )
    assert r.status_code == 201, r.text
    return r.json()


def auth(r):
    return {"Authorization": "Bearer " + r["token"]}


async def closed_room(env):
    r = await room(env)
    async with env["factory"]() as s:
        identity = UUID(r["room"]["id"])
        s.add(
            TranscriptSegment(
                meeting_id=identity,
                ordinal=0,
                speaker_id=r["room"]["me"],
                start=0,
                end=15,
                text=OLD,
            )
        )
        task = Task(
            meeting_id=identity,
            description="Подготовить договор",
            deadline=utcnow() + timedelta(days=1),
            responsible_name="Айдар",
            priority="normal",
            confidence=1,
            source_quote="Айдар подготовит договор",
            extraction_key="contract",
            analysis_version=1,
        )
        s.add(task)
        await s.commit()
        task_id = task.id
    response = await env["client"].post(f"{BASE}/{r['room']['id']}/end", headers=auth(r))
    assert response.status_code == 200
    return r, task_id


async def setup(env, current, previous, updates=NEW):
    return await env["client"].put(
        f"{BASE}/{current['room']['id']}/briefing",
        headers=auth(current),
        json={
            "previous_id": previous["room"]["id"],
            "previous_token": previous["token"],
            "updates": updates,
            "share_with_participants": True,
        },
    )


class Model:
    async def structured(self, context, schema, prompt):
        return BriefingAnalysis(
            items=[
                {
                    "category": "risk",
                    "text": "Поставщик остановил поставку.",
                    "previous_id": None,
                    "previous_quote": None,
                    "current_id": "update:0",
                    "current_quote": "Новый риск: поставщик остановил поставку.",
                },
                {
                    "category": "decision",
                    "text": "Выпуск перенесён с пятницы на понедельник.",
                    "previous_id": "segment:0",
                    "previous_quote": "Решили выпускать продукт в пятницу.",
                    "current_id": "update:0",
                    "current_quote": "Выпуск перенесли на понедельник.",
                },
                {
                    "category": "question",
                    "text": "По бюджету всё ещё нужен ответ финансистов.",
                    "previous_id": "segment:0",
                    "previous_quote": "Вопрос бюджета отложили до ответа финансистов.",
                    "current_id": None,
                    "current_quote": None,
                },
            ]
        )


async def test_briefing_requires_both_host_access_and_explicit_sharing(env):
    previous, _ = await closed_room(env)
    current = await room(env)
    path = f"{BASE}/{current['room']['id']}/briefing"
    body = {
        "previous_id": previous["room"]["id"],
        "previous_token": "x" * 32,
        "share_with_participants": True,
    }
    assert (await env["client"].put(path, headers=auth(current), json=body)).status_code == 403
    body["previous_token"] = previous["token"]
    body["share_with_participants"] = False
    assert (await env["client"].put(path, headers=auth(current), json=body)).status_code == 422
    assert (await setup(env, current, previous)).status_code == 202
    assert (await env["client"].get(path)).status_code == 401
    guest = (
        await env["client"].post(
            f"{BASE}/{current['room']['id']}/join",
            json={"invite": current["invite"], "name": "Коллега", "consent": True},
        )
    ).json()
    assert (await env["client"].get(path, headers=auth(guest))).status_code == 200
    assert (
        await env["client"].patch(path, headers=auth(guest), json={"updates": "Изменения"})
    ).status_code == 403
    live = await room(env)
    assert (await setup(env, current, live)).status_code == 409


async def test_real_dates_supported_categories_shared_output_and_invalidation(env):
    previous, task_id = await closed_room(env)
    current = await room(env)
    async with env["factory"]() as s:
        task = await s.get(Task, task_id)
        task.deadline = utcnow() - timedelta(hours=1)
        await s.commit()
    assert (await setup(env, current, previous)).status_code == 202
    processor = BriefingProcessor(env["factory"], env["settings"], Model())
    assert await processor.once()
    path = f"{BASE}/{current['room']['id']}/briefing"
    response = (await env["client"].get(path, headers=auth(current))).json()
    assert response["status"] == "ready" and not response["stale"]
    items = response["result"]["items"]
    assert {i["category"] for i in items} == {"deadline", "risk", "decision", "question"}
    assert sum(len(i["text"].split()) for i in items) <= 60
    assert all(i["evidence"] for i in items)
    async with env["factory"]() as s:
        task = await s.get(Task, task_id)
        task.status = TaskStatus.COMPLETED
        await s.commit()
    stale = (await env["client"].get(path, headers=auth(current))).json()
    assert stale["stale"] and stale["result"]["items"] == []
    assert (
        await env["client"].patch(path, headers=auth(current), json={"updates": ""})
    ).status_code == 202


async def test_no_unsupported_quotes_or_wrong_source_side(env):
    data = {
        "sources": [{"id": "segment:0", "side": "previous", "label": "Прошлый созвон", "text": OLD}]
    }
    analysis = await Model().structured({}, None, "")
    assert [x["category"] for x in validate_items(analysis, data)] == ["question"]
    analysis.items[-1].previous_quote = "Невыдуманный бюджет 1 миллион"
    assert validate_items(analysis, data) == []


async def test_old_meeting_without_baseline_does_not_invent_deadline_change(env):
    previous, task_id = await closed_room(env)
    current = await room(env)
    async with env["factory"]() as s:
        old = await s.get(Conference, UUID(previous["room"]["id"]))
        old.baseline_tasks = None
        task = await s.get(Task, task_id)
        task.deadline = utcnow() - timedelta(days=1)
        await s.commit()
    await setup(env, current, previous, "")
    async with env["factory"]() as s:
        b = await s.get(ConferenceBriefing, UUID(current["room"]["id"]))
        data = await inputs(s, b)
        assert data["deadlines"] == []
        assert any("нет снимка" in w for w in data["warnings"])


async def test_model_failure_keeps_real_deadlines_and_allows_retry(env):
    previous, task_id = await closed_room(env)
    current = await room(env)
    async with env["factory"]() as s:
        task = await s.get(Task, task_id)
        task.deadline = utcnow() - timedelta(hours=1)
        await s.commit()
    await setup(env, current, previous)

    class Unavailable:
        async def structured(self, *args):
            raise ConnectionError()

    await BriefingProcessor(env["factory"], env["settings"], Unavailable()).once()
    path = f"{BASE}/{current['room']['id']}/briefing"
    result = (await env["client"].get(path, headers=auth(current))).json()
    assert result["status"] == "error"
    assert [i["category"] for i in result["result"]["items"]] == ["deadline"]
    assert (
        await env["client"].patch(path, headers=auth(current), json={"updates": NEW})
    ).status_code == 202
    assert await BriefingProcessor(env["factory"], env["settings"], Model()).once()


async def test_edits_during_generation_cannot_overwrite_new_revision(env):
    previous, _ = await closed_room(env)
    current = await room(env)
    await setup(env, current, previous)

    class Changing(Model):
        async def structured(self, *args):
            await env["client"].patch(
                f"{BASE}/{current['room']['id']}/briefing",
                headers=auth(current),
                json={"updates": "Бюджет согласован."},
            )
            return await super().structured(*args)

    await BriefingProcessor(env["factory"], env["settings"], Changing()).once()
    async with env["factory"]() as s:
        b = await s.get(ConferenceBriefing, UUID(current["room"]["id"]))
        assert b.revision == 2 and b.status == "pending" and b.result is None


async def test_create_followup_and_end_snapshot_is_immutable(env):
    previous, task_id = await closed_room(env)
    r = await env["client"].post(
        BASE,
        json={
            "title": "Продолжение",
            "name": "Организатор",
            "consent": True,
            "previous_room_id": previous["room"]["id"],
            "previous_room_token": previous["token"],
            "share_previous_briefing": True,
        },
    )
    assert r.status_code == 201, r.text
    async with env["factory"]() as s:
        old = await s.get(Conference, UUID(previous["room"]["id"]))
        frozen = old.baseline_tasks
        task = await s.get(Task, task_id)
        task.deadline = utcnow() - timedelta(days=1)
        await s.commit()
    await env["client"].post(f"{BASE}/{previous['room']['id']}/end", headers=auth(previous))
    async with env["factory"]() as s:
        old = await s.get(Conference, UUID(previous["room"]["id"]))
        assert old.baseline_tasks == frozen
