"""EventBus seam (doc 1 §2.1).

Local implementations: InProcessEventBus (first-POC shortcut) and
RedisEventBus over Redis Streams (ADR-002). Kafka/SQS-SNS is doc 2.
"""

import json
import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol

_log = logging.getLogger("shared.event_bus")


class EventBus(Protocol):
    def publish(self, topic: str, payload: dict) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None: ...


class InProcessEventBus:
    """Synchronous fan-out inside one process — the first-POC shortcut."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[dict], None]]] = {}

    def publish(self, topic: str, payload: dict) -> None:
        for handler in self._handlers.get(topic, []):
            handler(payload)

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)


class RedisEventBus:
    """Redis Streams transport: XADD to publish, consumer group to subscribe."""

    def __init__(self, url: str, consumer_group: str = "forecast", block_ms: int = 1000):
        self._url = url
        self._group = consumer_group
        self._block_ms = block_ms
        self._client: Any = None
        self._threads: list[threading.Thread] = []
        self._stopping = threading.Event()

    def _redis(self) -> Any:
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        return self._client

    def publish(self, topic: str, payload: dict) -> None:
        self._redis().xadd(topic, {"payload": json.dumps(payload, default=str)})

    def _ensure_group(self, topic: str) -> None:
        try:
            self._redis().xgroup_create(topic, self._group, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP = group already exists, fine
            if "BUSYGROUP" not in str(exc):
                raise

    def consume_batch(self, topic: str, consumer: str, handler: Callable[[dict], None]) -> int:
        """Read + handle + ack one batch. Split out so the loop's error
        handling is testable without a live broker. Returns messages handled."""
        r = self._redis()
        entries = r.xreadgroup(self._group, consumer, {topic: ">"}, count=10, block=self._block_ms)
        handled = 0
        for _stream, messages in entries or []:
            for msg_id, fields in messages:
                try:
                    handler(json.loads(fields["payload"]))
                except Exception:  # noqa: BLE001 — a bad handler must not kill the consumer
                    _log.exception("event handler failed for %s", topic)
                finally:
                    r.xack(topic, self._group, msg_id)
                    handled += 1
        return handled

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._ensure_group(topic)

        def _loop() -> None:
            consumer = f"{self._group}-{threading.get_ident()}"
            while not self._stopping.is_set():
                try:
                    self.consume_batch(topic, consumer, handler)
                except Exception as exc:  # noqa: BLE001 — transient broker outage
                    # The consumer thread must survive a Redis blip or restart:
                    # log, wait, re-ensure the group (streams may be gone after
                    # an unpersisted restart), and keep reading.
                    _log.warning("event bus read failed on %s; retrying: %s", topic, exc)
                    self._stopping.wait(1.0)
                    try:
                        self._ensure_group(topic)
                    except Exception:  # noqa: BLE001 — still down; next loop retries
                        pass

        thread = threading.Thread(target=_loop, daemon=True, name=f"eventbus-{topic}")
        thread.start()
        self._threads.append(thread)

    def close(self) -> None:
        self._stopping.set()
