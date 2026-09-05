#include <cstddef>
#include <cstdint>
#include <new>

#include "imbe_vocoder_api.h"


namespace
{

constexpr std::size_t PCM_SAMPLES_PER_FRAME = 160U;
constexpr std::size_t IMBE_BYTES_PER_FRAME = 11U;

}


extern "C"
{


void* rf_gateway_imbe_create()
{
    try {
        return new imbe_vocoder();
    } catch (...) {
        return nullptr;
    }
}


void rf_gateway_imbe_destroy(
    void* handle
)
{
    if (handle == nullptr)
        return;

    auto* vocoder =
        static_cast<imbe_vocoder*>(handle);

    delete vocoder;
}


int rf_gateway_imbe_encode_4400(
    void* handle,
    const int16_t* pcm,
    std::size_t pcm_samples,
    uint8_t* imbe,
    std::size_t imbe_size
)
{
    if (handle == nullptr)
        return -1;

    if (pcm == nullptr)
        return -2;

    if (imbe == nullptr)
        return -3;

    if (
        pcm_samples
        != PCM_SAMPLES_PER_FRAME
    ) {
        return -4;
    }

    if (
        imbe_size
        < IMBE_BYTES_PER_FRAME
    ) {
        return -5;
    }

    auto* vocoder =
        static_cast<imbe_vocoder*>(handle);

    /*
     * imbe_vocoder::encode_4400() does not declare
     * its PCM input as const, so copy the caller's
     * 160-sample frame into a local mutable buffer.
     */
    int16_t frame[
        PCM_SAMPLES_PER_FRAME
    ];

    for (
        std::size_t i = 0U;
        i < PCM_SAMPLES_PER_FRAME;
        ++i
    ) {
        frame[i] = pcm[i];
    }

    try {
        vocoder->encode_4400(
            frame,
            imbe
        );
    } catch (...) {
        return -6;
    }

    return 0;
}


std::size_t rf_gateway_imbe_pcm_samples_per_frame()
{
    return PCM_SAMPLES_PER_FRAME;
}


std::size_t rf_gateway_imbe_pcm_bytes_per_frame()
{
    return (
        PCM_SAMPLES_PER_FRAME
        * sizeof(int16_t)
    );
}


std::size_t rf_gateway_imbe_bytes_per_frame()
{
    return IMBE_BYTES_PER_FRAME;
}


}
