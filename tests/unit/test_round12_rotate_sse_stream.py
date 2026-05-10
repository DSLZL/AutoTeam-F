"""Round 12 F2 — Tests for /api/rotate/stream SSE event stream.

Covers:
1. Generator emits the initial ``retry`` + connected comment lines.
2. Mock state transitions produce well-formed ``data:`` event lines whose JSON
   payload contains email/from/to/reason/ts/extra fields.
3. When subscriber queue is empty within heartbeat window, generator yields
   ``: heartbeat`` comment line.
4. When generator is closed (FastAPI client disconnect simulation), the
   subscriber is removed from the machine.
"""

from __future__ import annotations

import json

from autoteam.account_state import AccountState, StateMachine
from autoteam.api import _build_sse_event_stream


def _drain(gen, n):
    """Pull at most ``n`` chunks from the generator; abort on StopIteration."""
    out: list[bytes] = []
    for _ in range(n):
        try:
            out.append(next(gen))
        except StopIteration:
            break
    return out


def test_sse_stream_initial_retry_and_comment():
    machine = StateMachine()
    gen, _q, _cb = _build_sse_event_stream(machine, heartbeat_seconds=60)
    chunks = _drain(gen, 2)
    assert chunks[0] == b"retry: 5000\n\n"
    assert chunks[1] == b": connected\n\n"
    gen.close()


def test_sse_stream_emits_transition_as_data_event():
    machine = StateMachine()
    gen, _q, _cb = _build_sse_event_stream(machine, heartbeat_seconds=60)

    # consume retry + connected
    _drain(gen, 2)

    machine.transition(
        "alice@example.com",
        AccountState.ACTIVE,
        reason="invited",
        from_state=None,
    )

    chunk = next(gen)
    assert chunk.startswith(b"data: ")
    assert chunk.endswith(b"\n\n")
    payload = json.loads(chunk[len(b"data: "):-2].decode("utf-8"))
    assert payload["email"] == "alice@example.com"
    assert payload["from"] is None
    assert payload["to"] == "active"
    assert payload["reason"] == "invited"
    assert isinstance(payload["ts"], float)
    assert payload["extra"] == {}
    gen.close()


def test_sse_stream_emits_heartbeat_on_empty_queue():
    machine = StateMachine()
    # heartbeat=0 → queue.get returns Empty immediately
    gen, _q, _cb = _build_sse_event_stream(machine, heartbeat_seconds=0)

    _drain(gen, 2)  # retry + connected
    chunk = next(gen)
    assert chunk == b": heartbeat\n\n"
    gen.close()


def test_sse_stream_unsubscribes_on_generator_close():
    machine = StateMachine()
    gen, _q, _cb = _build_sse_event_stream(machine, heartbeat_seconds=60)
    assert machine.subscriber_count() == 1

    _drain(gen, 2)
    gen.close()

    assert machine.subscriber_count() == 0


def test_sse_stream_emits_extra_payload_fields():
    machine = StateMachine()
    gen, _q, _cb = _build_sse_event_stream(machine, heartbeat_seconds=60)
    _drain(gen, 2)

    machine.transition(
        "bob@example.com",
        AccountState.STANDBY,
        reason="exhausted",
        extra={"task_id": "t-12345678", "deadline": 1234567890},
        from_state=AccountState.ACTIVE,
    )

    chunk = next(gen)
    payload = json.loads(chunk[len(b"data: "):-2].decode("utf-8"))
    assert payload["from"] == "active"
    assert payload["to"] == "standby"
    assert payload["extra"] == {"task_id": "t-12345678", "deadline": 1234567890}
    gen.close()
