// DMR frame checker for RF Gateway development.
//
// Reads lines "H <hex>", "V <hex>" or "T <hex>" (33-byte DMR bursts as
// produced by app.voice.dmr) from stdin and validates them with the
// original MMDVM-Host code:
//   H/T  - CDMRFullLC::decode (BPTC(196,96) + RS(12,9) + CRC mask)
//   V    - CAMBEFEC::regenerateDMR bit-error count
// Voice frames are additionally decoded with mbelib and the synthesized
// 8 kHz S16LE audio is written to the file given as argv[1] (optional).

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>

#include "AMBEFEC.h"
#include "DMRDefines.h"
#include "DMRFullLC.h"
#include "DMRLC.h"
#include "Golay24128.h"
#include "Log.h"

extern "C" {
#include "mbelib.h"
#include "ambe.h"
}

void Log(unsigned int, const char* fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    std::fprintf(stderr, "[mmdvm] ");
    std::vfprintf(stderr, fmt, args);
    std::fprintf(stderr, "\n");
    va_end(args);
}
void LogInitialise(unsigned int, unsigned int) {}
void LogFinalise() {}
void WriteJSON(const std::string&, nlohmann::json&) {}

static const unsigned int A_TABLE[] = {0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44,
                                       48, 52, 56, 60, 64, 68, 1, 5, 9, 13, 17, 21};
static const unsigned int B_TABLE[] = {25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69,
                                       2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42};
static const unsigned int C_TABLE[] = {46, 50, 54, 58, 62, 66, 70, 3, 7, 11, 15, 19,
                                       23, 27, 31, 35, 39, 43, 47, 51, 55, 59, 63, 67, 71};

static bool readBit(const unsigned char* data, unsigned int pos)
{
    return (data[pos >> 3] & (0x80U >> (pos & 7U))) != 0U;
}

static unsigned int framePos(unsigned int base, unsigned int frame)
{
    if (frame == 0U)
        return base;
    if (frame == 1U) {
        unsigned int pos = base + 72U;
        return pos >= 108U ? pos + 48U : pos;
    }
    return base + 192U;
}

static unsigned int prng(unsigned int seed)
{
    unsigned int value = 16U * seed;
    unsigned int result = 0U;
    for (unsigned int i = 0U; i < 24U; i++) {
        value = (173U * value + 13849U) % 65536U;
        result = (result << 1) | (value >= 32768U ? 1U : 0U);
    }
    return result;
}

static void unpack49(const int bits[49], int b[9])
{
    b[0] = (bits[0] << 6) | (bits[1] << 5) | (bits[2] << 4) | (bits[3] << 3) | (bits[37] << 2) | (bits[38] << 1) | bits[39];
    b[1] = (bits[4] << 4) | (bits[5] << 3) | (bits[6] << 2) | (bits[7] << 1) | bits[35];
    b[2] = (bits[8] << 4) | (bits[9] << 3) | (bits[10] << 2) | (bits[11] << 1) | bits[36];
    b[3] = (bits[12] << 8) | (bits[13] << 7) | (bits[14] << 6) | (bits[15] << 5) | (bits[16] << 4) |
           (bits[17] << 3) | (bits[18] << 2) | (bits[19] << 1) | bits[40];
    b[4] = (bits[20] << 6) | (bits[21] << 5) | (bits[22] << 4) | (bits[23] << 3) | (bits[41] << 2) | (bits[42] << 1) | bits[43];
    b[5] = (bits[24] << 4) | (bits[25] << 3) | (bits[26] << 2) | (bits[27] << 1) | bits[44];
    b[6] = (bits[28] << 3) | (bits[29] << 2) | (bits[30] << 1) | bits[45];
    b[7] = (bits[31] << 3) | (bits[32] << 2) | (bits[33] << 1) | bits[46];
    b[8] = (bits[34] << 2) | (bits[47] << 1) | bits[48];
}

static bool parseHex(const std::string& hex, unsigned char* out, unsigned int length)
{
    if (hex.size() != length * 2U)
        return false;
    for (unsigned int i = 0U; i < length; i++)
        out[i] = (unsigned char)std::stoul(hex.substr(i * 2U, 2U), nullptr, 16);
    return true;
}

int main(int argc, char** argv)
{
    FILE* pcm = argc > 1 ? std::fopen(argv[1], "wb") : nullptr;

    mbe_parms cur, prev, prevEnh;
    mbe_errs errs;
    mbe_initMbeParms(&cur, &prev, &prevEnh);
    mbe_initErrParms(&errs);

    CAMBEFEC fec;
    unsigned int voiceBursts = 0U, totalErrors = 0U, headers = 0U, terminators = 0U, badLC = 0U;

    std::string kind, hex;
    while (std::cin >> kind >> hex) {
        unsigned char data[33U];
        if (!parseHex(hex, data, 33U)) {
            std::fprintf(stderr, "bad line\n");
            return 2;
        }
        if (kind == "H" || kind == "T") {
            CDMRFullLC fullLC;
            CDMRLC* lc = fullLC.decode(data, kind == "H" ? DT_VOICE_LC_HEADER : DT_TERMINATOR_WITH_LC);
            if (lc == nullptr) {
                badLC++;
                std::printf("%s LC INVALID\n", kind.c_str());
                continue;
            }
            std::printf("%s LC OK flco=%u src=%u dst=%u\n", kind.c_str(), (unsigned int)lc->getFLCO(), lc->getSrcId(), lc->getDstId());
            if (kind == "H")
                headers++;
            else
                terminators++;
            delete lc;
        } else if (kind == "V") {
            unsigned char copy[33U];
            std::memcpy(copy, data, 33U);
            totalErrors += fec.regenerateDMR(copy);
            voiceBursts++;

            for (unsigned int frame = 0U; frame < 3U; frame++) {
                unsigned int a = 0U, b = 0U, c = 0U;
                for (unsigned int i = 0U; i < 24U; i++)
                    a = (a << 1) | (readBit(data, framePos(A_TABLE[i], frame)) ? 1U : 0U);
                for (unsigned int i = 0U; i < 23U; i++)
                    b = (b << 1) | (readBit(data, framePos(B_TABLE[i], frame)) ? 1U : 0U);
                for (unsigned int i = 0U; i < 25U; i++)
                    c = (c << 1) | (readBit(data, framePos(C_TABLE[i], frame)) ? 1U : 0U);

                unsigned int aData = 0U;
                CGolay24128::decode24128(a, aData);
                unsigned int bData = CGolay24128::decode23127(b ^ (prng(aData) >> 1));

                int bits[49];
                for (unsigned int i = 0U; i < 12U; i++)
                    bits[i] = (aData >> (11U - i)) & 1U;
                for (unsigned int i = 0U; i < 12U; i++)
                    bits[12U + i] = (bData >> (11U - i)) & 1U;
                for (unsigned int i = 0U; i < 25U; i++)
                    bits[24U + i] = (c >> (24U - i)) & 1U;

                int params[9];
                unpack49(bits, params);
                mbe_dequantizeAmbe2250Parms(&cur, &prev, &errs, params);
                short audio[160];
                {
                // Unity gain (mbe_synthesizeSpeech applies a fixed x7) so the
                // decoded level can be compared with the encoder input.
                float audiof[160];
                mbe_synthesizeSpeechf(audiof, &cur, &prev, 3);
                for (unsigned int k = 0U; k < 160U; k++) {
                    float v = audiof[k];
                    audio[k] = (short)(v > 32760.0F ? 32760.0F : (v < -32760.0F ? -32760.0F : v));
                }
            }
                mbe_moveMbeParms(&cur, &prev);
                if (pcm != nullptr)
                    std::fwrite(audio, sizeof(short), 160U, pcm);
            }
        }
    }

    if (pcm != nullptr)
        std::fclose(pcm);

    std::printf("SUMMARY headers=%u terminators=%u bad_lc=%u voice_bursts=%u fec_errors=%u\n",
                headers, terminators, badLC, voiceBursts, totalErrors);
    return (badLC == 0U && totalErrors == 0U) ? 0 : 1;
}
