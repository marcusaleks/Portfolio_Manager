"""WriteQueueManager — centralises all DB writes to a single thread."""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable

log = logging.getLogger(__name__)


class WriteQueueManager:
    """Serialises all database write operations onto a dedicated thread.

    Usage::

        wq = WriteQueueManager(session_factory)
        wq.start()

        future = wq.submit(lambda session: session.add(obj))
        result  = future.result(timeout=10)   # blocks until done

        wq.stop()
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._queue: queue.Queue[tuple[Callable, Future] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="WriteQueueManager"
        )
        self._thread.start()
        log.info("WriteQueueManager started")

    def stop(self, timeout: float = 5.0) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put(None)  # sentinel
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("WriteQueueManager stopped")

    # ── public API ─────────────────────────────────────────────────────

    def submit(self, fn: Callable[[Any], Any]) -> Future:
        """Submit a callable that receives a *Session* and returns a value.

        The callable is executed inside a transaction; if it raises, the
        transaction is rolled back and the exception is set on the Future.
        """
        future: Future = Future()
        self._queue.put((fn, future))
        return future

    def submit_and_wait(self, fn: Callable[[Any], Any], timeout: float = 30.0) -> Any:
        """Convenience: submit + block until the result is available."""
        return self.submit(fn).result(timeout=timeout)

    # ── worker loop ────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, future = item
            session = self._session_factory()
            try:
                result = fn(session)
                session.commit()
                future.set_result(result)
            except Exception as exc:
                session.rollback()
                future.set_exception(exc)
                log.exception("WriteQueueManager error")
            finally:
                session.close()
