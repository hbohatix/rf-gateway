from __future__ import annotations

from collections import (
    deque,
)

from copy import (
    deepcopy,
)

from dataclasses import (
    dataclass,
)

from datetime import (
    datetime,
    timezone,
)

from threading import (
    RLock,
)

from typing import (
    Any,
)


DEFAULT_MAX_QUEUE_SIZE = 100

DEFAULT_MAX_SEEN_ITEMS = 2000


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


@dataclass(
    frozen=True,
)
class CallIdentity:
    group_id: str
    ts: int


    @property
    def key(
        self,
    ) -> str:
        return (
            f"{self.group_id}:"
            f"{self.ts}"
        )


class RouteCallQueue:
    def __init__(
        self,
        route_id: str,
        *,
        max_queue_size: int = (
            DEFAULT_MAX_QUEUE_SIZE
        ),
        max_seen_items: int = (
            DEFAULT_MAX_SEEN_ITEMS
        ),
    ) -> None:
        if not route_id:
            raise ValueError(
                "route_id cannot be empty"
            )


        if max_queue_size <= 0:
            raise ValueError(
                (
                    "max_queue_size must "
                    "be greater than zero"
                )
            )


        if max_seen_items <= 0:
            raise ValueError(
                (
                    "max_seen_items must "
                    "be greater than zero"
                )
            )


        self.route_id = (
            route_id
        )

        self.max_queue_size = (
            max_queue_size
        )

        self.max_seen_items = (
            max_seen_items
        )


        self._lock = (
            RLock()
        )


        self._queue: deque[
            dict[str, Any]
        ] = deque()


        self._seen_order: deque[
            str
        ] = deque()


        self._seen: set[
            str
        ] = set()


        self._total_enqueued = 0

        self._total_dequeued = 0

        self._total_duplicates = 0

        self._total_dropped = 0

        self._created_at = (
            utc_now()
        )

        self._updated_at = (
            self._created_at
        )


    def _touch(
        self,
    ) -> None:
        self._updated_at = (
            utc_now()
        )


    def _remember_seen(
        self,
        key: str,
    ) -> None:
        if key in self._seen:
            return


        self._seen.add(
            key
        )

        self._seen_order.append(
            key
        )


        while (
            len(
                self._seen_order
            )
            >
            self.max_seen_items
        ):
            oldest = (
                self._seen_order
                .popleft()
            )

            self._seen.discard(
                oldest
            )


    def _validate_call(
        self,
        call: dict[str, Any],
    ) -> CallIdentity:
        group_id_raw = (
            call.get(
                "group_id"
            )
            or
            call.get(
                "groupId"
            )
        )


        if not group_id_raw:
            raise ValueError(
                (
                    "Call does not contain "
                    "group_id/groupId"
                )
            )


        group_id = (
            str(
                group_id_raw
            )
            .strip()
        )


        if not group_id:
            raise ValueError(
                (
                    "Call group_id "
                    "cannot be empty"
                )
            )


        ts_raw = (
            call.get(
                "ts"
            )
        )


        if ts_raw is None:
            raise ValueError(
                (
                    "Call does not contain "
                    "ts"
                )
            )


        try:
            ts = int(
                ts_raw
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                (
                    "Call ts must be "
                    "an integer"
                )
            ) from error


        if ts <= 0:
            raise ValueError(
                (
                    "Call ts must be "
                    "greater than zero"
                )
            )


        return CallIdentity(
            group_id=group_id,
            ts=ts,
        )


    def enqueue(
        self,
        call: dict[str, Any],
    ) -> dict[str, Any]:
        identity = (
            self._validate_call(
                call
            )
        )


        with self._lock:
            if (
                identity.key
                in self._seen
            ):
                self._total_duplicates += 1

                self._touch()

                return {
                    "accepted":
                        False,

                    "duplicate":
                        True,

                    "dropped":
                        False,

                    "route_id":
                        self.route_id,

                    "call_key":
                        identity.key,

                    "queue_size":
                        len(
                            self._queue
                        ),
                }


            normalized = (
                deepcopy(
                    call
                )
            )


            normalized[
                "group_id"
            ] = (
                identity.group_id
            )


            normalized[
                "ts"
            ] = (
                identity.ts
            )


            normalized[
                "_queue"
            ] = {
                "route_id":
                    self.route_id,

                "call_key":
                    identity.key,

                "enqueued_at":
                    utc_now(),
            }


            dropped = False


            if (
                len(
                    self._queue
                )
                >=
                self.max_queue_size
            ):
                self._queue.popleft()

                self._total_dropped += 1

                dropped = True


            self._queue.append(
                normalized
            )


            self._remember_seen(
                identity.key
            )


            self._total_enqueued += 1

            self._touch()


            return {
                "accepted":
                    True,

                "duplicate":
                    False,

                "dropped":
                    dropped,

                "route_id":
                    self.route_id,

                "call_key":
                    identity.key,

                "queue_size":
                    len(
                        self._queue
                    ),
            }


    def enqueue_many(
        self,
        calls: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any]:
        accepted = 0

        duplicates = 0

        dropped = 0

        errors: list[
            dict[str, Any]
        ] = []


        for index, call in enumerate(
            calls
        ):
            try:
                result = (
                    self.enqueue(
                        call
                    )
                )

            except ValueError as error:
                errors.append(
                    {
                        "index":
                            index,

                        "error":
                            str(
                                error
                            ),
                    }
                )

                continue


            if result[
                "accepted"
            ]:
                accepted += 1


            if result[
                "duplicate"
            ]:
                duplicates += 1


            if result[
                "dropped"
            ]:
                dropped += 1


        return {
            "route_id":
                self.route_id,

            "input_count":
                len(
                    calls
                ),

            "accepted":
                accepted,

            "duplicates":
                duplicates,

            "dropped":
                dropped,

            "errors":
                errors,

            "queue_size":
                self.size(),
        }


    def pop_next(
        self,
    ) -> dict[str, Any] | None:
        with self._lock:
            if not self._queue:
                return None


            call = (
                self._queue
                .popleft()
            )


            self._total_dequeued += 1

            self._touch()


            return deepcopy(
                call
            )


    def peek(
        self,
    ) -> dict[str, Any] | None:
        with self._lock:
            if not self._queue:
                return None


            return deepcopy(
                self._queue[
                    0
                ]
            )


    def list_pending(
        self,
    ) -> list[
        dict[str, Any]
    ]:
        with self._lock:
            return [
                deepcopy(
                    call
                )
                for call
                in self._queue
            ]


    def size(
        self,
    ) -> int:
        with self._lock:
            return len(
                self._queue
            )


    def clear(
        self,
        *,
        clear_seen: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            removed = len(
                self._queue
            )


            self._queue.clear()


            if clear_seen:
                self._seen.clear()

                self._seen_order.clear()


            self._touch()


            return {
                "route_id":
                    self.route_id,

                "removed":
                    removed,

                "seen_cleared":
                    clear_seen,
            }


    def stats(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            return {
                "route_id":
                    self.route_id,

                "queue_size":
                    len(
                        self._queue
                    ),

                "max_queue_size":
                    self.max_queue_size,

                "seen_count":
                    len(
                        self._seen
                    ),

                "max_seen_items":
                    self.max_seen_items,

                "total_enqueued":
                    self._total_enqueued,

                "total_dequeued":
                    self._total_dequeued,

                "total_duplicates":
                    self._total_duplicates,

                "total_dropped":
                    self._total_dropped,

                "created_at":
                    self._created_at,

                "updated_at":
                    self._updated_at,
            }


class CallQueueManager:
    def __init__(
        self,
    ) -> None:
        self._lock = (
            RLock()
        )

        self._queues: dict[
            str,
            RouteCallQueue,
        ] = {}


    def get_queue(
        self,
        route_id: str,
    ) -> RouteCallQueue:
        if not route_id:
            raise ValueError(
                "route_id cannot be empty"
            )


        with self._lock:
            queue = (
                self._queues.get(
                    route_id
                )
            )


            if queue is None:
                queue = (
                    RouteCallQueue(
                        route_id
                    )
                )

                self._queues[
                    route_id
                ] = queue


            return queue


    def remove_queue(
        self,
        route_id: str,
    ) -> bool:
        with self._lock:
            return (
                self._queues.pop(
                    route_id,
                    None,
                )
                is not None
            )


    def list_stats(
        self,
    ) -> list[
        dict[str, Any]
    ]:
        with self._lock:
            queues = list(
                self._queues
                .values()
            )


        return [
            queue.stats()
            for queue in queues
        ]


    def clear_all(
        self,
        *,
        clear_seen: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            queues = list(
                self._queues
                .values()
            )


        removed = 0


        for queue in queues:
            result = (
                queue.clear(
                    clear_seen=(
                        clear_seen
                    )
                )
            )

            removed += int(
                result[
                    "removed"
                ]
            )


        return {
            "queue_count":
                len(
                    queues
                ),

            "removed":
                removed,

            "seen_cleared":
                clear_seen,
        }


call_queue_manager = (
    CallQueueManager()
)
