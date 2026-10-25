// D-Star frame checker for RF Gateway development.
//
// Reads "H <41-byte header hex>" and "V <12-byte frame hex>" lines (DSRP
// payloads from app.voice.dstar) and checks them with MMDVM-Host code:
// header CRC (CCRC::checkCCITT161) and AMBE FEC (CAMBEFEC::regenerateDStar).
// Voice is decoded with mbelib (AMBE 3600x2400) into argv[1] (optional).

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>

#include "AMBEFEC.h"
#include "CRC.h"
#include "DStarHeader.h"
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

static const unsigned int A_TABLE[] = {0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 1, 7, 13, 19, 25, 31, 37, 43, 49, 55, 61, 67};
static const unsigned int B_TABLE[] = {2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68, 3, 9, 15, 21, 27, 33, 39, 45, 51, 57, 63, 69};
static const unsigned int C_TABLE[] = {4, 10, 16, 22, 28, 34, 40, 46, 52, 58, 64, 70, 5, 11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71};
static const int M_LIST[] = {0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29, 30, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 7, 8, 9, 10, 15, 16, 24, 25, 31, 32, 6};
static const int B_LENGTHS[] = {7, 4, 6, 9, 7, 4, 4, 4, 3};

static bool readBit(const unsigned char* data, unsigned int pos)
{
    return (data[pos >> 3] & (0x80U >> (pos & 7U))) != 0U;
}

static unsigned int prng(unsigned int seed)
{
    unsigned int value = 16U * seed, result = 0U;
    for (unsigned int i = 0U; i < 24U; i++) {
        value = (173U * value + 13849U) % 65536U;
        result = (result << 1) | (value >= 32768U ? 1U : 0U);
    }
    return result;
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

    unsigned int headers = 0U, badHeaders = 0U, frames = 0U, fecErrors = 0U;
    std::string kind, hex;
    while (std::cin >> kind >> hex) {
        if (kind == "H") {
            unsigned char header[41U];
            if (!parseHex(hex, header, 41U))
                return 2;
            headers++;
            if (!CCRC::checkCCITT161(header, 41U)) {
                badHeaders++;
                continue;
            }
            CDStarHeader h(header);
            unsigned char my1[8U], my2[4U], your[8U], r1[8U], r2[8U];
            h.getMyCall1(my1);
            h.getMyCall2(my2);
            h.getYourCall(your);
            h.getRPTCall1(r1);
            h.getRPTCall2(r2);
            std::printf("HEADER my=%8.8s/%4.4s your=%8.8s rpt1=%8.8s rpt2=%8.8s\n", my1, my2, your, r1, r2);
            continue;
        }

        unsigned char frame[12U];
        if (!parseHex(hex, frame, 12U))
            return 2;
        frames++;
        unsigned char copy[12U];
        std::memcpy(copy, frame, 12U);
        fecErrors += fec.regenerateDStar(copy);

        unsigned int a = 0U, b = 0U, c = 0U;
        for (unsigned int i = 0U; i < 24U; i++) {
            a = (a << 1) | (readBit(frame, A_TABLE[i]) ? 1U : 0U);
            b = (b << 1) | (readBit(frame, B_TABLE[i]) ? 1U : 0U);
            c = (c << 1) | (readBit(frame, C_TABLE[i]) ? 1U : 0U);
        }
        unsigned int u0 = 0U, u1 = 0U;
        CGolay24128::decode24128(a, u0);
        CGolay24128::decode24128(b ^ prng(u0), u1);

        int pbuf[48], tbuf[48];
        for (unsigned int i = 0U; i < 12U; i++) {
            pbuf[i] = (u0 >> (11U - i)) & 1U;
            pbuf[12U + i] = (u1 >> (11U - i)) & 1U;
        }
        for (unsigned int i = 0U; i < 24U; i++)
            pbuf[24U + i] = (c >> (23U - i)) & 1U;
        for (unsigned int i = 0U; i < 48U; i++)
            tbuf[M_LIST[i]] = pbuf[i];
        int params[9], pos = 0;
        for (unsigned int i = 0U; i < 9U; i++) {
            int value = 0;
            for (int j = 0; j < B_LENGTHS[i]; j++)
                value = (value << 1) | tbuf[pos++];
            params[i] = value;
        }
        mbe_dequantizeAmbe2400Parms(&cur, &prev, &errs, params);
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

    if (pcm != nullptr)
        std::fclose(pcm);
    std::printf("SUMMARY headers=%u bad_headers=%u frames=%u fec_errors=%u\n", headers, badHeaders, frames, fecErrors);
    return (badHeaders == 0U && fecErrors == 0U) ? 0 : 1;
}
