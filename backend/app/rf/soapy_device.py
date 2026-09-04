from __future__ import annotations

from typing import Any

import SoapySDR
from SoapySDR import (
    SOAPY_SDR_RX,
    SOAPY_SDR_TX,
)

from .soapysdr import (
    mark_driver_closed,
    mark_driver_open,
)


class SoapyRFDevice:
    def __init__(
        self,
        device_id: str,
        driver: str,
    ) -> None:
        self.device_id = device_id
        self.driver = driver

        self._device: Any | None = None


    @property
    def is_open(self) -> bool:
        return (
            self._device
            is not None
        )


    def open(self) -> None:
        if (
            self._device
            is not None
        ):
            return


        device = SoapySDR.Device(
            f"driver={self.driver}"
        )


        self._device = device


        mark_driver_open(
            self.driver
        )


    def close(self) -> None:
        if (
            self._device
            is None
        ):
            return


        self._device = None


        mark_driver_closed(
            self.driver
        )


    def _require_device(
        self,
    ) -> Any:
        if (
            self._device
            is None
        ):
            raise RuntimeError(
                "RF device is not open"
            )

        return self._device


    def get_info(
        self,
    ) -> dict[str, Any]:
        device = (
            self._require_device()
        )

        return {
            "device_id":
                self.device_id,

            "driver":
                device.getDriverKey(),

            "hardware":
                device.getHardwareKey(),

            "hardware_info":
                dict(
                    device.getHardwareInfo()
                ),
        }


    def set_rx_frequency(
        self,
        frequency_hz: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setFrequency(
            SOAPY_SDR_RX,
            channel,
            frequency_hz,
        )

        return float(
            device.getFrequency(
                SOAPY_SDR_RX,
                channel,
            )
        )


    def set_tx_frequency(
        self,
        frequency_hz: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setFrequency(
            SOAPY_SDR_TX,
            channel,
            frequency_hz,
        )

        return float(
            device.getFrequency(
                SOAPY_SDR_TX,
                channel,
            )
        )


    def set_rx_sample_rate(
        self,
        sample_rate: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setSampleRate(
            SOAPY_SDR_RX,
            channel,
            sample_rate,
        )

        return float(
            device.getSampleRate(
                SOAPY_SDR_RX,
                channel,
            )
        )


    def set_tx_sample_rate(
        self,
        sample_rate: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setSampleRate(
            SOAPY_SDR_TX,
            channel,
            sample_rate,
        )

        return float(
            device.getSampleRate(
                SOAPY_SDR_TX,
                channel,
            )
        )


    def set_rx_bandwidth(
        self,
        bandwidth_hz: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setBandwidth(
            SOAPY_SDR_RX,
            channel,
            bandwidth_hz,
        )

        return float(
            device.getBandwidth(
                SOAPY_SDR_RX,
                channel,
            )
        )


    def set_tx_bandwidth(
        self,
        bandwidth_hz: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setBandwidth(
            SOAPY_SDR_TX,
            channel,
            bandwidth_hz,
        )

        return float(
            device.getBandwidth(
                SOAPY_SDR_TX,
                channel,
            )
        )


    def set_rx_gain(
        self,
        gain_db: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setGain(
            SOAPY_SDR_RX,
            channel,
            gain_db,
        )

        return float(
            device.getGain(
                SOAPY_SDR_RX,
                channel,
            )
        )


    def set_tx_gain(
        self,
        gain_db: float,
        channel: int = 0,
    ) -> float:
        device = (
            self._require_device()
        )

        device.setGain(
            SOAPY_SDR_TX,
            channel,
            gain_db,
        )

        return float(
            device.getGain(
                SOAPY_SDR_TX,
                channel,
            )
        )


    def get_runtime_state(
        self,
        channel: int = 0,
    ) -> dict[str, Any]:
        device = (
            self._require_device()
        )


        return {
            "device_id":
                self.device_id,

            "driver":
                device.getDriverKey(),

            "rx": {
                "frequency_hz":
                    float(
                        device.getFrequency(
                            SOAPY_SDR_RX,
                            channel,
                        )
                    ),

                "sample_rate":
                    float(
                        device.getSampleRate(
                            SOAPY_SDR_RX,
                            channel,
                        )
                    ),

                "bandwidth_hz":
                    float(
                        device.getBandwidth(
                            SOAPY_SDR_RX,
                            channel,
                        )
                    ),

                "gain_db":
                    float(
                        device.getGain(
                            SOAPY_SDR_RX,
                            channel,
                        )
                    ),
            },

            "tx": {
                "frequency_hz":
                    float(
                        device.getFrequency(
                            SOAPY_SDR_TX,
                            channel,
                        )
                    ),

                "sample_rate":
                    float(
                        device.getSampleRate(
                            SOAPY_SDR_TX,
                            channel,
                        )
                    ),

                "bandwidth_hz":
                    float(
                        device.getBandwidth(
                            SOAPY_SDR_TX,
                            channel,
                        )
                    ),

                "gain_db":
                    float(
                        device.getGain(
                            SOAPY_SDR_TX,
                            channel,
                        )
                    ),
            },
        }
