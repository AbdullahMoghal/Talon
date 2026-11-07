"""Caller-chosen ids for SpacetimeDB rows.

Reducers can't return values, so the pipeline picks conversation, turn and
campaign ids itself. An id is milliseconds since the epoch times 1000 plus a
counter: unique for up to 1000 ids per millisecond per process, roughly
time-ordered, and below 2**53 so JavaScript reads it exactly.
"""

import itertools
import threading
import time

_lock = threading.Lock()
_counter = itertools.count()
_last = (0, 0)


def new_id() -> int:
    global _last
    with _lock:
        ms = time.time_ns() // 1_000_000
        n = next(_counter) % 1000
        candidate = ms * 1000 + n
        # Never go backwards or repeat, even if the clock does.
        if candidate <= _last[0]:
            candidate = _last[0] + 1
        _last = (candidate, n)
        return candidate
