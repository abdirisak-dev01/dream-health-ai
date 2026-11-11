from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.core.db import get_sessionmaker
from app.reminders.models import Reminder
from app.reminders.service import is_due, run_due
from tests.test_messaging import verify_phone

CHI = ZoneInfo("America/Chicago")


def r(**kw):
    base = dict(label="lunch", at_time=time(12, 30), days=list(range(7)), channels=["in_app"], enabled=True,
                last_sent_on=None, skip_if_logged=True)
    base.update(kw)
    return Reminder(**base)


def test_is_due_window():
    mon = datetime(2026, 11, 9, 12, 30, tzinfo=CHI)  # a Monday
    assert is_due(r(), mon)
    assert not is_due(r(), mon.replace(hour=12, minute=29))
    assert is_due(r(), mon.replace(hour=14, minute=29))
    assert not is_due(r(), mon.replace(hour=14, minute=31))  # more than 2 h late: skip
    assert not is_due(r(days=[1, 2]), mon)  # not on Mondays
    assert not is_due(r(last_sent_on=mon.date()), mon)  # once a day
    assert not is_due(r(enabled=False), mon)


def _make(client, h, **body):
    data = {"label": "lunch", "at_time": "12:30", "channels": ["in_app"]} | body
    resp = client.post("/v1/reminders", headers=h, json=data)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _run_at(local: datetime) -> int:
    with get_sessionmaker()() as db:
        return run_due(db, now=local)


def _inbox(client, h, channel="in_app"):
    return [m for m in client.get("/v1/messages", params={"channel": channel}, headers=h).json()
            if m["kind"] == "reminder"]


def test_reminder_sends_once_in_users_time_zone(client, make_user):
    h = make_user(tz="Africa/Mogadishu")["headers"]
    _make(client, h)
    # 12:30 in Chicago is 21:30 in Mogadishu: not due
    assert _run_at(datetime(2026, 11, 9, 12, 30, tzinfo=CHI)) == 0
    moga = ZoneInfo("Africa/Mogadishu")
    assert _run_at(datetime(2026, 11, 9, 12, 31, tzinfo=moga)) == 1
    assert _run_at(datetime(2026, 11, 9, 12, 40, tzinfo=moga)) == 0  # not twice
    msgs = _inbox(client, h)
    assert len(msgs) == 1 and "log lunch" in msgs[0]["body"]


def test_reminder_skipped_when_meal_already_logged(client, make_user):
    h = make_user()["headers"]
    _make(client, h, at_time="23:58")
    p = client.post("/v1/meals/proposals", headers=h, json={"meal_type": "lunch", "text": "1 apple"}).json()
    client.post(f"/v1/meals/proposals/{p['id']}/confirm", headers=h)
    today = datetime.now(CHI).date()
    assert _run_at(datetime.combine(today, time(23, 59), tzinfo=CHI)) == 0
    assert _inbox(client, h) == []


def test_sms_reminder_needs_texts_on(client, make_user):
    h = make_user()["headers"]
    r1 = client.post("/v1/reminders", headers=h, json={"label": "dinner", "at_time": "18:00", "channels": ["sms"]})
    assert r1.status_code == 409
    verify_phone(client, h)
    rem = _make(client, h, label="dinner", at_time="18:00", channels=["in_app", "sms"])
    assert client.post(f"/v1/reminders/{rem['id']}/send-now", headers=h).json()["sent_on"] == ["in_app", "sms"]
    assert len(_inbox(client, h, "sms")) == 1

    # after STOP, SMS is skipped but in-app still arrives
    client.post("/v1/dev/fake-phone/send", headers=h, json={"text": "STOP"})
    assert client.post(f"/v1/reminders/{rem['id']}/send-now", headers=h).json()["sent_on"] == ["in_app"]


def test_reminder_crud_and_privacy(client, make_user):
    a, b = make_user(), make_user()
    rem = _make(client, a["headers"], days=[0, 0, 4], message="Drink water")
    assert rem["days"] == [0, 4] and rem["text"] == "Drink water"
    assert client.get("/v1/reminders", headers=b["headers"]).json() == []
    url = f"/v1/reminders/{rem['id']}"
    assert client.put(url, headers=b["headers"], json={"label": "lunch", "at_time": "13:00"}).status_code == 404
    assert client.delete(url, headers=b["headers"]).status_code == 404
    assert client.post(f"/v1/reminders/{rem['id']}/send-now", headers=b["headers"]).status_code == 404
    upd = client.put(f"/v1/reminders/{rem['id']}", headers=a["headers"],
                     json={"label": "lunch", "at_time": "13:15", "enabled": False}).json()
    assert upd["at_time"] == "13:15:00" and upd["enabled"] is False
    assert client.delete(f"/v1/reminders/{rem['id']}", headers=a["headers"]).status_code == 204
    assert client.post("/v1/reminders", headers=a["headers"],
                       json={"label": "lunch", "at_time": "12:00", "days": [9]}).status_code == 422
