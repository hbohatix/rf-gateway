"""Small streaming DSP blocks for demodulating remote SDR IQ to 8 kHz PCM.

Everything works on numpy blocks and keeps its own state, so consecutive
calls behave like one continuous stream.
"""

from __future__ import annotations

import math

import numpy as np


def design_lowpass(cutoff_hz: float, sample_rate: float, taps: int) -> np.ndarray:
    """Windowed-sinc low-pass FIR (Blackman), unity DC gain."""
    if taps % 2 == 0:
        taps += 1
    n = np.arange(taps) - (taps - 1) / 2.0
    fc = cutoff_hz / sample_rate
    h = np.sinc(2 * fc * n) * np.blackman(taps)
    return (h / np.sum(h)).astype(np.float32)


class FirDecimator:
    """FIR low-pass + integer decimation with carried-over history."""

    def __init__(self, taps: np.ndarray, decimation: int, *, complex_input: bool) -> None:
        self.taps = taps.astype(np.complex64 if complex_input else np.float32)
        self.decimation = int(decimation)
        dtype = np.complex64 if complex_input else np.float32
        self._history = np.zeros(len(taps) - 1, dtype=dtype)
        self._phase = 0

    def process(self, block: np.ndarray) -> np.ndarray:
        if block.size == 0:
            return block[:0]
        data = np.concatenate((self._history, block))
        filtered = np.convolve(data, self.taps, mode="valid")
        self._history = data[-(len(self.taps) - 1):] if len(self.taps) > 1 else data[:0]
        out = filtered[self._phase::self.decimation]
        consumed = len(filtered) - self._phase
        self._phase = (-consumed) % self.decimation
        return out


class FrequencyShifter:
    """Multiplies by exp(-j*2*pi*f*n/fs) with continuous phase."""

    def __init__(self, shift_hz: float, sample_rate: float) -> None:
        self._step = -2.0 * math.pi * shift_hz / sample_rate
        self._phase = 0.0

    def process(self, block: np.ndarray) -> np.ndarray:
        if self._step == 0.0:
            return block
        n = np.arange(block.size, dtype=np.float64)
        phase = self._phase + self._step * n
        self._phase = float((self._phase + self._step * block.size) % (2 * math.pi))
        return (block * np.exp(1j * phase).astype(np.complex64)).astype(np.complex64)


class FmDiscriminator:
    def __init__(self) -> None:
        self._last = np.complex64(1.0)

    def process(self, block: np.ndarray) -> np.ndarray:
        if block.size == 0:
            return np.zeros(0, dtype=np.float32)
        previous = np.concatenate(([self._last], block[:-1]))
        self._last = block[-1]
        return np.angle(block * np.conj(previous)).astype(np.float32)


class AmDetector:
    def __init__(self, sample_rate: float) -> None:
        self._dc = 0.0
        self._alpha = 1.0 - math.exp(-1.0 / (0.05 * sample_rate))

    def process(self, block: np.ndarray) -> np.ndarray:
        envelope = np.abs(block).astype(np.float32)
        out = np.empty_like(envelope)
        dc = self._dc
        alpha = self._alpha
        # Block-wise DC estimate is good enough for voice AM.
        for index, value in enumerate(envelope):
            dc += alpha * (value - dc)
            out[index] = value - dc
        self._dc = dc
        return out


class OnePoleHighPass:
    """Removes DC / CTCSS rumble below ``cutoff_hz``."""

    def __init__(self, cutoff_hz: float, sample_rate: float) -> None:
        rc = 1.0 / (2 * math.pi * cutoff_hz)
        dt = 1.0 / sample_rate
        self._a = rc / (rc + dt)
        self._x = 0.0
        self._y = 0.0

    def process(self, block: np.ndarray) -> np.ndarray:
        out = np.empty_like(block)
        a, x_prev, y_prev = self._a, self._x, self._y
        for index, x in enumerate(block):
            y_prev = a * (y_prev + x - x_prev)
            x_prev = x
            out[index] = y_prev
        self._x, self._y = x_prev, y_prev
        return out


class PowerSquelch:
    """Carrier squelch on channel power with an adaptive noise floor.

    ``threshold_db`` is either an absolute dBFS value or ``None`` for
    automatic mode (open at noise floor + ``auto_margin_db``).
    """

    def __init__(self, threshold_db: float | None = None, *, auto_margin_db: float = 10.0,
                 hysteresis_db: float = 3.0, hang_blocks: int = 8) -> None:
        self.threshold_db = threshold_db
        self.auto_margin_db = auto_margin_db
        self.hysteresis_db = hysteresis_db
        self.hang_blocks = hang_blocks
        self.noise_floor_db: float | None = None
        self.level_db: float | None = None
        self.open = False
        self._hang = 0

    def update(self, channel: np.ndarray) -> bool:
        power = float(np.mean(np.abs(channel) ** 2)) if channel.size else 0.0
        level = 10.0 * math.log10(power + 1e-12)
        self.level_db = level
        if self.noise_floor_db is None:
            self.noise_floor_db = level
        elif not self.open:
            # Track the floor quickly downwards and slowly upwards.
            rate = 0.2 if level < self.noise_floor_db else 0.01
            self.noise_floor_db += rate * (level - self.noise_floor_db)
        threshold = (
            self.threshold_db
            if self.threshold_db is not None
            else self.noise_floor_db + self.auto_margin_db
        )
        if self.open:
            if level < threshold - self.hysteresis_db:
                self._hang -= 1
                if self._hang <= 0:
                    self.open = False
            else:
                self._hang = self.hang_blocks
        elif level >= threshold:
            self.open = True
            self._hang = self.hang_blocks
        return self.open

    def status(self) -> dict:
        return {
            "open": self.open,
            "level_dbfs": None if self.level_db is None else round(self.level_db, 1),
            "noise_floor_dbfs": None if self.noise_floor_db is None else round(self.noise_floor_db, 1),
            "threshold_dbfs": self.threshold_db,
            "mode": "manual" if self.threshold_db is not None else "auto",
        }


class Resampler:
    """Linear-interpolating resampler with a pre-filter, for odd audio rates."""

    def __init__(self, input_rate: float, output_rate: float = 8000.0) -> None:
        self.input_rate = float(input_rate)
        self.output_rate = float(output_rate)
        self._step = self.input_rate / self.output_rate
        self._position = 0.0
        self._last = np.zeros(1, dtype=np.float32)
        self._filter = None
        if self.input_rate > self.output_rate:
            taps = design_lowpass(0.45 * self.output_rate, self.input_rate, 63)
            self._filter = FirDecimator(taps, 1, complex_input=False)

    def process(self, block: np.ndarray) -> np.ndarray:
        if block.size == 0:
            return np.zeros(0, dtype=np.float32)
        if self._filter is not None:
            block = self._filter.process(block.astype(np.float32))
        data = np.concatenate((self._last, block.astype(np.float32)))
        positions = np.arange(self._position, len(data) - 1, self._step)
        out = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
        if positions.size:
            next_position = positions[-1] + self._step
        else:
            next_position = self._position
        self._position = next_position - (len(data) - 1)
        self._last = data[-1:]
        return out


def float_to_pcm16(block: np.ndarray, gain: float = 1.0) -> bytes:
    scaled = np.clip(block * gain, -1.0, 1.0) * 32767.0
    return scaled.astype("<i2").tobytes()


class IqDemodulator:
    """IQ (complex64 at ``iq_rate``) -> 8 kHz float audio, with squelch."""

    AUDIO_RATE = 8000

    def __init__(
        self,
        *,
        iq_rate: int,
        offset_hz: float,
        modulation: str,
        channel_bandwidth_hz: float,
        squelch_db: float | None,
        deviation_hz: float = 2500.0,
        audio_gain: float = 1.0,
    ) -> None:
        if modulation not in ("nfm", "am"):
            raise ValueError("Demodulation supports nfm and am")
        self.modulation = modulation
        self.iq_rate = int(iq_rate)
        # Stage 1: channel filter + decimate to ~24 kHz (exact multiple of 8 kHz).
        self.channel_rate = 24000
        if self.iq_rate % self.channel_rate:
            raise ValueError("IQ sample rate must be a multiple of 24 kHz")
        decimation = self.iq_rate // self.channel_rate
        self.shifter = FrequencyShifter(offset_hz, self.iq_rate)
        channel_taps = design_lowpass(channel_bandwidth_hz / 2.0, self.iq_rate, 8 * decimation + 1)
        self.channel_filter = FirDecimator(channel_taps, decimation, complex_input=True)
        self.fm = FmDiscriminator()
        self.am = AmDetector(self.channel_rate)
        audio_taps = design_lowpass(3400.0, self.channel_rate, 63)
        self.audio_filter = FirDecimator(audio_taps, self.channel_rate // self.AUDIO_RATE, complex_input=False)
        self.highpass = OnePoleHighPass(300.0, self.AUDIO_RATE)
        self.squelch = PowerSquelch(squelch_db)
        self.deviation_hz = deviation_hz
        self.audio_gain = audio_gain
        self._am_agc = 0.1

    def process(self, iq: np.ndarray) -> np.ndarray:
        channel = self.channel_filter.process(self.shifter.process(iq))
        squelch_open = self.squelch.update(channel)
        if self.modulation == "nfm":
            demod = self.fm.process(channel)
            # Scale so the nominal deviation reaches about half of full scale.
            demod = demod * (0.5 / (2 * math.pi * self.deviation_hz / self.channel_rate))
        else:
            demod = self.am.process(channel)
            peak = float(np.max(np.abs(demod))) if demod.size else 0.0
            self._am_agc = max(0.9 * self._am_agc, peak, 1e-4)
            demod = demod * (0.5 / self._am_agc)
        audio = self.audio_filter.process(demod.astype(np.float32))
        audio = self.highpass.process(audio)
        if not squelch_open:
            audio = np.zeros_like(audio)
        return audio * self.audio_gain
