// YSF frame checker for RF Gateway development.
//
// Reads lines "Y <hex>" with 120-byte YSF frames (as sent in YSFD packets
// by app.voice.ysf) and validates them with MMDVM-Host's own decoders:
// FICH (Golay + convolution + CRC), header CSD, V/D mode 2 DCH and the
// VCH repetition code. Voice is decoded with mbelib and written as 8 kHz
// S16LE to argv[1] (optional).

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>

#include "Log.h"
#include "YSFDefines.h"
#include "YSFFICH.h"
#include "YSFPayload.h"

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

static const unsigned char WHITENING[] = {0x93U, 0xD7U, 0x51U, 0x21U, 0x9CU, 0x2FU, 0x6CU, 0xD0U, 0xEFU, 0x0FU, 0xF8U, 0x3DU, 0xF1U};

static bool readBit(const unsigned char* data, unsigned int pos)
{
    return (data[pos >> 3] & (0x80U >> (pos & 7U))) != 0U;
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

int main(int argc, char** argv)
{
    FILE* pcm = argc > 1 ? std::fopen(argv[1], "wb") : nullptr;
    mbe_parms cur, prev, prevEnh;
    mbe_errs errs;
    mbe_initMbeParms(&cur, &prev, &prevEnh);
    mbe_initErrParms(&errs);

    unsigned int frames = 0U, badFich = 0U, headers = 0U, badHeaders = 0U, terminators = 0U;
    unsigned int comms = 0U, dchOk = 0U, dchBad = 0U, vchErrors = 0U;

    std::string kind, hex;
    while (std::cin >> kind >> hex) {
        if (hex.size() != 240U)
            return 2;
        unsigned char data[120U];
        for (unsigned int i = 0U; i < 120U; i++)
            data[i] = (unsigned char)std::stoul(hex.substr(i * 2U, 2U), nullptr, 16);
        frames++;

        if (std::memcmp(data, YSF_SYNC_BYTES, YSF_SYNC_LENGTH_BYTES) != 0) {
            badFich++;
            continue;
        }

        CYSFFICH fich;
        if (!fich.decode(data)) {
            badFich++;
            continue;
        }

        CYSFPayload payload;
        unsigned char fi = fich.getFI();
        if (fi == YSF_FI_HEADER || fi == YSF_FI_TERMINATOR) {
            bool ok = payload.processHeaderData(data);
            if (fi == YSF_FI_HEADER)
                headers++;
            else
                terminators++;
            if (!ok)
                badHeaders++;
            else
                std::printf("%s src=%10.10s dst=%10.10s dgid=%u dt=%u\n", fi == YSF_FI_HEADER ? "HEADER" : "TERM",
                            (const char*)payload.getSource(), (const char*)payload.getDest(), fich.getDGId(), fich.getDT());
            continue;
        }

        comms++;
        unsigned char fn = fich.getFN();
        unsigned char copy[120U];
        std::memcpy(copy, data, 120U);
        bool dch = payload.processVDMode2Data(copy, fn, false);
        if (fn <= 1U) {
            if (dch)
                dchOk++;
            else
                dchBad++;
        }
        vchErrors += payload.processVDMode2Audio(copy);

        // Decode audio from the untouched frame.
        const unsigned char* p = data + YSF_SYNC_LENGTH_BYTES + YSF_FICH_LENGTH_BYTES;
        for (unsigned int block = 0U; block < 5U; block++) {
            unsigned int offset = 40U + block * 144U;
            unsigned char vch[13U];
            std::memset(vch, 0, sizeof(vch));
            for (unsigned int i = 0U; i < 104U; i++) {
                unsigned int n = (i % 26U) * 4U + i / 26U;
                if (readBit(p, offset + n))
                    vch[i >> 3] |= 0x80U >> (i & 7U);
            }
            for (unsigned int i = 0U; i < 13U; i++)
                vch[i] ^= WHITENING[i];
            int bits[49];
            for (unsigned int i = 0U; i < 27U; i++)
                bits[i] = readBit(vch, i * 3U) ? 1 : 0;
            for (unsigned int i = 0U; i < 22U; i++)
                bits[27U + i] = readBit(vch, 81U + i) ? 1 : 0;
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

    if (pcm != nullptr)
        std::fclose(pcm);

    std::printf("SUMMARY frames=%u bad_fich=%u headers=%u terminators=%u bad_headers=%u comms=%u dch_ok=%u dch_bad=%u vch_errors=%u\n",
                frames, badFich, headers, terminators, badHeaders, comms, dchOk, dchBad, vchErrors);
    return (badFich == 0U && badHeaders == 0U && dchBad == 0U && vchErrors == 0U) ? 0 : 1;
}
