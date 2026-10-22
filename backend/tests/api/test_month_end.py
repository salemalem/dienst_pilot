"""Month end, reminders, the nightly chain check and recovery of interrupted runs (Phase 9)."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from dienstpilot import worker
from dienstpilot.planning import service as planning
from dienstpilot.shared.events.consumer import consume
from dienstpilot.shared.events.relay import relay
from dienstpilot.shared.events.stream import MemoryStream
from dienstpilot.shared.settings import DEMO_NOW, TZ
from dienstpilot.workflows.handlers import CONSUMERS

pytestmark = pytest.mark.db
NOV_2 = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)


def _jump(client: Any, login: Any, clock: Any, to: datetime) -> None:
    clock.value = to
    assert client.get("/oversight/months", headers=login("vogel")).status_code == 200


def test_the_report_is_prepared_by_itself_once_the_month_is_over(
    client: Any, login: Any, clock: Any
) -> None:
    assert client.get("/oversight/months", headers=login("vogel")).json() == []
    assert client.get("/oversight/months/2026-10/report", headers=login("vogel")).status_code == 404
    _jump(client, login, clock, NOV_2)
    months = client.get("/oversight/months", headers=login("vogel")).json()
    assert months == [{"roster_month": "2026-10-01", "status": "prepared"}]
    r = client.get("/oversight/months/2026-10/report", headers=login("vogel")).json()
    assert r["status"] == "prepared" and r["payroll_released"] is False
    assert r["people"] and len(r["report_hash"]) == 64
    # The numbers are the screens' numbers.
    hours = client.get("/compliance/hours?month=2026-10", headers=login("vogel")).json()
    mine = {p["staff_id"]: p for p in r["people"]}
    for p in hours["people"]:
        assert mine[p["staff_id"]]["overtime_hours"] == p["overtime_hours"]
        assert mine[p["staff_id"]]["planned_hours"] == p["planned_hours"]
    assert r["total_overtime_hours"] == hours["total_overtime_hours"]
    assert r["rest_violations_total"] == hours["rest_violations_total"]
    assert r["narrative"]["engine"] == "stand-in" and "Platzhalter" in r["narrative"]["text"]
    assert r["decision_trail"] and all(
        set(e) == {"seq", "at", "actor", "action", "subject_type"} for e in r["decision_trail"]
    )
    assert "category" not in str(r)


def test_payroll_is_released_only_when_the_planner_closes_the_month(
    client: Any, login: Any, clock: Any, app_factory: Any
) -> None:
    _jump(client, login, clock, NOV_2)
    vogel, brandt = login("vogel"), login("brandt")
    assert client.get("/oversight/months/2026-10/payroll", headers=vogel).status_code == 409
    assert client.post("/planner/months/2026-10/close", headers=vogel).status_code == 403
    assert client.post("/planner/months/2026-09/close", headers=brandt).status_code == 404
    closed = client.post("/planner/months/2026-10/close", headers=brandt)
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert client.post("/planner/months/2026-10/close", headers=brandt).status_code == 409
    pay = client.get("/oversight/months/2026-10/payroll", headers=vogel).json()
    assert pay["rows"] and {"name", "worked_hours", "overtime_hours", "nights"} <= set(
        pay["rows"][0]
    )
    csv = client.get("/oversight/months/2026-10/payroll?format=csv", headers=vogel)
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0].startswith("staff_id;name;")
    assert len(csv.text.splitlines()) == len(pay["rows"]) + 1
    assert client.get("/oversight/months/2026-10/payroll", headers=login("kaya")).status_code == 403
    # Audited, and the stored report did not change when it was closed.
    acts = [
        e["action"]
        for e in client.get("/audit/events?action=month&limit=10", headers=brandt).json()["events"]
    ]
    assert acts == ["month.closed", "month.report_prepared"]
    # MonthClosed reaches the consumer, which prepares the next month's workflow.
    conn = app_factory.conn
    with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
        stream = MemoryStream()
        relay(s, stream, NOV_2)
        for c in CONSUMERS:
            assert consume(s, stream, c, NOV_2) >= 1
        due = s.execute(
            text("SELECT due_at FROM workflow.timer WHERE kind = 'month.prepare' AND key LIKE :k"),
            {"k": "%:2026-11"},
        ).scalar_one()
    assert due.astimezone(TZ) == datetime(2026, 12, 1, 0, 0, tzinfo=TZ)


def test_the_stored_report_cannot_be_prepared_twice(client: Any, login: Any, clock: Any) -> None:
    _jump(client, login, clock, NOV_2)
    first = client.get("/oversight/months/2026-10/report", headers=login("vogel")).json()
    _jump(client, login, clock, NOV_2 + timedelta(days=3))
    again = client.get("/oversight/months/2026-10/report", headers=login("vogel")).json()
    assert first["report_hash"] == again["report_hash"]


def test_the_two_day_reminder_fires_once_and_is_audited_as_the_system(
    client: Any, login: Any, clock: Any
) -> None:
    detail = client.get("/planner/windows/2026-12", headers=login("brandt")).json()
    open_ids = {p["staff_id"] for p in detail["people"] if p["responded_at"] is None}
    assert open_ids
    # 7 days before the close is in the past on the demo date: only the 2-day reminder is armed.
    clock.value = datetime(2026, 10, 25, 9, 0, tzinfo=TZ)
    client.get("/oversight/months", headers=login("vogel"))
    events = client.get(
        "/audit/events?action=window.reminder_sent", headers=login("brandt")
    ).json()["events"]
    auto = [e for e in events if e["payload"].get("automatic")]
    assert len(auto) == 1 and auto[0]["payload"]["reminded"] == len(open_ids)
    assert auto[0]["payload"]["days_before_close"] == "2d" and auto[0]["actor"] == "System"
    clock.value = datetime(2026, 10, 26, 9, 0, tzinfo=TZ)  # moving on does not remind again
    client.get("/oversight/months", headers=login("vogel"))
    events = client.get(
        "/audit/events?action=window.reminder_sent", headers=login("brandt")
    ).json()["events"]
    assert len([e for e in events if e["payload"].get("automatic")]) == 1


def test_reminders_arrive_in_the_app_of_those_who_have_not_answered(
    client: Any, login: Any, clock: Any, as_staff: Any
) -> None:
    brandt = login("brandt")
    detail = client.get("/planner/windows/2026-12", headers=brandt).json()
    waiting = next(p for p in detail["people"] if p["responded_at"] is None)
    answered = next(p for p in detail["people"] if p["responded_at"] is not None)
    clock.value = datetime(2026, 10, 25, 9, 0, tzinfo=TZ)
    client.get("/oversight/months", headers=login("vogel"))
    mine = client.get("/me/notifications", headers=as_staff(waiting["staff_id"])).json()
    note = next(n for n in mine if n["kind"] == "window_reminder")
    assert note["data"]["roster_month"] == "2026-12-01"
    theirs = client.get("/me/notifications", headers=as_staff(answered["staff_id"])).json()
    assert not any(n["kind"] == "window_reminder" for n in theirs)


def test_closing_the_window_stops_the_reminders(client: Any, login: Any, clock: Any) -> None:
    assert client.post("/planner/windows/2026-12/close", headers=login("brandt")).status_code == 200
    clock.value = datetime(2026, 10, 25, 9, 0, tzinfo=TZ)
    client.get("/oversight/months", headers=login("vogel"))
    events = client.get(
        "/audit/events?action=window.reminder_sent", headers=login("brandt")
    ).json()["events"]
    assert not [e for e in events if e["payload"].get("automatic")]


def test_the_nightly_check_runs_on_the_demo_clock_and_collapses_skipped_nights(
    client: Any, login: Any, clock: Any, app_factory: Any
) -> None:
    clock.value = DEMO_NOW + timedelta(days=60)
    page = client.get("/audit/events?limit=1", headers=login("brandt")).json()  # settles first
    rows = app_factory.conn.execute(
        text("SELECT checked_at FROM audit.chain_check WHERE trigger = 'nightly' ORDER BY id")
    ).all()
    assert len(rows) == 2  # the first night, and one for all the nights the jump skipped
    assert rows[0][0].astimezone(TZ) == datetime(2026, 10, 21, 2, 0, tzinfo=TZ)
    assert rows[1][0].astimezone(TZ) == (DEMO_NOW + timedelta(days=60)).replace(
        hour=2, minute=0
    ).astimezone(TZ)
    assert page["chain"]["state"] == "verified" and page["chain"]["trigger"] == "nightly"


def test_without_a_nightly_check_the_log_turns_stale_not_verified(
    client: Any, login: Any, clock: Any, app_factory: Any
) -> None:
    app_factory.conn.execute(
        text("UPDATE workflow.timer SET cancelled_at = now() WHERE kind = 'audit.nightly'")
    )
    clock.value = DEMO_NOW + timedelta(days=3)
    page = client.get("/audit/events?limit=1", headers=login("brandt")).json()
    assert page["chain"]["state"] == "stale"


def test_interrupted_runs_are_failed_unless_their_job_is_still_queued(
    app_factory: Any, client: Any, login: Any
) -> None:
    with Session(bind=app_factory.conn, join_transaction_mode="create_savepoint") as s:
        rule = "2026-1"
        month = datetime(2027, 3, 1).date()
        staff = s.execute(text("SELECT id::text FROM organization.staff LIMIT 1")).scalar_one()
        running = planning.create_run(s, month, rule, staff, DEMO_NOW)
        queued_dead = planning.create_run(s, month, rule, staff, DEMO_NOW)
        queued_live = planning.create_run(s, month, rule, staff, DEMO_NOW)
        planning.set_run_status(s, running, "running")
        failed = planning.fail_interrupted(s, DEMO_NOW, keep={queued_live})
        assert set(failed) == {running, queued_dead}
        run = planning.run(s, running)
        assert run and run.status == "failed" and run.error == planning.WORKER_RESTARTED
        assert planning.run(s, queued_live).status == "queued"  # type: ignore[union-attr]


def test_the_worker_keeps_runs_whose_job_is_on_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(worker, "_recover", lambda live: seen.setdefault("live", live) and [])

    class FakeRedis:
        async def zrange(self, key: str, a: int, b: int) -> list[bytes]:
            return [b"run_roster:run-1:dep", b"check_leave:chk:dep"]

    asyncio.run(worker.startup({"redis": FakeRedis()}))
    assert seen["live"] == {"run-1"}


def test_the_job_timeout_marks_the_run_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "_fail_run", lambda run_id, err: marked.append((run_id, err)))
    calls = {"n": 0}

    async def to_thread(fn: Any, *a: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise asyncio.CancelledError  # arq cancelled the job after job_timeout
        return fn(*a)

    monkeypatch.setattr(asyncio, "to_thread", to_thread)

    async def go() -> None:
        with pytest.raises(asyncio.CancelledError):
            await worker.run_roster({}, "run-9", "dep")

    asyncio.run(go())
    assert marked == [("run-9", planning.JOB_TIMEOUT)]
