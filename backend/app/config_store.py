from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import yaml


BACKEND_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    BACKEND_DIR
    / "data"
)

CONFIG_PATH = (
    DATA_DIR
    / "mode_settings.yaml"
)


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "modes": {},
}


class ModeConfigStore:
    def __init__(
        self,
        path: Path = CONFIG_PATH,
    ) -> None:
        self.path = path
        self._lock = RLock()

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )


    def _load_unlocked(
        self,
    ) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(
                DEFAULT_CONFIG
            )

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = (
                    yaml.safe_load(file)
                    or {}
                )

        except Exception:
            return deepcopy(
                DEFAULT_CONFIG
            )


        if not isinstance(
            loaded,
            dict,
        ):
            return deepcopy(
                DEFAULT_CONFIG
            )


        loaded.setdefault(
            "version",
            1,
        )

        loaded.setdefault(
            "modes",
            {},
        )


        if not isinstance(
            loaded["modes"],
            dict,
        ):
            loaded["modes"] = {}


        return loaded


    def _save_unlocked(
        self,
        config: dict[str, Any],
    ) -> None:
        temporary_path = (
            self.path.with_suffix(
                ".yaml.tmp"
            )
        )


        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            yaml.safe_dump(
                config,
                file,
                sort_keys=False,
                allow_unicode=True,
            )


        temporary_path.replace(
            self.path
        )


    def get_all(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            return deepcopy(
                self._load_unlocked()
            )


    def get_mode(
        self,
        protocol: str,
    ) -> dict[str, Any] | None:
        protocol = (
            protocol
            .strip()
            .lower()
        )


        with self._lock:
            config = (
                self._load_unlocked()
            )

            mode = (
                config
                .get("modes", {})
                .get(protocol)
            )


            if mode is None:
                return None


            return deepcopy(
                mode
            )


    def save_mode(
        self,
        protocol: str,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        protocol = (
            protocol
            .strip()
            .lower()
        )


        clean_settings = {
            key: value
            for key, value
            in settings.items()
            if key not in {
                "protocol",
                "device_id",
            }
        }


        clean_settings[
            "updated_at"
        ] = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )


        with self._lock:
            config = (
                self._load_unlocked()
            )


            config[
                "modes"
            ][
                protocol
            ] = (
                clean_settings
            )


            self._save_unlocked(
                config
            )


            return deepcopy(
                clean_settings
            )


    # The transmit mode: every route is sent in this protocol with its
    # saved settings. Routes themselves do not carry a protocol.
    def get_active_protocol(self) -> str | None:
        with self._lock:
            value = self._load_unlocked().get("active_protocol")
        value = str(value or "").strip().lower()
        return value or None


    def set_active_protocol(self, protocol: str | None) -> str | None:
        value = str(protocol or "").strip().lower() or None
        self._set_value("active_protocol", value)
        return value


    def get_active_device(self) -> str | None:
        with self._lock:
            value = self._load_unlocked().get("active_device_id")
        return str(value) if value else None


    def set_active_device(self, device_id: str | None) -> None:
        self._set_value("active_device_id", device_id or None)


    def _set_value(self, key: str, value: Any) -> None:
        with self._lock:
            config = self._load_unlocked()
            config[key] = value
            self._save_unlocked(config)


mode_config_store = (
    ModeConfigStore()
)
