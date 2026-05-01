"""二重VAD で精度悪化する原因の調査。

仮説:
  H1: temperature fallback の non-determinism
  H2: faster-whisper / ctranslate2 の内部キャッシュ汚染
  H3: webrtcvad_voice_ratio が audio numpy配列を破壊している
  H4: RuntimeWarning（feature_extractor matmul）で NaN混入
  H5: モデル順序依存（small→kotoba 累積影響）

検証音声: media_far_field_15.webm
  two_stage: "この色味とかもなんかかぶての色を見るとかを撮っていきたいとしてちょっとそれっぽい" CER=0.48
  two_stage_dualvad: "おうおう" CER=1.00
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import webrtcvad
from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_stt_quality import (  # noqa: E402
    load_audio_16k_mono,
    transcribe,
    webrtcvad_voice_ratio,
)

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "tests/fixtures/audio/incoming/media__youtube_far_field__15.webm"

EXPECTED = "この色味とかもなんかカブトの色味とかを取ってきたりして、ちょっとそれっぽい感じ。ええ、画像に合わせてくれたわけです。"


def hash_audio(audio: np.ndarray) -> str:
    """配列の代表値で破壊検知。"""
    return f"shape={audio.shape} mean={audio.mean():.6f} std={audio.std():.6f} max={np.abs(audio).max():.6f} nan={np.isnan(audio).sum()} inf={np.isinf(audio).sum()}"


def transcribe_kotoba(model: WhisperModel, audio: np.ndarray, beam: int = 5) -> tuple:
    text, lat, lp, meta = transcribe(model, audio, beam=beam, vad_filter=True)
    return text, lat, lp


def trace_webrtcvad(audio: np.ndarray, mode: int = 3) -> float:
    """webrtcvad_voice_ratio を ステップ単位で audio の状態を確認しながら実行。"""
    print(f"   ENTRY:  id={id(audio):x} writeable={audio.flags.writeable} mean={audio.mean():.6f}")
    print(f"   ENTRY:  base={audio.base} contiguous={audio.flags.c_contiguous}")
    vad = webrtcvad.Vad(mode)
    a1 = audio * 32767
    print(f"   STEP1:  id_a1={id(a1):x} a1.base={'audio' if a1.base is audio else a1.base} audio.mean={audio.mean():.6f}")
    a2 = a1.clip(-32768, 32767)
    print(f"   STEP2:  id_a2={id(a2):x} audio.mean={audio.mean():.6f}")
    a3 = a2.astype(np.int16)
    print(f"   STEP3:  id_a3={id(a3):x} audio.mean={audio.mean():.6f}")
    pcm = a3.tobytes()
    print(f"   STEP4:  pcm_len={len(pcm)} audio.mean={audio.mean():.6f}")
    frame_ms = 30
    frame_bytes = int(16000 * frame_ms / 1000) * 2
    voice = 0
    total = 0
    for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        frame = pcm[i : i + frame_bytes]
        if vad.is_speech(frame, 16000):
            voice += 1
        total += 1
    print(f"   STEP5:  voice={voice} total={total} audio.mean={audio.mean():.6f}")
    return voice / total if total else 0.0


def main() -> None:
    print("=" * 70)
    print(f"Investigation target: {TARGET.name}")
    print("=" * 70)

    print("\n[setup] Loading models...")
    model_small = WhisperModel("small", device="cpu", compute_type="int8")
    model_kotoba = WhisperModel(
        "kotoba-tech/kotoba-whisper-v2.0-faster",
        device="cpu",
        compute_type="int8",
    )
    print("  ok")

    audio_master = load_audio_16k_mono(TARGET)
    print(f"\n[audio] master: {hash_audio(audio_master)}")

    # ============================================================
    # H1: temperature fallback の non-determinism
    # ============================================================
    print("\n" + "=" * 70)
    print("H1: kotoba を5連続で同じ音声に対して呼ぶ → 結果の揺らぎ")
    print("=" * 70)
    audio = audio_master.copy()
    for i in range(5):
        text, lat, lp = transcribe_kotoba(model_kotoba, audio)
        print(f"  [{i+1}] lp={lp:.3f} lat={lat:.2f}s text='{text[:60]}'")

    # ============================================================
    # H3: webrtcvad_voice_ratio の副作用 — トレース版
    # ============================================================
    print("\n" + "=" * 70)
    print("H3-trace: webrtcvad の各ステップで audio が変わるかトレース")
    print("=" * 70)
    audio = audio_master.copy()
    print(f"  before vad: {hash_audio(audio)}")
    vr = trace_webrtcvad(audio, mode=3)
    print(f"  voice_ratio={vr:.3f}")
    print(f"  after  vad: {hash_audio(audio)}")
    print(f"  master same: {np.array_equal(audio, audio_master)}")

    # frombuffer 由来かどうか: 単純な float32 配列で再現するか
    print("\n  --- 別途: frombufferとは無関係の np.array で再現テスト ---")
    audio2 = np.random.randn(112000).astype(np.float32) * 0.1
    print(f"  before vad: {hash_audio(audio2)}")
    vr = trace_webrtcvad(audio2, mode=3)
    print(f"  after  vad: {hash_audio(audio2)}")

    # ============================================================
    # H1+H3: webrtcvad呼んだ後に kotoba 推論 → 結果が変わるか
    # ============================================================
    print("\n" + "=" * 70)
    print("H1+H3: webrtcvad → kotoba を5連続で実行")
    print("=" * 70)
    for i in range(5):
        audio = audio_master.copy()
        vr = webrtcvad_voice_ratio(audio, mode=3)
        text, lat, lp = transcribe_kotoba(model_kotoba, audio)
        print(f"  [{i+1}] vr={vr:.3f} lp={lp:.3f} text='{text[:60]}'")

    # ============================================================
    # H5: モデル順序依存
    # ============================================================
    print("\n" + "=" * 70)
    print("H5: small → kotoba 順序で5連続")
    print("=" * 70)
    for i in range(5):
        audio = audio_master.copy()
        text_s, lat_s, lp_s = transcribe(model_small, audio, beam=1, vad_filter=True)
        text_k, lat_k, lp_k = transcribe_kotoba(model_kotoba, audio)
        print(f"  [{i+1}] small='{text_s[:40]}'")
        print(f"        kotoba='{text_k[:60]}'")

    # ============================================================
    # H1+H5: webrtcvad → small → kotoba （実際の dualvad 経路）を5連続
    # ============================================================
    print("\n" + "=" * 70)
    print("H1+H5: webrtcvad → small → kotoba 経路（dualvad再現）を5連続")
    print("=" * 70)
    for i in range(5):
        audio = audio_master.copy()
        vr = webrtcvad_voice_ratio(audio, mode=3)
        text_s, _, lp_s = transcribe(model_small, audio, beam=1, vad_filter=True)
        text_k, _, lp_k = transcribe_kotoba(model_kotoba, audio)
        print(f"  [{i+1}] vr={vr:.3f} small='{text_s[:30]}' kotoba='{text_k[:60]}'")

    # ============================================================
    # H2: 同じインスタンスを使い回した時のキャッシュ汚染
    # 4構成順次実行 → kotoba結果のずれを観察
    # ============================================================
    print("\n" + "=" * 70)
    print("H2: 4構成順次実行を3 epoch（ベンチと同じ呼び順）")
    print("=" * 70)
    for epoch in range(3):
        print(f"\n--- epoch {epoch+1} ---")
        # small
        audio = audio_master.copy()
        text, _, _ = transcribe(model_small, audio, beam=1, vad_filter=True)
        print(f"  small             : '{text[:60]}'")
        # kotoba
        audio = audio_master.copy()
        text, _, _ = transcribe_kotoba(model_kotoba, audio)
        print(f"  kotoba            : '{text[:60]}'")
        # two_stage（small→kotoba）
        audio = audio_master.copy()
        ts, _, lps = transcribe(model_small, audio, beam=1, vad_filter=True)
        if ts and lps >= -0.8:
            audio2 = audio_master.copy()
            tk, _, _ = transcribe_kotoba(model_kotoba, audio2)
            print(f"  two_stage         : '{tk[:60]}'")
        else:
            print(f"  two_stage (stage1): '{ts[:60]}'")
        # two_stage_dualvad（webrtcvad→small→kotoba）
        audio = audio_master.copy()
        vr = webrtcvad_voice_ratio(audio, mode=3)
        if vr >= 0.1:
            audio = audio_master.copy()
            ts, _, lps = transcribe(model_small, audio, beam=1, vad_filter=True)
            if ts and lps >= -0.8:
                audio2 = audio_master.copy()
                tk, _, _ = transcribe_kotoba(model_kotoba, audio2)
                print(f"  two_stage_dualvad : vr={vr:.2f} '{tk[:60]}'")
            else:
                print(f"  two_stage_dualvad : vr={vr:.2f} stage1='{ts[:60]}'")
        else:
            print(f"  two_stage_dualvad : vr={vr:.2f} skipped")


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    main()
