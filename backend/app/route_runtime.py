from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from app.audio_bridge import (
    get_audio_bridge_capability,
)


ACTIVE_STATES = {
    "starting",
    "ready",
    "running",
}


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


class RouteRuntimeManager:
    def __init__(
        self,
    ) -> None:
        self._lock = RLock()

        self._states: dict[
            str,
            dict[str, Any],
        ] = {}


    def _default_state(
        self,
        route_id: str,
    ) -> dict[str, Any]:
        return {
            "route_id":
                route_id,

            "state":
                "stopped",

            "active":
                False,

            "protocol":
                None,

            "source_id":
                None,

            "device_id":
                None,

            "source_ready":
                False,

            "rf_ready":
                False,

            "config_ready":
                False,

            "audio_bridge_ready":
                False,

            "audio_bridge":
                None,

            "runtime_ready":
                False,

            "blocked_reason":
                None,

            "error":
                None,

            "started_at":
                None,

            "updated_at":
                utc_now(),
        }


    def get(
        self,
        route_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(
                route_id
            )

            if state is None:
                return self._default_state(
                    route_id
                )

            return deepcopy(
                state
            )


    def list_states(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            return [
                deepcopy(
                    state
                )
                for state
                in self._states.values()
            ]


    def _set_state(
        self,
        route_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        state[
            "updated_at"
        ] = utc_now()

        with self._lock:
            self._states[
                route_id
            ] = deepcopy(
                state
            )

        return deepcopy(
            state
        )


    def _device_in_use(
        self,
        route_id: str,
        device_id: str,
    ) -> str | None:
        with self._lock:
            for (
                other_route_id,
                state,
            ) in self._states.items():
                if (
                    other_route_id
                    == route_id
                ):
                    continue

                if (
                    state.get(
                        "device_id"
                    )
                    != device_id
                ):
                    continue

                if (
                    state.get(
                        "state"
                    )
                    in ACTIVE_STATES
                ):
                    return (
                        other_route_id
                    )

        return None


    def preflight(
        self,
        route: dict[str, Any],
        source: dict[str, Any],
        device: dict[str, Any],
        mode_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        route_id = str(
            route.get(
                "id",
                "",
            )
        )

        if not route_id:
            raise ValueError(
                "Route has no id"
            )


        state = self._default_state(
            route_id
        )

        state[
            "protocol"
        ] = route.get(
            "protocol"
        )

        state[
            "source_id"
        ] = route.get(
            "source_id"
        )

        state[
            "device_id"
        ] = route.get(
            "device_id"
        )

        state[
            "state"
        ] = "starting"


        if not route.get(
            "enabled",
            False,
        ):
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = "route_disabled"

            return self._set_state(
                route_id,
                state,
            )


        source_probe = (
            source.get(
                "probe"
            )
            or {}
        )


        source_reachable = bool(
            source_probe.get(
                "reachable",
                False,
            )
        )


        audio_api_configured = bool(
            source_probe.get(
                "audio_api_configured",
                False,
            )
        )


        if not source_reachable:
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = "source_unreachable"

            return self._set_state(
                route_id,
                state,
            )


        if not audio_api_configured:
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = (
                "source_audio_not_configured"
            )

            return self._set_state(
                route_id,
                state,
            )


        state[
            "source_ready"
        ] = True


        device_available = bool(
            device.get(
                "available",
                False,
            )
        )


        device_probe_ok = bool(
            device.get(
                "probe_ok",
                False,
            )
        )


        if not (
            device_available
            and
            device_probe_ok
        ):
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = "rf_device_unavailable"

            return self._set_state(
                route_id,
                state,
            )


        state[
            "rf_ready"
        ] = True


        device_id = str(
            route.get(
                "device_id",
                "",
            )
        )


        conflicting_route_id = (
            self._device_in_use(
                route_id,
                device_id,
            )
        )


        if (
            conflicting_route_id
            is not None
        ):
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = (
                "rf_device_in_use"
            )

            state[
                "error"
            ] = (
                "RF device is already "
                "reserved by route "
                f"{conflicting_route_id}"
            )

            return self._set_state(
                route_id,
                state,
            )


        if mode_config is None:
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = (
                "protocol_config_missing"
            )

            return self._set_state(
                route_id,
                state,
            )


        state[
            "config_ready"
        ] = True


        protocol = str(
            route.get(
                "protocol",
                "",
            )
        ).lower()


        try:
            audio_bridge = (
                get_audio_bridge_capability(
                    protocol
                )
            )

        except ValueError as error:
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = (
                "audio_bridge_unsupported_protocol"
            )

            state[
                "error"
            ] = str(
                error
            )

            return self._set_state(
                route_id,
                state,
            )


        state[
            "audio_bridge"
        ] = audio_bridge


        audio_bridge_ready = bool(
            audio_bridge.get(
                "audio_input_supported",
                False,
            )
            and
            audio_bridge.get(
                "bridge_state"
            )
            == "ready"
        )


        if not audio_bridge_ready:
            state[
                "state"
            ] = "blocked"

            state[
                "blocked_reason"
            ] = (
                audio_bridge.get(
                    "blocking_reason"
                )
                or
                "audio_bridge_not_ready"
            )

            return self._set_state(
                route_id,
                state,
            )


        state[
            "audio_bridge_ready"
        ] = True


        state[
            "state"
        ] = "ready"

        state[
            "runtime_ready"
        ] = True

        state[
            "blocked_reason"
        ] = None

        state[
            "error"
        ] = None


        return self._set_state(
            route_id,
            state,
        )


    def mark_running(
        self,
        route_id: str,
    ) -> dict[str, Any]:
        state = self.get(
            route_id
        )


        if not state.get(
            "runtime_ready",
            False,
        ):
            raise RuntimeError(
                (
                    "Route runtime is not "
                    "ready"
                )
            )


        state[
            "state"
        ] = "running"

        state[
            "active"
        ] = True

        state[
            "started_at"
        ] = (
            state.get(
                "started_at"
            )
            or utc_now()
        )


        return self._set_state(
            route_id,
            state,
        )


    def mark_error(
        self,
        route_id: str,
        error: str,
    ) -> dict[str, Any]:
        state = self.get(
            route_id
        )

        state[
            "state"
        ] = "error"

        state[
            "active"
        ] = False

        state[
            "runtime_ready"
        ] = False

        state[
            "error"
        ] = error


        return self._set_state(
            route_id,
            state,
        )


    def stop(
        self,
        route_id: str,
    ) -> dict[str, Any]:
        state = self._default_state(
            route_id
        )

        return self._set_state(
            route_id,
            state,
        )


    def remove(
        self,
        route_id: str,
    ) -> None:
        with self._lock:
            self._states.pop(
                route_id,
                None,
            )


route_runtime_manager = (
    RouteRuntimeManager()
)