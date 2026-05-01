"""Irodori TTS の先頭ノイズ／無音トリムのテスト。"""
import math
import struct

import app


def _make_wav(samples: list[int], sample_rate: int = 48000) -> bytes:
    pcm = b"".join(struct.pack("<h", s) for s in samples)
    data_size = len(pcm)
    riff_size = 36 + data_size
    header = b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
    fmt = (
        b"fmt " + struct.pack("<I", 16)
        + struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    )
    data = b"data" + struct.pack("<I", data_size) + pcm
    return header + fmt + data


def _samples_at_rms(target_rms: float, count: int) -> list[int]:
    if target_rms <= 0:
        return [0] * count
    amp = int(target_rms)
    return [amp if i % 2 == 0 else -amp for i in range(count)]


def _read_pcm(audio: bytes) -> bytes:
    tag = audio.find(b"data", 12)
    return audio[tag + 8:]


def test_trim_removes_long_buzzy_lead_in():
    sr = 48000
    # 1.5s of buzz (rms ~150) then 1s of speech (rms ~5000)
    buzz = _samples_at_rms(150, int(sr * 1.5))
    speech = _samples_at_rms(5000, int(sr * 1.0))
    audio = _make_wav(buzz + speech, sr)
    trimmed = app._trim_irodori_lead_in(audio, threshold_rms=500.0, max_trim_sec=2.0, keep_before_sec=0.05)

    original_duration = len(_read_pcm(audio)) / (sr * 2)
    trimmed_duration = len(_read_pcm(trimmed)) / (sr * 2)
    # Buzz removed minus 50ms keep-before buffer → ~1.45s shorter
    assert original_duration - trimmed_duration > 1.3
    assert trimmed_duration > 0.9  # speech preserved


def test_trim_keeps_clean_audio_untouched():
    sr = 48000
    audio = _make_wav(_samples_at_rms(5000, int(sr * 1.0)), sr)
    trimmed = app._trim_irodori_lead_in(audio)
    assert trimmed == audio


def test_trim_skips_when_no_loud_window_within_max_trim():
    sr = 48000
    # Entire audio is quiet noise — must not be trimmed (might be quiet speech)
    audio = _make_wav(_samples_at_rms(100, int(sr * 3.0)), sr)
    trimmed = app._trim_irodori_lead_in(audio, threshold_rms=500.0, max_trim_sec=2.0)
    assert trimmed == audio


def test_trim_handles_invalid_wav():
    assert app._trim_irodori_lead_in(b"") == b""
    assert app._trim_irodori_lead_in(b"NOTWAVE_______________") == b"NOTWAVE_______________"


def test_trim_preserves_wav_header_consistency():
    sr = 48000
    buzz = _samples_at_rms(100, int(sr * 1.0))
    speech = _samples_at_rms(5000, int(sr * 1.0))
    audio = _make_wav(buzz + speech, sr)
    trimmed = app._trim_irodori_lead_in(audio, threshold_rms=500.0, max_trim_sec=2.0)

    riff_size = struct.unpack_from("<I", trimmed, 4)[0]
    assert riff_size == len(trimmed) - 8
    tag = trimmed.find(b"data", 12)
    data_size = struct.unpack_from("<I", trimmed, tag + 4)[0]
    assert data_size == len(trimmed) - (tag + 8)
