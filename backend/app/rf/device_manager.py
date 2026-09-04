from __future__ import annotations

from typing import Any

from .soapy_device import SoapyRFDevice
from .soapysdr import discover_soapy_devices


class RFDeviceManager:
    def __init__(self) -> None:
        self._devices: dict[
            str,
            SoapyRFDevice,
        ] = {}


    def _find_device(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        discovery = (
            discover_soapy_devices()
        )

        for device in discovery.get(
            "devices",
            [],
        ):
            if (
                device.get("id") ==
                device_id
            ):
                return device

        raise RuntimeError(
            f"RF device "
            f"{device_id} "
            f"was not found"
        )


    def open(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        if device_id in self._devices:
            device = (
                self._devices[
                    device_id
                ]
            )

            if device.is_open:
                return {
                    "device_id":
                        device_id,
                    "open": True,
                    "info":
                        device.get_info(),
                    "state":
                        device.get_runtime_state(),
                }


        discovered_device = (
            self._find_device(
                device_id
            )
        )


        if not discovered_device.get(
            "available",
            False,
        ):
            raise RuntimeError(
                f"RF device "
                f"{device_id} "
                f"is not available"
            )


        if not discovered_device.get(
            "probe_ok",
            False,
        ):
            raise RuntimeError(
                f"RF device "
                f"{device_id} "
                f"failed probe"
            )


        driver = str(
            discovered_device.get(
                "driver",
                "",
            )
        )


        if not driver:
            raise RuntimeError(
                f"RF device "
                f"{device_id} "
                f"has no driver"
            )


        device = SoapyRFDevice(
            device_id=device_id,
            driver=driver,
        )


        device.open()


        self._devices[
            device_id
        ] = device


        return {
            "device_id":
                device_id,
            "open": True,
            "info":
                device.get_info(),
            "state":
                device.get_runtime_state(),
        }


    def close(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        device = (
            self._devices.get(
                device_id
            )
        )


        if device is None:
            return {
                "device_id":
                    device_id,
                "open": False,
            }


        device.close()


        del self._devices[
            device_id
        ]


        return {
            "device_id":
                device_id,
            "open": False,
        }


    def get(
        self,
        device_id: str,
    ) -> SoapyRFDevice:
        device = (
            self._devices.get(
                device_id
            )
        )


        if (
            device is None
            or not device.is_open
        ):
            raise RuntimeError(
                f"RF device "
                f"{device_id} "
                f"is not open"
            )


        return device


    def get_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        device = (
            self._devices.get(
                device_id
            )
        )


        if (
            device is None
            or not device.is_open
        ):
            return {
                "device_id":
                    device_id,
                "open": False,
                "state": None,
            }


        return {
            "device_id":
                device_id,
            "open": True,
            "state":
                device.get_runtime_state(),
        }


    def close_all(
        self,
    ) -> None:
        device_ids = list(
            self._devices.keys()
        )


        for device_id in device_ids:
            try:
                self.close(
                    device_id
                )
            except Exception:
                pass


rf_device_manager = (
    RFDeviceManager()
)
