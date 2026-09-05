from __future__ import annotations

import time

from copy import (
    deepcopy,
)

from datetime import (
    datetime,
    timezone,
)

from threading import (
    Event,
    RLock,
    Thread,
)

from typing import (
    Any,
)

from app.broadcastify_calls_client import (
    BroadcastifyCallsConfigurationError,
    BroadcastifyCallsError,
    BroadcastifyCallsHTTPError,
    BroadcastifyCallsClient,
    broadcastify_calls_client,
)

from app.call_queue import (
    CallQueueManager,
    call_queue_manager,
)


MIN_POLL_INTERVAL_SECONDS = 5.0

DEFAULT_POLL_INTERVAL_SECONDS = 5.0


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def unix_now() -> int:
    return int(
        time.time()
    )


class BroadcastifyWorker:
    def __init__(
        self,
        *,
        route_id: str,
        source: dict[str, Any],
        client:
            BroadcastifyCallsClient
            | None = None,
        queue_manager:
            CallQueueManager
            | None = None,
        poll_interval_seconds: float = (
            DEFAULT_POLL_INTERVAL_SECONDS
        ),
    ) -> None:
        if not route_id:
            raise ValueError(
                "route_id cannot be empty"
            )


        if (
            poll_interval_seconds
            <
            MIN_POLL_INTERVAL_SECONDS
        ):
            raise ValueError(
                (
                    "Broadcastify Live Calls "
                    "poll interval must be at "
                    "least "
                    f"{MIN_POLL_INTERVAL_SECONDS} "
                    "seconds"
                )
            )


        self.route_id = (
            route_id
        )


        self.source = (
            deepcopy(
                source
            )
        )


        self.client = (
            client
            or
            broadcastify_calls_client
        )


        self.queue_manager = (
            queue_manager
            or
            call_queue_manager
        )


        self.poll_interval_seconds = (
            float(
                poll_interval_seconds
            )
        )


        self._lock = (
            RLock()
        )


        self._stop_event = (
            Event()
        )


        self._thread: (
            Thread
            | None
        ) = None


        self._state: dict[
            str,
            Any,
        ] = {
            "route_id":
                self.route_id,

            "source_id":
                self.source.get(
                    "id"
                ),

            "playlist_uuid":
                self.source.get(
                    "playlist_uuid"
                ),

            "state":
                "stopped",

            "running":
                False,

            "poll_interval_seconds":
                self.poll_interval_seconds,

            "poll_count":
                0,

            "calls_received":
                0,

            "calls_enqueued":
                0,

            "calls_duplicates":
                0,

            "calls_dropped":
                0,

            "last_batch_count":
                0,

            "cursor_mode":
                "lastPos",

            "initial_pos":
                None,

            "last_pos":
                None,

            "next_pos":
                None,

            "polling_suspended":
                False,

            "polling_suspend_reason":
                None,

            "last_poll_at":
                None,

            "last_success_at":
                None,

            "last_error_at":
                None,

            "error":
                None,

            "started_at":
                None,

            "updated_at":
                utc_now(),
        }


    def _touch(
        self,
    ) -> None:
        self._state[
            "updated_at"
        ] = utc_now()


    def _set_state(
        self,
        state: str,
        *,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._state[
                "state"
            ] = state

            self._state[
                "error"
            ] = error


            if error:
                self._state[
                    "last_error_at"
                ] = utc_now()


            self._touch()


    def _suspend_polling(
        self,
        reason: str,
    ) -> None:
        with self._lock:
            self._state[
                "state"
            ] = "suspended"

            self._state[
                "polling_suspended"
            ] = True

            self._state[
                "polling_suspend_reason"
            ] = reason

            self._state[
                "error"
            ] = reason

            self._state[
                "last_error_at"
            ] = utc_now()

            self._touch()


    def _initialize_cursor(
        self,
    ) -> int:
        with self._lock:
            current = (
                self._state.get(
                    "next_pos"
                )
            )


            if current is not None:
                return int(
                    current
                )


            position = (
                unix_now()
            )


            self._state[
                "initial_pos"
            ] = position

            self._state[
                "next_pos"
            ] = position

            self._touch()


            return position


    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(
                self._state
            )


        queue = (
            self.queue_manager
            .get_queue(
                self.route_id
            )
        )


        state[
            "queue"
        ] = queue.stats()


        return state


    def _validate_source(
        self,
    ) -> str:
        source_type = (
            self.source.get(
                "type"
            )
        )


        provider = (
            self.source.get(
                "provider"
            )
        )


        if (
            source_type
            != "broadcastify_calls"
        ):
            raise ValueError(
                (
                    "Broadcastify worker requires "
                    "source type "
                    "broadcastify_calls"
                )
            )


        if (
            provider
            != "broadcastify"
        ):
            raise ValueError(
                (
                    "Broadcastify worker requires "
                    "provider broadcastify"
                )
            )


        playlist_uuid = (
            str(
                self.source.get(
                    "playlist_uuid"
                )
                or ""
            )
            .strip()
        )


        if not playlist_uuid:
            raise ValueError(
                (
                    "Source does not contain "
                    "playlist_uuid"
                )
            )


        return playlist_uuid


    def _configuration_status(
        self,
    ) -> dict[str, Any]:
        return (
            self.client
            .configuration_status()
        )


    def _poll_configuration_ready(
        self,
    ) -> bool:
        status = (
            self._configuration_status()
        )


        return bool(
            status.get(
                "configured",
                False,
            )
            and
            status.get(
                "live_calls_endpoint_configured",
                False,
            )
        )


    def _extract_calls(
        self,
        payload: Any,
    ) -> list[
        dict[str, Any]
    ]:
        if isinstance(
            payload,
            list,
        ):
            return [
                item
                for item in payload
                if isinstance(
                    item,
                    dict,
                )
            ]


        if not isinstance(
            payload,
            dict,
        ):
            return []


        direct_keys = (
            "calls",
            "items",
            "results",
        )


        for key in direct_keys:
            value = (
                payload.get(
                    key
                )
            )


            if isinstance(
                value,
                list,
            ):
                return [
                    item
                    for item in value
                    if isinstance(
                        item,
                        dict,
                    )
                ]


        data = (
            payload.get(
                "data"
            )
        )


        if isinstance(
            data,
            list,
        ):
            return [
                item
                for item in data
                if isinstance(
                    item,
                    dict,
                )
            ]


        if isinstance(
            data,
            dict,
        ):
            for key in direct_keys:
                value = (
                    data.get(
                        key
                    )
                )


                if isinstance(
                    value,
                    list,
                ):
                    return [
                        item
                        for item in value
                        if isinstance(
                            item,
                            dict,
                        )
                    ]


        return []


    def _extract_last_pos(
        self,
        payload: Any,
    ) -> int | None:
        if not isinstance(
            payload,
            dict,
        ):
            return None


        value = (
            payload.get(
                "lastPos"
            )
        )


        if value is None:
            data = (
                payload.get(
                    "data"
                )
            )


            if isinstance(
                data,
                dict,
            ):
                value = (
                    data.get(
                        "lastPos"
                    )
                )


        if value is None:
            return None


        try:
            position = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None


        if position <= 0:
            return None


        return position


    def _call_timestamp(
        self,
        call: dict[str, Any],
    ) -> int:
        try:
            return int(
                call.get(
                    "ts",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0


    def poll_once(
        self,
    ) -> dict[str, Any]:
        try:
            playlist_uuid = (
                self._validate_source()
            )

        except ValueError as error:
            self._set_state(
                "error",
                error=str(
                    error
                ),
            )

            return self.status()


        if not (
            self._poll_configuration_ready()
        ):
            self._set_state(
                (
                    "waiting_for_api_"
                    "configuration"
                )
            )

            return self.status()


        with self._lock:
            if self._state.get(
                "polling_suspended",
                False,
            ):
                self._state[
                    "state"
                ] = "suspended"

                self._touch()

                return self.status()


        requested_pos = (
            self._initialize_cursor()
        )


        with self._lock:
            self._state[
                "state"
            ] = "polling"

            self._state[
                "poll_count"
            ] += 1

            self._state[
                "last_poll_at"
            ] = utc_now()

            self._state[
                "error"
            ] = None

            self._touch()


        try:
            payload = (
                self.client
                .get_live_calls(
                    playlist_uuid=(
                        playlist_uuid
                    ),
                    extra_query={
                        "pos":
                            requested_pos,
                    },
                )
            )


            calls = (
                self._extract_calls(
                    payload
                )
            )


            response_last_pos = (
                self._extract_last_pos(
                    payload
                )
            )


            calls.sort(
                key=(
                    self._call_timestamp
                )
            )


            queue = (
                self.queue_manager
                .get_queue(
                    self.route_id
                )
            )


            enqueue_result = (
                queue.enqueue_many(
                    calls
                )
            )


            with self._lock:
                self._state[
                    "calls_received"
                ] += len(
                    calls
                )

                self._state[
                    "calls_enqueued"
                ] += int(
                    enqueue_result.get(
                        "accepted",
                        0,
                    )
                )

                self._state[
                    "calls_duplicates"
                ] += int(
                    enqueue_result.get(
                        "duplicates",
                        0,
                    )
                )

                self._state[
                    "calls_dropped"
                ] += int(
                    enqueue_result.get(
                        "dropped",
                        0,
                    )
                )

                self._state[
                    "last_batch_count"
                ] = len(
                    calls
                )


            if response_last_pos is None:
                reason = (
                    "Broadcastify Live Calls "
                    "response did not contain "
                    "a valid lastPos. Polling "
                    "was suspended to prevent "
                    "re-requesting billable "
                    "call records."
                )


                self._suspend_polling(
                    reason
                )


                return {
                    "worker":
                        self.status(),

                    "poll":
                        {
                            "playlist_uuid":
                                playlist_uuid,

                            "requested_pos":
                                requested_pos,

                            "last_pos":
                                None,

                            "calls_received":
                                len(
                                    calls
                                ),

                            "enqueue":
                                enqueue_result,

                            "suspended":
                                True,

                            "reason":
                                reason,
                        },
                }


            next_pos = max(
                requested_pos,
                response_last_pos,
            )


            with self._lock:
                self._state[
                    "last_pos"
                ] = response_last_pos

                self._state[
                    "next_pos"
                ] = next_pos

                self._state[
                    "state"
                ] = "idle"

                self._state[
                    "last_success_at"
                ] = utc_now()

                self._state[
                    "error"
                ] = None

                self._state[
                    "polling_suspend_reason"
                ] = None

                self._touch()


            return {
                "worker":
                    self.status(),

                "poll":
                    {
                        "playlist_uuid":
                            playlist_uuid,

                        "requested_pos":
                            requested_pos,

                        "last_pos":
                            response_last_pos,

                        "next_pos":
                            next_pos,

                        "calls_received":
                            len(
                                calls
                            ),

                        "enqueue":
                            enqueue_result,

                        "suspended":
                            False,
                    },
            }


        except BroadcastifyCallsConfigurationError as error:
            self._set_state(
                (
                    "waiting_for_api_"
                    "configuration"
                ),
                error=str(
                    error
                ),
            )


        except BroadcastifyCallsHTTPError as error:
            message = (
                "Broadcastify API HTTP "
                f"{error.status_code}"
            )


            if error.response_body:
                message += (
                    ": "
                    + error.response_body[
                        :500
                    ]
                )


            self._set_state(
                "error",
                error=message,
            )


        except BroadcastifyCallsError as error:
            self._set_state(
                "error",
                error=str(
                    error
                ),
            )


        except Exception as error:
            self._set_state(
                "error",
                error=(
                    "Unexpected worker error: "
                    f"{error}"
                ),
            )


        return self.status()


    def _run(
        self,
    ) -> None:
        while not (
            self._stop_event
            .is_set()
        ):
            self.poll_once()


            self._stop_event.wait(
                self.poll_interval_seconds
            )


        with self._lock:
            self._state[
                "state"
            ] = "stopped"

            self._state[
                "running"
            ] = False

            self._touch()


    def start(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                self._thread
                is not None
                and
                self._thread.is_alive()
            ):
                return self.status()


            self._stop_event.clear()


            initial_pos = (
                unix_now()
            )


            self._state[
                "running"
            ] = True

            self._state[
                "state"
            ] = "starting"

            self._state[
                "started_at"
            ] = utc_now()

            self._state[
                "initial_pos"
            ] = initial_pos

            self._state[
                "last_pos"
            ] = None

            self._state[
                "next_pos"
            ] = initial_pos

            self._state[
                "polling_suspended"
            ] = False

            self._state[
                "polling_suspend_reason"
            ] = None

            self._state[
                "last_batch_count"
            ] = 0

            self._state[
                "error"
            ] = None

            self._touch()


            self._thread = (
                Thread(
                    target=self._run,
                    name=(
                        "broadcastify-"
                        f"{self.route_id}"
                    ),
                    daemon=True,
                )
            )


            self._thread.start()


        return self.status()


    def stop(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            thread = (
                self._thread
            )


            if (
                thread is None
                or
                not thread.is_alive()
            ):
                self._state[
                    "running"
                ] = False

                self._state[
                    "state"
                ] = "stopped"

                self._touch()

                return self.status()


            self._state[
                "state"
            ] = "stopping"

            self._touch()


            self._stop_event.set()


        thread.join(
            timeout=(
                self.poll_interval_seconds
                + 2.0
            )
        )


        with self._lock:
            self._state[
                "running"
            ] = False

            self._state[
                "state"
            ] = "stopped"

            self._thread = None

            self._touch()


        return self.status()


class BroadcastifyWorkerManager:
    def __init__(
        self,
    ) -> None:
        self._lock = (
            RLock()
        )


        self._workers: dict[
            str,
            BroadcastifyWorker,
        ] = {}


    def create_or_get(
        self,
        *,
        route_id: str,
        source: dict[str, Any],
        poll_interval_seconds: float = (
            DEFAULT_POLL_INTERVAL_SECONDS
        ),
    ) -> BroadcastifyWorker:
        with self._lock:
            worker = (
                self._workers.get(
                    route_id
                )
            )


            if worker is not None:
                return worker


            worker = (
                BroadcastifyWorker(
                    route_id=route_id,
                    source=source,
                    poll_interval_seconds=(
                        poll_interval_seconds
                    ),
                )
            )


            self._workers[
                route_id
            ] = worker


            return worker


    def get(
        self,
        route_id: str,
    ) -> BroadcastifyWorker | None:
        with self._lock:
            return (
                self._workers.get(
                    route_id
                )
            )


    def stop(
        self,
        route_id: str,
    ) -> dict[str, Any] | None:
        worker = (
            self.get(
                route_id
            )
        )


        if worker is None:
            return None


        return worker.stop()


    def remove(
        self,
        route_id: str,
    ) -> bool:
        worker = (
            self.get(
                route_id
            )
        )


        if worker is None:
            return False


        worker.stop()


        with self._lock:
            self._workers.pop(
                route_id,
                None,
            )


        return True


    def stop_all(
        self,
    ) -> None:
        with self._lock:
            workers = list(
                self._workers
                .values()
            )


        for worker in workers:
            worker.stop()


    def list_status(
        self,
    ) -> list[
        dict[str, Any]
    ]:
        with self._lock:
            workers = list(
                self._workers
                .values()
            )


        return [
            worker.status()
            for worker in workers
        ]


broadcastify_worker_manager = (
    BroadcastifyWorkerManager()
)