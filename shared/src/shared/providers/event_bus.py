"""EventBus seam (doc 1 §2.1).

Local implementations: InProcessEventBus (first-POC shortcut) and
RedisEventBus over Redis Streams (ADR-002). Kafka/SQS-SNS is doc 2.
"""

import json
import threading
from collections.abc import Callable
from typing import Any, Protocol


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

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        r = self._redis()
        try:
            r.xgroup_create(topic, self._group, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP = group already exists, fine
            if "BUSYGROUP" not in str(exc):
                raise

        def _loop() -> None:
            consumer = f"{self._group}-{threading.get_ident()}"
            while not self._stopping.is_set():
                entries = r.xreadgroup(
                    self._group, consumer, {topic: ">"}, count=10, block=self._block_ms
                )
                for _stream, messages in entries or []:
                    for msg_id, fields in messages:
                        try:
                            handler(json.loads(fields["payload"]))
                        finally:
                            r.xack(topic, self._group, msg_id)

        thread = threading.Thread(target=_loop, daemon=True, name=f"eventbus-{topic}")
        thread.start()
        self._threads.append(thread)

    def close(self) -> None:
        self._stopping.set()
