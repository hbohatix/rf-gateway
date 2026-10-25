"""Forward error correction helpers shared by the DMR, YSF and NXDN framers.

The algorithms mirror the MMDVM-Host implementation (Golay24128.cpp,
AMBEFEC.cpp, BPTC19696.cpp, Hamming.cpp and RS129.cpp) so frames built
here pass MMDVM-Host's own regeneration checks unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence


# ---------------------------------------------------------------- bit helpers

def bytes_to_bits(data: bytes | bytearray) -> list[int]:
    """Big-endian bit expansion (MSB of byte 0 first)."""
    return [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]


def bits_to_bytes(bits: Sequence[int]) -> bytes:
    if len(bits) % 8:
        raise ValueError("bit count must be a multiple of 8")
    out = bytearray(len(bits) // 8)
    for index, bit in enumerate(bits):
        if bit:
            out[index >> 3] |= 0x80 >> (index & 7)
    return bytes(out)


def read_bit(data: bytes | bytearray, position: int) -> int:
    return (data[position >> 3] >> (7 - (position & 7))) & 1


def write_bit(data: bytearray, position: int, value: int) -> None:
    mask = 0x80 >> (position & 7)
    if value:
        data[position >> 3] |= mask
    else:
        data[position >> 3] &= ~mask & 0xFF


def int_to_bits(value: int, width: int) -> list[int]:
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def bits_to_int(bits: Sequence[int]) -> int:
    value = 0
    for bit in bits:
        value = (value << 1) | (1 if bit else 0)
    return value


# --------------------------------------------------------------------- Golay

GOLAY_23_12_POLY = 0xC75  # x^11 + x^10 + x^6 + x^5 + x^4 + x^2 + 1


def golay_23_12_encode(data: int) -> int:
    """Systematic Golay(23,12): returns (data << 11) | parity."""
    if not 0 <= data < 4096:
        raise ValueError("Golay(23,12) data must be 12 bits")
    remainder = data << 11
    for bit in range(22, 10, -1):
        if remainder & (1 << bit):
            remainder ^= GOLAY_23_12_POLY << (bit - 11)
    return (data << 11) | remainder


def golay_24_12_encode(data: int) -> int:
    """Extended Golay(24,12): Golay(23,12) plus an even overall parity bit."""
    code = golay_23_12_encode(data)
    parity = bin(code).count("1") & 1
    return (code << 1) | parity


def ambe_prng(seed: int) -> int:
    """24-bit pseudo-random scrambling sequence keyed on the A-block data.

    Matches MMDVM-Host's PRNG_TABLE and mbelib's demodulation sequence.
    """
    value = 16 * seed
    result = 0
    for _ in range(24):
        value = (173 * value + 13849) % 65536
        result = (result << 1) | (1 if value >= 32768 else 0)
    return result


# ------------------------------------------------- AMBE+2 (3600x2450) framing

DMR_A_TABLE = (0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44,
               48, 52, 56, 60, 64, 68, 1, 5, 9, 13, 17, 21)
DMR_B_TABLE = (25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69,
               2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42)
DMR_C_TABLE = (46, 50, 54, 58, 62, 66, 70, 3, 7, 11, 15, 19,
               23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71)


def ambe49_to_abc(bits49: Sequence[int]) -> tuple[int, int, int]:
    """Split a 49-bit AMBE+2 parameter vector (mbelib ``ambe_d`` order)
    into the FEC-protected A/B blocks and the unprotected C block, with FEC."""
    if len(bits49) != 49:
        raise ValueError("AMBE+2 frame must be 49 bits")
    a_data = bits_to_int(bits49[0:12])
    b_data = bits_to_int(bits49[12:24])
    c_data = bits_to_int(bits49[24:49])
    a = golay_24_12_encode(a_data)
    prn = ambe_prng(a_data) >> 1
    b = golay_23_12_encode(b_data) ^ prn
    return a, b, c_data


def abc_to_ambe49(a: int, b: int, c: int) -> list[int]:
    """Inverse of :func:`ambe49_to_abc` for error-free frames (tests/diagnostics)."""
    a_data = (a >> 12) & 0xFFF
    prn = ambe_prng(a_data) >> 1
    b_data = ((b ^ prn) >> 11) & 0xFFF
    return int_to_bits(a_data, 12) + int_to_bits(b_data, 12) + int_to_bits(c, 25)


def _dmr_frame_position(base: int, frame_index: int) -> int:
    if frame_index == 0:
        return base
    if frame_index == 1:
        position = base + 72
        return position + 48 if position >= 108 else position
    return base + 192


def place_dmr_ambe(burst: bytearray, frame_index: int, bits49: Sequence[int]) -> None:
    """Write one FEC-encoded AMBE+2 frame into a 33-byte DMR voice burst."""
    a, b, c = ambe49_to_abc(bits49)
    for i, base in enumerate(DMR_A_TABLE):
        write_bit(burst, _dmr_frame_position(base, frame_index), (a >> (23 - i)) & 1)
    for i, base in enumerate(DMR_B_TABLE):
        write_bit(burst, _dmr_frame_position(base, frame_index), (b >> (22 - i)) & 1)
    for i, base in enumerate(DMR_C_TABLE):
        write_bit(burst, _dmr_frame_position(base, frame_index), (c >> (24 - i)) & 1)


def extract_dmr_ambe(burst: bytes | bytearray, frame_index: int) -> tuple[int, int, int]:
    a = b = c = 0
    for base in DMR_A_TABLE:
        a = (a << 1) | read_bit(burst, _dmr_frame_position(base, frame_index))
    for base in DMR_B_TABLE:
        b = (b << 1) | read_bit(burst, _dmr_frame_position(base, frame_index))
    for base in DMR_C_TABLE:
        c = (c << 1) | read_bit(burst, _dmr_frame_position(base, frame_index))
    return a, b, c


def place_ambe72(frame: bytearray, bits49: Sequence[int]) -> None:
    """Single 72-bit AMBE+2 frame in the DMR/YSF-DN/NXDN bit order (9 bytes)."""
    a, b, c = ambe49_to_abc(bits49)
    for i, position in enumerate(DMR_A_TABLE):
        write_bit(frame, position, (a >> (23 - i)) & 1)
    for i, position in enumerate(DMR_B_TABLE):
        write_bit(frame, position, (b >> (22 - i)) & 1)
    for i, position in enumerate(DMR_C_TABLE):
        write_bit(frame, position, (c >> (24 - i)) & 1)


# ------------------------------------------------------------- Hamming codes

def hamming_15_11_3_encode(d: list[int]) -> None:
    """In-place row code used by BPTC(196,96) (MMDVM encode15113_2)."""
    d[11] = d[0] ^ d[1] ^ d[2] ^ d[3] ^ d[5] ^ d[7] ^ d[8]
    d[12] = d[1] ^ d[2] ^ d[3] ^ d[4] ^ d[6] ^ d[8] ^ d[9]
    d[13] = d[2] ^ d[3] ^ d[4] ^ d[5] ^ d[7] ^ d[9] ^ d[10]
    d[14] = d[0] ^ d[1] ^ d[2] ^ d[4] ^ d[6] ^ d[7] ^ d[10]


def hamming_13_9_3_encode(d: list[int]) -> None:
    """In-place column code used by BPTC(196,96) (MMDVM encode1393)."""
    d[9] = d[0] ^ d[1] ^ d[3] ^ d[5] ^ d[6]
    d[10] = d[0] ^ d[1] ^ d[2] ^ d[4] ^ d[6] ^ d[7]
    d[11] = d[0] ^ d[1] ^ d[2] ^ d[3] ^ d[5] ^ d[7] ^ d[8]
    d[12] = d[0] ^ d[2] ^ d[4] ^ d[5] ^ d[8]


# ------------------------------------------------------------ BPTC(196, 96)

_BPTC_DATA_RANGES = ((4, 11), (16, 26), (31, 41), (46, 56), (61, 71),
                     (76, 86), (91, 101), (106, 116), (121, 131))


def bptc_196_96_encode(payload: bytes, burst: bytearray) -> None:
    """Encode 12 bytes into the info fields of a 33-byte DMR data burst."""
    if len(payload) != 12:
        raise ValueError("BPTC(196,96) payload must be 12 bytes")
    data_bits = bytes_to_bits(payload)
    matrix = [0] * 196
    position = 0
    for start, end in _BPTC_DATA_RANGES:
        for index in range(start, end + 1):
            matrix[index] = data_bits[position]
            position += 1

    for row in range(9):
        start = row * 15 + 1
        segment = matrix[start:start + 15]
        hamming_15_11_3_encode(segment)
        matrix[start:start + 15] = segment

    for column in range(15):
        indices = [column + 1 + 15 * k for k in range(13)]
        segment = [matrix[i] for i in indices]
        hamming_13_9_3_encode(segment)
        for i, value in zip(indices, segment):
            matrix[i] = value

    raw = [0] * 196
    for index in range(196):
        raw[(index * 181) % 196] = matrix[index]

    first = bits_to_bytes(raw[0:96])
    burst[0:12] = first
    two_bits = bits_to_int(raw[96:100]) << 4  # bitsToByteBE of 8 bits, top 4 used
    burst[12] = (burst[12] & 0x3F) | (two_bits & 0xC0)
    burst[20] = (burst[20] & 0xFC) | ((two_bits >> 4) & 0x03)
    burst[21:33] = bits_to_bytes(raw[100:196])


# --------------------------------------------------------------- RS(12, 9)

def _build_gf_tables() -> tuple[list[int], list[int]]:
    exp = [0] * 512
    log = [0] * 256
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_GF_EXP, _GF_LOG = _build_gf_tables()
_RS129_POLY = (64, 56, 14, 1)


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def rs_12_9_parity(message: bytes) -> bytes:
    """Return the 3 parity bytes in transmission order (MMDVM parity[2..0])."""
    if len(message) != 9:
        raise ValueError("RS(12,9) message must be 9 bytes")
    parity = [0, 0, 0, 0]
    for byte in message:
        feedback = byte ^ parity[2]
        for j in range(2, 0, -1):
            parity[j] = parity[j - 1] ^ _gf_mul(_RS129_POLY[j], feedback)
        parity[0] = _gf_mul(_RS129_POLY[0], feedback)
    return bytes((parity[2], parity[1], parity[0]))


# ------------------------------------------------------- CRC-CCITT (YSF/NXDN)

def crc_ccitt162(data: bytes | bytearray) -> bytes:
    """MMDVM CCRC::addCCITT162: CRC-16/CCITT (0x1021), init 0, inverted.

    Returns the two CRC bytes in transmission order (high byte first).
    """
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    crc ^= 0xFFFF
    return bytes(((crc >> 8) & 0xFF, crc & 0xFF))


# ------------------------------------------ YSF rate 1/2 K=5 convolutional code

def ysf_convolve(data: bytes | bytearray, n_bits: int) -> bytearray:
    """MMDVM CYSFConvolution::encode: two output bits per input bit."""
    out = bytearray((2 * n_bits + 7) // 8)
    d1 = d2 = d3 = d4 = 0
    k = 0
    for i in range(n_bits):
        d = read_bit(data, i)
        g1 = (d + d3 + d4) & 1
        g2 = (d + d1 + d2 + d4) & 1
        d4, d3, d2, d1 = d3, d2, d1, d
        write_bit(out, k, g1)
        write_bit(out, k + 1, g2)
        k += 2
    return out


def crc_ccitt161(data: bytes | bytearray) -> bytes:
    """MMDVM CCRC::addCCITT161 (D-Star header CRC, CRC-16/X.25).

    Reflected 0x1021 (0x8408), init 0xFFFF, inverted, low byte first.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    crc ^= 0xFFFF
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


# ------------------------------------------------------ D-Star AMBE (2400)

DSTAR_A_TABLE = (0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66,
                 1, 7, 13, 19, 25, 31, 37, 43, 49, 55, 61, 67)
DSTAR_B_TABLE = (2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68,
                 3, 9, 15, 21, 27, 33, 39, 45, 51, 57, 63, 69)
DSTAR_C_TABLE = (4, 10, 16, 22, 28, 34, 40, 46, 52, 58, 64, 70,
                 5, 11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71)

# OP25 p25p2_vf.cc: parameter widths and bit priority order for AMBE 3600x2400.
DSTAR_B_LENGTHS = (7, 4, 6, 9, 7, 4, 4, 4, 3)
DSTAR_M_LIST = (0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30,
                33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 7, 8, 9, 10, 15, 16,
                24, 25, 31, 32, 6)


def dstar_params_to_bits(params: list[int]) -> list[int]:
    """Nine quantized AMBE 2400 parameters -> 48 priority-ordered bits."""
    if len(params) != 9:
        raise ValueError("D-Star AMBE needs nine parameters")
    tbuf: list[int] = []
    for value, width in zip(params, DSTAR_B_LENGTHS):
        tbuf.extend(int_to_bits(int(value) & ((1 << width) - 1), width))
    return [tbuf[index] for index in DSTAR_M_LIST]


def dstar_ambe_frame(bits48: list[int]) -> bytes:
    """48 data bits -> 9-byte FEC-protected D-Star AMBE frame (MMDVM byte order)."""
    if len(bits48) != 48:
        raise ValueError("D-Star AMBE frame must be 48 bits")
    u0 = bits_to_int(bits48[0:12])
    u1 = bits_to_int(bits48[12:24])
    c = bits_to_int(bits48[24:48])
    a = golay_24_12_encode(u0)
    b = golay_24_12_encode(u1) ^ ambe_prng(u0)
    frame = bytearray(9)
    for i in range(24):
        write_bit(frame, DSTAR_A_TABLE[i], (a >> (23 - i)) & 1)
        write_bit(frame, DSTAR_B_TABLE[i], (b >> (23 - i)) & 1)
        write_bit(frame, DSTAR_C_TABLE[i], (c >> (23 - i)) & 1)
    return bytes(frame)
