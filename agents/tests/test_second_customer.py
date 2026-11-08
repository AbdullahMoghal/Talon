"""The second customer's phone gets the campaign automatically: a reworded copy, then a follow-up Talon blocks."""

from __future__ import annotations

import re
import time

from talon_agents import live
from talon_agents.cli import DEMO_OPENER
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.live import LiveRunner
from talon_agents.llm import FakeLLM
from talon_agents.second_customer import reword
from talon_agents.spacetime import SpacetimeError

PAYMENT_TURN = "If your card doesn't work you can pay with Cash App $TollDeskPay"


class FakeClient:
    """Just enough of SpacetimeDB for the runner: scammer_send queues a row the next tick picks up."""

    def __init__(self, has_viewer_table: bool = True):
        self.calls: list[tuple] = []
        self.outbox: list[dict] = []
        self.viewers: list[dict] = []  # room_viewer rows
        self.has_viewer_table = has_viewer_table

    def open_phone(self, room: str) -> None:
        self.viewers.append({"room_code": room, "joined_at": int(time.time() * 1_000_000)})

    def call(self, reducer: str, *args) -> None:
        self.calls.append((reducer, args))
        if reducer == "scammer_send":
            self.outbox.append({"id": len(self.outbox) + 1, "room_code": args[0], "text": args[1], "status": "queued"})
        elif reducer == "set_scammer_message_status":
            for m in self.outbox:
                if m["id"] == args[0]:
                    m["status"] = args[1]

    def sql(self, query: str) -> list[dict]:
        if "FROM room_viewer" in query:
            if not self.has_viewer_table:
                raise SpacetimeError("sql: HTTP 400: no such table room_viewer")
            room = re.search(r"room_code = '([^']+)'", query).group(1)
            return [v for v in self.viewers if v["room_code"] == room]
        if "FROM scammer_message" in query:
            room = re.search(r"room_code = '([^']+)'", query).group(1)
            return [dict(m) for m in self.outbox if m["room_code"] == room and m["status"] == "queued"]
        return []


def make_runner(llm: FakeLLM | None = None, client: FakeClient | None = None) -> tuple[LiveRunner, FakeClient]:
    client = client or FakeClient()
    engine = TalonEngine(llm=llm or FakeLLM(), settings=Settings(api_key=None))
    runner = LiveRunner(client, engine, "T1", log=lambda *a: None)
    runner.setup()
    return runner, client


def inbox(runner: LiveRunner, customer_index: int) -> list[dict]:
    ref = runner.customers[customer_index]["id"]
    return [m for m in runner.engine.store.inbound_messages if m["customer_ref"] == ref]


def test_second_customer_is_texted_once_the_first_scam_is_identified():
    runner, client = make_runner()
    client.call("scammer_send", "T1", DEMO_OPENER)
    runner.tick()

    second = inbox(runner, 1)
    assert len(second) == 1, "the second phone should get the scam without anyone playing the scammer"
    assert second[0]["text"] != DEMO_OPENER and "ezpass-tollpay.example/pay" in second[0]["text"]
    assert second[0]["sender"] == runner.scammer_numbers["T1-2"] != runner.scammer_numbers["T1"]
    assert second[0]["status"] == "warned"  # triage caught it on its own

    # More texts from the scammer don't send the second customer more copies.
    client.call("scammer_send", "T1", "Final notice: pay your toll at ezpass-tollpay.example/pay")
    runner.tick()
    assert len(inbox(runner, 1)) == 1


def burn_first_campaign(runner: LiveRunner, client: FakeClient) -> None:
    client.call("scammer_send", "T1", DEMO_OPENER)
    runner.tick()
    sid = runner.engine.request_takeover(inbox(runner, 0)[0]["id"])[0]["id"]
    runner.engine.handle_scammer_message(sid, PAYMENT_TURN)
    assert runner.engine.store.campaigns[runner.engine.store.sessions[sid]["campaign_id"]]["status"] == "burned"


def test_follow_up_after_the_burn_is_blocked_by_the_extracted_handle(monkeypatch):
    runner, client = make_runner()
    client.open_phone("T1-2")  # someone scanned the second customer's QR code
    client.call("scammer_send", "T1", DEMO_OPENER)
    runner.tick()
    first = inbox(runner, 0)[0]
    sid = runner.engine.request_takeover(first["id"])[0]["id"]
    runner.engine.handle_scammer_message(sid, PAYMENT_TURN)
    campaign = runner.engine.store.campaigns[runner.engine.store.sessions[sid]["campaign_id"]]
    assert campaign["status"] == "burned"
    # The reworded copy shares the campaign's link, so the burn warns the second customer about it.
    b = runner.customers[1]["id"]
    assert any(a["customer_ref"] == b and a["kind"] == "warned" for a in runner.engine.store.customer_alerts)

    runner.tick()
    assert len(inbox(runner, 1)) == 1, "the follow-up waits a moment after the burn"

    monkeypatch.setattr(live, "FOLLOWUP_DELAY_S", 0)
    runner.tick()  # sends the follow-up
    runner.tick()  # processes it like any scammer text
    second = inbox(runner, 1)
    assert len(second) == 2
    assert "$TollDeskPay" in second[-1]["text"] and second[-1]["status"] == "blocked"

    runner.tick()
    assert len(inbox(runner, 1)) == 2  # one follow-up only


def test_no_second_customer_when_turned_off():
    client = FakeClient()
    runner = LiveRunner(client, TalonEngine(llm=FakeLLM(), settings=Settings(api_key=None)), "T1",
                        log=lambda *a: None, auto_second=False)
    runner.setup()
    client.call("scammer_send", "T1", DEMO_OPENER)
    runner.tick()
    assert inbox(runner, 1) == []


def test_rewording_that_drops_the_link_falls_back_to_the_original():
    llm = FakeLLM().script("scammer", "E-ZPass: you owe a toll, pay today or get a $50 fee")
    text, source = reword(llm, DEMO_OPENER)
    assert source == "fallback" and "ezpass-tollpay.example/pay" in text


def test_follow_up_waits_until_someone_opens_the_second_phone(monkeypatch):
    monkeypatch.setattr(live, "FOLLOWUP_DELAY_S", 0)
    runner, client = make_runner()
    burn_first_campaign(runner, client)
    for _ in range(3):
        runner.tick()
    assert len(inbox(runner, 1)) == 1, "no follow-up while nobody is watching the second phone"

    client.open_phone("T1-2")
    runner.tick()  # sends the follow-up
    runner.tick()  # processes it
    assert inbox(runner, 1)[-1]["status"] == "blocked"


def test_follow_up_waits_a_moment_after_the_phone_opens(monkeypatch):
    monkeypatch.setattr(live, "FOLLOWUP_DELAY_S", 60)
    runner, client = make_runner()
    burn_first_campaign(runner, client)
    client.open_phone("T1-2")
    runner.tick()
    runner.tick()
    assert len(inbox(runner, 1)) == 1  # the viewer gets a moment to look before it arrives


def test_follow_up_falls_back_to_the_timer_on_a_module_without_room_viewer(monkeypatch):
    monkeypatch.setattr(live, "FOLLOWUP_DELAY_S", 0)
    runner, client = make_runner(client=FakeClient(has_viewer_table=False))
    burn_first_campaign(runner, client)
    runner.tick()
    runner.tick()
    assert inbox(runner, 1)[-1]["status"] == "blocked"
