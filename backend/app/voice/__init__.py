"""Voice transmit sessions for the MMDVM digital and analog modes.

Each session takes 8 kHz mono S16LE PCM in 20 ms chunks and hands the
encoded audio to MMDVM-Host over its local network interface.
"""
