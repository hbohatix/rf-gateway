// P25 TDMA Decoder (C) Copyright 2013, 2014 Max H. Parke KA1RBI
// 
// This file is part of OP25
// 
// OP25 is free software; you can redistribute it and/or modify it
// under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 3, or (at your option)
// any later version.
// 
// OP25 is distributed in the hope that it will be useful, but WITHOUT
// ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
// or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
// License for more details.
// 
// You should have received a copy of the GNU General Public License
// along with OP25; see the file COPYING. If not, write to the Free
// Software Foundation, Inc., 51 Franklin Street, Boston, MA
// 02110-1301, USA.

#ifndef INCLUDED_AMBE_ENCODER_H
#define INCLUDED_AMBE_ENCODER_H

#include <stdint.h>

#include "imbe.h"          /* IMBE_PARAM */
#include "imbe_vocoder.h"
#include "mbelib.h"

class ambe_encoder {
public:
	/* RF Gateway: 49-bit AMBE+2 codeword (one bit per byte) */
	bool encode(int16_t samples[], uint8_t codeword[49]);
	/* RF Gateway: raw quantized parameters b0..b8 */
	bool encode_params(int16_t samples[], int b[9]);
	ambe_encoder(void);
	void set_49bit_mode(void);
	void set_dstar_mode(void);
	void set_gain_adjust(const float gain_adjust) {d_gain_adjust = gain_adjust;}
private:
	imbe_vocoder vocoder;
	mbe_parms cur_mp;
	mbe_parms prev_mp;
	mbe_errs errs_mp;
	bool d_49bit_mode;
	bool d_dstar_mode;
	float d_gain_adjust;
};

#endif /* INCLUDED_AMBE_ENCODER_H */
