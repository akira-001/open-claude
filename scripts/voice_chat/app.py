"""Ember Chat Web App - STT (Whisper) + LLM (Ollama) + TTS (VOICEVOX)"""
import asyncio
import hashlib
import difflib
import json
import logging
import math
import os
import re
import struct
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_chat")
logger.propagate = False
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
logger.addHandler(_sh)
# Suppress noisy third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)
logging.getLogger("speechbrain").setLevel(logging.WARNING)

import warnings
warnings.filterwarnings("ignore", message=".*encountered in matmul.*", category=RuntimeWarning)

import numpy as np


def _is_whisper_hallucination(text: str) -> bool:
    """Detect Whisper hallucination patterns: repeated chars, gibberish, etc."""
    cleaned = re.sub(r'[、。！？\s]', '', text)
    if not cleaned:
        return True
    # Repeated single character dominates (e.g., "んんんんんんん")
    from collections import Counter
    counts = Counter(cleaned)
    most_common_char, most_common_count = counts.most_common(1)[0]
    if most_common_count / len(cleaned) > 0.5 and len(cleaned) > 4:
        return True
    # Very low unique char ratio (e.g., "あんまんまいいっんんんん")
    if len(counts) <= 3 and len(cleaned) > 6:
        return True
    return False


def _has_repeated_phrase(text: str, min_phrase_len: int = 3, min_repeats: int = 4) -> bool:
    """Patch Z1: STT/LLM補正後の繰り返しフレーズ幻覚を検出する。
    例: 'あったら、あったら、あったら、あったら、あったら、' のような繰り返し。
    min_phrase_len文字以上のフレーズがmin_repeats回以上連続する場合はTrueを返す。"""
    # 区切り文字を正規化して繰り返しを検出しやすくする
    normalized = re.sub(r'[、。！？\s　]+', '|', text.strip())
    parts = [p for p in normalized.split('|') if len(p) >= min_phrase_len]
    if len(parts) < min_repeats:
        return False
    # スライドウィンドウで連続する同一フレーズを検出
    for i in range(len(parts) - min_repeats + 1):
        window = parts[i:i + min_repeats]
        if len(set(window)) == 1:  # 全て同じフレーズ
            return True
    return False

import emoji as emoji_lib
import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from faster_whisper import WhisperModel

from wake_detect import detect_wake_word
from wake_response import WakeResponseCache
import wake_response as _wake_response_module
from ambient_commands import detect_ambient_command
from ambient_listener import AmbientListener
from ambient_policy import normalize_ambient_reply, should_apply_stt_correction
from speaker_id import SpeakerIdentifier, audio_bytes_to_wav, compute_embedding

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3456", "http://192.168.1.7:3456"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_tts_locks: dict[str, asyncio.Lock] = {}

def _get_tts_lock(engine: str) -> asyncio.Lock:
    if engine not in _tts_locks:
        _tts_locks[engine] = asyncio.Lock()
    return _tts_locks[engine]

# TTS 結果の短期キャッシュ（重複リクエスト防止）
_tts_cache: dict[str, tuple[float, bytes]] = {}
_TTS_CACHE_TTL = 30  # seconds

_wake_cache = WakeResponseCache()
_wait_cache = WakeResponseCache(responses=[
    "ちょっと待ってね、調べてくる",
    "わかった、確認するね",
    "了解、ちょっと調べるね",
    "はいはい、見てくるね",
    "オッケー、ちょっと待って",
])

VOICEVOX_URL = "http://localhost:50021"
VOICEVOX_SPEAKER = 2  # 四国めたん ノーマル

# Irodori-TTS voice presets (caption-based voice design)
IRODORI_VOICES = [
    {"id": "irodori-calm-female", "name": "落ち着いた女性", "caption": "落ち着いた女性の声で、近い距離感でやわらかく自然に読み上げてください。"},
    {"id": "irodori-bright-female", "name": "明るい女性", "caption": "明るく元気な女性の声で、はきはきと楽しそうに読み上げてください。"},
    {"id": "irodori-cool-female", "name": "クールな女性", "caption": "クールで知的な女性の声で、淡々と落ち着いて読み上げてください。"},
    {"id": "irodori-tsundere", "name": "ツンデレ女性", "caption": "少しツンとした態度の女性の声で、照れ隠しをしながら読み上げてください。"},
    {"id": "irodori-gentle-male", "name": "穏やかな男性", "caption": "穏やかで優しい男性の声で、ゆっくりと丁寧に読み上げてください。"},
    {"id": "irodori-energetic-male", "name": "元気な男性", "caption": "元気で活発な男性の声で、力強く読み上げてください。"},
    {"id": "irodori-narrator", "name": "ナレーター", "caption": "プロのナレーターのような、落ち着いて聞き取りやすい声で読み上げてください。"},
    {"id": "irodori-anime-girl", "name": "アニメ風少女", "caption": "かわいらしいアニメの女の子のような声で、元気に読み上げてください。"},
    {"id": "irodori-emilia", "name": "銀髪のお嬢様", "caption": "透明感のある澄んだ女性の声で、品がありつつも芯の強さを感じさせる、少しおっとりした丁寧な話し方で読み上げてください。"},
    {"id": "irodori-lora-emilia", "name": "エミリア(LoRA)", "lora": True},
]

# GPT-SoVITS config
GPTSOVITS_API_URL = "http://localhost:9880"
GPTSOVITS_REF_DIR = "/Users/akira/workspace/GPT-SoVITS/ref_audio"
GPTSOVITS_VOICES = [
    {"id": "sovits-emilia", "name": "エミリア", "ref_audio": "emilia.wav", "prompt_text": "ルグニカ王国次期王候補の一人なの。なんだか力がみなぎって、もっともっと強くなりたい。"},
]

# Slack config
SLACK_USER_TOKENS = {
    "mei": os.getenv("SLACK_USER_TOKEN_MEI", ""),
    "eve": os.getenv("SLACK_USER_TOKEN_EVE", ""),
}
SLACK_DM_CHANNELS = {
    "mei": os.getenv("SLACK_DM_CHANNEL_MEI", ""),
    "eve": os.getenv("SLACK_DM_CHANNEL_EVE", ""),
}
SLACK_BOT_TOKENS = {
    "mei": os.getenv("SLACK_BOT_TOKEN_MEI", ""),
    "eve": os.getenv("SLACK_BOT_TOKEN_EVE", ""),
}
MEETING_SUMMARY_TARGET_BOTS = [
    b.strip() for b in os.getenv("SLACK_MEETING_SUMMARY_BOTS", "mei").split(",")
    if b.strip()
]
MEETING_SUMMARY_MIN_SNIPPETS = int(os.getenv("MEETING_SUMMARY_MIN_SNIPPETS", "4"))
MEETING_SUMMARY_IDLE_SEC = int(os.getenv("MEETING_SUMMARY_IDLE_SEC", "120"))
MEETING_SUMMARY_COOLDOWN_SEC = int(os.getenv("MEETING_SUMMARY_COOLDOWN_SEC", "1800"))

# --- Shared settings (cross-browser sync) ---
SETTINGS_FILE = Path(__file__).parent / "settings.json"
CO_VIEW_AUTO_APPROVE_FILE = Path("/tmp/co_view_auto_approve")
YOMIGANA_FILE = Path(__file__).parent / "yomigana_map.json"
_settings: dict = {}
_clients: set[WebSocket] = set()


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(s: dict):
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False))


def _sync_auto_approve_file(enabled: bool) -> None:
    """Keep the co_view auto-approve sentinel file in sync with settings."""
    if enabled:
        CO_VIEW_AUTO_APPROVE_FILE.touch(exist_ok=True)
    else:
        CO_VIEW_AUTO_APPROVE_FILE.unlink(missing_ok=True)


def _get_auto_approve_enabled() -> bool:
    enabled = bool(_settings.get("autoApproveEnabled")) or CO_VIEW_AUTO_APPROVE_FILE.exists()
    if _settings.get("autoApproveEnabled") != enabled:
        _settings["autoApproveEnabled"] = enabled
    return enabled


def _set_auto_approve_enabled(enabled: bool) -> bool:
    _settings["autoApproveEnabled"] = enabled
    _sync_auto_approve_file(enabled)
    _save_settings(_settings)
    return enabled


def _load_public_yomigana_map() -> list[tuple[re.Pattern, str]]:
    """共有 TTS 読み仮名辞書を JSON から読み込む。"""
    try:
        raw = json.loads(YOMIGANA_FILE.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"[yomigana] failed to load {YOMIGANA_FILE.name}: {e}")
        return []

    entries: list[tuple[re.Pattern, str]] = []
    if not isinstance(raw, list):
        logger.warning(f"[yomigana] invalid format in {YOMIGANA_FILE.name}: expected list")
        return []

    for item in raw:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern")
        replacement = item.get("replacement")
        if not isinstance(pattern, str) or not isinstance(replacement, str):
            continue
        try:
            entries.append((re.compile(pattern), replacement))
        except re.error as e:
            logger.warning(f"[yomigana] invalid regex '{pattern}': {e}")
    return entries


def _load_personal_yomigana_map() -> list[tuple[re.Pattern, str]]:
    """個人設定に保存された読み仮名辞書を読み込む。"""
    raw = _settings.get("yomiganaPersonalEntries", [])
    if not isinstance(raw, list):
        return []

    entries: list[tuple[re.Pattern, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pattern = item.get("from")
        replacement = item.get("to")
        if not isinstance(pattern, str) or not isinstance(replacement, str):
            continue
        pattern = pattern.strip()
        replacement = replacement.strip()
        if not pattern or not replacement:
            continue
        try:
            entries.append((re.compile(pattern), replacement))
        except re.error as e:
            logger.warning(f"[yomigana] invalid personal regex '{pattern}': {e}")
    return entries


def _get_yomigana_map() -> list[tuple[re.Pattern, str]]:
    """共有辞書と個人辞書を合わせた読み仮名辞書を返す。"""
    return _load_public_yomigana_map() + _load_personal_yomigana_map()


async def _broadcast_settings(exclude: WebSocket | None = None):
    _get_auto_approve_enabled()
    msg = json.dumps({"type": "sync_settings", "settings": _settings})
    for client in list(_clients):
        if client is exclude:
            continue
        try:
            await client.send_text(msg)
        except Exception:
            _clients.discard(client)


def _render_diagnostic_text(info: str) -> str:
    rendered = info if re.match(r"^\d{2}:\d{2}:\d{2}\s", info) else f"{_debug_ts()} {info}"
    return rendered.strip()


async def _send_diagnostic_event(rendered_text: str, target: WebSocket | None = None):
    payload = json.dumps({"type": "diagnostic", "text": rendered_text}, ensure_ascii=False)
    targets = [target] if target else list(_clients)
    for client in targets:
        try:
            await client.send_text(payload)
        except Exception:
            _clients.discard(client)


# --- Models (lazy load) ---
_whisper_model = None
_whisper_model_fast = None


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        print("Whisper large-v3 読み込み中...")
        _whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        print("Whisper 準備完了")
    return _whisper_model


def get_whisper_fast():
    """Small model for always-on wake word detection — ~10x faster than large-v3."""
    global _whisper_model_fast
    if _whisper_model_fast is None:
        print("Whisper small 読み込み中 (always-on用)...")
        _whisper_model_fast = WhisperModel("small", device="cpu", compute_type="int8")
        print("Whisper small 準備完了")
    return _whisper_model_fast


async def transcribe(audio_bytes: bytes, fast: bool = False) -> str:
    """音声バイト列をテキストに変換。fast=True で always-on 用高速モード。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, audio_bytes, fast)


_HALLUCINATION_RE = re.compile(
    r"ご視聴|チャンネル登録|高評価|字幕|この動画|お届け|"
    r"ありがとうございました。$|"
    r"(.{5,})\1{2,}"  # 同じフレーズ3回以上繰り返し
)

_INITIAL_PROMPT_TEXT = "ねぇメイ、メイ、今日のスケジュールは？"
_INITIAL_PROMPT_NORMALIZED = re.sub(r'[、。！？\s?]+', '', _INITIAL_PROMPT_TEXT)


def _looks_like_initial_prompt_echo(text: str) -> bool:
    """Reject STT outputs that collapse into the seeded wake prompt."""
    normalized = re.sub(r'[、。！？\s?]+', '', text)
    if not normalized:
        return False

    prompt_variants = {
        _INITIAL_PROMPT_NORMALIZED,
        "メイ今日のスケジュールは",
        "メイメイ今日のスケジュールは",
        "ねぇメイメイ今日のスケジュールは",
        "ねえメイメイ今日のスケジュールは",
    }
    if normalized in prompt_variants:
        return True

    if "今日のスケジュールは" in normalized and normalized.startswith("メイ"):
        if len(normalized) <= len("メイメイ今日のスケジュールは"):
            return True

    if normalized.startswith("メイ") and "今日のスケジュールは" in normalized:
        if re.fullmatch(r"メイ(?:メイ)?今日のスケジュールは", normalized):
            return True

    return False


def _transcribe_sync(audio_bytes: bytes, fast: bool) -> str:
    """Whisper推論（同期）。run_in_executorからスレッドプールで実行。"""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        model = get_whisper_fast() if fast else get_whisper()
        segments, info = model.transcribe(
            f.name, language="ja",
            beam_size=1 if fast else 5,
            vad_filter=fast,  # always-on時のみSilero VADで非音声区間をカット
            initial_prompt=_INITIAL_PROMPT_TEXT,
        )
        seg_list = list(segments)
        text = "".join(seg.text for seg in seg_list).strip()

    if not text:
        return ""

    # Hallucination filter: high no_speech_prob → likely silence misinterpreted
    avg_no_speech = (sum(s.no_speech_prob for s in seg_list) / len(seg_list)) if seg_list else 0
    if avg_no_speech > 0.6:
        logger.info(f"[whisper] hallucination filtered (no_speech={avg_no_speech:.2f}): '{text[:40]}'")
        return ""

    # Hallucination filter: known phantom patterns from silent audio
    if fast and avg_no_speech > 0.3 and _HALLUCINATION_RE.search(text):
        logger.info(f"[whisper] hallucination filtered (pattern+no_speech={avg_no_speech:.2f}): '{text[:40]}'")
        return ""

    return text


_KEYBOARD_PULSE_MIN_SEC = 0.12
_KEYBOARD_PULSE_MAX_SEC = 1.25
_KEYBOARD_PULSE_MIN_PEAK = 0.02
_KEYBOARD_PULSE_MIN_RMS = 0.004
_KEYBOARD_PULSE_MAX_ACTIVE_RATIO = 0.22
_KEYBOARD_PULSE_MIN_CREST = 9.5
_KEYBOARD_PULSE_MIN_FLATNESS = 0.48
_KEYBOARD_PULSE_MAX_FLATNESS = 0.95


def _keyboard_pulse_stats(audio_bytes: bytes) -> dict | None:
    """Convert audio and compute cheap waveform stats for short pulse-like noise."""
    wav = audio_bytes_to_wav(audio_bytes)
    if wav is None or len(wav) < 320:
        return None

    duration = len(wav) / 16000.0
    if duration > _KEYBOARD_PULSE_MAX_SEC:
        return None

    abs_wav = np.abs(wav)
    peak = float(np.max(abs_wav))
    rms = float(np.sqrt(np.mean(np.square(wav))))
    if rms <= 0:
        return None

    frame_size = 320  # 20ms at 16kHz
    usable = len(wav) - (len(wav) % frame_size)
    if usable < frame_size * 2:
        return None
    frames = wav[:usable].reshape(-1, frame_size)
    frame_rms = np.sqrt(np.mean(np.square(frames), axis=1))
    active_threshold = max(rms * 0.6, _KEYBOARD_PULSE_MIN_RMS * 1.5)
    active_ratio = float(np.mean(frame_rms > active_threshold))
    crest = peak / max(rms, 1e-6)
    zero_crossing = float(np.mean(wav[1:] * wav[:-1] < 0)) if len(wav) > 1 else 0.0

    window = np.hanning(len(wav)) if len(wav) > 1 else np.ones_like(wav)
    spectrum = np.abs(np.fft.rfft(wav * window)) + 1e-12
    spectral_flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))

    return {
        "duration": duration,
        "peak": peak,
        "rms": rms,
        "active_ratio": active_ratio,
        "crest": crest,
        "zero_crossing": zero_crossing,
        "spectral_flatness": spectral_flatness,
    }


def _looks_like_keyboard_pulse(audio_bytes: bytes) -> tuple[bool, str]:
    """Heuristically reject short pulse-like sounds such as keyboard taps."""
    stats = _keyboard_pulse_stats(audio_bytes)
    if not stats:
        return False, ""

    duration = stats["duration"]
    peak = stats["peak"]
    rms = stats["rms"]
    active_ratio = stats["active_ratio"]
    crest = stats["crest"]
    zero_crossing = stats["zero_crossing"]
    spectral_flatness = stats["spectral_flatness"]

    if duration < _KEYBOARD_PULSE_MIN_SEC:
        return False, ""
    if peak < _KEYBOARD_PULSE_MIN_PEAK or rms < _KEYBOARD_PULSE_MIN_RMS:
        return False, ""
    if crest < _KEYBOARD_PULSE_MIN_CREST:
        return False, ""
    if active_ratio > _KEYBOARD_PULSE_MAX_ACTIVE_RATIO:
        return False, ""
    if spectral_flatness < _KEYBOARD_PULSE_MIN_FLATNESS or spectral_flatness > _KEYBOARD_PULSE_MAX_FLATNESS:
        return False, ""

    # Very pulse-like sounds usually have sparse active frames with jagged edges.
    if zero_crossing < 0.08 and active_ratio > 0.1:
        return False, ""

    reason = (
        f"duration={duration:.2f}s peak={peak:.4f} rms={rms:.4f} "
        f"active_ratio={active_ratio:.2f} crest={crest:.1f} zcr={zero_crossing:.2f} "
        f"flatness={spectral_flatness:.2f}"
    )
    return True, reason


def _transcribe_sync_with_metrics(audio_bytes: bytes, fast: bool) -> dict:
    """Whisper推論（同期）+ 軽量メトリクス。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        model = get_whisper_fast() if fast else get_whisper()
        segments, info = model.transcribe(
            f.name,
            language="ja",
            beam_size=1 if fast else 5,
            vad_filter=False,
            initial_prompt=_INITIAL_PROMPT_TEXT,
        )
        seg_list = list(segments)
        text = "".join(seg.text for seg in seg_list).strip()

    avg_no_speech = (sum(s.no_speech_prob for s in seg_list) / len(seg_list)) if seg_list else 0.0
    confidence = max(0.0, min(1.0, 1.0 - avg_no_speech))
    return {
        "text": text,
        "avg_no_speech": avg_no_speech,
        "confidence": confidence,
        "language": getattr(info, "language", "ja"),
    }


async def chat_with_llm(messages: list[dict], model: str = "gemma4:e4b") -> str:
    """Ollama でチャット応答を取得"""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# --- STT Post-Correction (Aqua Voice inspired) ---

# 辞書ベース高速置換（LLM より先に適用、レイテンシゼロ）
# (誤認識パターン, 正しいテキスト) — 音韻的に近い誤認識を収録
_STT_DICT: list[tuple[re.Pattern, str]] = [
    # 企業・サービス名
    (re.compile(r'アンソロピック|アンスロピック|アンソロッピック|アントロピック'), 'Anthropic'),
    (re.compile(r'クロード'), 'Claude'),
    (re.compile(r'オープンエーアイ|オープンAI'), 'OpenAI'),
    (re.compile(r'ジェミニ|ジェミナイ'), 'Gemini'),
    (re.compile(r'チャットGPT|チャットジーピーティー'), 'ChatGPT'),
    (re.compile(r'ギットハブ|ギッドハブ'), 'GitHub'),
    (re.compile(r'スラック'), 'Slack'),
    (re.compile(r'ノーション'), 'Notion'),
    # 技術用語
    (re.compile(r'デンダー'), 'カレンダー'),
    (re.compile(r'ウィスパー'), 'Whisper'),
    (re.compile(r'エンバー'), 'Ember'),
    (re.compile(r'プロアクティ[ヴブ]'), 'プロアクティブ'),
    (re.compile(r'アンビエン[スト]'), 'アンビエント'),
    (re.compile(r'ウェブソケッ[トツ]'), 'WebSocket'),
    (re.compile(r'エレクトロン'), 'Electron'),
    (re.compile(r'タイプスクリプト'), 'TypeScript'),
    (re.compile(r'ジャバスクリプト'), 'JavaScript'),
    (re.compile(r'パイソン'), 'Python'),
    # 人名
    (re.compile(r'あきら(?!さん)'), 'Akiraさん'),
]


def _apply_stt_dict(text: str) -> str:
    """辞書ベースの高速 STT 補正。マッチしたら置換して返す。"""
    corrected = text
    for pattern, replacement in _STT_DICT:
        corrected = pattern.sub(replacement, corrected)
    return corrected


# 明らかに補正不要なパターン（短い相槌、感嘆詞、コマンド系）
_STT_SKIP_CORRECTION = re.compile(
    r'^(うん|ええ|はい|いいえ|そう|ね|へー|ふーん|おー|あー|なるほど'
    r'|ありがとう|おはよう|おやすみ|こんにちは|こんばんは'
    r'|メイ|めい|ストップ|とめて|止めて|静かに|もっと話して)$'
)
_STT_SYMBOL_ONLY = re.compile(r'^[^\w\s]+$')

# Patch B3: 音声品質メタコメントを出力後に検出して強制SKIP
_CO_VIEW_AUDIO_QUALITY_RE = re.compile(r'音声が|聞き取り(?:にくい|れない|づらい)|途切れ|ノイズ|音質')

# Patch A2: 疑問文コメントを出力後に検出して強制SKIP
_CO_VIEW_QUESTION_STRIP = re.compile(r'[。！　 ]+$')

# Patch BA1: 統計・市場数値型コメントへのpost-filter（設計原則2: 適切な距離感）
# 背景: 「487億ドルまで成長するらしいよ」「30%増加するらしいよ」のような市場規模・成長率・予測統計を
#       そのまま言うコメントは「豆知識の披露」になり、同居人らしい距離感を壊す。
#       meeting/非meeting問わず全typeに適用（数値が主体の情報提供型コメントを遮断）。
_BA1_STATS_RE = re.compile(
    r'\d{2,}億\s*(?:ドル|円|ユーロ|元)|'        # 市場規模（「487億ドル」等）
    r'\d{1,3}(?:\.\d+)?\s*%\s*(?:成長|増加|増|減少|減|上昇|拡大|縮小)|'  # 成長率
    r'\d{4}年まで[にの]\s*\d'                   # 予測年+数値（「2035年までに487億」等）
)

# Patch AU1: meeting コメントのアドバイス調・汎用コメントを出力後に検出して強制SKIP
# 背景: meeting type でプロンプト禁止にもかかわらず「〜が欠かせない」「〜が重要だよね」等の
#       汎用PMアドバイス調コメントが生成される問題。コード層の安全網として追加。
# Patch AW1: ニュース情報伝達型・具体日付ハルシネーション防止パターンを追加
# 背景: 「さっきのニュースでExcel方眼紙に対応したツールが4月末にリリースらしいよ！」のような
#       enrich素材にLLMが具体的日付を追加するハルシネーション混じり情報伝達コメントがAU1をすり抜けた問題
_CO_VIEW_MEETING_ADVICE_RE = re.compile(
    r'(?:が|は)(?:欠かせ[なない]|重要[だよね]+|大切[だよね]+|大事[だよね]+)|'
    r'プロジェクト管理|アジェンダ管理|スケジュール管理(?:[がはっ]|って)|'
    r'管理(?:が|は)(?:重要|大切|大事|欠かせ)|'
    r'エクセルで(?:管理|整理|作成)|スプレッドシートで|'
    # AW1: ニュース情報伝達型（「さっきのニュースで〜らしいよ」等のハルシネーション混じり報告を遮断）
    r'さっきのニュース[でにから]|ニュース[でにから].{0,30}(?:らしい|だって)|'
    r'[0-9０-９]+月[末初]に.{0,20}(?:リリース|発売|公開)|'
    r'(?:リリース|発売).{0,20}[0-9０-９]+月[末初]|'
    # Patch BB1: meeting業界情報伝達型（「〜業界って...らしいよ」型の第三者情報を会議参加者に伝える系）
    # 背景: 「金融データプロバイダーの業界って、AI影響で結構大変らしいよ。」のような
    #       enrich由来の業界動向情報がAU1をすり抜ける問題。設計原則2（距離感）に基づきSKIP。
    r'(?:業界|市場|産業|分野)って.{0,60}(?:らしいよ|だって|みたいだよ)|'
    r'AI(?:影響|の影響|の波).{0,40}(?:大変|厳しい|苦しい|難しい).{0,20}(?:らしい|みたい|だって)'
)

# Patch BE2: youtube_talk内容反射型コメントフィルター
# 「〜の話なんだね〜」「〜について話してるんだね」等の内容をそのまま反射するコメントを遮断
# 背景: BD1ではmeetingのみ対象だったが、youtube_talkでも「試合データの話してるんだね〜」
#       「オー、無料で使えるローカルLLMの話なんだね！」等の反射型が生成された
# Patch BF2: 「〜させるのね！」「〜してるのね」型を追加（行動確認系）
_CO_VIEW_REFLECTION_RE = re.compile(
    r'(?:の話|について話|って話)(?:してるんだね|してるね|なんだね|なんだ)|'
    r'(?:の話|について)(?:なんだね|なんだ)[〜～]?|'
    r'(?:話|言って)(?:るんだね|るね)[〜～]?$|'
    r'(?:する|させる|してる|している|できる|れる|てる)のね[！。〜～]?',
    re.UNICODE
)

# Patch AU2: meeting enrich検索から除外する汎用ビジネス語セット
# 背景: gcal_title空時に「アジェンダ」「スケジュール」等の汎用語でNews検索→
#       一般PMニュース大量取得→LLMが「PMが欠かせない」等の汎用アドバイスを生成する根本原因
_MEETING_GENERIC_TERMS = frozenset([
    'アジェンダ', '進捗', 'スケジュール', 'プロジェクト', '会議', 'ミーティング',
    'タスク', '計画', '管理', '標準', '手順', '報告', '確認', '共有', '打ち合わせ',
])

# ---------------------------------------------------------------------------
# Co-view: TV/YouTube 視聴中の同居人コメント生成
# ---------------------------------------------------------------------------

_CO_VIEW_COMMENT_COOLDOWN   = 300    # 5分: コメント間隔
_CO_VIEW_INFERENCE_MIN_SNIP = 5      # 推論トリガーに必要な最低スニペット数
_CO_VIEW_ASK_USER_COOLDOWN  = 1800   # 30分: 「何見てるの？」問い合わせ間隔
_CO_VIEW_ASK_USER_MIN_SNIP  = 5      # 問い合わせ前に必要な最低スニペット数
_CO_VIEW_ENRICH_COOLDOWN    = 600    # 10分: 外部情報再取得間隔

_SLACK_BOT_DATA_DIR = Path(
    os.getenv("SLACK_BOT_DATA_DIR",
              str(Path(__file__).resolve().parents[3] / "claude-code-slack-bot" / "data"))
)


@dataclass
class _MediaContext:
    media_buffer: list = field(default_factory=list)   # [{"text": str, "ts": float}]
    inferred_type: str = "unknown"     # baseball|golf|youtube_talk|news|drama|music|other|unknown
    inferred_topic: str = ""
    matched_title: str = ""            # 具体的な作品/番組名 (Pattern O)
    confidence: float = 0.0
    enriched_info: str = ""
    keywords: list = field(default_factory=list)
    last_inferred_at: float = 0.0
    last_enriched_at: float = 0.0
    co_view_last_at: float = 0.0
    ask_user_last_at: float = 0.0
    snippets_since_infer: int = 0
    recent_co_view_comments: list = field(default_factory=list)  # 直近3件のコメント履歴（enrich繰り返し防止）
    # Patch M1: matched_title フォールバック用（直前5分以内の有効な作品名を保持）
    last_valid_matched_title: str = ""
    last_valid_matched_at: float = 0.0
    # Patch AL2: last_valid取得時のcontent_type記録（youtube_talk→youtube_talkのfallback抑制に使用）
    last_valid_inferred_type: str = ""
    # Meeting digest spam prevention
    last_meeting_digest_signature: str = ""
    last_meeting_digest_at: float = 0.0
    meeting_digest_pending_signature: str = ""
    meeting_digest_pending_title: str = ""
    meeting_digest_pending_topic: str = ""
    meeting_digest_pending_transcript: str = ""
    meeting_digest_pending_keywords: list = field(default_factory=list)
    meeting_digest_pending_at: float = 0.0
    # Patch Y1: enrich query rotation — 毎回同じニュースを繰り返さないよう検索suffixをローテーション
    enrich_query_idx: int = 0
    # Patch Y1補: 同一作品で既に返した記事タイトルを記憶して重複を除外
    enrich_seen_titles: set = field(default_factory=set)
    # Patch Z3: 直近コメントで実際に使用したenrich内容を記録（30分間の繰り返し防止）
    last_enrich_used_lines: list = field(default_factory=list)  # 直近コメントに渡したenrich行リスト
    last_enrich_used_at: float = 0.0
    # Patch AK1: content_type変化のhysteresis（連続2回確認で変化確定）
    _pending_type: str = ""       # 確定待ちの新content_type
    _pending_type_count: int = 0  # 同じtypeが連続で判定された回数

    def add_snippet(self, text: str):
        # STT重複除去: 直前のスニペットの先頭50文字と80%以上一致なら追加しない
        if self.media_buffer:
            prev = self.media_buffer[-1]["text"]
            head_len = min(50, len(prev), len(text))
            if head_len >= 10:
                common = sum(c1 == c2 for c1, c2 in zip(prev[:head_len], text[:head_len]))
                similarity = common / head_len
                if similarity >= 0.8:
                    logger.debug(f"[co_view] dedup skip (head_sim={similarity:.2f}): '{text[:30]}'")
                    return
        self.media_buffer.append({"text": text, "ts": time.time()})
        self.snippets_since_infer += 1
        if len(self.media_buffer) > 20:
            self.media_buffer = self.media_buffer[-20:]

    def get_buffer_text(self, last_n: int = 10) -> str:
        return "\n".join(e["text"] for e in self.media_buffer[-last_n:])

    def reset(self):
        self.media_buffer.clear()
        self.inferred_type = "unknown"
        self.inferred_topic = ""
        self.matched_title = ""
        self.confidence = 0.0
        self.enriched_info = ""
        self.keywords.clear()
        self.snippets_since_infer = 0
        self.recent_co_view_comments.clear()
        # Patch M1: last_valid は reset 時も保持（5分クールダウンは _handle_co_view 側で判断）
        # Patch Z5: last_enrich_used_lines/at は reset 時も保持（5minリセット後も30分クールダウン継続）
        # Patch AK1: pending_type は reset 時にクリア（前セッションの中途pendingを引き継がない）
        self._pending_type = ""
        self._pending_type_count = 0
        self.meeting_digest_pending_signature = ""
        self.meeting_digest_pending_title = ""
        self.meeting_digest_pending_topic = ""
        self.meeting_digest_pending_transcript = ""
        self.meeting_digest_pending_keywords = []
        self.meeting_digest_pending_at = 0.0


_media_ctx = _MediaContext()

# Patch AQ2: グローバルenrich使用履歴（enrich cacheリセット後も同ニュース再利用を防ぐ）
# key: enrich行の文字列、value: 使用したUnix時刻
_GLOBAL_ENRICH_USED: dict[str, float] = {}
# Patch AT1: 3600→10800秒（3時間）に延長（アニメ等2-3時間視聴で同一情報が1時間後に再出現する問題解消）
# Patch BF1: 10800→3600秒に短縮（Z3+AQ2ダブルブロックでZ3後にAQ2が3時間ブロックし続けコメント停止するため）
#            AI系youtube_talkでニュース多様性が低い場合、同一ニュースを1時間後に再利用することを許容する
_GLOBAL_ENRICH_REUSE_SEC = 3600  # 1時間は同じenrich行をコメントに使わない

# co_view 同時実行防止ロック + 原文重複検出
_co_view_lock = asyncio.Lock()
_STT_RAW_SEEN: dict[str, float] = {}   # trigger_text先頭60文字 → 最終受信timestamp
_STT_RAW_DEDUP_WINDOW = 30.0           # 30秒以内の同一原文はスキップ

# TV guide cache
_tv_guide_cache: dict = {"data": "", "fetched_at": 0.0}
_meeting_digest_lock = asyncio.Lock()
_meeting_digest_idle_task: asyncio.Task | None = None


def _load_youtube_titles() -> list:
    path = _SLACK_BOT_DATA_DIR / "youtube-history-cache.json"
    try:
        data = json.loads(path.read_text())
        titles = [e["title"] for e in data.get("entries", []) if e.get("title")]
        logger.info(f"[co_view] youtube titles loaded: {len(titles)} from {path}")
        return titles
    except Exception as e:
        logger.warning(f"[co_view] youtube titles load failed: {e} (path: {path})")
        return []


def _load_interest_priorities() -> dict:
    try:
        data = json.loads((_SLACK_BOT_DATA_DIR / "interest-cache.json").read_text())
        return data.get("priorities", {})
    except Exception:
        return {}


_youtube_titles: list = _load_youtube_titles()
_interest_priorities: dict = _load_interest_priorities()


def _find_matching_yt_titles(buffer_text: str, top_n: int = 5) -> list:
    """バッファテキストに単語レベルでマッチするYouTubeタイトルを返す。"""
    if not _youtube_titles:
        return []
    words = set(re.findall(r'[^\s、。！？!?]{1,}', buffer_text))
    scored = []
    for title in _youtube_titles:
        score = sum(1 for w in words if w in title)
        if score > 0:
            logger.debug(f"[co_view/yt_match] title='{title[:40]}' score={score}")
            scored.append((score, title))
    scored.sort(key=lambda x: -x[0])
    results = [t for _, t in scored[:top_n]]
    logger.info(f"[co_view/yt_match] words={list(words)[:10]} hits={len(scored)} filtered={len(results)} top={results[:2]}")
    return results


async def _fetch_tv_guide() -> str:
    """NHK RSS + Google News でTV番組表を取得（1時間キャッシュ）。"""
    now = time.time()
    if now - _tv_guide_cache["fetched_at"] < 3600 and _tv_guide_cache["data"]:
        return _tv_guide_cache["data"]
    results: list = []
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            rss_url = "https://news.google.com/rss/search?q=TV番組+今日&hl=ja&gl=JP&ceid=JP:ja"
            resp = await client.get(rss_url)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('.//item')[:5]:
                    title = item.findtext('title', '')
                    if title:
                        results.append(title)
    except Exception as e:
        logger.debug(f"[tv_guide] fetch failed: {e}")
    data = "\n".join(results)
    _tv_guide_cache["data"] = data
    _tv_guide_cache["fetched_at"] = now
    return data


_YT_AD_NARRATION = re.compile(
    r'(続きはチャ.{1,15}確認|チャット欄確認|チャットで確認してね|次はチャット|チャットで確認|'
    r'詳しくはこちら|今すぐダウンロード|今すぐ登録|無料で始め|アプリをダウンロード|'
    r'リンクは概要欄)',
)  # Patch C改: 続きはチャ*.{1,15}確認 で STT誤認識バリアント（チャトレ/チャット欄等）も除去

# STT補正LLMがデフォルト応答として返しがちなパターン（これが返ってきたら元テキストを使う）
_STT_LLM_DEFAULT_RE = re.compile(
    r'^(今日のスケジュールは？?|今回のスケジュールは？?|おめでとうございます[。！]?'
    r'|何かお手伝いできますか[？。]?|ご質問があればどうぞ[。！]?'
    r'|はい、お手伝いします[。！]?|了解です[。！]?'
    r'|ありがとうございます[。！]?)$'
)


async def _correct_media_transcript(text: str) -> str:
    """メディア音声(実況・YouTubeなど)向けSTT補正。"""
    text = _YT_AD_NARRATION.sub('', text).strip()
    if not text:
        return ""
    if _STT_SYMBOL_ONLY.match(text.strip()):
        return ""
    dict_corrected = _apply_stt_dict(text)
    if dict_corrected != text:
        logger.info(f"[co_view/stt_dict] '{text}' → '{dict_corrected}'")
        text = dict_corrected
    if len(text) < 4 or _STT_SKIP_CORRECTION.match(text.strip()):
        return text
    context = [e["text"] for e in _media_ctx.media_buffer[-3:]]
    context_block = ("\n直近の音声:\n" + "\n".join(f"- {t}" for t in context)) if context else ""
    messages = [
        {"role": "system", "content": (
            "あなたはメディア音声（スポーツ実況・YouTubeコメンタリー・ニュース）の音声認識校正者です。\n"
            "音声認識の出力を正しい日本語に修正してください。\n"
            "特にスポーツ実況: 選手名（大谷、フリーマン、シェフラー等）、チーム名（ドジャース等）を正確に。\n"
            "意味が通じない単語は音の類似性と文脈から推測・置換してください。\n"
            "修正後のテキストだけを返してください。説明不要。"
            f"{context_block}"
        )},
        {"role": "user", "content": text},
    ]
    try:
        corrected = await asyncio.wait_for(chat_with_llm(messages, "gemma4:e4b"), timeout=15.0)
        corrected = corrected.strip().strip('"\'「」')
        if corrected and corrected != text:
            if not corrected or corrected in ("（沈黙）", "(沈黙)", "…", "...", ""):
                logger.info(f"[co_view/stt] hallucination(empty): '{text}' → '{corrected}' → keep original")
                return text
            if len(corrected) > len(text) * 2.5:  # Patch BH1: 3.0→2.5倍に厳格化（短文誤変換検出強化）
                logger.info(f"[co_view/stt] hallucination(2.5x): '{text}'({len(text)}) → '{corrected}'({len(corrected)}) → keep original")
                return text
            if _STT_LLM_DEFAULT_RE.match(corrected.strip()):
                logger.info(f"[co_view/stt] llm_default: '{text}' → '{corrected}' → keep original")
                return text
            # Patch Z1: 補正後テキストに繰り返しフレーズが含まれる場合は元テキストを返す
            if _has_repeated_phrase(corrected):
                logger.info(f"[co_view/stt] hallucination(repeat): '{text[:40]}' → repeat pattern detected → keep original")
                return text
            logger.info(f"[co_view/stt] '{text}' → '{corrected}'")
            return corrected
    except Exception as e:
        logger.debug(f"[co_view/stt] failed: {e}")
    return text


async def _infer_media_content() -> dict:
    """バッファ済み音声テキストから視聴コンテンツを推測する。"""
    buffer_text = _media_ctx.get_buffer_text(last_n=10)
    if not buffer_text:
        return {"content_type": "unknown", "topic": "", "matched_title": "", "keywords": [], "confidence": 0.0}

    matched_titles = _find_matching_yt_titles(buffer_text, top_n=5)
    yt_hint = ""
    if matched_titles:
        yt_hint = "\n\nYouTube視聴履歴マッチ(参考):\n" + "\n".join(f"- {t}" for t in matched_titles)
    elif _youtube_titles:
        sample = _youtube_titles[:20]
        yt_hint = "\n\nYouTube視聴履歴(参考):\n" + "\n".join(f"- {t}" for t in sample)

    interest_hint = ""
    if _interest_priorities:
        top = sorted(_interest_priorities.items(), key=lambda x: -x[1])[:5]
        interest_hint = "\n\nユーザーの興味(優先度順):\n" + "\n".join(f"- {k}: {v:.2f}" for k, v in top)

    # Patch Z4: 直前6分以内に特定済みのmatched_titleをhintとして渡し、youtube_talk判定でも作品継続性を維持
    # Patch AE1: 900s→360sに短縮（長すぎると別コンテンツに切り替わっても古いtitleが引き継がれるため）
    import time as _time
    prev_match_hint = ""
    if (_media_ctx.last_valid_matched_title
            and ((_time.time() - _media_ctx.last_valid_matched_at) < 360)
            and _media_ctx.inferred_type != "meeting"):
        prev_match_hint = f"\n\n直前に特定済みの作品(参考): {_media_ctx.last_valid_matched_title}\n※この会話が同じ作品に関するアフタートーク等の場合、matched_titleに引き継ぐこと"

    tv_guide = await _fetch_tv_guide()
    tv_hint = f"\n\nTV番組表(参考):\n{tv_guide[:300]}" if tv_guide else ""

    messages = [
        {"role": "system", "content": (
            "あなたはメディアコンテンツ分析者です。音声認識テキストから視聴コンテンツを推測してください。\n"
            "以下のJSONのみ返してください。余分なテキスト不要。\n"
            '{"content_type":"meeting|baseball|golf|anime|vtuber|youtube_talk|news|drama|music|other|unknown",'
            '"topic":"具体的なトピック(例:ドジャースvsパドレス、Re:ゼロ2期17話、京セラ案件の戦略会議)",'
            '"matched_title":"具体的なアニメ/番組/ゲーム/VTuberチャンネル名(不明なら空文字)",'
            '"keywords":["検索キーワード1","キーワード2"],'
            '"confidence":0.0から1.0}\n\n'
            "content_type 選択ルール:\n"
            "- meeting: ★最優先。話者が会話・発言している状態のビジネス会議・打ち合わせ・商談。"
            "以下のいずれかが出現すれば meeting:\n"
            "  * ビジネス用語: 「アジェンダ」「議事録」「マイルストーン」「要件定義」「PMO」「KPI」「ROI」「ステークホルダー」\n"
            "  * 会議フレーズ: 「では始めます」「それでは」「共有します」「確認させてください」「以上です」「いかがでしょうか」\n"
            "  * クライアント・プロジェクト名が文脈に出る（例: 「京セラ」「KC」「KC：」「CSC」「二機工業」+ 戦略/提案/進捗）\n"
            "  ※ KC = 京セラ（クライアント）の略称。「KC：社内」「KC：」が出現すれば meeting 確定\n"
            "  ※ CSC = 株式会社アバントの部署名（自社）。「CSC|内部」等が出現すれば社内会議として meeting 確定\n"
            "  * 複数人が交互に発言している（会話のターンテイク）\n"
            "  ★ Patch AD1 meeting除外ルール: 以下は絶対に meeting にしない → youtube_talk または news にする:\n"
            "    - YouTube解説動画・ITニュース・技術デモ・製品発表動画・ポッドキャスト\n"
            "    - 「〜をリリースしました」「〜が公開されました」「〜の解説をします」「〜を発表しました」等のナレーション/報道フレーズがある場合\n"
            "    - 企業名やサービス名が出ても、Akiraさんが実際に参加している会議でなければ meeting 不可\n"
            "    - meetingはAkiraさん自身がリアルタイムで参加している双方向会議のみ（視聴コンテンツは meeting にしない）\n"
            "- anime: アニメキャラ名・作品固有名詞が出現(例: レム/エミリア/プリシラ → anime)\n"
            "- vtuber: VTuber名・ホロライブ等が出現\n"
            "- baseball: 大谷/ドジャース等の明確な固有名詞がある場合のみ\n"
            "- golf: マスターズ/タイガー等の明確な固有名詞がある場合のみ\n"
            "- youtube_talk: 上記に該当しない一般的なYouTube/ラジオトーク\n\n"
            "matched_title 推定方法(登場人物名・固有名詞から作品名を推定):\n"
            "- エミリア/レム/スバル/プリシラ/ベアトリス/クリスタ/パンドラ/エレシア/ヘルム/テレシア/ビルフェル/ラインハルト/フォルトナ/エキドナ/サテラ/ロズワール/ペテルギウス → Re:ゼロから始める異世界生活\n"
            "- 知夏/大輝/矢野晴/美咲/西田(ラブコメ文脈) → 青の箱 ※youtube_talkで感想を話していても対象作品をmatched_titleにセット\n"
            "- 白上フブキ/宝鐘マリン/兎田ぺこら → ホロライブ\n"
            "- ゼルダ/リンク/ガノン → ゼルダの伝説\n"
            "- 声優名・スタッフ名からも推定可。確信がなければ空文字。\n"
            "- 声優名 + ラジオ/配信/ゲスト/番組 → matched_title に「[声優名]のラジオ」または番組名を推定\n"
            "  例: 「藤井さん」「石川さん」などの声優名が複数出て収録/演技/キャラ話題 → matched_title=「[声優名]ラジオ」\n"
            "topic の具体化ルール:\n"
            "- 出演者名・声優名・番組名・作品名を必ず topic に含める\n"
            "- 「フィクション作品の考察」「演技についての感想交換」のような汎用説明文は厳禁\n"
            "- 「個人的な経験や感情についての対談/回想」「コンテンツの続編に関するトーク」のような汎用表現も禁止\n"
            "- 良い例: 「藤井ゆきよ・石川由依の声優ラジオ」「Re:ゼロ3期エミリア戦闘シーン」「クルノー均衡と寡占市場の解説」\n"
            "- 悪い例: 「フィクション作品の演技や展開についての感想交換」「個人的な経験や感情についての対談」\n"
            "baseball/golf は明確な固有名詞(大谷/ドジャース/マスターズ等)がある場合のみ。\n"
            "Patch U1 - youtube_talk の keywords ルール:\n"
            "- 会話中に登場する固有名詞（人名・会社名・サービス名・製品名・チャンネル名）を優先的に keywords に含める\n"
            "- 「起業」「財務」「マーケティング」のような抽象カテゴリ語は keywords に入れない\n"
            "- 例: 会話に「ドコモ」「ChatGPT」「孫正義」が出た → keywords: [\"ドコモ\", \"ChatGPT\", \"孫正義\"]\n"
            "- 固有名詞が1つも特定できない場合のみ抽象キーワードを使用"
            f"{yt_hint}{interest_hint}{tv_hint}{prev_match_hint}"
        )},
        {"role": "user", "content": f"音声テキスト:\n{buffer_text}"},
    ]
    try:
        raw = await asyncio.wait_for(chat_with_llm(messages, "gemma4:e4b"), timeout=15.0)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw)
        # baseball/golf で conf < 0.6 → youtube_talk にフォールバック（改善2）
        if result.get("content_type") in ("baseball", "golf") and float(result.get("confidence", 0.0)) < 0.6:
            logger.info(f"[co_view/infer] low-conf {result['content_type']} → youtube_talk fallback")
            result["content_type"] = "youtube_talk"
        # Patch P1: matched_title STT誤変換正規化（B-ZERO等→Re:ゼロ）
        if result.get("matched_title"):
            mt = result["matched_title"]
            mt = re.sub(r'B-?ZERO|B-?ゼロ', 'Re:ゼロ', mt, flags=re.IGNORECASE)
            result["matched_title"] = mt
        # Patch P2: topic略称からmatched_title補完（リゼロ/rezero等）
        # Patch Q1: Re:ゼロ固有キャラ名からmatched_title補完（レグルス/エキドナ/サテラ等）
        if not result.get("matched_title"):
            topic_lower = (result.get("topic") or "").lower()
            topic_str = result.get("topic") or ""
            # Patch R1: 主要キャラ（エミリア/スバル/レム/プリシラ）を追加
            # Patch AH1: 「ライ」を除外（ライブ・ライン・ライト等の一般語に誤マッチするため）
            _REZERO_CHARS = ["エミリア", "スバル", "レム", "プリシラ", "レグルス", "エキドナ", "サテラ", "ロズワール", "フレデリカ", "ガーフィール", "ベアトリス", "オットー", "エルザ", "メィリィ", "ラム", "クルシュ", "フェルト", "セシルス"]
            if "リゼロ" in topic_str or "rezero" in topic_lower or "re:zero" in topic_lower:
                result["matched_title"] = "Re:ゼロから始める異世界生活"
                logger.info("[co_view/infer] matched補完: topic略称(リゼロ)→Re:ゼロから始める異世界生活")
            elif any(c in topic_str for c in _REZERO_CHARS):
                result["matched_title"] = "Re:ゼロから始める異世界生活"
                matched_char = next(c for c in _REZERO_CHARS if c in topic_str)
                logger.info(f"[co_view/infer] matched補完: Re:ゼロキャラ({matched_char})→Re:ゼロから始める異世界生活")
            # Patch Q2: 青の箱キャラ名からmatched_title補完
            _AONOBOX_CHARS = ["知夏", "大輝", "青の箱", "矢野晴", "美咲"]
            if not result.get("matched_title") and any(c in topic_str for c in _AONOBOX_CHARS):
                result["matched_title"] = "青の箱"
                matched_char = next(c for c in _AONOBOX_CHARS if c in topic_str)
                logger.info(f"[co_view/infer] matched補完: 青の箱キャラ({matched_char})→青の箱")
        # Patch AA2: buffer_textに番組名が直接言及されている場合の正規表現補完
        # LLM(gemma4)が明示的な番組名を見落とすケースへの対策（例: オールナイトニッポン）
        if not result.get("matched_title"):
            if "オールナイトニッポン" in buffer_text:
                ann_m = re.search(r'([^\s、。\n！？]{1,8})(?:の|と)?オールナイトニッポン', buffer_text)
                talent_prefix = ann_m.group(1) if ann_m and len(ann_m.group(1)) >= 2 else ""
                talent_prefix = re.sub(r'[がのをにはでもと]+$', '', talent_prefix).strip()
                if talent_prefix:
                    result["matched_title"] = f"{talent_prefix}のオールナイトニッポン"
                else:
                    result["matched_title"] = "オールナイトニッポン"
                logger.info(f"[co_view/infer] Patch AA2: buffer直接検出 matched_title={result['matched_title']!r}")
        # Patch AN1: buffer_text直接マッチ（LLMのtopic欄補完が効かなかった場合の最終フォールバック）
        # 対象: ガーフィール等のキャラ名がbuffer_textに含まれているのにmatched_title未特定なケース
        if not result.get("matched_title"):
            _AN1_REZERO = ["ゼロから始める異世界生活", "エミリア", "スバル", "レム", "ガーフィール", "ベアトリス",
                           "オットー", "プリシラ", "エキドナ", "サテラ", "ロズワール", "ユリウス",
                           "レグルス", "テレシア", "ヴィルヘルム", "リカード"]
            for _an1_char in _AN1_REZERO:
                if _an1_char in buffer_text:
                    result["matched_title"] = "Re:ゼロから始める異世界生活"
                    if result.get("content_type") in ("unknown", "youtube_talk"):
                        result["content_type"] = "anime"
                    if float(result.get("confidence") or 0.0) < 0.75:
                        result["confidence"] = 0.75
                    logger.info(f"[co_view/infer] Patch AN1: buffer_text直接マッチ '{_an1_char}' → matched_title=Re:ゼロから始める異世界生活")
                    break
        # Patch AR1: 青の箱 STT誤変換バリアントでbuffer_text直接マッチ
        # 背景: 知夏→千夏、大輝→大気 などSTT誤変換により _AONOBOX_CHARS が機能しないケースへの対策
        if not result.get("matched_title"):
            _AR1_AONOBOX = ["知夏", "大輝", "青の箱", "矢野晴", "美咲",
                            "千夏", "大気",  # STT誤変換バリアント（知夏→千夏, 大輝→大気）
                            "チカ", "タイキ"]  # カタカナ読みバリアント
            for _ar1_char in _AR1_AONOBOX:
                if _ar1_char in buffer_text:
                    result["matched_title"] = "青の箱"
                    if result.get("content_type") in ("unknown", "youtube_talk"):
                        result["content_type"] = "anime"
                    if float(result.get("confidence") or 0.0) < 0.75:
                        result["confidence"] = 0.75
                    logger.info(f"[co_view/infer] Patch AR1: buffer_text直接マッチ '{_ar1_char}' → matched_title=青の箱")
                    break
        logger.info(f"[co_view/infer] type={result.get('content_type')} topic='{result.get('topic')}' matched='{result.get('matched_title','')}' kws={result.get('keywords',[])} conf={result.get('confidence')}")
        return result
    except Exception as e:
        logger.warning(f"[co_view/infer] failed: {e}")
        # Patch AN1: 例外時もbuffer_text直接マッチを試みる（JSONパース失敗等でも早期matched_title特定）
        fallback = {"content_type": "unknown", "topic": "", "matched_title": "", "keywords": [], "confidence": 0.0}
        _AN1_REZERO = ["ゼロから始める異世界生活", "エミリア", "スバル", "レム", "ガーフィール", "ベアトリス",
                       "オットー", "プリシラ", "エキドナ", "サテラ", "ロズワール", "ユリウス", "レグルス"]
        for _an1_char in _AN1_REZERO:
            if _an1_char in buffer_text:
                fallback["matched_title"] = "Re:ゼロから始める異世界生活"
                fallback["content_type"] = "anime"
                fallback["confidence"] = 0.75
                fallback["topic"] = "Re:ゼロから始める異世界生活関連"
                logger.info(f"[co_view/infer] Patch AN1: infer失敗時buffer直接マッチ '{_an1_char}'")
                break
        return fallback


# Patch W2: Google Calendar から現在の会議タイトルを取得するキャッシュ
_gcal_token_cache: dict = {"access_token": "", "expires_at": 0.0}
_gcal_meeting_cache: dict = {"title": "", "fetched_at": 0.0, "ttl": 300.0}

async def _fetch_current_gcal_meeting() -> str:
    """Google Calendar API で現在時刻付近の会議タイトルを取得。5分キャッシュ。"""
    now = time.time()
    if now - _gcal_meeting_cache["fetched_at"] < _gcal_meeting_cache["ttl"]:
        return _gcal_meeting_cache["title"]

    try:
        import json as _json
        # access_token がなければ refresh_token で取得
        if now >= _gcal_token_cache["expires_at"] - 60:
            cred_path = "/Users/akira/.openclaw/credentials/google_oauth.json"
            token_path = "/Users/akira/.config/google-calendar-mcp/tokens.json"
            cred = _json.load(open(cred_path))["installed"]
            tok = _json.load(open(token_path))["normal"]
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post("https://oauth2.googleapis.com/token", data={
                    "client_id": cred["client_id"],
                    "client_secret": cred["client_secret"],
                    "refresh_token": tok["refresh_token"],
                    "grant_type": "refresh_token",
                })
                r = resp.json()
                _gcal_token_cache["access_token"] = r["access_token"]
                _gcal_token_cache["expires_at"] = now + r.get("expires_in", 3600)

        # 現在時刻 ±30分 のイベントを取得
        import datetime as _dt
        jst = _dt.timezone(_dt.timedelta(hours=9))
        t_min = (_dt.datetime.now(jst) - _dt.timedelta(minutes=10)).isoformat()
        t_max = (_dt.datetime.now(jst) + _dt.timedelta(minutes=30)).isoformat()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers={"Authorization": f"Bearer {_gcal_token_cache['access_token']}"},
                params={
                    "timeMin": t_min, "timeMax": t_max,
                    "singleEvents": "true", "orderBy": "startTime",
                    "maxResults": 3, "fields": "items(summary,start,end,description)",
                },
            )
            items = resp.json().get("items", [])
            title = ""
            if items:
                # 最初のイベントのタイトルを使う
                title = items[0].get("summary", "")
                logger.info(f"[co_view/gcal] current meeting: '{title}'")
            _gcal_meeting_cache["title"] = title
            _gcal_meeting_cache["fetched_at"] = now
            return title
    except Exception as e:
        logger.debug(f"[co_view/gcal] fetch failed: {e}")
        _gcal_meeting_cache["fetched_at"] = now  # エラー時も5分待つ
        return ""


def _meeting_digest_signature(title: str, topic: str, transcript: str) -> str:
    payload = {
        "title": title.strip(),
        "topic": topic.strip(),
        "transcript": re.sub(r"\s+", " ", transcript.strip())[:600],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _capture_meeting_digest_snapshot() -> str | None:
    if _media_ctx.inferred_type != "meeting":
        return None
    if len(_media_ctx.media_buffer) < MEETING_SUMMARY_MIN_SNIPPETS:
        return None

    meeting_title = _gcal_meeting_cache.get("title", "") or ""
    topic = _media_ctx.inferred_topic or meeting_title or "会議"
    transcript = _media_ctx.get_buffer_text(last_n=10)
    signature = _meeting_digest_signature(meeting_title, topic, transcript)

    _media_ctx.meeting_digest_pending_signature = signature
    _media_ctx.meeting_digest_pending_title = meeting_title
    _media_ctx.meeting_digest_pending_topic = topic
    _media_ctx.meeting_digest_pending_transcript = transcript
    _media_ctx.meeting_digest_pending_keywords = list(_media_ctx.keywords or [])
    _media_ctx.meeting_digest_pending_at = time.time()
    return signature


def _cancel_meeting_digest_idle_task() -> None:
    global _meeting_digest_idle_task
    if _meeting_digest_idle_task and not _meeting_digest_idle_task.done():
        _meeting_digest_idle_task.cancel()
    _meeting_digest_idle_task = None


def _schedule_meeting_digest_idle_task() -> None:
    global _meeting_digest_idle_task
    signature = _capture_meeting_digest_snapshot()
    if not signature:
        return

    _cancel_meeting_digest_idle_task()

    async def _worker(expected_signature: str) -> None:
        try:
            await asyncio.sleep(MEETING_SUMMARY_IDLE_SEC)
            if _media_ctx.meeting_digest_pending_signature != expected_signature:
                return
            if time.time() - _media_ctx.meeting_digest_pending_at < MEETING_SUMMARY_IDLE_SEC:
                return
            if _media_ctx.last_meeting_digest_signature == expected_signature:
                return
            if len(_media_ctx.meeting_digest_pending_transcript.strip()) < 10:
                return

            bot_id = _resolve_meeting_summary_bot_id()
            if not bot_id:
                logger.info("[meeting_digest] slack target not configured, skip")
                return

            async with _meeting_digest_lock:
                if _media_ctx.meeting_digest_pending_signature != expected_signature:
                    return
                if _media_ctx.last_meeting_digest_signature == expected_signature:
                    return

                digest = await _generate_meeting_digest(
                    meeting_title=_media_ctx.meeting_digest_pending_title,
                    topic=_media_ctx.meeting_digest_pending_topic,
                    transcript=_media_ctx.meeting_digest_pending_transcript,
                    keywords=list(_media_ctx.meeting_digest_pending_keywords or []),
                )
                ts = await slack_post_message(bot_id, digest)
                _media_ctx.last_meeting_digest_signature = expected_signature
                _media_ctx.last_meeting_digest_at = time.time()
                if ts:
                    logger.info(f"[meeting_digest] sent to Slack bot={bot_id} ts={ts}")
                else:
                    logger.warning(f"[meeting_digest] failed to post to Slack bot={bot_id}")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"[meeting_digest] idle worker failed: {e}")

    _meeting_digest_idle_task = asyncio.create_task(_worker(signature))


def _build_meeting_digest_messages(
    *,
    meeting_title: str,
    topic: str,
    transcript: str,
    keywords: list[str],
) -> list[dict]:
    keyword_text = ", ".join(keywords[:8]) if keywords else "(なし)"
    return [
        {
            "role": "system",
            "content": (
                "あなたは会議メモの整理役です。"
                "入力された音声認識テキストだけを使って、Slackに貼れる日本語の会議メモを作ってください。"
                "推測で補わず、会話中に明示された事実だけを使ってください。"
                "必ずJSONのみを返してください。"
                "形式は次のとおりです: "
                '{"summary":"1〜2文の要約","minutes":["議事録の箇条書き"],'
                '"decisions":["決定事項の箇条書き"],'
                '"todos":["TODOの箇条書き"],'
                '"next_actions":["NextActionの箇条書き"]}'
                " どれも不明なら空配列にしてください。"
                "余計な前置き、コードブロック、説明文は不要です。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"会議タイトル: {meeting_title or '(なし)'}\n"
                f"推定トピック: {topic or '(なし)'}\n"
                f"キーワード: {keyword_text}\n\n"
                "直近の音声:\n"
                f"{transcript}"
            ),
        },
    ]


def _parse_json_object(text: str) -> dict | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_meeting_items(value: object) -> list[str]:
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return items[:6]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _format_meeting_digest_message(
    *,
    meeting_title: str,
    topic: str,
    payload: dict | None,
    transcript: str,
) -> str:
    summary = ""
    minutes: list[str] = []
    decisions: list[str] = []
    todos: list[str] = []
    next_actions: list[str] = []

    if payload:
        summary = str(payload.get("summary", "")).strip()
        minutes = _normalize_meeting_items(payload.get("minutes"))
        decisions = _normalize_meeting_items(payload.get("decisions"))
        todos = _normalize_meeting_items(payload.get("todos"))
        next_actions = _normalize_meeting_items(payload.get("next_actions"))

    if not summary:
        summary = "会議内容を整理したよ"

    if not minutes:
        minutes = [f"直近の音声: {transcript[:160].strip() or '未確認'}"]
    if not decisions:
        decisions = ["未確認"]
    if not todos:
        todos = ["未確認"]
    if not next_actions:
        next_actions = ["未確認"]

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    lines = [
        "*会議メモ*",
    ]
    if meeting_title.strip():
        lines.append(f"*会議名:* {meeting_title.strip()}")
    if topic.strip():
        lines.append(f"*トピック:* {topic.strip()}")
    lines.extend([
        "",
        f"*要約*\n{summary}",
        "",
        f"*議事録*\n{bullets(minutes)}",
        "",
        f"*決定事項*\n{bullets(decisions)}",
        "",
        f"*TODO*\n{bullets(todos)}",
        "",
        f"*NextAction*\n{bullets(next_actions)}",
    ])
    return "\n".join(lines).strip()


async def _generate_meeting_digest(
    *,
    meeting_title: str,
    topic: str,
    transcript: str,
    keywords: list[str],
) -> str:
    model = (
        _settings.get("meetingSummaryModel")
        or _settings.get("ambientModel")
        or _settings.get("modelSelect")
        or "gemma4:e4b"
    )
    messages = _build_meeting_digest_messages(
        meeting_title=meeting_title,
        topic=topic,
        transcript=transcript,
        keywords=keywords,
    )
    try:
        raw = await asyncio.wait_for(chat_with_llm(messages, model), timeout=40.0)
        payload = _parse_json_object(raw or "")
    except Exception as e:
        logger.warning(f"[meeting_digest] generation failed: {e}")
        payload = None
    return _format_meeting_digest_message(
        meeting_title=meeting_title,
        topic=topic,
        payload=payload,
        transcript=transcript,
    )


def _resolve_meeting_summary_bot_id() -> str | None:
    candidates = MEETING_SUMMARY_TARGET_BOTS or ["mei"]
    for bot_id in candidates:
        if SLACK_USER_TOKENS.get(bot_id) and SLACK_DM_CHANNELS.get(bot_id):
            return bot_id
    for bot_id in ("mei", "eve"):
        if SLACK_USER_TOKENS.get(bot_id) and SLACK_DM_CHANNELS.get(bot_id):
            return bot_id
    return None


async def _maybe_send_meeting_digest() -> None:
    if not _ambient_listener:
        return
    signature = _capture_meeting_digest_snapshot()
    if not signature:
        return

    now = time.time()
    meeting_title = _media_ctx.meeting_digest_pending_title
    topic = _media_ctx.meeting_digest_pending_topic
    transcript = _media_ctx.meeting_digest_pending_transcript

    if (
        _media_ctx.last_meeting_digest_signature == signature
        and now - _media_ctx.last_meeting_digest_at < MEETING_SUMMARY_COOLDOWN_SEC
    ):
        return

    bot_id = _resolve_meeting_summary_bot_id()
    if not bot_id:
        logger.info("[meeting_digest] slack target not configured, skip")
        return

    async with _meeting_digest_lock:
        # Re-check after acquiring the lock to avoid duplicate sends.
        now = time.time()
        if (
            _media_ctx.last_meeting_digest_signature == signature
            and now - _media_ctx.last_meeting_digest_at < MEETING_SUMMARY_COOLDOWN_SEC
        ):
            return

        digest = await _generate_meeting_digest(
            meeting_title=meeting_title,
            topic=topic,
            transcript=transcript,
            keywords=list(_media_ctx.meeting_digest_pending_keywords or _media_ctx.keywords or []),
        )
        if not digest:
            return

        ts = await slack_post_message(bot_id, digest)
        _media_ctx.last_meeting_digest_signature = signature
        _media_ctx.last_meeting_digest_at = now
        if ts:
            logger.info(f"[meeting_digest] sent to Slack bot={bot_id} ts={ts}")
        else:
            logger.warning(f"[meeting_digest] failed to post to Slack bot={bot_id}")


async def _enrich_media_context() -> str:
    """inferred contentに基づき外部情報(GoogleNews RSS / Wikipedia)を取得・キャッシュ。"""
    now = time.time()
    if now - _media_ctx.last_enriched_at < _CO_VIEW_ENRICH_COOLDOWN:
        return _media_ctx.enriched_info

    results: list = []
    content_type = _media_ctx.inferred_type
    keywords = _media_ctx.keywords

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            is_baseball = (content_type == "baseball"
                           or any("ドジャース" in k or "dodger" in k.lower() or "野球" in k for k in keywords))
            is_golf = (content_type == "golf"
                       or any("ゴルフ" in k or "マスターズ" in k or "golf" in k.lower() for k in keywords))

            if is_baseball:
                rss_url = "https://news.google.com/rss/search?q=ドジャース+試合&hl=ja&gl=JP&ceid=JP:ja"
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall('.//item')[:3]:
                        title = item.findtext('title', '')
                        if title:
                            results.append(f"ニュース: {title}")
            elif is_golf:
                rss_url = "https://news.google.com/rss/search?q=マスターズ+ゴルフ&hl=ja&gl=JP&ceid=JP:ja"
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall('.//item')[:3]:
                        title = item.findtext('title', '')
                        if title:
                            results.append(f"ニュース: {title}")

            # Pattern O: matched_title が特定できている場合は優先してそのタイトルで検索
            if _media_ctx.matched_title:
                wiki = await _tool_wikipedia_summary(_media_ctx.matched_title)
                if not wiki:
                    # Patch V3: "〜ラジオ" 等の略称でWikipedia 0 results の場合、suffix除去で再検索
                    fallback_title = re.sub(r'ラジオ$|Radio$|radio$', '', _media_ctx.matched_title).strip()
                    if fallback_title and fallback_title != _media_ctx.matched_title:
                        wiki = await _tool_wikipedia_summary(fallback_title)
                        if wiki:
                            logger.info(f"[co_view/enrich] Patch V3: wiki fallback '{fallback_title}' hit")
                if wiki:
                    results.append(wiki)
                # Patch Y1: query rotation — 毎回同じニュースにならないよう検索suffixをローテーション
                _ENRICH_QUERY_SUFFIXES = [" 最新情報", " 声優 キャスト", " イベント グッズ", " シーズン 続編"]
                suffix = _ENRICH_QUERY_SUFFIXES[_media_ctx.enrich_query_idx % len(_ENRICH_QUERY_SUFFIXES)]
                _media_ctx.enrich_query_idx += 1
                logger.debug(f"[co_view/enrich] query suffix={suffix!r} (idx={_media_ctx.enrich_query_idx-1})")
                query = urllib.parse.quote(_media_ctx.matched_title + suffix)
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    added = 0
                    for item in root.findall('.//item')[:4]:  # Patch Y1補: 候補を多めに取り既見をスキップ
                        t = item.findtext('title', '')
                        if t and t not in _media_ctx.enrich_seen_titles:
                            results.append(f"ニュース: {t}")
                            _media_ctx.enrich_seen_titles.add(t)
                            added += 1
                            if added >= 2:
                                break
                    if not results:  # 全件既見の場合は seen_titles をリセットして再取得
                        _media_ctx.enrich_seen_titles.clear()
                        logger.debug("[co_view/enrich] Patch Y1補: seen_titles exhausted, reset")
            elif (_media_ctx.inferred_topic and content_type not in ("music", "unknown")
                  and not (content_type == "youtube_talk" and not _media_ctx.matched_title)):
                # Patch T2: youtube_talk + matched_title="" はinferred_topicでのWikipedia検索もスキップ
                # （Patch S1と対称）会議系トピックで無関係な記事が混入するのを防ぐ
                wiki = await _tool_wikipedia_summary(_media_ctx.inferred_topic)
                if wiki:
                    results.append(wiki)

            # Patch S1: youtube_talk + matched_title="" の場合はkeywordsフォールバック検索をスキップ
            # 会議系コンテンツのkeywordsで無関係ニュース（映画・インフラ等）が混入するのを防ぐ
            # Patch U2: ただし固有名詞keywordsがある場合は検索を許可（抽象語は除外）
            # Patch AR2: enrich keyword検索はカタカナ主体語のみを使用（「先輩」「朝日」等の一般語除外）
            _ABSTRACT_SUFFIXES = ("について", "における", "に関する", "の標準化", "の改善", "の考察", "の戦略", "の課題")
            _KATAKANA_COMMON_KW = frozenset(["アニメ", "スケジュール", "ゲーム", "ドラマ", "ニュース",
                                             "イベント", "サービス", "システム", "コンテンツ", "チャンネル",
                                             "ビジネス", "マーケット", "プロジェクト", "インターネット"])
            _KATAKANA_RE_STRICT = re.compile(r'[ァ-ヶー]')
            # AR2: カタカナを含む語のみを enrich 検索キーワードとして採用
            _enrich_kws = [
                k for k in keywords[:4]
                if _KATAKANA_RE_STRICT.search(k)
                and k not in _KATAKANA_COMMON_KW
                and len(k) >= 2
                and not any(k.endswith(s) for s in _ABSTRACT_SUFFIXES)
            ] if keywords else []
            _has_specific_kw = bool(_enrich_kws)
            _yt_no_specific = content_type == "youtube_talk" and not _media_ctx.matched_title and not _has_specific_kw
            if not results and _enrich_kws and not _yt_no_specific:
                _ar2_kws = _enrich_kws[:2]
                logger.info(f"[co_view/enrich] Patch AR2: keyword filter {keywords[:4]} → {_ar2_kws}")
                query = urllib.parse.quote("+".join(_ar2_kws))
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    # Patch Z1: PRプレスリリースサイト除外
                    _ENRICH_EXCLUDE_KEYWORDS = ("PR TIMES", "prtimes", "プレスリリース", "dreamnews", "atpress")
                    for item in root.findall('.//item')[:4]:
                        title = item.findtext('title', '')
                        link = item.findtext('link', '')
                        if title and not any(ex in title or ex in link for ex in _ENRICH_EXCLUDE_KEYWORDS):
                            results.append(f"関連: {title}")
                            if len([r for r in results if r.startswith("関連:")]) >= 2:
                                break

            # Patch Z2: matched_title未特定時、topicから固有名詞（カタカナ・英字）を抽出してWikipedia検索
            # ガーフ/MARZ等のマイナーVTuber・ゲームキャラを特定するフォールバック
            if not results and not _media_ctx.matched_title and _media_ctx.inferred_topic:
                _KATAKANA_RE = re.compile(r'[ァ-ヶー]{2,}')
                _ASCII_WORD_RE = re.compile(r'[A-Za-z]{2,}')
                # Patch AB1: 漢字固有名詞（人名・地名・作品名等）もZ2対象に追加
                # 一般語（話題・雑談・場面・状況等）は除外リストで除外
                _KANJI_RE = re.compile(r'[一-龥]{2,4}')
                _KANJI_COMMON = frozenset([
                    '話題', '雑談', '場面', '状況', '内容', '様子', '以下', '以上',
                    '最近', '関連', '固有', '会話', '言及', '紹介', '友人', '複数',
                    '複雑', '一般', '中心', '情報', '議論', '映画', '動画', '番組',
                    '放送', '特定', '視聴', '配信', '具体', '概要', '全体', '前半',
                    '後半', '日本', '世界', '現在', '過去', '未来', '登場', '人物',
                    '関係', '物語', '展開', '感想', '楽しい', '面白', '雰囲気',
                ])
                kanji_nouns = [
                    w for w in _KANJI_RE.findall(_media_ctx.inferred_topic)
                    if w not in _KANJI_COMMON
                ]
                proper_nouns = (
                    _KATAKANA_RE.findall(_media_ctx.inferred_topic) +
                    _ASCII_WORD_RE.findall(_media_ctx.inferred_topic) +
                    kanji_nouns
                )
                for noun in proper_nouns[:5]:
                    wiki = await _tool_wikipedia_summary(noun)
                    if wiki:
                        results.append(wiki)
                        logger.info(f"[co_view/enrich] Patch Z2/AB1: proper noun fallback '{noun}' → wiki hit")
                        break
    except Exception as e:
        logger.warning(f"[co_view/enrich] failed: {e}")

    enriched = "\n".join(results)
    _media_ctx.enriched_info = enriched
    _media_ctx.last_enriched_at = now
    # Patch V2: enrich取得内容をログに出力（次回分析で根拠追跡可能にする）
    logger.info(f"[co_view/enrich] {len(results)} results: {results}")
    return enriched


async def _handle_co_view(ws, trigger_text: str, method: str, keyword: str):
    """co_view モード: メディア音声を蓄積→コンテンツ推測→外部補完→コメント生成。"""
    if not _ambient_listener:
        return
    now = time.time()

    # 原文ベースdedup
    raw_key = trigger_text[:60]
    last_seen = _STT_RAW_SEEN.get(raw_key, 0.0)
    if now - last_seen < _STT_RAW_DEDUP_WINDOW:
        logger.debug(f"[co_view] raw dedup skip ({now - last_seen:.1f}s): '{raw_key[:30]}'")
        return
    _STT_RAW_SEEN[raw_key] = now
    if len(_STT_RAW_SEEN) > 100:
        cutoff = now - _STT_RAW_DEDUP_WINDOW * 2
        for k in [k for k, v in _STT_RAW_SEEN.items() if v < cutoff]:
            del _STT_RAW_SEEN[k]

    async with _co_view_lock:

        corrected = await _correct_media_transcript(trigger_text)
        if not corrected:
            return
        _media_ctx.add_snippet(corrected)
        await _broadcast_debug(f"[co_view] buf={len(_media_ctx.media_buffer)} '{corrected[:40]}'")

        if len(_media_ctx.media_buffer) >= 2:
            if now - _media_ctx.media_buffer[-2]["ts"] > 300:
                logger.info("[co_view] 5min gap → reset context")
                _media_ctx.reset()
                _media_ctx.add_snippet(corrected)

        if now - _media_ctx.co_view_last_at < _CO_VIEW_COMMENT_COOLDOWN:
            remaining = int(_CO_VIEW_COMMENT_COOLDOWN - (now - _media_ctx.co_view_last_at))
            await _broadcast_debug(f"[co_view] cooldown {remaining}s")
            return

        # Patch AI1: enriched/filtered_enriched をif block前にデフォルト初期化
        # 背景: AG1でif block外からenriched参照→NameError→snippets<5の全パスでコメント停止(03:26〜)
        enriched = _media_ctx.enriched_info
        filtered_enriched = enriched

        # Patch AP1: conf=0.00（初期状態 or リセット直後）かつ2スニペット以上の場合は早期infer
        # 背景: snippets_since_infer < 5 の累積期間中、confidence=0.00のままco_viewが呼ばれると
        #       全件low conf skipになる問題（特にリセット直後や視聴開始時）を解消する
        _infer_early = _media_ctx.confidence == 0.0 and _media_ctx.snippets_since_infer >= 2
        if _infer_early:
            logger.info(f"[co_view/infer] Patch AP1: early infer (conf=0.0, snips={_media_ctx.snippets_since_infer})")
        if _media_ctx.snippets_since_infer >= _CO_VIEW_INFERENCE_MIN_SNIP or _infer_early:
            inferred = await _infer_media_content()
            # Patch V1: content_type変化時にenrichキャッシュをリセット（前セッションの情報混入防止）
            # Patch V2: conf < 0.7 の低信頼度判定ではtype変更をスキップ（誤判定によるenrich cache resetを防ぐ）
            new_content_type = inferred.get("content_type", "unknown")
            new_conf = float(inferred.get("confidence") or 0.0)  # Patch AL1: None安全処理
            _v2_type_skipped = False  # Patch AO1: V2スキップフラグ（confidence保持判定用）
            if new_content_type != _media_ctx.inferred_type:
                # Patch AV1: meeting型へのV2 conf閾値を0.7→0.6に緩和
                # 背景: meeting判定がconf=0.60で安定しているがV2の0.7閾値でブロックされていた
                #       AD1のmeeting除外ルール（YouTube解説動画・ITニュース除外）が既に入っているため安全
                _av1_meeting_ok = (new_content_type == "meeting" and new_conf >= 0.6)
                # Patch BH1: _bg1_from_meetingをV2ゲートの外で評価（BG1バグ修正）
                # BG1バグ: _bg1_from_meetingがif new_conf>=0.7の内側にあったため
                #          conf<0.7のmeeting→non-meeting遷移でV2にブロックされBG1が発動しなかった
                _bg1_from_meeting_precheck = (new_content_type != "meeting" and
                                              _media_ctx.inferred_type == "meeting")
                if new_conf >= 0.7 or _av1_meeting_ok or _bg1_from_meeting_precheck:
                    # Patch AF1: 同一matched_titleでのcontent_type変化（例: anime↔youtube_talk）は
                    # enrich cacheをリセットしない（同じ作品の情報が引き継がれる）
                    # 背景: 同一作品視聴中にtypeが行き来するたびにenrich cacheがリセットされ無駄なAPI呼び出しが発生していた
                    new_matched_title = inferred.get("matched_title", "")
                    # Patch AJ1: strip()でwhitespace差異によるsame_title誤判定を防ぐ
                    same_title = bool(new_matched_title and new_matched_title.strip() == _media_ctx.matched_title.strip())
                    # Patch AK1: content_type変化のhysteresis
                    # 同一matched_titleの場合（同一作品のanime↔youtube_talk）は即時確定（AF1と協調）
                    # 異なるタイトルへの変化は連続2回確認で確定（1回の変化ではpendingとして保留）
                    if same_title:
                        # 同一作品内でのtype揺れ → 即時確定（enrich cacheはリセットしない）
                        logger.info(f"[co_view/infer] Patch AF1: same matched_title '{new_matched_title}', enrich cache kept ({_media_ctx.inferred_type}→{new_content_type})")
                        _media_ctx._pending_type = ""
                        _media_ctx._pending_type_count = 0
                    else:
                        # 異なるコンテンツへの変化 → hysteresisで確認
                        if _media_ctx._pending_type == new_content_type:
                            _media_ctx._pending_type_count += 1
                        else:
                            _media_ctx._pending_type = new_content_type
                            _media_ctx._pending_type_count = 1
                        # Patch AN2: conf >= 0.9の場合はhysteresisを1回に緩和（高確信度なら即時type確定）
                        # Patch AQ1: unknown→X の遷移はhysteresis不要（unknownは安定状態でないため即時確定）
                        # Patch BG1: meeting→non-meeting 遷移は1段確認で即時確定（会議終了→視聴切替の遅延解消）
                        #            BD1/AU1 post-filterが誤コメントを安全網として担保
                        _aq1_from_unknown = (_media_ctx.inferred_type == "unknown")
                        _bg1_from_meeting = (_media_ctx.inferred_type == "meeting" and new_content_type != "meeting")
                        if _media_ctx._pending_type_count >= 2 or new_conf >= 0.9 or _aq1_from_unknown or _bg1_from_meeting:
                            # 2回連続確認 OR 高確信度(conf>=0.9) OR meeting終了 → 確定
                            _media_ctx.enriched_info = ""
                            _media_ctx.last_enriched_at = 0.0
                            # Patch AC1: content_type変化時にmatched_title fallbackもリセット
                            _media_ctx.last_valid_matched_title = ""
                            _media_ctx.last_valid_matched_at = 0.0
                            _media_ctx.last_valid_inferred_type = ""  # Patch AL2
                            confirm_reason = ("2/2" if _media_ctx._pending_type_count >= 2
                                              else f"AQ1:from_unknown" if _aq1_from_unknown
                                              else f"BG1:from_meeting" if _bg1_from_meeting
                                              else f"AN2:conf={new_conf:.2f}>=0.9")
                            logger.info(f"[co_view/infer] Patch AK1/AN2: content_type confirmed {_media_ctx.inferred_type}→{new_content_type} ({confirm_reason}), enrich cache reset")
                            _media_ctx._pending_type = ""
                            _media_ctx._pending_type_count = 0
                        else:
                            logger.info(f"[co_view/infer] Patch AK1: content_type change pending {_media_ctx.inferred_type}→{new_content_type} (1/2), waiting confirmation")
                            new_content_type = _media_ctx.inferred_type  # 確定まではtype変更しない
                else:
                    logger.info(f"[co_view/infer] Patch V2: low-conf type change skipped ({_media_ctx.inferred_type}→{new_content_type} conf={new_conf:.2f})")
                    new_content_type = _media_ctx.inferred_type  # conf < 0.7 はtype変更せず
                    _v2_type_skipped = True
            else:
                # Patch AK1: type変化なし → pendingをリセット（連続性が途切れた）
                if _media_ctx._pending_type and _media_ctx._pending_type != new_content_type:
                    logger.debug(f"[co_view/infer] Patch AK1: pending type '{_media_ctx._pending_type}' cancelled (current stayed {new_content_type})")
                _media_ctx._pending_type = ""
                _media_ctx._pending_type_count = 0
            _media_ctx.inferred_type  = new_content_type
            _media_ctx.inferred_topic = inferred.get("topic", "")
            _media_ctx.matched_title  = inferred.get("matched_title", "")
            # Patch AO1: V2でtype変化をスキップした場合はconfidenceも前回値を維持する
            # 背景: infer失敗時にconf=0.00で上書きされるとAN3 bypass(conf>=0.65)が無効化され
            #       前回type(youtube_talk)を維持しているにもかかわらず5連続skipが発生していた
            if _v2_type_skipped:
                logger.info(f"[co_view/infer] Patch AO1: V2 skip → confidence preserved ({_media_ctx.confidence:.2f}, not overwritten with {new_conf:.2f})")
            else:
                _media_ctx.confidence = float(inferred.get("confidence") or 0.0)  # Patch AM1: AL1と同じNone安全処理（confidence: null対応）
            _media_ctx.keywords       = inferred.get("keywords", [])
            _media_ctx.last_inferred_at = now
            _media_ctx.snippets_since_infer = 0
            # Patch M1: matched_title が特定できた場合は last_valid を更新
            if _media_ctx.matched_title:
                # Patch Y1: matched_title が変わったら enrich_query_idx と seen_titles をリセット
                if _media_ctx.matched_title != _media_ctx.last_valid_matched_title:
                    _media_ctx.enrich_query_idx = 0
                    _media_ctx.enrich_seen_titles = set()  # Patch Y1補: 作品変更時のみリセット
                _media_ctx.last_valid_matched_title = _media_ctx.matched_title
                _media_ctx.last_valid_matched_at = now
                _media_ctx.last_valid_inferred_type = _media_ctx.inferred_type  # Patch AL2: type記録
                logger.info(f"[co_view/infer] matched={_media_ctx.matched_title}")
            elif (_media_ctx.last_valid_matched_title and (now - _media_ctx.last_valid_matched_at < 360)
                  and _media_ctx.inferred_type != "meeting"
                  # Patch AL2: youtube_talk→youtube_talkのfallback抑制
                  # 直前youtube_talkで特定したtitleを別のyoutube_talkには引き継がない
                  # （例: Re:ゼロあふれこ→無関係なお悩み番組でRe:ゼロコメント防止）
                  # anime/vtuber→youtube_talkのアフタートーク引き継ぎは維持
                  and not (_media_ctx.inferred_type == "youtube_talk" and _media_ctx.last_valid_inferred_type == "youtube_talk")):
                # Patch N1: matched='' でも直前6分以内の有効なタイトルを引き継ぐ（5分→6分に延長）
                # Patch Z3: 6分→15分に拡大（アフタートーク中のyoutube_talk一時判定で16分ロスが発生したため）
                # Patch AE1: 15分(900s)→6分(360s)に短縮（別コンテンツへの誤引き継ぎを防ぐため）
                # Patch X1: meeting中はfallback無効（前の作品タイトルで無関係なenrichが走るのを防ぐ）
                _media_ctx.matched_title = _media_ctx.last_valid_matched_title
                logger.info(f"[co_view/infer] matched fallback→{_media_ctx.matched_title} (last_valid {int(now - _media_ctx.last_valid_matched_at)}s ago)")
            await _broadcast_debug(
                f"[co_view] inferred: {_media_ctx.inferred_type} "
                f"'{_media_ctx.inferred_topic}' conf={_media_ctx.confidence:.2f}"
            )

        # Patch M3: conf < 0.75 かつ matched='' → コメントSKIP（低信頼度×作品不明では不用意に喋らない）
        # Patch AN3: youtube_talk + conf>=0.65 の場合はenrich試行を許可（M3をバイパス）
        # Patch AV2: meeting型はgcal_titleで文脈補完できるためmatched_title不要。conf>=0.6でバイパス
        # AA1（youtube_talk + enrich=0 → hard SKIP）が第2防衛ラインとして機能
        _an3_bypass = (_media_ctx.inferred_type == "youtube_talk" and _media_ctx.confidence >= 0.65)
        _av2_meeting_bypass = (_media_ctx.inferred_type == "meeting" and _media_ctx.confidence >= 0.6)
        if _media_ctx.confidence < 0.75 and not _media_ctx.matched_title and not _an3_bypass and not _av2_meeting_bypass:
            # Patch AI2: low conf skipをログファイルに記録（_broadcast_debugのみでは不可視だったため）
            logger.info(f"[co_view] low conf skip (conf={_media_ctx.confidence:.2f}, no matched_title)")
            await _broadcast_debug(f"[co_view] low conf skip (conf={_media_ctx.confidence:.2f}, no matched_title)")
            return
        if _an3_bypass and _media_ctx.confidence < 0.75 and not _media_ctx.matched_title:
            logger.info(f"[co_view] AN3: youtube_talk conf={_media_ctx.confidence:.2f}>=0.65, proceeding to enrich")

        if _media_ctx.confidence < 0.5:
            if (len(_media_ctx.media_buffer) >= _CO_VIEW_ASK_USER_MIN_SNIP
                    and now - _media_ctx.ask_user_last_at > _CO_VIEW_ASK_USER_COOLDOWN):
                _media_ctx.ask_user_last_at = now
                _media_ctx.co_view_last_at  = now
                mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
                mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
                mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
                await _ambient_broadcast_reply("ちなみに何見てるの？", "co_view_ask", method, keyword, mei_speaker, mei_speed)
                logger.info("[co_view] asked user: 何見てるの？")
            else:
                await _broadcast_debug(f"[co_view] low conf={_media_ctx.confidence:.2f}, accumulating")
            return

        # Patch Z2: meeting中はGoogle News軽量enrich（gcal_title → keywords[:2] → topic[:20] の優先順で検索）
        # Patch Y1: 0件時はfallback連鎖（内部業務用語ではヒットしないケースに対応）
        if _media_ctx.inferred_type == "meeting":
            gcal_title = await _fetch_current_gcal_meeting()
            if _media_ctx.confidence >= 0.6:
                _schedule_meeting_digest_idle_task()
            enriched = ""
            _meeting_kws = _media_ctx.keywords[:2]
            # Patch AU2: 汎用ビジネス語を含むキーワードをenrich検索から除外
            # 背景: gcal_title空時に「アジェンダ」「スケジュール」等の汎用語でNewsRSS検索→
            #       一般PMニュース大量取得→LLMが「PMが欠かせない」等の汎用アドバイスを生成する根本原因
            _meeting_kws_specific = [
                k for k in _meeting_kws
                if not any(g in k for g in _MEETING_GENERIC_TERMS)
            ]
            if len(_meeting_kws_specific) < len(_meeting_kws):
                logger.info(
                    f"[co_view/meeting_enrich] Patch AU2: filtered generic kws "
                    f"{_meeting_kws} → {_meeting_kws_specific}"
                )
            _meeting_search_candidates = [c for c in [
                _gcal_meeting_cache.get("title", ""),
                " ".join(_meeting_kws_specific) if _meeting_kws_specific else "",
                _meeting_kws_specific[0] if _meeting_kws_specific else "",
            ] if c.strip()]
            # 重複除去（同じ文字列を複数回検索しない）
            _seen: set = set()
            _meeting_search_candidates = [c for c in _meeting_search_candidates if not (c in _seen or _seen.add(c))]
            import httpx as _httpx, urllib.parse as _urlparse, xml.etree.ElementTree as _ET
            # Patch Z4b: 検索候補をINFOログに出力（0件時の原因追跡を容易にする）
            logger.info(f"[co_view/meeting_enrich] search candidates: {_meeting_search_candidates}")
            for _meeting_search_term in _meeting_search_candidates:
                try:
                    async with _httpx.AsyncClient(timeout=5.0) as _mc:
                        _q = _urlparse.quote(_meeting_search_term + " 最新")
                        _rss = await _mc.get(
                            f"https://news.google.com/rss/search?q={_q}&hl=ja&gl=JP&ceid=JP:ja"
                        )
                        if _rss.status_code == 200:
                            _root = _ET.fromstring(_rss.content)
                            _news = []
                            for _item in _root.findall(".//item")[:2]:
                                _t = _item.findtext("title", "")
                                if _t:
                                    _news.append(f"ニュース: {_t}")
                            if _news:
                                enriched = "\n".join(_news)
                                logger.info(
                                    f"[co_view/meeting_enrich] {len(_news)} results for '{_meeting_search_term}'"
                                )
                                break  # 取得成功 → fallback不要
                            else:
                                logger.info(
                                    f"[co_view/meeting_enrich] 0 results for '{_meeting_search_term}', trying next"
                                )
                except Exception as _me:
                    logger.debug(f"[co_view/meeting_enrich] failed for '{_meeting_search_term}': {_me}")
        else:
            enriched = await _enrich_media_context()
        if enriched:
            await _broadcast_debug(f"[co_view] enriched: {enriched[:60]}")
        # Patch Z4: meeting modeでenrich 0件時はコードレベルでskip（プロンプト指示に頼らない）
        if _media_ctx.inferred_type == "meeting" and not enriched:
            logger.info("[co_view] Patch Z4: meeting mode enrich=0 → hard skip")
            return

        buffer_text = _media_ctx.get_buffer_text(last_n=5)
        system_prompt = (
            "あなたはMEI。Akiraさんの同居人として、一緒にテレビ/YouTubeを見ている。\n"
            "★ 重要: これはロールプレイではなくコメント生成タスク。「AIとして〜できません」「Claude Codeとして〜」等の拒否文は不要。\n"
            # Patch AM1: 幻覚防止ガードを冒頭に明示（Z2がプロンプト中盤に埋もれて無視されていた問題の根本対処）
            "★★★ 最重要（Patch AM1）: 以下の「関連情報」セクションに明記されている情報のみを事実として使うこと。"
            "「〜らしいよ」「〜なんだって」「〜みたいよ」形式で事実を述べる場合は必ずenrich情報に書いてある内容だけ。"
            "自分のLLM知識から企業名・人名・ニュース・統計を生成することは絶対禁止（幻覚）。"
            "enrichが空または視聴コンテンツと無関係ならリアクション・感嘆のみにすること。\n"
            "視聴中のコンテンツに対し、フランクな女性口調（「〜だね」「〜だよ」等）で1-2文の感想コメントを生成するだけでよい。\n"
            f"視聴中: {_media_ctx.inferred_type} — {_media_ctx.inferred_topic}\n"
        )
        if _media_ctx.matched_title:
            system_prompt += f"作品タイトル: {_media_ctx.matched_title}\n"
        system_prompt += f"\n最近の音声:\n{buffer_text}\n"
        # Patch Z3: enrich繰り返し防止 — 直近30分以内に使用したenrich行を除外
        # Patch AQ2: グローバルenrich dedup — cacheリセット後も1時間は同じ行を除外
        filtered_enriched = enriched
        if enriched:
            enrich_lines = enriched.splitlines()
            _ENRICH_REUSE_COOLDOWN = 600  # Patch BF1: 1800→600秒（Z3クールダウン短縮、AQ2が1時間グローバルdedupするため30分は冗長）
            now_t = time.time()
            # AQ2: 古いglobal dedup エントリをクリーン（2時間以上前）
            _expired = [k for k, v in _GLOBAL_ENRICH_USED.items() if now_t - v > 7200]
            for k in _expired:
                del _GLOBAL_ENRICH_USED[k]
            if (_media_ctx.last_enrich_used_lines
                    and now_t - _media_ctx.last_enrich_used_at < _ENRICH_REUSE_COOLDOWN):
                used_set = set(_media_ctx.last_enrich_used_lines)
                fresh_lines = [l for l in enrich_lines if l not in used_set]
                if len(fresh_lines) < len(enrich_lines):
                    # Patch AJ2: Z3フィルタリングをDEBUG→INFOに昇格（効果可視化）
                    logger.info(f"[co_view/enrich] Patch Z3: filtered {len(enrich_lines)-len(fresh_lines)} stale lines, {len(fresh_lines)} remain")
                filtered_enriched = "\n".join(fresh_lines) if fresh_lines else ""
                if not filtered_enriched and enriched:
                    # Patch AJ2: filtered_enrichedが空になった場合もINFOログ（enrich全除外の追跡）
                    logger.info(f"[co_view/enrich] Patch Z3: all lines filtered out (cooldown {int(now_t - _media_ctx.last_enrich_used_at)}s < {_ENRICH_REUSE_COOLDOWN}s)")
            # Patch AQ2: グローバルdedup (cacheリセット後も適用)
            if filtered_enriched:
                pre_aq2 = filtered_enriched.splitlines()
                aq2_fresh = [l for l in pre_aq2 if l not in _GLOBAL_ENRICH_USED or now_t - _GLOBAL_ENRICH_USED[l] >= _GLOBAL_ENRICH_REUSE_SEC]
                if len(aq2_fresh) < len(pre_aq2):
                    logger.info(f"[co_view/enrich] Patch AQ2: global dedup filtered {len(pre_aq2)-len(aq2_fresh)} lines, {len(aq2_fresh)} remain")
                filtered_enriched = "\n".join(aq2_fresh) if aq2_fresh else ""
        if filtered_enriched:
            _topic_hint = _media_ctx.matched_title or _media_ctx.inferred_topic
            system_prompt += (
                f"\n関連情報(現在視聴中の「{_topic_hint}」に"
                "直接関連する情報のみ自然にコメントに盛り込む。「〇〇って最近△△らしいよ」「へー、〇〇なんだね」等の口語表現で盛り込む。"
                # Patch AX1: 「さっきのニュースで」等の情報源明示フレーズは距離感を壊すため禁止（AW1 post-filterと整合）
                "「さっきのニュースで」「〇〇によると」「〇〇から」等の情報ソース明示フレーズは使わない。"
                # Patch S2: コンテキスト不一致時の禁止を強化
                # Patch U1: 政治ニュース系ドメインを禁止リストに追加
                "★★ 視聴コンテンツ（ビジネス会議・企業戦略等）と明らかに無関係な情報（映画・スポーツ・アニメ・政治ニュース・国政・選挙・記者会見・議員・幹事長等）は絶対に使わない。"
                "無関係情報を使うくらいなら視聴内容だけにリアクションすること。"
                # Patch AY1: enrich整合性チェック強化 — 単一汎用語マッチによる無関係ニュース使用防止
                f"★★ Patch AY1: 以下の関連情報のタイトルに視聴コンテンツ（「{_topic_hint}」）に登場する具体的な固有名詞（人物名・チャンネル名・作品名）が含まれる場合のみ使うこと。"
                "「イラスト」「料理」「音楽」「映像」のような一般的な語のみで一致した場合（同じ語が使われているだけで内容が全く別のトピック）は絶対に使わない。"
                "視聴中のコンテンツと関係する固有名詞が1つも一致しなければSKIPすること):\n"
                f"{filtered_enriched}\n"
            )
        if _media_ctx.recent_co_view_comments:
            recent_str = "\n".join(f"- {c}" for c in _media_ctx.recent_co_view_comments[-3:])
            system_prompt += f"\n直近のコメント履歴（同じ内容・同じenrich事実を繰り返さない）:\n{recent_str}\n"
            # Patch Z4: 使用済みenrich事実を具体的禁止リストとして明示（filtered_enriched空でも適用）
            _z4_now = time.time()
            if (_media_ctx.last_enrich_used_lines
                    and _z4_now - _media_ctx.last_enrich_used_at < 1800):
                _z4_forbidden = []
                for _z4_line in _media_ctx.last_enrich_used_lines:
                    _z4_snippet = re.sub(r'^(ニュース|関連|Wikipedia): ', '', _z4_line).strip()
                    if _z4_snippet:
                        _z4_forbidden.append(_z4_snippet[:50])
                if _z4_forbidden:
                    system_prompt += "🚫 以下は直近コメントで使用済みのenrich事実（同じ内容・同じキーワードを含む言及は完全禁止）:\n"
                    for _z4_s in _z4_forbidden:
                        system_prompt += f"  - {_z4_s}\n"
            elif filtered_enriched:
                system_prompt += "★ 上記コメントで既に言及したenrich事実は絶対に繰り返さない。別の視点・別の反応を選ぶこと。\n"
        # Patch W1: 会議モード — 同居人コメントではなく会議サポート情報を提供
        if _media_ctx.inferred_type == "meeting":
            topic_hint = _media_ctx.inferred_topic[:50] if _media_ctx.inferred_topic else "ビジネス会議"
            # KC → 京セラ など既知略称を展開
            _KC_ALIASES = {"KC": "京セラ", "CSC": "アバント（自社部署）"}
            if gcal_title:
                for alias, full in _KC_ALIASES.items():
                    gcal_title = gcal_title.replace(alias, full)
                meeting_title_hint = f"Googleカレンダーの会議タイトル: 「{gcal_title}」\n"
                logger.info(f"[co_view/meeting] gcal_title='{gcal_title}'")
            else:
                meeting_title_hint = ""
            # Patch AM2: filtered_enriched（Z3済み）を使い、「必ず引用」→「関連する場合のみ引用」に緩和
            # 背景: raw enriched + 「必ず引用」により会議に無関係なニュース（CAMPFIRE/Netflix等）を強制コメントしていた
            meeting_enrich_note = (
                f"\n以下のニュースが会議内容（{topic_hint[:30]}）と直接関連する場合のみ引用してよい（「〇〇らしいよ」「〇〇が発表されてたよ」等の自然な形式）。\n"
                "無関係なニュース（会社名・製品名・業界が一致しない）は無視してSKIPすること:\n"
                f"{filtered_enriched}\n"
                if filtered_enriched else ""
            )
            if _media_ctx.recent_co_view_comments:
                recent_str = "\n".join(f"- {c}" for c in _media_ctx.recent_co_view_comments[-3:])
                system_prompt += f"\n直近の提供情報（繰り返し禁止）:\n{recent_str}\n"
            system_prompt += (
                f"\n会議中: {topic_hint}\n"
                f"{meeting_title_hint}"
                f"{meeting_enrich_note}"
                "\n会議サポート指示:\n"
                "- Akiraさんが今ビジネス会議に参加中。会議の流れを聞いて、有益な情報・視点・データを1文で提供する\n"
                "- Googleカレンダーの会議タイトルがあれば、そのクライアント・テーマを優先的に参照する\n"
                "- KC=京セラ（クライアント）、CSC=株式会社アバントの部署名（自社） として解釈する\n"
                "- 会議で出てきたキーワード（会社名・製品名・課題）に関連する業界情報・競合動向があれば提供\n"
                "- 上記「会議関連情報」にニュースが提供されている場合はそのヘッドラインを根拠として引用してよい\n"
                "- 例: 「〇〇社がDX強化を発表したらしいよ」「〇〇がさ、△△するらしいよ」\n"
                "- 禁止: 「さっきのニュースで」「〇〇によると」等の情報源明示フレーズ（AX1）\n"
                "- Patch M_GUARD: 数値・パーセンテージ・時期（「7-9月が活発」「時給8000円」等）を自分の知識だけで断言しない\n"
                "  → 外部情報（上記ニュース）に明示的に書いてある場合のみ引用してよい\n"
                "  → 確信が持てない数値・統計はSKIP\n"
                "- 関連情報がなければ「SKIP」。知識が確信持てない場合も「SKIP」\n"
                # Patch X1: enrich 0件時はLLM一般知識でのコメント生成を禁止
                "- ★★ 上記「会議関連情報」セクションにニュースが1件も提供されていない場合は、必ず「SKIP」と返すこと\n"
                "  → 自分のLLM知識だけで業界データ・市場動向・統計を生成しない\n"
                "- 架空の数値・文書・マニュアルを引用しない\n"
                # Patch W3: アドバイス口調を禁止、事実情報のみに限定
                # Patch Y2: アドバイス調の表現を明示禁止（「〜が重要だよね」等も含む）
                "- アドバイス・示唆・評価は全て禁止: 「〜しておいた方がいい」「〜が大切」「〜が重要なポイントだよね」「〜視点で見るといいかもね」「〜が重要だよね」「〜が大事だよね」等は全てNG\n"
                "- 会議内容への評価・感想コメント禁止（例: 「課題共有が重要だよね」「プロジェクト管理って大変だよね」等はNG）\n"
                "- 発言形式: 「〇〇らしいよ」「〇〇が発表されてたよ」など短い外部情報の中継のみ許可（「さっきのニュースで」「〇〇によると」等の情報源明示フレーズは使わない）\n"
                "- 外部情報がなければ必ず SKIP。会議内容だけで話を作らない\n"
                # Patch BD1: 会議内容反射コメント禁止 + スポーツ選手名・芸能人名引用禁止
                # 背景: 「試合データの話してるんだね〜。」のように会議内容を要約するだけのコメントが生成された
                #       また「ア・リーグクラブ」「試合データ」kwから野球選手名(山本由伸/大谷翔平)がenrichされLLMに渡されていた
                "- ★ Patch BD1: 会議参加者が話している内容をそのまま反射・要約・確認するコメントは禁止（例: 「試合データの話してるんだね〜」「フェーズの話してるね」「スケジュールの確認中だね」等はNG）\n"
                "  → 会議内容を外から観察してコメントする形は距離感を壊す。外部情報がなければSKIP\n"
                "- ★ Patch BD1: enrich情報にスポーツ選手名・芸能人名・歌手名が含まれていても引用禁止\n"
                "  → 会議業界・市場動向・競合企業・業界ニュースのみ引用可。「山本由伸が〜」「大谷翔平が〜」等はNG\n"
                # Patch B2: meeting modeにも音声品質メタコメント禁止を追加
                "- 音声品質・聞き取りにくさ・途切れ・ノイズについてコメントしない。そのような状況はSKIPする\n"
                "- 声に出す言葉だけ。1〜2文で完結させる\n"
                "- コメントする価値がなければ \"SKIP\" と返す\n"
            )
        else:
            if _media_ctx.inferred_type == "baseball":
                system_prompt += "\nAkiraさんはドジャースの大ファン。試合展開・選手プレー・スコアに自然にリアクション。\n"
            elif _media_ctx.inferred_type == "golf":
                system_prompt += "\nゴルフ観戦中。ショットや選手の動きに自然にリアクション。\n"
            elif _media_ctx.inferred_type in ("anime", "vtuber"):
                system_prompt += "\nアニメ/VTuber視聴中。作品・キャラクター・声優への共感リアクション。関連情報があればキャラ名や声優名を交えて自然に一言。\n"
            # Patch AA1: youtube_talk + enrich空 → hard SKIP（LLM知識のみでのSTT誤変換幻覚を根絶）
            # 旧Patch R2 + T1: LLM知識でコメントを促していたが、enrich 0件時に人名誤認識等の幻覚が頻発したため廃止
            # Patch AS2: filtered_enrichedを使う（Z3フィルタ後0件の場合もenrich=0と同様にSKIP）
            # 背景: enrich取得済み(enriched>0)でもZ3で全除外→filtered_enriched=""の場合、
            #       AA1が発動せず空のenrichでコメント生成（「三心のシーン...」等の根拠薄いコメント）が発生
            if _media_ctx.inferred_type == "youtube_talk" and not filtered_enriched:
                if _media_ctx.confidence >= 0.7:
                    # Patch BE1: enrich=0でもconf>=0.8なら感想専用モードで生成（幻覚防止: 情報提供禁止）
                    # Patch BH2: conf閾値を0.8→0.7に緩和（conf=0.7のyoutube_talkでもreaction-only有効化）
                    # 背景: Z3クールダウン(1800s)中にyoutube_talkを30分以上視聴すると
                    #       AA1が連発してコメントが完全停止する問題を緩和する
                    logger.info(f"[co_view] Patch BE1: youtube_talk + enrich=0 + conf={_media_ctx.confidence:.2f} → reaction-only mode")
                    system_prompt += (
                        "\n指示（Patch BE1 感想専用モード）:\n"
                        "- enrich情報なし。純粋な感想・リアクション・共感のみ1文。\n"
                        "- 例: 「へー！」「おもしろいね〜」「なるほどね。」「そういうことか！」「ほんとだ〜」「すごいね！」\n"
                        "- ★★ 事実・情報・知識を提供する系（「〜らしいよ」「〜だって」）は禁止\n"
                        "- ★★ 視聴内容を要約・確認する系（「〜の話なんだね」「〜について言ってるね」）も禁止\n"
                        "- 価値のある感想がなければ \"SKIP\" と返す\n"
                    )
                else:
                    logger.info("[co_view] Patch AA1: youtube_talk + enrich=0 → hard skip")
                    return
            # Patch M2: enrich結果がある時は具体的固有名詞を必ず1つ含める（汎用「〜らしい」のみ禁止）
            # Patch O4: 汎用配信サービス言及を明示禁止ワードとして追加
            enrich_note = (
                "- ★ 上記の関連情報を必ず盛り込む。具体的な固有名詞（作品名・声優名・イベント名・数字）を1つ入れること\n"
                "- ★ 「ファンクラブイベントとかも色々連動してるらしい」「配信で見返せるサービスも増えてるらしい」のような汎用コメントは禁止\n"
                "- ★ 「DアニメストアとかAbema」「Abemaでも」「配信サービスで」のような配信サービス名を挙げるコメントは禁止\n"
                "- ★ 「無料で見返せる」「配信で見返せる」「見返せるサービス」のような汎用配信情報も禁止\n"
                "- ★ 「〜らしいよ」スタイルで、enrich情報から具体的な事実名をそのまま使う\n"
                # Patch Z2: enrich情報に書かれていない職業・活動・経歴を付け加えるhallucination防止
                "- ★★ Patch Z2: enrich情報のテキストに明記されていない事実（職業・活動内容・経歴・作品・発言等）を付け加えない。「〇〇がアニメ関連の活動してる」「〇〇が最近〇〇してる」等、enrich情報に書かれていないことは捏造禁止\n"
                # Patch AF1: Z3フィルタ後にenrich情報が全部除外された場合(filtered_enriched="")は
                # enrich_noteも無効化する。enrichが存在してもZ3で全除外されていれば「必ず盛り込め」は矛盾する
                if filtered_enriched else ""
            )
            system_prompt += (
                "\n指示:\n"
                "- 一緒に見ている同居人として、自然な1文のコメント\n"
                "- 例: 「すごいね！」「えー！」「お、大谷打った！」「このYouTuber面白いね」「あー、そこか〜」\n"
                "- 短い感嘆 + 1フレーズで止める。毎回同じ冒頭フレーズ（「わー！」「すごいね！」等）を繰り返さない\n"
                "- 「〜らしいよ」「〜らしいよね」「〜だって」を2回連続で使わない。語尾バリエーション例: 「〜なんだって！」「〜みたいよ」「〜って聞いたよ」「〜なんだね」「〜じゃん！」「〜だったんだ」「〜なんだ！」\n"
                "- 外部からの解説・アドバイスは禁止。感想・リアクション・共感が基本\n"
                f"{enrich_note}"
                "- 分析構文禁止: 「〜ってことは〜」「〜からこそ〜」「〜ということで〜」はNG\n"
                "- 無関係な数字・年数・回数の解説はNG（関連情報の事実を雑談として使うのはOK）\n"
                "- 評価・アドバイス禁止: 「〜大事だよね」「〜必要」「〜すごい世界観」はNG\n"
                "- 疑問文・問いかけで終わらせない（「？」「だろ」「だろう」「かな」「なのかな」「のか」で終わる文は禁止）。一緒に見ているので内容は知っている前提\n"
                # Patch BE2: 視聴内容確認系コメント禁止（BE1のenrich=0モードと同じルールを標準パスにも適用）
                # 背景: enrich有りの標準パスでも「〜の話なんだね！」「〜するのね！」型の確認コメントが生成されていた
                #       BE1ではenrich=0のみ禁止していたが、標準パスには同ルールが未適用だった
                "- ★ Patch BE2: 視聴内容を要約・確認する系（「〜の話なんだね」「〜について言ってるね」「〜してるのね」「〜を連携させるのね」「〜の話なんですね」等）は禁止。内容は既に知っている前提。純粋な驚き・共感・感嘆のみ\n"
                "- 声に出す言葉だけ。ト書き・括弧付き説明は禁止\n"
                "- 音声品質・聞き取りにくさ・途切れ・ノイズについてコメントしない。そのような状況はSKIPする\n"
                "- コメントする価値がなければ \"SKIP\" と返す\n"
            )

        # Patch AG1: コメント生成試行ログ（どこで止まるか追跡できるように）
        logger.info(
            f"[co_view] generating: type={_media_ctx.inferred_type} "
            f"matched={_media_ctx.matched_title!r} "
            f"enrich={len(enriched)} filtered={len(filtered_enriched)}"
        )
        try:
            speaker = _ambient_listener.current_speaker if _ambient_listener else None
            co_reply = await asyncio.wait_for(
                _ask_slack_bot(
                    f"視聴中のコンテンツにコメントして: {_media_ctx.matched_title or _media_ctx.inferred_topic}\n音声: {buffer_text[:200]}",
                    speaker,
                    system_prompt=system_prompt,
                ),
                timeout=45,  # Patch O3: 30→45秒に延長
            )
            if not co_reply or co_reply.strip().upper() == "SKIP":
                # Patch AC2: SKIP時のINFOログ追加（broadcast_debugのみでは長時間気づけないため）
                logger.info(f"[co_view] LLM→SKIP (type={_media_ctx.inferred_type} matched={_media_ctx.matched_title!r} topic={_media_ctx.inferred_topic[:40]!r})")
                await _broadcast_debug("[co_view] → SKIP")
                # Patch AS1: meeting LLM→SKIP後にco_view_last_atを更新（5分クールダウン再利用で無駄LLMコール削減）
                # 背景: meeting typeで全件SKIPにもかかわらずco_view_last_atが更新されず毎1-2分LLMコールが発生していた
                if _media_ctx.inferred_type == "meeting":
                    _media_ctx.co_view_last_at = time.time()
                    logger.info("[co_view] Patch AS1: meeting SKIP → co_view_last_at updated (5min cooldown)")
                return

            # Patch L1: bot refusal パターン追加
            # Patch BC2: 「専門外」バリエーション追加（「会議のコメント生成は専門外なの」等がClaude Codeパターンなしで来た場合の防衛）
            _BOT_REFUSAL_PATTERNS = ("申し訳", "役割範囲外", "Claude Code", "できません", "お手伝いできません", "何かお手伝い", "お手伝いできること", "こんにちは！何か", "こんにちは！", "ご用件", "専門外")
            if any(p in co_reply for p in _BOT_REFUSAL_PATTERNS):
                logger.warning(f"[co_view] bot refusal detected, skip: '{co_reply[:50]}'")
                await _broadcast_debug("[co_view] → SKIP (bot refusal)")
                # Patch BC1: bot refusal後もco_view_last_atを更新（AS1と同様の5分クールダウン）
                # 背景: refusal後にco_view_last_atが更新されず即再試行→連続refusalが発生していた（14:52→14:53確認）
                if _media_ctx.inferred_type == "meeting":
                    _media_ctx.co_view_last_at = time.time()
                    logger.info("[co_view] Patch BC1: bot refusal → co_view_last_at updated (5min cooldown)")
                return

            co_reply = re.sub(r'[（(][^）)]*[）)]', '', co_reply).strip()
            if not co_reply or co_reply.strip().upper() == "SKIP":
                # Patch AH2: サイレントSKIPパスにINFOログ追加（括弧剥ぎ後にSKIPになったケースの追跡）
                logger.info(f"[co_view] bracket-stripped→SKIP (type={_media_ctx.inferred_type} matched={_media_ctx.matched_title!r})")
                return

            # Patch B3: 音声品質メタコメントが生成された場合は強制SKIP（プロンプト指示をLLMが無視した場合の安全網）
            if _CO_VIEW_AUDIO_QUALITY_RE.search(co_reply):
                logger.warning(f"[co_view] Patch B3: audio quality comment filtered: '{co_reply[:60]}'")
                return

            # Patch A2: 疑問文コメントが生成された場合は強制SKIP
            _stripped_reply = _CO_VIEW_QUESTION_STRIP.sub('', co_reply)
            if _stripped_reply.endswith('？') or _stripped_reply.endswith('?'):
                logger.warning(f"[co_view] Patch A2: question comment filtered: '{co_reply[:60]}'")
                return

            # Patch AU1: meeting typeのアドバイス調・汎用コメントを強制SKIP
            # 「欠かせない」「重要だよね」等のプロンプト禁止パターンがLLMに無視された場合の安全網
            if _media_ctx.inferred_type == "meeting" and _CO_VIEW_MEETING_ADVICE_RE.search(co_reply):
                logger.warning(f"[co_view] Patch AU1: meeting advice comment filtered: '{co_reply[:60]}'")
                _media_ctx.co_view_last_at = time.time()
                return

            # Patch BE2: youtube_talk内容反射型コメントフィルター
            # 「〜の話なんだね〜」「〜について話してるんだね」等の反射型をSKIP
            # 背景: BD1はmeeting専用だったが、youtube_talkでも同様の反射型が生成されていた
            if _media_ctx.inferred_type == "youtube_talk" and _CO_VIEW_REFLECTION_RE.search(co_reply):
                logger.info(f"[co_view] Patch BE2: reflection comment → skip: '{co_reply[:60]}'")
                return

            # Patch AZ1: 複数文コメントを1文に切り詰め（「！」「。」の後に続く内容は除去）
            # 背景: プロンプトの「自然な1文のコメント」指示がLLMに無視され、
            #       「〜なんだって！そんな長いつながりがあるから〜だろうね〜」のような
            #       2文構成（2文目が分析・推論調）コメントが生成される問題。
            # 設計原則2（距離感=分析禁止）・原則3（関係性=短く刺さるコメント優先）に基づく。
            _az1_m = __import__('re').search(r'[！。]', co_reply)
            if _az1_m and _az1_m.end() < len(co_reply) and co_reply[_az1_m.end():].strip():
                _az1_orig = co_reply
                co_reply = co_reply[:_az1_m.end()]
                logger.info(f"[co_view] Patch AZ1: truncated to 1 sentence: '{_az1_orig[:80]}' → '{co_reply}'")

            # Patch BA1: 統計・市場数値型コメントをSKIPする（設計原則2: 適切な距離感）
            # 「487億ドルまで成長」「30%増加」「2035年までに〇億」等は豆知識の披露になるためSKIP
            if _BA1_STATS_RE.search(co_reply):
                logger.info(f"[co_view] Patch BA1: stats-type comment skipped: '{co_reply[:60]}'")
                return

            logger.info(f"[co_view] comment: '{co_reply[:100]}'")
            # Patch H2: コメント履歴に追加（enrich繰り返し防止）
            _media_ctx.recent_co_view_comments.append(co_reply)
            if len(_media_ctx.recent_co_view_comments) > 5:
                _media_ctx.recent_co_view_comments = _media_ctx.recent_co_view_comments[-5:]
            # Patch Z3: 使用したenrich行を記録（30分間の繰り返し防止）
            # Patch AQ2: グローバルdedup dictにも記録（cacheリセット後も1時間は再使用しない）
            if filtered_enriched:
                _used_lines = filtered_enriched.splitlines()
                _media_ctx.last_enrich_used_lines = _used_lines
                _media_ctx.last_enrich_used_at = time.time()
                _now_g = time.time()
                for _gl in _used_lines:
                    if _gl:
                        _GLOBAL_ENRICH_USED[_gl] = _now_g
            mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
            mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
            mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
            await _ambient_broadcast_reply(co_reply, "co_view", method, keyword, mei_speaker, mei_speed)
            _media_ctx.co_view_last_at = now

        except asyncio.TimeoutError:
            logger.warning("[co_view] Claude timeout (45s)")
            await _broadcast_debug("[co_view] TIMEOUT")
        except Exception as e:
            logger.warning(f"[co_view] error: {e}")


async def _correct_stt_text(text: str, context_texts: list[str] | None = None) -> str:
    """Whisper STT の誤認識を補正。2段構成:
    1. 辞書ベース高速置換（レイテンシゼロ）
    2. LLM 補正（辞書で直らなかった未知の誤認識用）
    """
    # 短すぎる / 明らかに補正不要なテキストはスキップ
    if _STT_SYMBOL_ONLY.match(text.strip()):
        return ""
    if len(text) < 3 or _STT_SKIP_CORRECTION.match(text.strip()):
        return text

    # Stage 1: 辞書ベース置換
    dict_corrected = _apply_stt_dict(text)
    if dict_corrected != text:
        logger.info(f"[stt_dict] '{text}' → '{dict_corrected}'")
        text = dict_corrected

    # Stage 2: LLM 補正（辞書で解決しなかった誤認識を拾う）
    context_block = ""
    if context_texts:
        recent = context_texts[-3:]  # 直近3発話
        context_block = f"\n直近の会話:\n" + "\n".join(f"- {t}" for t in recent) + "\n"

    messages = [
        {"role": "system", "content": (
            "あなたは音声認識テキストの校正者です。\n"
            "音声認識の出力を正しい日本語に修正してください。\n"
            "意味が通じない単語は音の類似性と文脈から正しい単語に推測・置換してください。\n"
            "例: デンダー→カレンダー、コンピュー→コンピュータ、ジェンメイ→人名\n"
            "修正後のテキストだけを返してください。説明や補足は一切不要です。\n"
            "修正不要ならそのまま返してください。"
            f"{context_block}"
        )},
        {"role": "user", "content": text},
    ]
    try:
        corrected = await asyncio.wait_for(
            chat_with_llm(messages, "gemma4:e4b"),
            timeout=3.0,
        )
        corrected = corrected.strip().strip('"\'「」')
        if corrected and corrected != text:
            logger.info(f"[stt_correct] '{text}' → '{corrected}'")
            return corrected
        return text
    except Exception as e:
        logger.debug(f"[stt_correct] failed ({e}), using original text")
        return text


class TTSQualityError(Exception):
    """TTS 生成結果が品質基準を満たさない場合の例外"""
    def __init__(self, message: str, duration: float, size: int, text_len: int):
        self.duration = duration
        self.size = size
        self.text_len = text_len
        super().__init__(message)


_TTS_MAX_CHARS = 80

# Instruction/technical question patterns — Claude Code向けの発話を検出
_INSTRUCTION_PATTERN = re.compile(
    r'(してください|を確認して|を調べて|を教えて|を開いて|を消して|を送って'
    r'|作り替えて|変更して|修正して|立ち上げて|実行して|作成して|まとめて|揃えて'
    r'|のせて|追加して|削除して|更新して|書いて|書き換えて|コミットして'
    r'|設定して|フィルター.*して|表示して|非表示.*して|読み込んで'
    r'|[てで]ください$|ます$'
    r'|(?:設定|ファイル|コード|関数|変数|API|CSS|HTML|パス|ディレクトリ|データベース|サーバー|エンドポイント|ブランド|ロゴ|デザイン|カレンダー|アカウント|ダッシュボード).*(?:どこ|どう|どれ|何|なに|ですか|ますか)'
    r'|(?:どこに|どうやって|どうすれば).*(?:ますか|ですか|する|した))',
)

# Claude Code向け指示かどうかを判断するための開発文脈キーワード
_DEV_CONTEXT_PATTERN = re.compile(
    r'(?:claude\s*code|コード|ファイル|関数|変数|api|sdk|mcp|'
    r'サーバー?|データベース|db|エンドポイント|ログ|エラー|'
    r'スタックトレース|テスト|ビルド|コミット|ブランチ|'
    r'リポジトリ|ディレクトリ|パス|slack\s*bot|openai|llm|'
    r'python|javascript|typescript|react|css|html|app\.py|'
    r'wake_detect)',
    re.IGNORECASE,
)


def _is_claude_code_instruction(text: str) -> bool:
    """Claude Codeに向けた開発/操作指示かを判定する。"""
    if not text:
        return False
    # まずは依頼文らしい形かを確認
    if not _INSTRUCTION_PATTERN.search(text):
        return False
    # 開発文脈がない一般質問（例: 今日の予定を教えて）は除外
    return bool(_DEV_CONTEXT_PATTERN.search(text))

def _clean_text_for_tts(text: str) -> str:
    """TTS 用テキスト前処理: URL・絵文字を除去し空行を整理、名前を読み仮名に変換、長文を切り詰め"""
    text = re.sub(r'https?://\S+', '', text)
    text = emoji_lib.replace_emoji(text, replace='')
    text = re.sub(r'\n{3,}', '\n\n', text)
    for pattern, yomi in _get_yomigana_map():
        if pattern.search(text):
            before = text
            text = pattern.sub(yomi, text)
            logger.info(f"[YOMIGANA] '{pattern.pattern}' -> '{yomi}' | before='{before[:60]}' | after='{text[:60]}'")
    text = text.strip()
    # Truncate long text for voice readability
    if len(text) > _TTS_MAX_CHARS:
        # Try to cut at sentence boundary
        cut = text[:_TTS_MAX_CHARS]
        for sep in ('。', '、', '！', '？', '…', '. '):
            idx = cut.rfind(sep)
            if idx > _TTS_MAX_CHARS // 2:
                cut = cut[:idx + len(sep)]
                break
        text = cut.rstrip() + '…続きはチャットで確認してね'
        logger.info(f"[TTS] truncated to {len(text)} chars")
    return text


def _wav_duration(audio: bytes) -> float:
    """WAV バイト列から再生時間（秒）を計算"""
    if len(audio) < 44 or audio[:4] != b'RIFF':
        return 0.0
    # WAV header: bytes 24-27 = sample rate, 34-35 = bits per sample, 22-23 = channels
    sample_rate = struct.unpack_from('<I', audio, 24)[0]
    bits = struct.unpack_from('<H', audio, 34)[0]
    channels = struct.unpack_from('<H', audio, 22)[0]
    if sample_rate == 0 or bits == 0 or channels == 0:
        return 0.0
    data_size = len(audio) - 44
    return data_size / (sample_rate * (bits // 8) * channels)


def _wav_peak_db(audio: bytes) -> float | None:
    """WAVのピーク音量をdBFSで返す。16-bit PCM以外は None。"""
    if len(audio) < 44 or audio[:4] != b'RIFF':
        return None
    bits = struct.unpack_from('<H', audio, 34)[0]
    if bits != 16:
        return None
    pcm = audio[44:]
    if not pcm:
        return None
    peak = 0
    limit = len(pcm) - (len(pcm) % 2)
    for (sample,) in struct.iter_unpack('<h', pcm[:limit]):
        value = abs(sample)
        if value > peak:
            peak = value
    if peak <= 0:
        return -96.0
    return 20.0 * math.log10(peak / 32767.0)


def _apply_wav_peak_guard(audio: bytes, target_db: float = -1.5, trigger_db: float = -0.5) -> tuple[bytes, float | None]:
    """16-bit PCM WAVのピークが高すぎる場合に、全体ゲインを下げてクリップを回避する。"""
    peak_db = _wav_peak_db(audio)
    if peak_db is None or peak_db <= trigger_db:
        return audio, None
    gain_db = target_db - peak_db
    scale = 10 ** (gain_db / 20.0)
    pcm = audio[44:]
    limit = len(pcm) - (len(pcm) % 2)
    if limit <= 0:
        return audio, None

    out = bytearray(limit)
    offset = 0
    for (sample,) in struct.iter_unpack('<h', pcm[:limit]):
        scaled = int(round(sample * scale))
        if scaled > 32767:
            scaled = 32767
        elif scaled < -32768:
            scaled = -32768
        struct.pack_into('<h', out, offset, scaled)
        offset += 2

    adjusted = audio[:44] + bytes(out) + pcm[limit:]
    return adjusted, gain_db


def _normalize_compare_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r'https?://\S+', '', lowered)
    lowered = re.sub(r'[\s　、。！？!?,.…「」『』（）()\-]+', '', lowered)
    return lowered.strip()


def _reading_match_status(input_text: str, retranscribed_text: str, similarity: float) -> str:
    if similarity >= 0.92:
        return "ok"
    if similarity >= 0.75:
        return "warn"
    expected_terms = []
    for pattern, replacement in _get_yomigana_map():
        if pattern.search(input_text):
            expected_terms.append(replacement)
    if expected_terms and any(term in retranscribed_text for term in expected_terms):
        return "warn"
    return "fail"


def _tts_risk(similarity: float, reading_match: str, duration: float, peak_db: float | None, clipped: bool) -> str:
    if clipped or similarity < 0.70 or reading_match == "fail":
        return "high"
    if similarity < 0.88 or reading_match == "warn" or duration < 1.0 or (peak_db is not None and peak_db < -30.0):
        return "medium"
    return "low"


async def _emit_tts_diagnostic(text: str, audio: bytes):
    """TTS出力を再STTして発声品質を可視化する。"""
    if not _clients:
        return
    cleaned = _clean_text_for_tts(text)
    if len(cleaned) < 4:
        return
    loop = asyncio.get_event_loop()
    try:
        metrics = await loop.run_in_executor(None, _transcribe_sync_with_metrics, audio, True)
        retranscribed = metrics.get("text", "")
        normalized_input = _normalize_compare_text(cleaned)
        normalized_output = _normalize_compare_text(retranscribed)
        similarity = difflib.SequenceMatcher(None, normalized_input, normalized_output).ratio() if normalized_input or normalized_output else 0.0
        duration = _wav_duration(audio)
        peak_db = _wav_peak_db(audio)
        clipped = peak_db is not None and peak_db >= -0.3
        reading_match = _reading_match_status(cleaned, retranscribed, similarity)
        risk = _tts_risk(similarity, reading_match, duration, peak_db, clipped)
        peak_part = f"{peak_db:.1f}" if peak_db is not None else "n/a"
        diag = (
            f"[tts_eval] input='{cleaned[:80]}' "
            f"retranscribed='{retranscribed[:80]}' "
            f"similarity={similarity:.2f} "
            f"reading={reading_match} "
            f"duration={duration:.1f} "
            f"peak_db={peak_part} "
            f"risk={risk} "
            f"clipped={'true' if clipped else 'false'}"
        )
        logger.info(diag)
        await _broadcast_debug(diag)
    except Exception as e:
        logger.warning(f"[tts_eval] failed: {e}")


_MIN_DURATION_SEC = 3.0
_MIN_SIZE_BYTES = 50_000  # ~50KB
_MIN_TEXT_LEN_FOR_CHECK = 30  # 短いテキストはチェック不要


async def synthesize_speech(text: str, speaker_id: int | str, speed: float = 1.0, engine: str | None = None) -> bytes:
    """TTS エンジンでテキストを音声に変換（ロック内 double-check キャッシュ）"""
    global _last_tts_text
    text = _clean_text_for_tts(text)
    _last_tts_text = text  # エコー除去用に記録
    tts_engine = engine or _settings.get("ttsEngine", "voicevox")
    # Auto-detect engine from speaker_id prefix
    if tts_engine == "voicevox" and isinstance(speaker_id, str) and speaker_id.startswith("irodori-"):
        tts_engine = "irodori"
    cache_key = f"{tts_engine}:{speaker_id}:{speed}:{text}"
    now = time.time()
    cached = _tts_cache.get(cache_key)
    if cached and now - cached[0] < _TTS_CACHE_TTL:
        logger.info(f"[synthesize_speech] cache hit, engine={tts_engine}, speaker_id={speaker_id}")
        return cached[1]
    lock = _get_tts_lock(tts_engine)
    async with lock:
        now = time.time()
        cached = _tts_cache.get(cache_key)
        if cached and now - cached[0] < _TTS_CACHE_TTL:
            logger.info(f"[synthesize_speech] cache hit (after lock), engine={tts_engine}, speaker_id={speaker_id}")
            return cached[1]
        logger.info(f"[synthesize_speech] engine={tts_engine}, speaker_id={speaker_id}, speed={speed}")
        if tts_engine == "irodori":
            audio = await _synthesize_irodori_unlocked(text, str(speaker_id), speed)
        elif tts_engine == "gptsovits":
            audio = await synthesize_speech_gptsovits(text, str(speaker_id))
        else:
            audio = await synthesize_speech_voicevox(text, int(speaker_id), speed)

        adjusted_audio, gain_db = _apply_wav_peak_guard(audio)
        if gain_db is not None:
            before_peak = _wav_peak_db(audio)
            after_peak = _wav_peak_db(adjusted_audio)
            logger.info(
                f"[TTS] peak_guard gain_db={gain_db:.1f} "
                f"peak_before={before_peak:.1f} peak_after={after_peak:.1f}"
            )
        audio = adjusted_audio

        # --- 品質チェック: 長いテキストに対して短すぎる音声を検出 ---
        if len(text) >= _MIN_TEXT_LEN_FOR_CHECK:
            duration = _wav_duration(audio)
            if duration < _MIN_DURATION_SEC or len(audio) < _MIN_SIZE_BYTES:
                logger.error(f"[TTS QUALITY ERROR] duration={duration:.1f}s, size={len(audio)} bytes, text_len={len(text)}, engine={tts_engine}, speaker={speaker_id}")
                raise TTSQualityError(
                    f"TTS生成異常: {duration:.1f}秒 / {len(audio)//1024}KB（テキスト{len(text)}文字に対して短すぎる）",
                    duration=duration, size=len(audio), text_len=len(text),
                )

        _tts_cache[cache_key] = (time.time(), audio)
        # 古いキャッシュを掃除
        expired = [k for k, (t, _) in _tts_cache.items() if time.time() - t > _TTS_CACHE_TTL]
        for k in expired:
            del _tts_cache[k]
        return audio


async def synthesize_speech_voicevox(text: str, speaker_id: int, speed: float = 1.0) -> bytes:
    """VOICEVOX でテキストを音声に変換"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker_id},
        )
        resp.raise_for_status()
        query = resp.json()
        query["speedScale"] = speed

        resp = await client.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker_id},
            json=query,
        )
        resp.raise_for_status()
        return resp.content


IRODORI_API_URL = "http://localhost:7860"





async def _synthesize_irodori_unlocked(text: str, voice_id: str, speed: float = 1.0) -> bytes:
    """Irodori-TTS（ロックなし版 — 呼び出し元でロック取得済み前提）"""
    # LoRA ボイスの場合は /tts-ref エンドポイントを使用
    voice_entry = next((v for v in IRODORI_VOICES if v["id"] == voice_id), None)
    if voice_entry and voice_entry.get("lora"):
        if speed == 0:
            num_steps = 40 if len(text) > 120 else 30 if len(text) > 80 else 20
        else:
            num_steps = int(speed) if speed >= 2 else 20
        logger.info(f"[IRODORI TTS LoRA] voice_id={voice_id}, num_steps={num_steps}, text_len={len(text)}")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{IRODORI_API_URL}/tts-ref",
                json={"text": text, "num_steps": num_steps},
            )
            resp.raise_for_status()
            return resp.content

    caption = "自然で聞き取りやすい声で読み上げてください。"
    if voice_entry:
        caption = voice_entry.get("caption", caption)

    if speed == 0:
        # auto: テキスト長に応じてステップ数を自動決定
        if len(text) > 120:
            num_steps = 40
        elif len(text) > 80:
            num_steps = 30
        else:
            num_steps = 20
    else:
        num_steps = int(speed) if speed >= 2 else 10

    logger.info(f"[IRODORI TTS] voice_id={voice_id}, speed={speed}, num_steps={num_steps}, caption={caption[:30]}..., text_len={len(text)}")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{IRODORI_API_URL}/tts",
            json={"text": text, "caption": caption, "num_steps": num_steps},
        )
        resp.raise_for_status()
        return resp.content



_gptsovits_model_loaded = False

async def _ensure_gptsovits_model():
    """初回呼び出し時に v2ProPlus モデルに切り替え"""
    global _gptsovits_model_loaded
    if _gptsovits_model_loaded:
        return
    async with httpx.AsyncClient(timeout=60) as client:
        await client.get(f"{GPTSOVITS_API_URL}/set_gpt_weights?weights_path=GPT_SoVITS/pretrained_models/s1v3.ckpt")
        await client.get(f"{GPTSOVITS_API_URL}/set_sovits_weights?weights_path=GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth")
    _gptsovits_model_loaded = True
    print("[GPT-SoVITS] Loaded v2ProPlus model")

async def synthesize_speech_gptsovits(text: str, voice_id: str) -> bytes:
    """GPT-SoVITS でゼロショット音声クローン"""
    await _ensure_gptsovits_model()
    ref_audio = "emilia.wav"
    prompt_text = "ルグニカ王国次期王候補の一人なの。なんだか力がみなぎって、もっともっと強くなりたい。"
    for v in GPTSOVITS_VOICES:
        if v["id"] == voice_id:
            ref_audio = v["ref_audio"]
            prompt_text = v["prompt_text"]
            break
    ref_path = os.path.join(GPTSOVITS_REF_DIR, ref_audio)
    logger.info(f"[GPT-SoVITS] voice_id={voice_id}, ref={ref_audio}, text_len={len(text)}")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{GPTSOVITS_API_URL}/tts",
            json={
                "text": text,
                "text_lang": "ja",
                "ref_audio_path": ref_path,
                "prompt_text": prompt_text,
                "prompt_lang": "ja",
                "media_type": "wav",
                "streaming_mode": False,
            },
        )
        resp.raise_for_status()
        return resp.content


@app.get("/api/models")
async def get_models():
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("http://localhost:11434/api/tags")
        resp.raise_for_status()
        models = resp.json()["models"]
        return [
            {"name": m["name"], "size": m["details"]["parameter_size"]}
            for m in models
            if "embed" not in m["name"] and "e5" not in m["name"]
        ]


BOT_STATE_DIR = Path("/Users/akira/workspace/claude-code-slack-bot/data")

SAMPLE_TEXTS = [
    "こんにちは、今日はいい天気ですね。お散歩日和です。",
    "おはようございます。今日も一日頑張りましょう。",
    "最近、面白い本を読みました。おすすめですよ。",
    "今日のお昼ごはんは何にしようかな。ラーメンが食べたいな。",
    "週末はどこかに出かけませんか？温泉とかいいですね。",
    "プログラミングって楽しいですよね。新しいことを学ぶのが好きです。",
    "猫ってかわいいですよね。もふもふしたい。",
    "コーヒーと紅茶、どっちが好きですか？私はコーヒー派です。",
]


@app.get("/api/preview")
async def preview_voice(speaker: str = "2", speed: str = "auto"):
    import random
    text = random.choice(SAMPLE_TEXTS)
    spd = 0 if (speed or "auto") == "auto" else float(speed)
    audio = await synthesize_speech(text, speaker, spd)
    return Response(content=audio, media_type="audio/wav")



def _get_latest_bot_entry(bot_id: str) -> dict | None:
    state_file = BOT_STATE_DIR / f"{bot_id}-state.json"
    if not state_file.exists():
        return None
    state = json.loads(state_file.read_text())
    history = state.get("history", [])
    if not history:
        return None
    latest = history[-1]
    text = latest.get("fullText", latest.get("preview", ""))
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    return {"text": text.strip(), "sentAt": latest.get("sentAt", "")}


@app.get("/api/bot-text/{bot_id}")
async def get_bot_text(bot_id: str):
    entry = _get_latest_bot_entry(bot_id)
    if not entry:
        return Response(status_code=404)
    return entry


@app.get("/api/bot-audio/{bot_id}")
async def get_bot_audio(bot_id: str, speaker: str = "2", speed: str = "auto", engine: str | None = None):
    entry = _get_latest_bot_entry(bot_id)
    if not entry:
        return Response(status_code=404)
    spd = 0 if (speed or "auto") == "auto" else float(speed)
    try:
        audio = await synthesize_speech(entry["text"], speaker, spd, engine=engine)
    except TTSQualityError as e:
        return Response(
            content=json.dumps({"error": str(e), "duration": e.duration, "size": e.size, "text_len": e.text_len}),
            status_code=422,
            media_type="application/json",
        )
    return Response(content=audio, media_type="audio/wav")


# Slack DM 新着チェック用の最終既読 ts（ボット別）
_last_seen_ts: dict[str, str] = {}


@app.get("/api/slack/new-messages/{bot_id}")
async def slack_new_messages(bot_id: str, since: str = ""):
    """Slack DM の新着ボットメッセージを返す"""
    token = SLACK_USER_TOKENS.get(bot_id)
    channel = SLACK_DM_CHANNELS.get(bot_id)
    if not token or not channel:
        return {"messages": []}

    # since が指定されていれば使う、なければサーバー側の最終既読
    # 初回（sinceもサーバー側tsも空）は「今」をセットして次回から検知開始
    oldest = since or _last_seen_ts.get(bot_id, "")
    if not oldest:
        _last_seen_ts[bot_id] = str(time.time())
        return {"messages": []}

    async with httpx.AsyncClient(timeout=10) as client:
        params = {"channel": channel, "limit": 10}
        if oldest:
            params["oldest"] = oldest
        resp = await client.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        data = resp.json()

    if not data.get("ok"):
        return {"messages": []}

    results = []
    for msg in data.get("messages", []):
        # ボットからのメッセージのみ（ユーザー自身のは除外）
        msg_user = msg.get("user", "")
        if msg_user == os.getenv("SLACK_USER_ID", "U3SFGQXNH"):
            continue
        # ts が since 以前ならスキップ（oldest は exclusive ではないため）
        if oldest and msg.get("ts", "") <= oldest:
            continue
        text = msg.get("text", "")
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = emoji_lib.emojize(text, language='alias')
        text = text.strip()
        if text:
            results.append({"text": text, "ts": msg.get("ts", "")})

    # 最新の ts を記録
    if results:
        max_ts = max(r["ts"] for r in results)
        _last_seen_ts[bot_id] = max_ts

    return {"messages": results}


@app.get("/api/tts")
async def tts_endpoint(text: str, speaker: str = "2", speed: str = "auto"):
    """任意のテキストを音声合成して返す"""
    spd = 0 if (speed or "auto") == "auto" else float(speed)
    audio = await synthesize_speech(text, speaker, spd)
    return Response(content=audio, media_type="audio/wav")



@app.get("/api/speakers")
async def get_speakers(engine: str | None = None):
    tts_engine = engine or _settings.get("ttsEngine", "voicevox")
    if tts_engine == "irodori":
        return [
            {
                "name": v["name"],
                "styles": [{"id": v["id"], "name": "ノーマル"}],
            }
            for v in IRODORI_VOICES
        ]
    if tts_engine == "gptsovits":
        return [
            {
                "name": v["name"],
                "styles": [{"id": v["id"], "name": "ノーマル"}],
            }
            for v in GPTSOVITS_VOICES
        ]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{VOICEVOX_URL}/speakers")
        resp.raise_for_status()
        return resp.json()


async def slack_post_message(bot_id: str, text: str) -> str | None:
    """ユーザーとして Slack DM にメッセージを投稿し、ts を返す"""
    token = SLACK_USER_TOKENS.get(bot_id)
    channel = SLACK_DM_CHANNELS.get(bot_id)
    if not token or not channel:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": text},
        )
        data = resp.json()
        return data.get("ts") if data.get("ok") else None


async def slack_poll_response(bot_id: str, after_ts: str, timeout: float = 60) -> tuple[str, str] | tuple[None, None]:
    """Slack DM でボットの返信をポーリングする。(text, ts) を返す"""
    token = SLACK_USER_TOKENS.get(bot_id)
    channel = SLACK_DM_CHANNELS.get(bot_id)
    if not token or not channel:
        return None

    # ボットの bot user ID を取得（投稿者のフィルタリング用）
    bot_token = SLACK_BOT_TOKENS.get(bot_id)
    bot_user_id = None
    if bot_token:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {bot_token}"},
            )
            data = resp.json()
            if data.get("ok"):
                bot_user_id = data.get("user_id")

    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=10) as client:
        while time.time() < deadline:
            resp = await client.get(
                "https://slack.com/api/conversations.history",
                headers={"Authorization": f"Bearer {token}"},
                params={"channel": channel, "oldest": after_ts, "limit": 5},
            )
            data = resp.json()
            if data.get("ok"):
                for msg in data.get("messages", []):
                    # 投稿した本人のメッセージはスキップ
                    if msg.get("ts") == after_ts:
                        continue
                    # ボットの user_id からの返信を探す
                    if bot_user_id and msg.get("user") == bot_user_id:
                        text = msg.get("text", "")
                        text = re.sub(r'\*([^*]+)\*', r'\1', text)
                        text = re.sub(r'<[^>]+>', '', text)
                        return text.strip(), msg.get("ts", "")
                    # フォールバック: bot_user_id が不明な場合、自分以外の bot_id メッセージ
                    if not bot_user_id and (msg.get("bot_id") or msg.get("bot_profile")):
                        if msg.get("user") != "U3SFGQXNH":  # Akira のユーザーID
                            text = msg.get("text", "")
                            text = re.sub(r'\*([^*]+)\*', r'\1', text)
                            text = re.sub(r'<[^>]+>', '', text)
                            return text.strip(), msg.get("ts", "")
            await asyncio.sleep(3)
    return None, None


@app.post("/api/slack/reply/{bot_id}")
async def slack_reply(bot_id: str, speaker: int = 2, speed: float = 1.0):
    """音声を受け取り、STT → Slack投稿 → ボット返信待ち → TTS"""
    from fastapi import Request
    # This endpoint is called from JS with audio blob
    return {"error": "use websocket"}  # placeholder


@app.get("/api/settings")
async def get_settings():
    _get_auto_approve_enabled()
    return _settings


@app.get("/api/improve_loop/auto_approve")
async def get_improve_loop_auto_approve():
    return {"enabled": _get_auto_approve_enabled()}


@app.post("/api/improve_loop/auto_approve")
async def toggle_improve_loop_auto_approve(body: dict | None = None):
    if body and "enabled" in body:
        enabled = _set_auto_approve_enabled(bool(body["enabled"]))
    else:
        enabled = _set_auto_approve_enabled(not _get_auto_approve_enabled())
    await _broadcast_settings()
    return {"ok": True, "enabled": enabled}


@app.post("/api/improve_loop/run")
async def run_improve_loop():
    script = Path(__file__).parent / "co_view_hourly_analysis.sh"
    if not script.exists():
        return Response(
            content=json.dumps({"ok": False, "error": "script not found"}),
            status_code=404,
            media_type="application/json",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash",
            str(script),
            cwd=str(Path(__file__).parent),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"ok": True, "pid": proc.pid, "enabled": _get_auto_approve_enabled()}
    except Exception as e:
        return Response(
            content=json.dumps({"ok": False, "error": str(e)}),
            status_code=500,
            media_type="application/json",
        )


@app.get("/api/yomigana")
async def get_yomigana_dictionary():
    return {
        "entries": [
            {"pattern": pattern.pattern, "replacement": replacement}
            for pattern, replacement in _load_public_yomigana_map()
        ]
    }


@app.put("/api/yomigana")
async def update_yomigana_dictionary(body: dict):
    entries = body.get("entries", [])
    if not isinstance(entries, list):
        return {"error": "entries must be a list"}

    normalized: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern", "")).strip()
        replacement = str(item.get("replacement", "")).strip()
        if not pattern or not replacement:
            continue
        if len(pattern) > 128 or len(replacement) > 64:
            return {"error": "pattern or replacement too long"}
        try:
            re.compile(pattern)
        except re.error as e:
            return {"error": f"invalid regex: {pattern} ({e})"}
        normalized.append({"pattern": pattern, "replacement": replacement})

    YOMIGANA_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    return {"ok": True, "count": len(normalized)}


# --- Ambient REST API ---

@app.get("/api/ambient/rules")
async def get_ambient_rules():
    if not _ambient_listener:
        return {"rules": [], "keywords": []}
    return _ambient_listener.rules


@app.post("/api/ambient/rules")
async def add_ambient_rule(body: dict):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    rule = _ambient_listener.add_rule(body["text"], source=body.get("source", "manual"))
    return rule


@app.delete("/api/ambient/rules/{rule_id}")
async def delete_ambient_rule(rule_id: str):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    _ambient_listener.remove_rule(rule_id)
    return {"ok": True}


@app.patch("/api/ambient/rules/{rule_id}")
async def toggle_ambient_rule(rule_id: str, body: dict):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    _ambient_listener.toggle_rule(rule_id, enabled=body["enabled"])
    return {"ok": True}


@app.get("/api/ambient/examples")
async def get_ambient_examples():
    if not _ambient_listener:
        return {"examples": []}
    return _ambient_listener.examples


@app.post("/api/ambient/examples")
async def add_ambient_example(body: dict):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    ex = _ambient_listener.add_example(body["context"], body["response"], body.get("rating", "positive"))
    return ex


@app.delete("/api/ambient/examples/{example_id}")
async def delete_ambient_example(example_id: str):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    _ambient_listener.remove_example(example_id)
    return {"ok": True}


@app.post("/api/ambient/reactivity")
async def set_ambient_reactivity(body: dict):
    if not _ambient_listener:
        return {"error": "ambient not initialized"}
    _ambient_listener.set_reactivity(body["level"])
    _settings["ambient_reactivity"] = body["level"]
    _save_settings(_settings)
    await _broadcast_ambient_state()
    return {"ok": True, "level": _ambient_listener.reactivity}


@app.get("/api/ambient/stats")
async def get_ambient_stats():
    if not _ambient_listener:
        return {"judgments_today": 0, "speaks_today": 0, "speak_rate": 0}
    return _ambient_listener.get_stats()


@app.get("/api/speaker-id/profiles")
async def list_speaker_profiles():
    if not _speaker_id:
        return {"profiles": []}
    return {"profiles": _speaker_id.list_profiles()}


@app.post("/api/speaker-id/enroll/start")
async def start_enrollment(req: dict):
    if not _speaker_id:
        return {"ok": False, "message": "Speaker ID not initialized"}
    name = req.get("name", "").strip()
    display_name = req.get("display_name", "").strip()
    if not name:
        return {"ok": False, "message": "name is required"}
    msg = _speaker_id.start_enrollment(name, display_name)
    return {"ok": True, "message": msg}


@app.post("/api/speaker-id/enroll/sample")
async def upload_enrollment_sample(audio: UploadFile = File(...)):
    """Upload an audio sample for enrollment (from dashboard mic recording)."""
    if not _speaker_id:
        return {"ok": False, "message": "Speaker ID not initialized"}
    if not _speaker_id.is_enrolling:
        return {"ok": False, "message": "Enrollment not started"}
    audio_bytes = await audio.read()
    if len(audio_bytes) < 1000:
        return {"ok": False, "message": "Audio too short"}
    result = _speaker_id.add_enrollment_sample(audio_bytes)
    return result


@app.post("/api/speaker-id/enroll/finish")
async def finish_enrollment():
    if not _speaker_id:
        return {"ok": False, "message": "Speaker ID not initialized"}
    return _speaker_id.finish_enrollment()


@app.post("/api/speaker-id/enroll/guided")
async def start_guided_enrollment_api(req: dict):
    """Start Siri-style guided enrollment via REST."""
    global _enrollment_active
    if not _speaker_id:
        return {"ok": False, "message": "Speaker ID not initialized"}
    if _enrollment_active:
        return {"ok": False, "message": "Enrollment already in progress"}
    name = req.get("name", "").strip()
    display_name = req.get("display_name", "").strip() or name
    yomigana = req.get("yomigana", "").strip()
    if not name:
        return {"ok": False, "message": "name is required"}
    asyncio.create_task(_guided_enrollment(name, display_name, yomigana))
    return {"ok": True, "message": f"Guided enrollment started for {display_name}"}


@app.post("/api/speaker-id/enroll/cancel")
async def cancel_enrollment():
    global _enrollment_active
    if _speaker_id:
        _speaker_id.cancel_enrollment()
    _enrollment_active = False
    return {"ok": True}


@app.delete("/api/speaker-id/profiles/{name}")
async def remove_speaker(name: str):
    if not _speaker_id:
        return {"ok": False}
    ok = _speaker_id.remove_profile(name)
    return {"ok": ok}


@app.get("/")
async def index():
    html = (Path(__file__).parent / "index.html").read_text()
    return HTMLResponse(html)


_proactive_task: asyncio.Task | None = None


_always_on_echo_suppress_until: float = 0
_always_on_conversation_until: float = 0  # conversation window after wake
_whisper_busy: bool = False  # drop new audio while Whisper is processing
_last_tts_text: str = ""  # 直前のTTS出力テキスト（エコー除去用）
_always_on_conversation: list[dict] = [
    {"role": "system", "content": "あなたはメイという名前のフレンドリーな日本語の会話アシスタントです。音声会話なので、簡潔に1-2文で返答してください。"}
]
_ambient_listener: AmbientListener | None = None
_ambient_batch_task: asyncio.Task | None = None
_speaker_id: SpeakerIdentifier | None = None
_enrollment_active: bool = False
_enrollment_queue: asyncio.Queue | None = None  # audio bytes queue for guided enrollment


_TOOL_NEEDED_KEYWORDS = re.compile(
    r'予定|スケジュール|カレンダー|天気|メール|リマインダー|タイマー|'
    r'調べて|検索して|送って|教えて.*(今日|明日|来週|何時)'
)

_SLACK_BOT_API = "http://127.0.0.1:3457"
_TOOL_ROUTE_FAIL_COUNT = 0
_TOOL_ROUTE_COOLDOWN_UNTIL = 0.0
_TOOL_ROUTE_FAIL_THRESHOLD = 2
_TOOL_ROUTE_COOLDOWN_SEC = 90.0
_LOCAL_TOOL_WEATHER_LAT = float(os.getenv("LOCAL_TOOL_WEATHER_LAT", "35.6764"))   # Tokyo
_LOCAL_TOOL_WEATHER_LON = float(os.getenv("LOCAL_TOOL_WEATHER_LON", "139.6500"))  # Tokyo
_LOCAL_TOOL_WEATHER_LABEL = os.getenv("LOCAL_TOOL_WEATHER_LABEL", "東京")

_TIME_QUERY_RE = re.compile(r'何時|なんじ|時刻|今何時|いま何時|日時|今日|明日|曜日')
_WEATHER_QUERY_RE = re.compile(r'天気|気温|降水|雨|晴れ|曇り|風')
_SEARCH_QUERY_RE = re.compile(r'調べて|検索して|教えて|とは|って何|について')
_UNSUPPORTED_LOCAL_TOOLS_RE = re.compile(r'メール|リマインダー|タイマー|カレンダー|予定|スケジュール')

_WEATHER_CODE_MAP = {
    0: "快晴",
    1: "晴れ",
    2: "薄曇り",
    3: "曇り",
    45: "霧",
    48: "霧氷",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    80: "にわか雨",
    81: "強いにわか雨",
    82: "激しいにわか雨",
    95: "雷雨",
}


def _tool_route_in_cooldown() -> float:
    return _TOOL_ROUTE_COOLDOWN_UNTIL - time.time()


def _extract_search_query(text: str) -> str:
    """簡易検索用に発話からクエリを抽出。"""
    cleaned = text.strip()
    cleaned = re.sub(r'^(?:ねぇ|ねえ|メイ|めい)[、,\s]*', '', cleaned)
    cleaned = re.sub(r'[？?！!。]+$', '', cleaned)
    cleaned = re.sub(r'(調べて|検索して|教えて)$', '', cleaned).strip()
    return cleaned[:80]


async def _tool_weather_summary() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": _LOCAL_TOOL_WEATHER_LAT,
                    "longitude": _LOCAL_TOOL_WEATHER_LON,
                    "current": "temperature_2m,weather_code,wind_speed_10m",
                    "timezone": "Asia/Tokyo",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("current", {})
            temp = data.get("temperature_2m")
            wcode = data.get("weather_code")
            wind = data.get("wind_speed_10m")
            weather = _WEATHER_CODE_MAP.get(wcode, f"code={wcode}")
            return f"{_LOCAL_TOOL_WEATHER_LABEL}の現在: {weather}, 気温{temp}°C, 風速{wind}m/s"
    except Exception as e:
        logger.warning(f"[local_tool] weather fetch failed: {e}")
        return None


async def _tool_wikipedia_summary(query_text: str) -> str | None:
    if not query_text:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            search_resp = await client.get(
                "https://ja.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query_text,
                    "format": "json",
                    "utf8": 1,
                },
            )
            search_resp.raise_for_status()
            results = search_resp.json().get("query", {}).get("search", [])
            if not results:
                return None
            title = results[0].get("title", "")
            detail_resp = await client.get(
                "https://ja.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "titles": title,
                    "format": "json",
                    "utf8": 1,
                },
            )
            detail_resp.raise_for_status()
            pages = detail_resp.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            extract = (page.get("extract", "") or "").strip().replace("\n", " ")
            if not extract:
                return f"Wikipedia候補: {title}"
            return f"Wikipedia: {title} — {extract[:140]}"
    except Exception as e:
        logger.warning(f"[local_tool] wikipedia fetch failed: {e}")
        return None


async def _local_tool_evidence(text: str) -> list[str]:
    """ローカルで実行できるツール結果を収集。"""
    evidence: list[str] = []
    if _TIME_QUERY_RE.search(text):
        now = datetime.now()
        evidence.append(f"現在日時: {now.strftime('%Y-%m-%d %H:%M:%S (%a)')}")
    if _WEATHER_QUERY_RE.search(text):
        weather = await _tool_weather_summary()
        if weather:
            evidence.append(weather)
    if _SEARCH_QUERY_RE.search(text):
        query_text = _extract_search_query(text)
        wiki = await _tool_wikipedia_summary(query_text)
        if wiki:
            evidence.append(wiki)
    if _UNSUPPORTED_LOCAL_TOOLS_RE.search(text):
        evidence.append("注意: ローカルフォールバックではメール/カレンダー等の個人データ参照は不可")
    return evidence


async def _local_llm_with_tools_reply(text: str, model: str) -> str | None:
    """tool_route失敗時に、ローカルツール結果を添えてローカルLLMで返答。"""
    evidence = await _local_tool_evidence(text)
    if not evidence:
        return None
    tool_block = "\n".join(f"- {item}" for item in evidence)
    messages = [
        {
            "role": "system",
            "content": (
                "あなたは日本語の会話アシスタントです。"
                "以下のツール結果を優先して、音声向けに簡潔な1-2文で返答してください。"
                "推測で断定せず、足りない情報は不足と明示してください。"
            ),
        },
        {"role": "user", "content": f"質問: {text}\n\nローカルツール結果:\n{tool_block}"},
    ]
    try:
        reply = await chat_with_llm(messages, model)
        return emoji_lib.replace_emoji(reply, replace='').strip()
    except Exception as e:
        logger.warning(f"[local_tool] local LLM fallback failed: {e}")
        return None


async def _ask_slack_bot(question: str, speaker: str | None = None, *, system_prompt: str | None = None) -> str | None:
    """Route question to Slack Bot (Claude + MCP tools) for tool-assisted answers."""
    global _TOOL_ROUTE_FAIL_COUNT, _TOOL_ROUTE_COOLDOWN_UNTIL
    remaining = _tool_route_in_cooldown()
    if remaining > 0:
        logger.info(f"[tool_route] bypass in cooldown ({remaining:.0f}s left)")
        return None
    try:
        payload: dict = {"question": question, "speaker": speaker}
        if system_prompt:
            payload["systemPrompt"] = system_prompt
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{_SLACK_BOT_API}/internal/ask",
                json=payload,
            )
            data = resp.json()
            if data.get("ok"):
                _TOOL_ROUTE_FAIL_COUNT = 0
                _TOOL_ROUTE_COOLDOWN_UNTIL = 0.0
                logger.info(f"[tool_route] Slack Bot replied in {data.get('durationMs')}ms")
                return data["reply"]
            else:
                _TOOL_ROUTE_FAIL_COUNT += 1
                err_msg = data.get("error", "")
                is_auth_err = "authentication" in str(err_msg).lower() or "401" in str(err_msg)
                if _TOOL_ROUTE_FAIL_COUNT >= _TOOL_ROUTE_FAIL_THRESHOLD:
                    _TOOL_ROUTE_COOLDOWN_UNTIL = time.time() + _TOOL_ROUTE_COOLDOWN_SEC
                    logger.warning(
                        f"[tool_route] Slack Bot error: {err_msg} "
                        f"(cooldown {_TOOL_ROUTE_COOLDOWN_SEC:.0f}s)"
                    )
                else:
                    logger.warning(f"[tool_route] Slack Bot error: {err_msg}")
                if is_auth_err:
                    ts = datetime.now().strftime("%H:%M")
                    asyncio.create_task(_broadcast_session_error(f"Auth 401 [{ts}]"))
                return None
    except Exception as e:
        _TOOL_ROUTE_FAIL_COUNT += 1
        if _TOOL_ROUTE_FAIL_COUNT >= _TOOL_ROUTE_FAIL_THRESHOLD:
            _TOOL_ROUTE_COOLDOWN_UNTIL = time.time() + _TOOL_ROUTE_COOLDOWN_SEC
            logger.warning(f"[tool_route] Slack Bot unreachable: {e} (cooldown {_TOOL_ROUTE_COOLDOWN_SEC:.0f}s)")
        else:
            logger.warning(f"[tool_route] Slack Bot unreachable: {e}")
        return None


async def _always_on_llm_reply(ws: WebSocket, text: str):
    """Process text through LLM and send TTS response."""
    global _always_on_echo_suppress_until, _always_on_conversation_until
    try:
        _always_on_conversation.append({"role": "user", "content": text})
        if len(_always_on_conversation) > 11:  # system + 5 turns
            _always_on_conversation[1:3] = []

        await ws.send_json({"type": "status", "text": "考え中..."})

        # Check if external tools are needed
        needs_tool = bool(_TOOL_NEEDED_KEYWORDS.search(text))
        reply = None

        if needs_tool and _tool_route_in_cooldown() <= 0:
            logger.info(f"[tool_route] routing to Slack Bot: '{text[:50]}'")
            await _send_debug(ws, f"[tool] Slack Bot に問い合わせ中...")

            # Play pre-cached wait message instantly
            wait_resp = _wait_cache.get_random()
            if wait_resp:
                wait_text, wait_audio = wait_resp
                await ws.send_json({"type": "assistant_text", "text": wait_text})
                await ws.send_bytes(wait_audio)
                duration = _wav_duration(wait_audio)
                _always_on_echo_suppress_until = time.time() + max(5.0, duration + 3.0)

            speaker = _ambient_listener.current_speaker if _ambient_listener else None
            reply = await _ask_slack_bot(text, speaker)
        elif needs_tool:
            remaining = _tool_route_in_cooldown()
            logger.info(f"[tool_route] skipped by cooldown ({remaining:.0f}s left)")

        if not reply:
            model = _settings.get("modelSelect", "gemma4:e4b")
            if needs_tool:
                local_tool_reply = await _local_llm_with_tools_reply(text, model)
                if local_tool_reply:
                    reply = local_tool_reply
                    logger.info("[tool_route] local tool fallback used")
                    await _send_debug(ws, "[tool] local fallback used")
            if not reply:
                reply = await chat_with_llm(_always_on_conversation, model)
        reply = emoji_lib.replace_emoji(reply, replace='').strip()
        if not reply:
            reply = "ちょっとわからなかった"
        _always_on_conversation.append({"role": "assistant", "content": reply})
        logger.info(f"[always_on] LLM reply: '{reply[:80]}'")
        if _ambient_listener:
            _ambient_listener.record_mei_utterance(reply)

        # TTS
        mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
        mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
        mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
        try:
            _always_on_echo_suppress_until = time.time() + 3.0  # pre-emptive (短め、TTS後に実時間で上書き)
            audio = await synthesize_speech(reply, mei_speaker, mei_speed)
            await ws.send_json({"type": "assistant_text", "text": reply})
            await ws.send_bytes(audio)
            duration = _wav_duration(audio)
            _always_on_echo_suppress_until = time.time() + max(3.0, duration + 2.0)
            asyncio.create_task(_emit_tts_diagnostic(reply, audio))
        except Exception as e:
            _always_on_echo_suppress_until = 0
            await ws.send_json({"type": "assistant_text", "text": reply, "tts_fallback": True})
            logger.warning(f"[always_on] TTS error: {e}")

        # Extend conversation window
        _always_on_conversation_until = time.time() + 30.0
    except Exception as e:
        logger.warning(f"[always_on] LLM error: {e}")


def _debug_ts() -> str:
    return time.strftime("%H:%M:%S")


async def _send_debug(ws: WebSocket, info: str):
    """Send listening debug info to client if debug mode is enabled."""
    if _settings.get("listeningDebug"):
        try:
            rendered = _render_diagnostic_text(info)
            await ws.send_json({"type": "listening_debug", "text": rendered})
            if "[" in info and "]" in info:
                await _send_diagnostic_event(rendered, target=ws)
        except Exception:
            pass


async def _broadcast_session_error(msg: str):
    """Broadcast session error to all clients (shown in UI regardless of debug setting)."""
    payload = json.dumps({"type": "session_error", "msg": msg})
    for client in list(_clients):
        try:
            await client.send_text(payload)
        except Exception:
            _clients.discard(client)


async def _broadcast_debug(info: str):
    """Broadcast listening debug info to all clients."""
    if not _settings.get("listeningDebug"):
        return
    rendered = _render_diagnostic_text(info)
    payload = json.dumps({"type": "listening_debug", "text": rendered})
    for client in list(_clients):
        try:
            await client.send_text(payload)
        except Exception:
            _clients.discard(client)
    if "[" in info and "]" in info:
        await _send_diagnostic_event(rendered)


def _identify_speaker_sync(audio_data: bytes) -> dict | None:
    """Synchronous speaker identification (runs in executor)."""
    if not _speaker_id:
        return None
    try:
        return _speaker_id.identify(audio_data)
    except Exception as e:
        logger.warning(f"[speaker_id] error: {e}")
        return None


# --- Guided Enrollment (Siri-style voice enrollment) ---

_ENROLLMENT_PROMPTS = [
    "メイ、今日の天気はどう？",
    "メイ、おはよう",
    "メイ、今何時？",
    "メイ、音楽をかけて",
    "メイ、おやすみ",
]


async def _broadcast_tts(text: str):
    """Send TTS audio + text to all connected clients."""
    global _always_on_echo_suppress_until
    mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
    mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
    mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
    try:
        audio = await synthesize_speech(text, mei_speaker, mei_speed)
        payload = json.dumps({"type": "assistant_text", "text": text})
        for client in list(_clients):
            try:
                await client.send_text(payload)
                await client.send_bytes(audio)
            except Exception:
                _clients.discard(client)
        duration = _wav_duration(audio)
        _always_on_echo_suppress_until = time.time() + max(5.0, duration + 2.0)
    except Exception as e:
        logger.warning(f"[enrollment] TTS error: {e}")
        payload = json.dumps({"type": "assistant_text", "text": text, "tts_fallback": True})
        for client in list(_clients):
            try:
                await client.send_text(payload)
            except Exception:
                _clients.discard(client)


async def _guided_enrollment(name: str, display_name: str, yomigana: str = ""):
    """Siri-style guided voice enrollment.

    MEI speaks prompts via TTS, always-on listener captures responses,
    and audio is routed to enrollment via _enrollment_queue.
    """
    global _enrollment_active, _enrollment_queue
    if not _speaker_id:
        return

    _enrollment_queue = asyncio.Queue()
    _enrollment_active = True
    _speaker_id.start_enrollment(name, display_name)
    # Use yomigana for TTS pronunciation, fallback to display_name
    tts_name = yomigana or display_name
    logger.info(f"[enrollment] guided enrollment started for '{display_name}' (yomigana='{tts_name}')")

    try:
        # Opening prompt
        await _broadcast_tts(
            f"{tts_name}さんの声を登録するね。"
            f"私が言うフレーズを繰り返してね。"
        )
        await asyncio.sleep(4.0)  # wait for TTS playback

        samples_collected = 0
        for i, phrase in enumerate(_ENROLLMENT_PROMPTS):
            if samples_collected >= 5:
                break

            # Announce the phrase
            prompt_text = f"「{phrase}」と言ってください"
            await _broadcast_tts(prompt_text)
            await asyncio.sleep(3.5)  # wait for TTS playback

            # Wait for audio from always-on listener (timeout 10s)
            try:
                audio_data = await asyncio.wait_for(
                    _enrollment_queue.get(), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"[enrollment] timeout waiting for sample {i+1}")
                await _broadcast_tts("聞き取れませんでした。もう一度お願いします")
                await asyncio.sleep(3.0)
                # Retry once
                try:
                    audio_data = await asyncio.wait_for(
                        _enrollment_queue.get(), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"[enrollment] retry timeout for sample {i+1}")
                    continue

            # Add sample
            result = _speaker_id.add_enrollment_sample(audio_data)
            if result.get("ok"):
                samples_collected = result.get("samples", samples_collected + 1)
                logger.info(f"[enrollment] sample {samples_collected} accepted")
                # Brief acknowledgment
                if samples_collected < 3:
                    await _broadcast_tts("OK")
                    await asyncio.sleep(1.5)
                elif result.get("can_finish"):
                    await _broadcast_tts("いい感じ")
                    await asyncio.sleep(1.5)
            else:
                msg = result.get("message", "")
                logger.warning(f"[enrollment] sample rejected: {msg}")
                await _broadcast_tts("もう一度お願いします")
                await asyncio.sleep(2.5)

        # Finish enrollment
        if samples_collected >= 3:
            result = _speaker_id.finish_enrollment()
            if result.get("ok"):
                await _broadcast_tts(
                    f"登録完了。{tts_name}さんの声を覚えたよ。"
                    f"これからは声で誰が話しているかわかるようになるね。"
                )
                logger.info(f"[enrollment] completed with {samples_collected} samples")
            else:
                await _broadcast_tts("登録に失敗しました。もう一度やり直してください。")
                logger.warning(f"[enrollment] finish failed: {result}")
        else:
            _speaker_id.cancel_enrollment()
            await _broadcast_tts(
                f"サンプルが足りなかったので登録できませんでした。"
                f"もう一度やり直してね。"
            )
            logger.warning(f"[enrollment] insufficient samples ({samples_collected})")

    except Exception as e:
        logger.error(f"[enrollment] error: {e}")
        _speaker_id.cancel_enrollment()
        await _broadcast_tts("エラーが発生しました。登録を中断します。")
    finally:
        _enrollment_active = False
        _enrollment_queue = None
        logger.info("[enrollment] guided enrollment ended")

    # Broadcast updated profiles
    payload = json.dumps({
        "type": "speaker_profiles",
        "profiles": _speaker_id.list_profiles(),
    })
    for client in list(_clients):
        try:
            await client.send_text(payload)
        except Exception:
            _clients.discard(client)


async def _process_always_on(ws: WebSocket, audio_data: bytes, *, speech_ts: int | None = None):
    """Process always-on audio in background — doesn't block WS receive loop."""
    global _always_on_echo_suppress_until, _always_on_conversation_until, _whisper_busy
    try:
        # Route to enrollment if active
        if _enrollment_active and _enrollment_queue:
            await _enrollment_queue.put(audio_data)
            return

        echo_remaining = _always_on_echo_suppress_until - time.time()
        if echo_remaining > 0:
            logger.info(f"[always_on] BLOCKED echo_suppress: {echo_remaining:.1f}s remain, {len(audio_data)}bytes")
            return

        # Filter out very short audio fragments
        audio_duration = len(audio_data) / 32000  # rough estimate: 16kHz * 16bit = 32000 bytes/s
        if audio_duration < 0.5:
            logger.info(f"[always_on] BLOCKED short: {audio_duration:.1f}s ({len(audio_data)}bytes)")
            return

        if _whisper_busy:
            logger.info(f"[always_on] BLOCKED whisper_busy: {audio_duration:.1f}s")
            return

        keyboard_like, keyboard_reason = _looks_like_keyboard_pulse(audio_data)
        if keyboard_like:
            logger.info(f"[always_on] BLOCKED keyboard_pulse: {keyboard_reason}")
            return

        _whisper_busy = True
        try:
            # Run Whisper STT and speaker ID in parallel
            # Always use small model for always-on (speed > accuracy)
            # large-v3 is reserved for non-always-on transcription
            use_fast = True
            loop = asyncio.get_event_loop()
            whisper_task = asyncio.ensure_future(transcribe(audio_data, fast=use_fast))
            speaker_task = loop.run_in_executor(
                None, _identify_speaker_sync, audio_data
            ) if _speaker_id and _speaker_id.profiles else None

            text = await whisper_task
            speaker_result = await speaker_task if speaker_task else None
        finally:
            _whisper_busy = False
        if not text:
            if len(audio_data) > 5000:
                await _send_debug(ws, f"[hallucination] filtered (audio={len(audio_data)}bytes, no text)")
            return

        # Filter Whisper hallucinations (repeated chars, gibberish)
        if _is_whisper_hallucination(text):
            logger.debug(f"[hallucination] gibberish filtered: '{text[:40]}'")
            await _send_debug(ws, f"[hallucination] '{text[:30]}' (gibberish)")
            return

        if _looks_like_initial_prompt_echo(text):
            logger.info(f"[always_on] BLOCKED prompt_echo: '{text[:40]}'")
            await _send_debug(ws, f"[hallucination] '{text[:30]}' (prompt echo)")
            return

        # Strip TTS echo from STT result (e.g. proactive "続きはチャットで確認してね" captured by mic)
        if _last_tts_text and len(_last_tts_text) >= 6:
            tts_clean = _last_tts_text.replace(" ", "").replace("　", "").replace("、", "").replace("。", "")
            text_clean = text.replace(" ", "").replace("　", "").replace("、", "").replace("。", "")
            # Check if STT text is a substring of the TTS text (echo of any part)
            if len(text_clean) >= 5 and text_clean in tts_clean:
                logger.info(f"[echo_strip] entire text was TTS echo: '{text[:40]}'")
                return
            # Check if TTS text tail appears as prefix of STT result (partial echo + user speech)
            for prefix_len in range(min(len(tts_clean), len(text_clean)), 4, -1):
                if text_clean[:prefix_len] == tts_clean[-prefix_len:]:
                    stripped = text[prefix_len:].strip()
                    if stripped:
                        logger.info(f"[echo_strip] removed TTS echo prefix ({prefix_len} chars) → remaining: '{stripped}'")
                        text = stripped
                    else:
                        logger.info(f"[echo_strip] entire text was TTS echo: '{text[:40]}'")
                        return
                    break

        in_conversation = time.time() < _always_on_conversation_until
        wake_result = detect_wake_word(text)
        should_correct = should_apply_stt_correction(
            text,
            speaker_identified=bool(speaker_result and speaker_result.get("speaker")),
            wake_detected=wake_result.detected,
            in_conversation=in_conversation,
            instruction_pattern=_INSTRUCTION_PATTERN,
        )
        if should_correct:
            context_texts = None
            if _ambient_listener and _ambient_listener.text_buffer:
                context_texts = [e["text"] for e in _ambient_listener.text_buffer[-3:]]
            original_text = text
            text = await _correct_stt_text(text, context_texts)
            if text != original_text:
                await _send_debug(ws, f"[stt_correct] '{original_text}' → '{text}'")
        else:
            await _send_debug(ws, f"[stt_correct] skipped for low-confidence ambient text")

        # Log speaker identification and track for multi-speaker detection
        spk_name_global = None
        if speaker_result and speaker_result.get("speaker"):
            spk_name_global = speaker_result["display_name"]
            sim = speaker_result["similarity"]
            logger.info(f"[speaker_id] identified: {spk_name_global} (sim={sim:.3f}) | '{text[:40]}'")
        elif speaker_result:
            sim = speaker_result["similarity"]
            if audio_duration < 4.0:
                logger.debug(f"[speaker_id] unknown speaker (best_sim={sim:.3f}, short={audio_duration:.1f}s) | '{text[:40]}'")
            else:
                logger.info(f"[speaker_id] unknown speaker (best_sim={sim:.3f}) | '{text[:40]}'")
        if _ambient_listener:
            _ambient_listener.record_speaker(spk_name_global)

        if time.time() < _always_on_echo_suppress_until:
            await _send_debug(ws, f"[echo suppress] '{text[:40]}'")
            return

        # Format speech timestamp for debug display
        model_tag = "small" if use_fast else "large-v3"
        if speech_ts:
            speech_time = datetime.fromtimestamp(speech_ts / 1000).strftime("%H:%M:%S")
            stt_delay = round(time.time() - speech_ts / 1000, 1)
            await _send_debug(ws, f"[STT/{model_tag}] '{text}' (spoke@{speech_time}, +{stt_delay}s)")
        else:
            await _send_debug(ws, f"[STT/{model_tag}] '{text}'")

        # --- Ambient command detection (highest priority) ---
        cmd = detect_ambient_command(text)
        if cmd.type == "stop":
            logger.info(f"[ambient] STOP command: '{text}'")
            await _send_debug(ws, f"[command] STOP")
            _always_on_conversation_until = 0
            if _ambient_listener:
                _ambient_listener.state = "listening"
            for client in list(_clients):
                try:
                    await client.send_json({"type": "stop_audio"})
                except Exception:
                    pass
            return

        if cmd.type in ("quiet", "talk_more") and _ambient_listener:
            logger.info(f"[ambient] mode command: {cmd.type} delta={cmd.level_delta}")
            await _send_debug(ws, f"[command] {cmd.type} (delta={cmd.level_delta})")
            _ambient_listener.apply_override(
                level_delta=cmd.level_delta,
                duration_sec=cmd.duration_sec,
                trigger=text,
            )
            ack_texts = {
                "quiet": "わかった、静かにするね",
                "talk_more": "了解、もっと話しかけるね",
            }
            await _ambient_broadcast_text(ack_texts.get(cmd.type, ""), ws)
            await _broadcast_ambient_state()
            return

        # --- Wake word detection ---
        if wake_result.detected:
            logger.info(f"[always_on] WAKE DETECTED: '{text}' → remaining: '{wake_result.remaining_text}'")
            await _send_debug(ws, f"[wake] keyword='{wake_result.keyword}' remaining='{wake_result.remaining_text}'")
            wake_resp = _wake_cache.get_random()
            if wake_resp:
                resp_text, resp_audio = wake_resp
                await ws.send_json({"type": "wake_detected", "keyword": wake_result.keyword, "response_text": resp_text})
                await ws.send_bytes(resp_audio)
                _always_on_echo_suppress_until = time.time() + 3.0
            else:
                await ws.send_json({"type": "wake_detected", "keyword": wake_result.keyword, "response_text": ""})
            _always_on_conversation_until = time.time() + 30.0
            remaining = wake_result.remaining_text
            # Only send to LLM if remaining is a real question/request (>8 chars)
            # Short remainders like "聞こえる?" "起きてる?" are covered by wake response
            if remaining and len(remaining) > 8:
                await _always_on_llm_reply(ws, remaining)
        elif in_conversation:
            # Echo check: skip if STT matches MEI's recent utterance
            if _ambient_listener and _ambient_listener.is_echo(text):
                logger.info(f"[always_on] conversation echo filtered: '{text[:50]}'")
                await _send_debug(ws, f"[conversation] echo filtered")
                return
            # Instruction detection: Claude Code向けの指示は会話モードでも拒否
            if _is_claude_code_instruction(text):
                logger.info(f"[always_on] conversation instruction filtered: '{text[:50]}'")
                await _send_debug(ws, f"[conversation] instruction → decline")
                # 短く断って会話を続行可能にする
                decline_reply = "それは私にはできないよ。Claude Code に聞いてみて。"
                mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
                mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
                mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
                try:
                    _always_on_echo_suppress_until = time.time() + 3.0
                    audio = await synthesize_speech(decline_reply, mei_speaker, mei_speed)
                    await ws.send_json({"type": "assistant_text", "text": decline_reply})
                    await ws.send_bytes(audio)
                    duration = _wav_duration(audio)
                    _always_on_echo_suppress_until = time.time() + max(3.0, duration + 2.0)
                    if _ambient_listener:
                        _ambient_listener.record_mei_utterance(decline_reply)
                    asyncio.create_task(_emit_tts_diagnostic(decline_reply, audio))
                except Exception:
                    pass
                return
            logger.info(f"[always_on] conversation: '{text[:50]}'")
            conv_remaining = int(_always_on_conversation_until - time.time())
            await _send_debug(ws, f"[conversation] window={conv_remaining}s")
            await _always_on_llm_reply(ws, text)
        else:
            # --- Ambient processing ---
            if _ambient_listener and _ambient_listener.effective_reactivity > 0:
                # Pass speaker identity to ambient listener
                spk_name = speaker_result.get("display_name") if speaker_result and speaker_result.get("speaker") else None
                if spk_name:
                    _ambient_listener.current_speaker = spk_name
                else:
                    _ambient_listener.current_speaker = None
                _ambient_listener.record_speaker(spk_name)

                if not _ambient_listener.add_to_buffer(text):
                    logger.info(f"[ambient] echo filtered: '{text[:50]}'")
                    await _send_debug(ws, f"[ambient] echo filtered")
                else:
                    kw_match = _ambient_listener.check_keywords(text)
                    if kw_match and not _ambient_listener.is_llm_in_cooldown():
                        logger.info(f"[ambient] keyword hit: {kw_match['category']} in '{text[:50]}'")
                        await _send_debug(ws, f"[ambient] keyword='{kw_match['category']}' → LLM")
                        _ambient_listener.record_cooldown(kw_match["category"])
                        await _ambient_llm_reply(ws, text, method="keyword", keyword=kw_match["category"])
                    else:
                        logger.info(f"[ambient] buffered: '{text[:50]}'")
                        await _send_debug(ws, f"[ambient] buffered")
            else:
                await _send_debug(ws, f"[ignored] ambient off")
            if ws in _clients:
                await ws.send_json({"type": "always_on_result", "wake": False})
    except Exception as e:
        if "websocket" not in str(e).lower() and "disconnect" not in str(e).lower():
            logger.warning(f"[always_on] processing error: {e}")


async def _ambient_llm_reply(ws: WebSocket, trigger_text: str, method: str = "keyword", keyword: str = ""):
    """Two-tier ambient response: fast local LLM first, then optional Claude follow-up."""
    global _always_on_echo_suppress_until
    if not _ambient_listener:
        return
    try:
        _ambient_listener.state = "processing"
        source_hint = _ambient_listener.classify_source(trigger_text)
        intervention = _ambient_listener.decide_intervention(trigger_text, source_hint)
        logger.info(f"[ambient] source: {source_hint} intervention={intervention} | '{trigger_text[:40]}'")
        source_label = {"user_response": "User(応答)", "user_initiative": "User(呼びかけ)",
                        "user_likely": "User(推定)", "user_identified": "User(声紋)",
                        "media_likely": "Media(TV等)", "fragmentary": "Fragment", "unknown": "不明",
                        "user_in_conversation": "User(会話中)"}.get(source_hint, source_hint)
        ambient_model = _settings.get("ambientModel", "") or _settings.get("modelSelect", "gemma4:e4b")
        await _broadcast_debug(f"[ambient] model={ambient_model} method={method} source={source_label} intervention={intervention} text='{trigger_text[:50]}'")

        if intervention == "skip":
            logger.info(f"[ambient] intervention=skip → server-side SKIP")
            await _broadcast_debug(f"[ambient] → SKIP ({source_hint})")
            _ambient_listener.record_judgment(method=method, result="skip", keyword=keyword, source_hint=source_hint, intervention=intervention)
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        if intervention == "co_view":
            logger.info("[ambient] intervention=co_view")
            await _broadcast_debug("[ambient] → co_view path")
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            await _handle_co_view(ws, trigger_text, method, keyword)
            return

        # Detect instructions/technical questions directed at Claude Code, not MEI
        is_instruction = _is_claude_code_instruction(trigger_text)

        prompt = _ambient_listener.build_llm_prompt(source_hint=source_hint)
        if intervention == "backchannel":
            prompt += "\n\n今回の目標は短い相槌のみ。必ず `BACKCHANNEL: ...` 形式で、4〜12文字くらいに収める。迷ったら SKIP。"
        if is_instruction:
            prompt += "\n\n【最重要】この発話は他のシステムへの作業指示です。絶対に \"SKIP\" と返してください。応援も不要です。"
            logger.info(f"[ambient] instruction detected → forcing SKIP hint")

        # co_view バックグラウンド蓄積結果を reply/backchannel にも注入
        if _media_ctx.confidence >= 0.5 and _media_ctx.media_buffer:
            media_section = (
                f"\n\n## 現在の視聴コンテキスト\n"
                f"視聴中: {_media_ctx.inferred_type} — {_media_ctx.inferred_topic}\n"
                f"最近の音声:\n{_media_ctx.get_buffer_text(last_n=5)}\n"
            )
            if _media_ctx.enriched_info:
                media_section += f"\n関連情報:\n{_media_ctx.enriched_info}\n"
            prompt += media_section

        mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
        mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
        mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)

        # --- Tier 1: Fast local LLM for instant reaction ---
        local_model = _settings.get("modelSelect", "gemma4:e4b")
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"直近の発話: {trigger_text}"},
        ]
        try:
            logger.info(f"[ambient/tier1] local LLM ({local_model}) starting")
            await _broadcast_debug(f"[ambient/tier1] {local_model} で即レス判定中...")
            local_reply = await asyncio.wait_for(chat_with_llm(messages, local_model), timeout=30)
            logger.info(f"[ambient/tier1] local reply: '{local_reply[:60]}'")
        except asyncio.TimeoutError:
            logger.warning(f"[ambient/tier1] local LLM timeout (30s)")
            await _broadcast_debug(f"[ambient/tier1] TIMEOUT")
            _ambient_listener.record_judgment(method=method, result="timeout", keyword=keyword, source_hint=source_hint, intervention=intervention)
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        reply_kind, local_reply = normalize_ambient_reply(local_reply, emoji_replacer=emoji_lib.replace_emoji)
        if reply_kind == "skip":
            logger.info(f"[ambient] judgment: SKIP (method={method})")
            await _broadcast_debug(f"[ambient/tier1] → SKIP")
            _ambient_listener.record_judgment(method=method, result="skip", keyword=keyword, source_hint=source_hint, intervention=intervention)
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        logger.info(f"[ambient/tier1] {reply_kind.upper()} '{local_reply[:60]}'")
        await _broadcast_debug(f"[ambient/tier1] → {reply_kind.upper()} '{local_reply[:40]}'")
        _ambient_listener.record_judgment(method=method, result="speak", keyword=keyword, utterance=local_reply, intervention=reply_kind, source_hint=source_hint)
        _ambient_listener.record_mei_utterance(local_reply)
        await _broadcast_ambient_log()
        _ambient_listener.record_llm_cooldown()

        try:
            # Pre-emptive echo suppression: set BEFORE TTS to prevent recapture
            _always_on_echo_suppress_until = time.time() + 3.0
            audio = await synthesize_speech(local_reply, mei_speaker, mei_speed)
            duration = _wav_duration(audio)
            payload = json.dumps({"type": "ambient_response", "text": local_reply, "method": method})
            sent = 0
            for client in list(_clients):
                try:
                    await client.send_text(payload)
                    await client.send_bytes(audio)
                    sent += 1
                except Exception:
                    _clients.discard(client)
            logger.info(f"[ambient/tier1] sent to {sent}/{len(_clients)+sent} clients (audio {len(audio)}bytes, {duration:.1f}s)")
            _always_on_echo_suppress_until = time.time() + max(3.0, duration + 2.0)
            asyncio.create_task(_emit_tts_diagnostic(local_reply, audio))
        except Exception as e:
            _always_on_echo_suppress_until = 0  # release on error
            logger.warning(f"[ambient/tier1] TTS error: {e}")
            payload = json.dumps({"type": "ambient_response", "text": local_reply, "method": method, "tts_fallback": True})
            for client in list(_clients):
                try:
                    await client.send_text(payload)
                except Exception:
                    _clients.discard(client)

        _ambient_listener.state = "listening"
        await _broadcast_ambient_state()

        # --- Tier 2: Claude follow-up for quality comment (if ambient model is claude) ---
        # Skip Tier 2 for instructions, short/trivial triggers, or non-claude mode
        _skip_tier2 = (
            ambient_model != "claude"
            or is_instruction
            or reply_kind == "backchannel"
            or len(trigger_text) < 10
        )
        if ambient_model != "claude":
            # Also handle tool routing for local-only mode
            needs_tool = bool(_TOOL_NEEDED_KEYWORDS.search(trigger_text))
            if needs_tool:
                logger.info(f"[ambient/tool_route] routing to Slack Bot: '{trigger_text[:50]}'")
                await _broadcast_debug(f"[ambient] tool routing → Slack Bot")
                speaker = _ambient_listener.current_speaker if _ambient_listener else None
                tool_reply = await _ask_slack_bot(trigger_text, speaker)
                if tool_reply:
                    await _ambient_broadcast_reply(tool_reply, "tool_route", method, keyword, mei_speaker, mei_speed)
                    return
                local_tool_reply = await _local_llm_with_tools_reply(trigger_text, local_model)
                if local_tool_reply and local_tool_reply != local_reply:
                    logger.info(f"[ambient/tool_route] local tool fallback used: '{local_tool_reply[:60]}'")
                    await _broadcast_debug(f"[ambient] local tool fallback")
                    await _ambient_broadcast_reply(local_tool_reply, "local_tool_fallback", method, keyword, mei_speaker, mei_speed)
            return
        if _skip_tier2:
            logger.info(f"[ambient/tier2] skipped (instruction={is_instruction}, reply_kind={reply_kind}, text_len={len(trigger_text)})")
            await _broadcast_debug(f"[ambient/tier2] → skipped")
            return

        # Claude tier 2: deeper follow-up
        # Build a prompt that asks for a quality comment, knowing the fast reply was already sent
        tier2_prompt = prompt + f"""

追加指示（Tier2 品質コメント）:
先ほど「{local_reply[:40]}」と短く返した。
もしこの会話トピックについて、もう少し面白い知識・視点・質問があれば、1-2文で追加コメントして。
追加する価値がなければ "SKIP" と返して。
先ほどの返答を繰り返さないこと。"""

        logger.info(f"[ambient/tier2] Claude follow-up starting")
        await _broadcast_debug(f"[ambient/tier2] Claude で品質コメント生成中...")
        try:
            speaker = _ambient_listener.current_speaker if _ambient_listener else None
            claude_reply = await asyncio.wait_for(
                _ask_slack_bot(trigger_text, speaker, system_prompt=tier2_prompt),
                timeout=60,
            )
            if not claude_reply or claude_reply.strip().upper() == "SKIP":
                logger.info(f"[ambient/tier2] Claude → SKIP (no follow-up needed)")
                await _broadcast_debug(f"[ambient/tier2] → SKIP")
                return
            # Strip stage directions (ト書き)
            claude_reply = re.sub(r'[（(][^）)]*[）)]', '', claude_reply).strip()
            if not claude_reply or claude_reply.strip().upper() == "SKIP":
                logger.info(f"[ambient/tier2] empty after stage-direction strip, treating as SKIP")
                return
            logger.info(f"[ambient/tier2] Claude follow-up: '{claude_reply[:60]}'")
            await _broadcast_debug(f"[ambient/tier2] → SPEAK '{claude_reply[:40]}'")
            _ambient_listener.record_mei_utterance(claude_reply)
            await _ambient_broadcast_reply(claude_reply, "tier2_claude", method, keyword, mei_speaker, mei_speed)
        except asyncio.TimeoutError:
            logger.warning(f"[ambient/tier2] Claude timeout (60s)")
            await _broadcast_debug(f"[ambient/tier2] TIMEOUT")
        except Exception as e:
            logger.warning(f"[ambient/tier2] Claude error: {e}")

    except Exception as e:
        logger.warning(f"[ambient] LLM error: {e}")
        if _ambient_listener:
            _ambient_listener.state = "listening"


async def _ambient_broadcast_reply(reply: str, reply_method: str, method: str, keyword: str,
                                    mei_speaker: str, mei_speed: float):
    """Broadcast an ambient reply (text + TTS) to all clients."""
    global _always_on_echo_suppress_until
    reply = emoji_lib.replace_emoji(reply, replace='').strip()
    if not reply:
        return
    _ambient_listener.record_judgment(method=reply_method, result="speak", keyword=keyword, utterance=reply)
    _ambient_listener.record_mei_utterance(reply)
    await _broadcast_ambient_log()
    _ambient_listener.record_llm_cooldown()
    try:
        _always_on_echo_suppress_until = time.time() + 3.0  # pre-emptive
        audio = await synthesize_speech(reply, mei_speaker, mei_speed)
        payload = json.dumps({"type": "ambient_response", "text": reply, "method": reply_method})
        for client in list(_clients):
            try:
                await client.send_text(payload)
                await client.send_bytes(audio)
            except Exception:
                _clients.discard(client)
        duration = _wav_duration(audio)
        _always_on_echo_suppress_until = time.time() + max(3.0, duration + 2.0)
        asyncio.create_task(_emit_tts_diagnostic(reply, audio))
    except Exception as e:
        _always_on_echo_suppress_until = 0
        logger.warning(f"[ambient/{reply_method}] TTS error: {e}")
        payload = json.dumps({"type": "ambient_response", "text": reply, "method": reply_method, "tts_fallback": True})
        for client in list(_clients):
            try:
                await client.send_text(payload)
            except Exception:
                _clients.discard(client)


async def _ambient_broadcast_text(text: str, ws: WebSocket):
    """Send a short text response (e.g., command ack) with TTS to all clients."""
    global _always_on_echo_suppress_until
    if not text:
        return
    mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
    mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
    mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
    try:
        audio = await synthesize_speech(text, mei_speaker, mei_speed)
        payload = json.dumps({"type": "ambient_response", "text": text, "method": "command"})
        for client in list(_clients):
            try:
                await client.send_text(payload)
                await client.send_bytes(audio)
            except Exception:
                _clients.discard(client)
        _always_on_echo_suppress_until = time.time() + 3.0
        asyncio.create_task(_emit_tts_diagnostic(text, audio))
    except Exception as e:
        logger.warning(f"[ambient] ack TTS error: {e}")


async def _broadcast_ambient_state():
    """Push ambient state to all connected clients."""
    if not _ambient_listener:
        return
    snap = _ambient_listener.get_state_snapshot()
    msg = json.dumps({"type": "ambient_state", "data": snap})
    for client in list(_clients):
        try:
            await client.send_text(msg)
        except Exception:
            _clients.discard(client)


async def _broadcast_ambient_log():
    """Push latest ambient log entry to all connected clients."""
    if not _ambient_listener or not _ambient_listener.log_entries:
        return
    entry = _ambient_listener.log_entries[-1]
    msg = json.dumps({"type": "ambient_log", "data": entry})
    for client in list(_clients):
        try:
            await client.send_text(msg)
        except Exception:
            _clients.discard(client)


async def _ambient_batch_loop():
    """Periodic LLM batch judgment for ambient audio."""
    logger.info("[ambient] batch loop started")
    while True:
        try:
            if not _ambient_listener or not _clients:
                await asyncio.sleep(5)
                continue

            interval = _ambient_listener.config["batch_interval_sec"]
            if interval <= 0:
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(interval)
            logger.info(f"[ambient] batch cycle: clients={len(_clients)} buffer={len(_ambient_listener.text_buffer)} cooldown={_ambient_listener.is_llm_in_cooldown()}")

            # Periodic state broadcast
            await _broadcast_ambient_state()

            if not _ambient_listener.text_buffer:
                continue
            if _ambient_listener.is_llm_in_cooldown():
                continue

            logger.info(f"[ambient] batch judgment ({len(_ambient_listener.text_buffer)} texts)")
            texts_preview = [e["text"][:30] for e in _ambient_listener.text_buffer[-3:]]
            await _broadcast_debug(f"[batch] {len(_ambient_listener.text_buffer)}件 → LLM: {texts_preview}")
            ws = next(iter(_clients), None)
            if ws:
                # Filter out media markers (※音楽, ♪, BGM etc.) before joining
                raw_texts = [e["text"] for e in _ambient_listener.text_buffer[-3:]]
                filtered_texts = [t for t in raw_texts if not re.match(r'^[※♪♫☆★]', t.strip())]
                if not filtered_texts:
                    logger.info(f"[ambient] batch all media markers, skipping")
                    _ambient_listener.flush_buffer()
                    continue
                trigger = " ".join(filtered_texts)
                await _ambient_llm_reply(ws, trigger, method="llm_batch")
                _ambient_listener.flush_buffer()
        except Exception as e:
            logger.warning(f"[ambient] batch loop error: {e}")
            await asyncio.sleep(5)


def _ensure_proactive_polling():
    """最初の WebSocket 接続時にポーリングタスクを開始"""
    global _proactive_task, _settings
    if _proactive_task is None or _proactive_task.done():
        _settings = _load_settings()
        _proactive_task = asyncio.create_task(_proactive_polling_loop())
        logger.info("Proactive polling started")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    logger.info(f"[WS] new connection. total: {len(_clients)}")
    _ensure_proactive_polling()

    # 接続時に現在の設定を送信
    _get_auto_approve_enabled()
    if _settings:
        await ws.send_json({"type": "sync_settings", "settings": _settings})

    # Send server status summary to debug panel
    if _settings.get("listeningDebug"):
        status_lines = []
        status_lines.append(f"Whisper large-v3: {'ready' if _whisper_model else 'not loaded'}")
        status_lines.append(f"Whisper small: {'ready' if _whisper_model_fast else 'not loaded'}")
        status_lines.append(f"Wake cache: {'ready' if _wake_cache.is_ready else 'warming up...'}")
        status_lines.append(f"Wait cache: {'ready' if _wait_cache.is_ready else 'warming up...'}")
        if _ambient_listener:
            status_lines.append(f"Ambient: {_ambient_listener.state}")
        await ws.send_json({"type": "listening_debug", "text": f"{_debug_ts()} [server] {' | '.join(status_lines)}"})

    raw_voice = _settings.get("voiceSelect", VOICEVOX_SPEAKER)
    speaker_id = int(raw_voice) if str(raw_voice).isdigit() else raw_voice
    _spd_raw = _settings.get("speedSelect", "auto") or "auto"
    speed = 0 if _spd_raw == "auto" else float(_spd_raw)
    model = _settings.get("modelSelect", "gemma4:e4b")
    slack_reply_bot = None  # None = 通常モード, "mei"/"eve" = Slack返信モード
    slack_reply_speaker = 2
    slack_reply_speed = 1.0
    conversation: list[dict] = [
        {"role": "system", "content": (
            "あなたはフレンドリーな日本語の会話アシスタントです。"
            "音声会話なので、簡潔に2-3文で返答してください。"
        )}
    ]

    try:
        while True:
            msg = await ws.receive()

            # テキストメッセージ = コマンド or テキストチャット
            if "text" in msg:
                data = json.loads(msg["text"])
                if data.get("type") == "set_speaker":
                    speaker_id = data["speaker_id"]
                    continue
                elif data.get("type") == "set_speed":
                    _sv2 = data["speed"] or "auto"
                    speed = 0 if _sv2 == "auto" else float(_sv2)
                    continue
                elif data.get("type") == "set_model":
                    model = data["model"]
                    continue
                elif data.get("type") == "update_settings":
                    # クライアントから設定変更 → 保存 & 他クライアントへブロードキャスト
                    _settings.update(data.get("settings", {}))
                    if "autoApproveEnabled" in data.get("settings", {}):
                        _sync_auto_approve_file(bool(_settings.get("autoApproveEnabled")))
                    _save_settings(_settings)
                    # サーバー側の変数も更新
                    if "voiceSelect" in data.get("settings", {}):
                        v = _settings["voiceSelect"]
                        speaker_id = int(v) if str(v).isdigit() else v
                    if "speedSelect" in data.get("settings", {}):
                        _sv = _settings["speedSelect"] or "auto"
                        speed = 0 if _sv == "auto" else float(_sv)
                    if "modelSelect" in data.get("settings", {}):
                        model = _settings["modelSelect"]
                    await _broadcast_settings(exclude=ws)
                    continue
                elif data.get("type") == "slack_reply":
                    slack_reply_bot = data.get("bot_id")
                    slack_reply_speaker = data.get("speaker_id", 2)
                    _srv = data.get("speed", "auto") or "auto"
                    slack_reply_speed = 0 if _srv == "auto" else float(_srv)
                    continue
                elif data.get("type") == "stop_audio":
                    # 全クライアントへブロードキャスト（送信元含む）
                    broadcast = json.dumps(data)
                    for client in list(_clients):
                        try:
                            await client.send_text(broadcast)
                        except Exception:
                            _clients.discard(client)
                    continue
                elif data.get("type") == "cancel_reply":
                    slack_reply_bot = None
                    continue
                elif data.get("type") == "start_guided_enrollment":
                    # Siri-style guided enrollment via WS
                    name = data.get("name", "").strip()
                    display_name = data.get("display_name", "").strip() or name
                    yomigana = data.get("yomigana", "").strip()
                    if name and _speaker_id and not _enrollment_active:
                        asyncio.create_task(_guided_enrollment(name, display_name, yomigana))
                        await ws.send_json({"type": "enroll_status", "ok": True, "message": f"Guided enrollment started"})
                    else:
                        await ws.send_json({"type": "enroll_status", "ok": False, "message": "Cannot start enrollment"})
                    continue
                elif data.get("type") == "enroll_audio":
                    # Voice enrollment: collect audio sample (manual mode)
                    audio_msg = await ws.receive()
                    if "bytes" not in audio_msg or not _speaker_id:
                        continue
                    result = _speaker_id.add_enrollment_sample(audio_msg["bytes"])
                    await ws.send_json({"type": "enroll_status", **result})
                    continue
                elif data.get("type") == "always_on_audio":
                    # Always-On mode: VAD-filtered audio from Electron
                    speech_ts = data.get("speech_ts")  # epoch ms from client
                    recv_ts = time.time()
                    if speech_ts:
                        logger.info(f"[always_on] audio received: spoke {(recv_ts - speech_ts/1000):.1f}s ago")
                    # Next binary message contains the audio data
                    audio_msg = await ws.receive()
                    if "bytes" not in audio_msg:
                        continue
                    audio_data = audio_msg["bytes"]

                    # Process in background task so WS handler keeps receiving
                    asyncio.create_task(_process_always_on(ws, audio_data, speech_ts=speech_ts))
                    continue
                elif data.get("type") == "barge_in":
                    logger.info("[barge-in] Client detected user speech during playback")
                    _always_on_echo_suppress_until = 0
                    for client in list(_clients):
                        try:
                            await client.send_json({"type": "stop_audio"})
                        except Exception:
                            _clients.discard(client)
                    continue
                elif data.get("type") == "text_message":
                    text = data.get("text", "").strip()
                    if not text:
                        continue
                    await ws.send_json({"type": "user_text", "text": text})
                else:
                    continue
            elif "bytes" in msg:
                # バイナリ = 音声データ → STT
                audio_data = msg["bytes"]
                await ws.send_json({"type": "status", "text": "文字起こし中..."})
                text = await transcribe(audio_data)
                if not text:
                    await ws.send_json({"type": "status", "text": "音声を認識できませんでした"})
                    continue
                await ws.send_json({"type": "user_text", "text": text})
            else:
                continue

            # Slack 返信モード
            if slack_reply_bot:
                bot_id = slack_reply_bot
                await ws.send_json({"type": "status", "text": f"Slack ({bot_id}) に送信中..."})
                ts = await slack_post_message(bot_id, text)
                if not ts:
                    await ws.send_json({"type": "assistant_text", "text": f"[Slack 送信失敗]"})
                    slack_reply_bot = None
                    await ws.send_json({"type": "reply_ended"})
                    continue

                await ws.send_json({"type": "status", "text": f"{bot_id} の返信を待っています..."})
                reply, reply_ts = await slack_poll_response(bot_id, ts, timeout=120)
                slack_reply_bot = None  # 1回で終了

                if not reply:
                    await ws.send_json({"type": "assistant_text", "text": f"[{bot_id} からの返信がタイムアウトしました]"})
                    await ws.send_json({"type": "reply_ended"})
                    continue

                # TTS
                await ws.send_json({"type": "status", "text": "音声生成中..."})
                try:
                    audio = await synthesize_speech(reply, slack_reply_speaker, slack_reply_speed)
                    await ws.send_json({"type": "assistant_text", "text": f"[{bot_id}] {reply}"})
                    await ws.send_bytes(audio)
                    asyncio.create_task(_emit_tts_diagnostic(reply, audio))
                except TTSQualityError as e:
                    print(f"TTS quality error: {e}")
                    await ws.send_json({"type": "assistant_text", "text": f"[{bot_id}] {reply}"})
                    await ws.send_json({"type": "status", "text": f"音声生成エラー: {e}"})
                except Exception as e:
                    print(f"TTS error: {e}")
                    await ws.send_json({"type": "assistant_text", "text": f"[{bot_id}] {reply}", "tts_fallback": True})
                await ws.send_json({"type": "reply_ended", "bot_id": bot_id, "reply_ts": reply_ts})
                continue

            # 通常モード: LLM
            await ws.send_json({"type": "status", "text": "考え中..."})
            conversation.append({"role": "user", "content": text})
            try:
                reply = await chat_with_llm(conversation, model)
            except Exception as e:
                conversation.pop()
                await ws.send_json({"type": "assistant_text", "text": f"[LLM エラー: {e}]"})
                continue
            conversation.append({"role": "assistant", "content": reply})

            # TTS (VOICEVOX)
            await ws.send_json({"type": "status", "text": "音声生成中..."})
            try:
                audio = await synthesize_speech(reply, speaker_id, speed)
                await ws.send_json({"type": "assistant_text", "text": reply})
                await ws.send_bytes(audio)
                asyncio.create_task(_emit_tts_diagnostic(reply, audio))
            except TTSQualityError as e:
                await ws.send_json({"type": "assistant_text", "text": reply})
                await ws.send_json({"type": "status", "text": f"音声生成エラー: {e}"})
            except Exception as e:
                await ws.send_json({"type": "assistant_text", "text": reply, "tts_fallback": True})

    except (WebSocketDisconnect, RuntimeError):
        _clients.discard(ws)
        logger.info(f"[WS] disconnected. total: {len(_clients)}")


async def _proactive_polling_loop():
    """サーバー側でプロアクティブメッセージをポーリングし、全クライアントへ配信"""
    global _always_on_echo_suppress_until
    while True:
        await asyncio.sleep(10)
        if not _settings.get("proactiveEnabled"):
            continue
        if not _clients:
            continue
        for bot_id in ["mei", "eve"]:
            try:
                since = _settings.get("lastSeen", {}).get(bot_id, "") or _last_seen_ts.get(bot_id, "")
                if since and not re.match(r"^\d+\.\d+$", since):
                    since = ""
                resp_data = await slack_new_messages(bot_id, since)
                messages = resp_data.get("messages", [])
                if not messages:
                    continue
                sorted_msgs = sorted(messages, key=lambda m: float(m["ts"]))
                engine = _settings.get(f"{bot_id}Engine", _settings.get("ttsEngine", "voicevox"))
                speaker = _settings.get(f"{bot_id}Voice", "2")
                speed = _settings.get(f"{bot_id}Speed", "1.0")
                # 最新メッセージだけ TTS（複数検知時の GPU 過負荷防止）
                latest_idx = len(sorted_msgs) - 1
                for i, msg_item in enumerate(sorted_msgs):
                    payload = json.dumps({
                        "type": "proactive_message",
                        "botId": bot_id,
                        "text": msg_item["text"],
                        "speaker": speaker,
                        "speed": speed,
                        "ts": msg_item["ts"],
                    })
                    audio_bytes: bytes | None = None
                    if i == latest_idx:
                        try:
                            _spd_p = speed or "auto"
                            audio_bytes = await synthesize_speech(msg_item["text"], speaker, 0 if _spd_p == "auto" else float(_spd_p), engine=engine)
                            logger.info(f"[proactive] TTS generated {len(audio_bytes)} bytes for {bot_id}")
                        except TTSQualityError as e:
                            logger.warning(f"[proactive] TTS quality error for {bot_id}: {e}")
                        except Exception as e:
                            logger.error(f"[proactive] TTS failed: {e}")
                    else:
                        logger.info(f"[proactive] skipping TTS for older msg ({i+1}/{len(sorted_msgs)}) {bot_id}")
                    active_clients = len(_clients)
                    sent_count = 0
                    for client in list(_clients):
                        try:
                            await client.send_text(payload)
                            if audio_bytes:
                                await client.send_bytes(audio_bytes)
                            sent_count += 1
                        except Exception as exc:
                            logger.error(f"[proactive] WS send failed: {exc}")
                            _clients.discard(client)
                    logger.info(f"[proactive] sent to {sent_count}/{active_clients} clients ({'audio+text' if audio_bytes else 'text only'})")
                    # Echo suppression for proactive TTS — shorter window since
                    # proactive is background; don't block user speech detection too long
                    if audio_bytes:
                        duration = _wav_duration(audio_bytes)
                        _always_on_echo_suppress_until = time.time() + min(8.0, duration + 1.0)
                        logger.info(f"[proactive] echo suppress for {min(8.0, duration + 1.0):.1f}s")
                    # lastSeen を更新
                    if "lastSeen" not in _settings:
                        _settings["lastSeen"] = {}
                    _settings["lastSeen"][bot_id] = msg_item["ts"]
                _save_settings(_settings)
            except Exception as e:
                logger.error(f"proactive poll {bot_id}: {e}")


async def _warmup_irodori():
    """起動時にダミー推論してGPUウォームアップ"""
    try:
        logger.info("[warmup] Irodori TTS warming up...")
        await _synthesize_irodori_unlocked("ウォームアップ", "irodori-bright-female", 20.0)
        logger.info("[warmup] Irodori TTS ready")
    except Exception as e:
        logger.warning(f"[warmup] Irodori TTS warmup failed (non-fatal): {e}")


@app.on_event("startup")
async def on_startup():
    global _settings
    _settings = _load_settings()
    _sync_auto_approve_file(_get_auto_approve_enabled())
    await _warmup_irodori()
    # Wire up synthesize_speech for wake_response module
    _wake_response_module.synthesize_speech = synthesize_speech
    # Warm up wake response cache with mei's voice settings
    _mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
    _mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
    _mei_speed = 0 if _mei_speed_raw == "auto" else float(_mei_speed_raw)
    try:
        await _broadcast_debug("[startup] Wake cache warming up...")
        await _wake_cache.warmup(speaker_id=_mei_speaker, speed=_mei_speed)
        logger.info(f"[startup] Wake response cache ready ({_wake_cache.is_ready})")
        await _broadcast_debug("[startup] Wake cache ready")
        await _broadcast_debug("[startup] Wait cache warming up...")
        await _wait_cache.warmup(speaker_id=_mei_speaker, speed=_mei_speed)
        logger.info(f"[startup] Wait response cache ready ({_wait_cache.is_ready})")
        await _broadcast_debug("[startup] Wait cache ready")
    except Exception as e:
        logger.warning(f"[startup] Wake/Wait response cache warmup failed: {e}")
        await _broadcast_debug(f"[startup] Cache warmup failed: {e}")

    # Initialize ambient listener
    global _ambient_listener, _ambient_batch_task
    _rules_path = Path(__file__).parent / "ambient_rules.json"
    _examples_path = Path(__file__).parent / "ambient_examples.json"
    _ambient_reactivity = _settings.get("ambient_reactivity", 3)
    _ambient_listener = AmbientListener(
        rules_path=_rules_path,
        examples_path=_examples_path,
        reactivity=_ambient_reactivity,
    )
    _ambient_listener.state = "listening"
    _ambient_batch_task = asyncio.create_task(_ambient_batch_loop())
    logger.info(f"[startup] Ambient listener ready (reactivity={_ambient_reactivity})")

    # Initialize speaker identification
    global _speaker_id
    _profiles_dir = Path(__file__).parent / "speaker_profiles"
    _speaker_id = SpeakerIdentifier(_profiles_dir)
    logger.info(f"[startup] Speaker ID ready ({len(_speaker_id.profiles)} profile(s))")


if __name__ == "__main__":
    get_whisper()
    get_whisper_fast()
    uvicorn.run(app, host="0.0.0.0", port=8767, access_log=False)
