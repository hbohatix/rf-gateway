# Software AMBE encoder (from OP25)

These files are a minimal copy of the software AMBE+2 / AMBE encoder from
[OP25](https://github.com/boatbod/op25) (`op25/gr-op25_repeater/lib`, commit
`d294cd9e7a02b54001008d60690434af0529a0eb`, October 2026):

| File | Origin | License |
|---|---|---|
| `ambe_encoder.cc`, `ambe_encoder.h` | OP25, Max H. Parke KA1RBI | GPL-3.0-or-later |
| `ambe.c`, `ambe.h`, `ambe3600x2250_const.h`, `ambe3600x2400_const.h` | OP25 / mbelib | GPL-3.0-or-later / ISC |
| `mbelib.c`, `mbelib.h`, `mbelib_const.h` | mbelib | ISC |

RF Gateway changes (marked "RF Gateway" in the sources):

- `encode()` returns the 49-bit AMBE+2 codeword and a new `encode_params()`
  returns the nine quantized parameters (used for D-Star AMBE 2400);
- the P25 Phase 2 interleaver (`p25p2_vf`) and `op25_imbe_frame.h`
  dependencies were removed — DMR, YSF, NXDN and D-Star FEC and
  interleaving are done in `backend/app/voice/fec.py`;
- an out-of-range pitch index now returns an error instead of printing to
  stderr (and the off-by-one table bound was fixed).

Speech analysis uses the `third_party/imbe_vocoder` submodule (also from
OP25). Build the shared library with:

```bash
bash backend/native/build_ambe_wrapper.sh
```

The software encoder lets RF Gateway generate DMR, System Fusion DN, NXDN
and D-Star voice without DVSI hardware. Audio quality is lower than a DVSI
AMBE-3000 chip; a ThumbDV/DV3000/AMBEServer can be selected instead for
AMBE+2 modes in the RF Output settings (experimental).

AMBE and AMBE+2 are DVSI technologies. Check the patent and licensing
situation for your use and jurisdiction.
