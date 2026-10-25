// RF Gateway AMBE+2 / AMBE encoder wrapper.
//
// Exposes the OP25 software AMBE encoder (backend/native/ambe, GPLv3)
// through a small C ABI for ctypes. Speech analysis comes from the same
// imbe_vocoder used by the P25 path; the encoder only quantizes the model
// parameters to AMBE+2 3600x2450 (DMR, YSF DN, NXDN) or AMBE 3600x2400
// (D-Star). Channel FEC and interleaving are done in Python.

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>

#include "ambe/ambe_encoder.h"

namespace {

constexpr std::size_t kPcmSamplesPerFrame = 160;

struct Encoder {
    ambe_encoder impl;
};

}  // namespace

extern "C" {

int rf_gateway_ambe_abi_version()
{
    return 1;
}

void* rf_gateway_ambe_create(int dstar_mode)
{
    Encoder* encoder = new (std::nothrow) Encoder();
    if (encoder == nullptr)
        return nullptr;
    if (dstar_mode != 0)
        encoder->impl.set_dstar_mode();
    else
        encoder->impl.set_49bit_mode();
    return encoder;
}

void rf_gateway_ambe_destroy(void* handle)
{
    delete static_cast<Encoder*>(handle);
}

void rf_gateway_ambe_set_gain_adjust(void* handle, float gain_db)
{
    if (handle == nullptr)
        return;
    static_cast<Encoder*>(handle)->impl.set_gain_adjust(gain_db);
}

// Returns 1 when the frame was quantized, 0 when the encoder fell back to
// an all-zero parameter set, and -1 on invalid arguments.
int rf_gateway_ambe_encode_49(void* handle, const int16_t* pcm, uint8_t* bits_out)
{
    if (handle == nullptr || pcm == nullptr || bits_out == nullptr)
        return -1;
    int16_t samples[kPcmSamplesPerFrame];
    std::memcpy(samples, pcm, sizeof(samples));
    bool ok = static_cast<Encoder*>(handle)->impl.encode(samples, bits_out);
    return ok ? 1 : 0;
}

int rf_gateway_ambe_encode_params(void* handle, const int16_t* pcm, int* params_out)
{
    if (handle == nullptr || pcm == nullptr || params_out == nullptr)
        return -1;
    int16_t samples[kPcmSamplesPerFrame];
    std::memcpy(samples, pcm, sizeof(samples));
    bool ok = static_cast<Encoder*>(handle)->impl.encode_params(samples, params_out);
    return ok ? 1 : 0;
}

std::size_t rf_gateway_ambe_pcm_samples_per_frame()
{
    return kPcmSamplesPerFrame;
}

}  // extern "C"
