"""STT 品質ベンチマーク。

4 構成を fixtures に対して走らせて CER / 幻聴率 / レイテンシを計測する。

構成:
  - small        : faster-whisper "small" + Silero VAD (現状)
  - kotoba       : kotoba-whisper-v2.0 + Silero VAD
  - two_stage    : Stage1=small で確認 → 自信ある時のみ Stage2=kotoba 再デコード
  - two_stage_dualvad : webrtcvad pre-filter + two_stage

使い方:
  cd voice_chat && source .venv/bin/activate
  python tests/benchmark_stt_quality.py [--quick]

出力:
  docs/superpowers/plans/2026-04-25-stt-benchmark-results.{json,md}
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import jiwer
import numpy as np
import webrtcvad
from faster_whisper import WhisperModel
from scipy.io import wavfile
from scipy.signal import resample_poly

REPO = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO / "tests/fixtures/audio/samples"
INCOMING_DIR = REPO / "tests/fixtures/audio/incoming"
SYNTHETIC_DIR = REPO / "tests/fixtures/audio/synthetic"
MANIFEST = REPO / "tests/fixtures/audio/manifest.json"
REPORT_DIR = REPO / "docs/superpowers/plans"

CONFIGS = ["small", "kotoba", "two_stage", "two_stage_dualvad"]


@dataclass
class Sample:
    id: str
    file: Path
    transcript: str
    expected_skip: bool
    category: str


@dataclass
class RunResult:
    text: str = ""
    latency_sec: float = 0.0
    cer: float = 0.0
    outcome: str = ""
    avg_logprob: float = 0.0
    extra: dict = field(default_factory=dict)


# ---------- audio helpers ----------

def _load_via_ffmpeg(path: Path) -> np.ndarray:
    """webm/mp3/m4a 等を 16kHz mono float32 PCM にデコード。"""
    cmd = [
        "ffmpeg",
        "-i", str(path),
        "-ar", "16000",
        "-ac", "1",
        "-f", "f32le",
        "-loglevel", "error",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def load_audio_16k_mono(path: Path) -> np.ndarray:
    """任意フォーマットを 16kHz mono float32 にロード。"""
    if path.suffix.lower() != ".wav":
        return _load_via_ffmpeg(path)
    sr, data = wavfile.read(str(path))
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / float(2**31)
    elif data.dtype == np.uint8:
        audio = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype in (np.float32, np.float64):
        audio = data.astype(np.float32)
    else:
        raise ValueError(f"unsupported dtype: {data.dtype}")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        from math import gcd
        g = gcd(sr, 16000)
        audio = resample_poly(audio, 16000 // g, sr // g).astype(np.float32)
    return audio.astype(np.float32)


def make_silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * 16000), dtype=np.float32)


def make_white_noise(seconds: float, level: float = 0.005) -> np.ndarray:
    rng = np.random.default_rng(42)
    return (rng.standard_normal(int(seconds * 16000)) * level).astype(np.float32)


def save_wav_16k(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    wavfile.write(str(path), 16000, pcm)


def webrtcvad_voice_ratio(audio: np.ndarray, mode: int = 3) -> float:
    vad = webrtcvad.Vad(mode)
    # Defensive: 一部の Python/NumPy 環境で `audio * 32767` が in-place 化されて
    # 元の配列を破壊する事例を観測（Python 3.14 + NumPy 1.26 + 特定の呼び出し履歴下）。
    # 明示的にコピーしてから演算する。
    scaled = np.multiply(audio, 32767.0, dtype=np.float32)
    pcm = np.clip(scaled, -32768, 32767).astype(np.int16).tobytes()
    frame_ms = 30
    frame_bytes = int(16000 * frame_ms / 1000) * 2  # 16-bit
    if len(pcm) < frame_bytes:
        return 0.0
    voice = 0
    total = 0
    for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        frame = pcm[i : i + frame_bytes]
        if vad.is_speech(frame, 16000):
            voice += 1
        total += 1
    return voice / total if total else 0.0


# ---------- transcription ----------

WHISPER_HOTWORDS = "メイ"


def transcribe(
    model: WhisperModel,
    audio: np.ndarray,
    *,
    beam: int = 1,
    vad_filter: bool = True,
) -> tuple[str, float, float, dict]:
    t0 = time.perf_counter()
    segments, info = model.transcribe(
        audio,
        language="ja",
        beam_size=beam,
        vad_filter=vad_filter,
        hotwords=WHISPER_HOTWORDS,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        temperature=[0.0, 0.2, 0.4],
    )
    seg_list = list(segments)
    text = "".join(s.text for s in seg_list).strip()
    dt = time.perf_counter() - t0
    if seg_list:
        lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
        nsp = sum(s.no_speech_prob for s in seg_list) / len(seg_list)
    else:
        lp = 0.0
        nsp = 1.0
    return text, dt, lp, {"no_speech_prob": nsp, "segment_count": len(seg_list)}


# ---------- config runners ----------

def run_small(model_small: WhisperModel, audio: np.ndarray) -> RunResult:
    text, lat, lp, meta = transcribe(model_small, audio, beam=1, vad_filter=True)
    return RunResult(text=text, latency_sec=lat, avg_logprob=lp, extra=meta)


def run_kotoba(model_kotoba: WhisperModel, audio: np.ndarray) -> RunResult:
    text, lat, lp, meta = transcribe(model_kotoba, audio, beam=5, vad_filter=True)
    return RunResult(text=text, latency_sec=lat, avg_logprob=lp, extra=meta)


def run_two_stage(
    model_small: WhisperModel,
    model_kotoba: WhisperModel,
    audio: np.ndarray,
) -> RunResult:
    """Stage1: small で確認。 中身ありかつ avg_logprob > -0.8 なら Stage2: kotoba。"""
    t0 = time.perf_counter()
    text1, lat1, lp1, _ = transcribe(model_small, audio, beam=1, vad_filter=True)
    if not text1 or lp1 < -0.8:
        total = time.perf_counter() - t0
        return RunResult(
            text=text1,
            latency_sec=total,
            avg_logprob=lp1,
            extra={
                "stage": 1,
                "stage1_text": text1,
                "stage1_logprob": lp1,
                "stage1_latency": lat1,
            },
        )
    text2, lat2, lp2, _ = transcribe(model_kotoba, audio, beam=5, vad_filter=True)
    total = time.perf_counter() - t0
    return RunResult(
        text=text2,
        latency_sec=total,
        avg_logprob=lp2,
        extra={
            "stage": 2,
            "stage1_text": text1,
            "stage1_logprob": lp1,
            "stage1_latency": lat1,
            "stage2_text": text2,
            "stage2_logprob": lp2,
            "stage2_latency": lat2,
        },
    )


def run_two_stage_dualvad(
    model_small: WhisperModel,
    model_kotoba: WhisperModel,
    audio: np.ndarray,
) -> RunResult:
    """webrtcvad で 30ms フレームごとに音声判定。voice率 < 0.1 なら即skip。"""
    t0 = time.perf_counter()
    voice_ratio = webrtcvad_voice_ratio(audio, mode=3)
    if voice_ratio < 0.1:
        total = time.perf_counter() - t0
        return RunResult(
            text="",
            latency_sec=total,
            avg_logprob=0.0,
            extra={"skipped_by_webrtcvad": True, "voice_ratio": voice_ratio, "stage": 0},
        )
    inner = run_two_stage(model_small, model_kotoba, audio)
    inner.extra["skipped_by_webrtcvad"] = False
    inner.extra["voice_ratio"] = voice_ratio
    inner.latency_sec = time.perf_counter() - t0
    return inner


# ---------- evaluation ----------

_PUNCT_RE = re.compile(r"[、。！？!?\s　「」『』,.;:]")


def _normalize(s: str) -> str:
    return _PUNCT_RE.sub("", s.strip())


def compute_cer(hyp: str, ref: str, *, normalize: bool = True) -> float:
    h = _normalize(hyp) if normalize else hyp.strip()
    r = _normalize(ref) if normalize else ref.strip()
    if not r:
        return 1.0 if h else 0.0
    return jiwer.cer(r, h)


def evaluate_outcome(hyp: str, sample: Sample) -> str:
    h = _normalize(hyp)
    if sample.expected_skip:
        return "ok_skip" if not h else "hallucinated"
    if not h:
        return "missed"
    cer = compute_cer(h, sample.transcript, normalize=True)
    if cer < 0.10:
        return "ok"
    if cer < 0.30:
        return "partial"
    return "wrong"


# ---------- sample collection ----------

def collect_samples() -> list[Sample]:
    samples: list[Sample] = []

    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest:
        cat = entry["id"].split("_")[0] if "_" in entry["id"] else "other"
        samples.append(
            Sample(
                id=entry["id"],
                file=SAMPLES_DIR / Path(entry["file"]).name,
                transcript=entry["transcript"],
                expected_skip=False,
                category=cat,
            )
        )

    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    silence_path = SYNTHETIC_DIR / "silence_3s.wav"
    noise_path = SYNTHETIC_DIR / "white_noise_3s.wav"
    if not silence_path.exists():
        save_wav_16k(silence_path, make_silence(3.0))
    if not noise_path.exists():
        save_wav_16k(noise_path, make_white_noise(3.0, level=0.005))
    samples.append(Sample("synthetic_silence", silence_path, "", True, "silence"))
    samples.append(Sample("synthetic_white_noise", noise_path, "", True, "noise"))

    if INCOMING_DIR.exists():
        seen: set[str] = set()
        for ext in ("wav", "webm", "mp3", "m4a", "ogg"):
            for f in sorted(INCOMING_DIR.glob(f"*.{ext}")):
                if f.stem in seen:
                    continue
                seen.add(f.stem)
                if f.stem.startswith("media"):
                    samples.append(
                        Sample(
                            id=f.stem,
                            file=f,
                            transcript="",
                            expected_skip=True,
                            category="media_far_field",
                        )
                    )
                elif f.stem.startswith("wake") or f.stem.startswith("akira"):
                    samples.append(
                        Sample(
                            id=f.stem,
                            file=f,
                            transcript="",  # 録音時に sidecar JSON で transcript 渡せるように後で拡張
                            expected_skip=False,
                            category="akira_near_field",
                        )
                    )

    # sidecar transcript 上書き（任意）: <stem>.transcript.txt があれば読む
    for s in samples:
        sidecar = s.file.with_suffix(".transcript.txt")
        if sidecar.exists():
            s.transcript = sidecar.read_text(encoding="utf-8").strip()
            s.expected_skip = False if s.transcript else s.expected_skip

    return samples


# ---------- markdown ----------

def fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def generate_markdown(
    samples: list[Sample],
    results: dict,
    summary: dict,
    metadata: dict,
) -> str:
    lines: list[str] = []
    lines.append("# STT Quality Benchmark Results — 2026-04-25")
    lines.append("")
    lines.append("> 4構成（small / kotoba / 2段階 / +二重VAD）の比較ベンチ。")
    lines.append("")
    lines.append("## メタデータ")
    lines.append("")
    for k, v in metadata.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    # === サマリ表 ===
    lines.append("## サマリ")
    lines.append("")
    lines.append("| 構成 | 平均CER (transcript付きのみ) | 平均レイテンシ | ok | partial | wrong | missed | hallucinated | ok_skip |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for cfg in CONFIGS:
        s = summary[cfg]
        oc = s["outcome_counts"]
        lines.append(
            f"| {cfg} | {fmt(s['avg_cer'], 3)} | {fmt(s['avg_latency_sec'], 2)}s | "
            f"{oc.get('ok', 0)} | {oc.get('partial', 0)} | {oc.get('wrong', 0)} | "
            f"{oc.get('missed', 0)} | {oc.get('hallucinated', 0)} | {oc.get('ok_skip', 0)} |"
        )
    lines.append("")

    # === サンプル別 ===
    lines.append("## サンプル別の出力")
    lines.append("")
    lines.append("**Outcome 凡例**: `ok`(CER<0.15) / `partial`(<0.40) / `wrong`(≥0.40) / `missed`(空・期待あり) / `hallucinated`(出力・期待空) / `ok_skip`(空・期待空)")
    lines.append("")
    for sample in samples:
        r = results[sample.id]
        lines.append(f"### `{sample.id}` ({sample.category})")
        lines.append("")
        lines.append(f"- 期待: `{sample.transcript or '(空が正解)'}`")
        lines.append("")
        lines.append("| 構成 | outcome | text | CER | latency | logprob | extra |")
        lines.append("|---|---|---|---|---|---|---|")
        for cfg in CONFIGS:
            run = r[cfg]
            extra_str = ""
            if "stage" in run.get("extra", {}):
                extra_str = f"stage={run['extra']['stage']}"
            if run.get("extra", {}).get("skipped_by_webrtcvad"):
                extra_str = f"vad_skip(vr={run['extra']['voice_ratio']:.2f})"
            elif "voice_ratio" in run.get("extra", {}):
                extra_str = f"vr={run['extra']['voice_ratio']:.2f} {extra_str}"
            text_safe = run["text"].replace("|", "\\|")[:60]
            lines.append(
                f"| {cfg} | {run['outcome']} | `{text_safe}` | "
                f"{fmt(run['cer'], 3)} | {fmt(run['latency_sec'], 2)}s | "
                f"{fmt(run.get('avg_logprob', 0), 2)} | {extra_str} |"
            )
        lines.append("")

    # === 推奨 ===
    lines.append("## 結果サマリと推奨")
    lines.append("")
    cer_ranking = sorted(CONFIGS, key=lambda c: summary[c]["avg_cer"])
    lat_ranking = sorted(CONFIGS, key=lambda c: summary[c]["avg_latency_sec"])
    lines.append(f"- 平均CER最良: **{cer_ranking[0]}** ({fmt(summary[cer_ranking[0]]['avg_cer'], 3)})")
    lines.append(f"- 平均レイテンシ最速: **{lat_ranking[0]}** ({fmt(summary[lat_ranking[0]]['avg_latency_sec'], 2)}s)")
    halluc = {c: summary[c]["outcome_counts"].get("hallucinated", 0) for c in CONFIGS}
    best_anti_halluc = min(halluc, key=halluc.get)
    lines.append(f"- 幻聴最少: **{best_anti_halluc}** ({halluc[best_anti_halluc]}件)")
    lines.append("")
    lines.append("## 次のアクション候補")
    lines.append("")
    lines.append("1. 推奨構成を Plan の Phase 0/0.5/0.7 に反映")
    lines.append("2. 本番 `app.py` への段階統合")
    lines.append("3. AEC（信号レベル自TTSキャンセル）を別フェーズで評価")
    return "\n".join(lines) + "\n"


# ---------- main ----------

def run_all(quick: bool = False) -> None:
    print("=" * 60)
    print("STT Quality Benchmark")
    print("=" * 60)

    print("[1/3] Loading models...")
    t = time.time()
    model_small = WhisperModel("small", device="cpu", compute_type="int8")
    print(f"  small: {time.time()-t:.1f}s")
    t = time.time()
    model_kotoba = WhisperModel(
        "kotoba-tech/kotoba-whisper-v2.0-faster",
        device="cpu",
        compute_type="int8",
    )
    print(f"  kotoba-whisper-v2.0: {time.time()-t:.1f}s")

    print("[2/3] Collecting samples...")
    samples = collect_samples()
    if quick:
        samples = samples[:5]
    print(f"  {len(samples)} samples")
    for s in samples:
        print(f"    - {s.id} ({s.category}) expect_skip={s.expected_skip}")

    print("[3/3] Running benchmarks...")
    results: dict = {}
    for sample in samples:
        audio = load_audio_16k_mono(sample.file)
        results[sample.id] = {
            "category": sample.category,
            "expected": sample.transcript,
            "expected_skip": sample.expected_skip,
            "duration_sec": len(audio) / 16000.0,
        }
        for cfg_name in CONFIGS:
            print(f"  [{sample.id:<35}] {cfg_name:<22}", end="", flush=True)
            if cfg_name == "small":
                r = run_small(model_small, audio)
            elif cfg_name == "kotoba":
                r = run_kotoba(model_kotoba, audio)
            elif cfg_name == "two_stage":
                r = run_two_stage(model_small, model_kotoba, audio)
            elif cfg_name == "two_stage_dualvad":
                r = run_two_stage_dualvad(model_small, model_kotoba, audio)
            r.cer = compute_cer(r.text, sample.transcript)
            r.outcome = evaluate_outcome(r.text, sample)
            results[sample.id][cfg_name] = {
                "text": r.text,
                "latency_sec": r.latency_sec,
                "cer": r.cer,
                "outcome": r.outcome,
                "avg_logprob": r.avg_logprob,
                "extra": r.extra,
            }
            print(f" {r.outcome:<14} CER={r.cer:.2f} lat={r.latency_sec:.2f}s text='{r.text[:40]}'")

    # サマリ
    summary = {}
    for cfg in CONFIGS:
        cers = [
            results[s][cfg]["cer"]
            for s in results
            if not results[s].get("expected_skip")
        ]
        latencies = [results[s][cfg]["latency_sec"] for s in results]
        outcomes = [results[s][cfg]["outcome"] for s in results]
        summary[cfg] = {
            "avg_cer": sum(cers) / len(cers) if cers else 0.0,
            "avg_latency_sec": sum(latencies) / len(latencies) if latencies else 0.0,
            "outcome_counts": {o: outcomes.count(o) for o in set(outcomes)},
        }

    metadata = {
        "date": "2026-04-25",
        "device": "cpu",
        "compute_type": "int8",
        "samples_count": len(samples),
        "small_model": "small",
        "kotoba_model": "kotoba-tech/kotoba-whisper-v2.0-faster",
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "2026-04-25-stt-benchmark-results.json"
    md_path = REPORT_DIR / "2026-04-25-stt-benchmark-results.md"
    json_path.write_text(
        json.dumps(
            {"metadata": metadata, "results": results, "summary": summary},
            ensure_ascii=False,
            indent=2,
        )
    )
    md_path.write_text(generate_markdown(samples, results, summary, metadata))
    print()
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print()
    print("=== Summary ===")
    for cfg in CONFIGS:
        s = summary[cfg]
        print(
            f"  {cfg:<22} CER={s['avg_cer']:.3f} "
            f"lat={s['avg_latency_sec']:.2f}s outcomes={s['outcome_counts']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Use only first 5 samples")
    args = parser.parse_args()
    run_all(quick=args.quick)
