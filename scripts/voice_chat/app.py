"""Ember Chat Web App - STT (Whisper) + LLM (Ollama) + TTS (VOICEVOX)"""
import asyncio
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

# --- Shared settings (cross-browser sync) ---
SETTINGS_FILE = Path(__file__).parent / "settings.json"
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
            initial_prompt="ねぇメイ、メイ、今日のスケジュールは？",
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
            initial_prompt="ねぇメイ、メイ、今日のスケジュールは？",
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


async def _correct_stt_text(text: str, context_texts: list[str] | None = None) -> str:
    """Whisper STT の誤認識を補正。2段構成:
    1. 辞書ベース高速置換（レイテンシゼロ）
    2. LLM 補正（辞書で直らなかった未知の誤認識用）
    """
    # 短すぎる / 明らかに補正不要なテキストはスキップ
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


# ---------------------------------------------------------------------------
# Co-view (Listening mode) — MediaContext + constants
# ---------------------------------------------------------------------------

_CO_VIEW_COMMENT_COOLDOWN   = 300    # 5分: コメント間隔
_CO_VIEW_INFERENCE_MIN_SNIP = 3      # 推論トリガーに必要な最低スニペット数
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
    confidence: float = 0.0
    enriched_info: str = ""
    keywords: list = field(default_factory=list)
    last_inferred_at: float = 0.0
    last_enriched_at: float = 0.0
    co_view_last_at: float = 0.0
    ask_user_last_at: float = 0.0
    snippets_since_infer: int = 0

    def add_snippet(self, text: str):
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
        self.confidence = 0.0
        self.enriched_info = ""
        self.keywords.clear()
        self.snippets_since_infer = 0


_media_ctx = _MediaContext()

# TV guide cache
_tv_guide_cache: dict = {"data": "", "fetched_at": 0.0}


def _load_youtube_titles() -> list:
    try:
        data = json.loads((_SLACK_BOT_DATA_DIR / "youtube-history-cache.json").read_text())
        return [e["title"] for e in data.get("entries", []) if e.get("title")]
    except Exception:
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
    words = set(re.findall(r'[^\s、。！？!?]{2,}', buffer_text))
    scored = []
    for title in _youtube_titles:
        score = sum(1 for w in words if w in title)
        if score > 0:
            scored.append((score, title))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:top_n]]


async def _fetch_tv_guide() -> str:
    """NHK RSS + Google News でTV番組表を取得（1時間キャッシュ）。"""
    now = time.time()
    if now - _tv_guide_cache["fetched_at"] < 3600 and _tv_guide_cache["data"]:
        return _tv_guide_cache["data"]
    results: list = []
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            # Google News で今日のTV・番組情報
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


# ---------------------------------------------------------------------------
# Co-view async functions
# ---------------------------------------------------------------------------

_YT_AD_NARRATION = re.compile(
    r'(続きはチャットで確認|チャットで確認してね|次はチャット|チャットで確認|'
    r'詳しくはこちら|今すぐダウンロード|今すぐ登録|無料で始め|アプリをダウンロード|'
    r'リンクは概要欄)',
)


async def _correct_media_transcript(text: str) -> str:
    """メディア音声(実況・YouTubeなど)向けSTT補正。"""
    text = _YT_AD_NARRATION.sub('', text).strip()
    if not text:
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
            if len(corrected) > len(text) * 3:
                logger.info(f"[co_view/stt] hallucination(3x): '{text}'({len(text)}) → '{corrected}'({len(corrected)}) → keep original")
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
        return {"content_type": "unknown", "topic": "", "keywords": [], "confidence": 0.0}

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

    tv_guide = await _fetch_tv_guide()
    tv_hint = f"\n\nTV番組表(参考):\n{tv_guide[:300]}" if tv_guide else ""

    messages = [
        {"role": "system", "content": (
            "あなたはメディアコンテンツ分析者です。音声認識テキストから視聴コンテンツを推測してください。\n"
            "以下のJSONのみ返してください。余分なテキスト不要。\n"
            '{"content_type":"baseball|golf|youtube_talk|news|drama|music|other|unknown",'
            '"topic":"具体的なトピック(例:ドジャースvsパドレス)",'
            '"keywords":["検索キーワード1","キーワード2"],'
            '"matched_title":"一致したYouTubeタイトル(なければ空文字)",'
            '"confidence":0.0から1.0}\n\n'
            "注意: 野球実況(特にドジャース)はconfidence高め。ゴルフ(マスターズ等)はgolf。"
            "音楽BGMのみはconfidence低め。材料不足は0.3以下。"
            f"{yt_hint}{interest_hint}{tv_hint}"
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
        logger.info(f"[co_view/infer] type={result.get('content_type')} topic='{result.get('topic')}' conf={result.get('confidence')}")
        return result
    except Exception as e:
        logger.warning(f"[co_view/infer] failed: {e}")
        return {"content_type": "unknown", "topic": "", "keywords": [], "confidence": 0.0}


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

            if _media_ctx.inferred_topic and content_type not in ("music", "unknown"):
                wiki = await _tool_wikipedia_summary(_media_ctx.inferred_topic)
                if wiki:
                    results.append(wiki)

            if not results and keywords:
                query = "+".join(keywords[:2])
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall('.//item')[:2]:
                        title = item.findtext('title', '')
                        if title:
                            results.append(f"関連: {title}")
    except Exception as e:
        logger.warning(f"[co_view/enrich] failed: {e}")

    enriched = "\n".join(results)
    _media_ctx.enriched_info = enriched
    _media_ctx.last_enriched_at = now
    logger.info(f"[co_view/enrich] {len(results)} results")
    return enriched


async def _handle_co_view(ws, trigger_text: str, method: str, keyword: str):
    """co_view モード: メディア音声を蓄積→コンテンツ推測→外部補完→コメント生成。"""
    if not _ambient_listener:
        return
    now = time.time()

    # Step 1: 補正してバッファに追加
    corrected = await _correct_media_transcript(trigger_text)
    if not corrected:
        return
    _media_ctx.add_snippet(corrected)
    await _broadcast_debug(f"[co_view] buf={len(_media_ctx.media_buffer)} '{corrected[:40]}'")

    # メディアが5分以上途切れていたらコンテキストリセット
    if len(_media_ctx.media_buffer) >= 2:
        if now - _media_ctx.media_buffer[-2]["ts"] > 300:
            logger.info("[co_view] 5min gap → reset context")
            _media_ctx.reset()
            _media_ctx.add_snippet(corrected)

    # Step 2: コメントクールダウンチェック
    if now - _media_ctx.co_view_last_at < _CO_VIEW_COMMENT_COOLDOWN:
        remaining = int(_CO_VIEW_COMMENT_COOLDOWN - (now - _media_ctx.co_view_last_at))
        await _broadcast_debug(f"[co_view] cooldown {remaining}s")
        return

    # Step 3: コンテンツ推論 (新スニペットが閾値以上の時だけ)
    if _media_ctx.snippets_since_infer >= _CO_VIEW_INFERENCE_MIN_SNIP:
        inferred = await _infer_media_content()
        _media_ctx.inferred_type  = inferred.get("content_type", "unknown")
        _media_ctx.inferred_topic = inferred.get("topic", "")
        _media_ctx.confidence     = float(inferred.get("confidence", 0.0))
        _media_ctx.keywords       = inferred.get("keywords", [])
        _media_ctx.last_inferred_at = now
        _media_ctx.snippets_since_infer = 0
        await _broadcast_debug(
            f"[co_view] inferred: {_media_ctx.inferred_type} "
            f"'{_media_ctx.inferred_topic}' conf={_media_ctx.confidence:.2f}"
        )

    # Step 4: 低信頼度 → ユーザーに聞くか、蓄積継続
    if _media_ctx.confidence < 0.4:
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

    # Step 5: 外部情報を取得（コメント生成には使わず、reply時の参照用のみキャッシュ）
    await _enrich_media_context()

    # Step 6: Claude でコメント生成（enriched dataは渡さない — 報告調になるため）
    buffer_text = _media_ctx.get_buffer_text(last_n=5)
    system_prompt = (
        "あなたはMEI。Akiraさんの同居人として、一緒にテレビ/YouTubeを見ている。\n"
        f"視聴中: {_media_ctx.inferred_type} — {_media_ctx.inferred_topic}\n"
        f"\n最近の音声:\n{buffer_text}\n"
    )
    if _media_ctx.inferred_type == "baseball":
        system_prompt += "\nAkiraさんはドジャースの大ファン。試合展開・選手プレー・スコアに自然にリアクション。\n"
    elif _media_ctx.inferred_type == "golf":
        system_prompt += "\nゴルフ観戦中。ショットや選手の動きに自然にリアクション。\n"
    system_prompt += (
        "\n指示:\n"
        "- 一緒に見ている同居人として、自然な1-2文のコメント\n"
        "- 例: 「お、大谷打った！」「このYouTuber面白いね」「へー、そうなんだ」\n"
        "- 解説・情報提供ではなく感想・リアクション・共感を\n"
        "- 疑問文で終わらせない。一緒に見ているので内容は知っている前提。「〜見てるの？」「〜ってどういうこと？」はNG\n"
        "- 声に出す言葉だけ。ト書き・括弧付き説明は禁止\n"
        "- コメントする価値がなければ \"SKIP\" と返す\n"
    )

    try:
        speaker = _ambient_listener.current_speaker if _ambient_listener else None
        co_reply = await asyncio.wait_for(
            _ask_slack_bot(
                f"視聴中のコンテンツにコメントして: {_media_ctx.inferred_topic}\n音声: {buffer_text[:200]}",
                speaker,
                system_prompt=system_prompt,
            ),
            timeout=30,
        )
        if not co_reply or co_reply.strip().upper() == "SKIP":
            await _broadcast_debug("[co_view] → SKIP")
            return

        co_reply = re.sub(r'[（(][^）)]*[）)]', '', co_reply).strip()
        if not co_reply or co_reply.strip().upper() == "SKIP":
            return

        logger.info(f"[co_view] comment: '{co_reply[:60]}'")
        mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
        mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
        mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
        await _ambient_broadcast_reply(co_reply, "co_view", method, keyword, mei_speaker, mei_speed)
        _media_ctx.co_view_last_at = now

    except asyncio.TimeoutError:
        logger.warning("[co_view] Claude timeout (30s)")
        await _broadcast_debug("[co_view] TIMEOUT")
    except Exception as e:
        logger.warning(f"[co_view] error: {e}")


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
    return _settings


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


@app.post("/api/improve_loop/run")
async def improve_loop_run():
    """co_view改善ループ: cmux右ペインYouTubeを正解ラベルとして精度を評価しSlackに投稿。

    正解ラベル取得: cmux browser snapshot (テスト・改善ループ専用)
    通常運用: iPad/TVからの外部音声に依存 → このパスは使わない
    """
    import subprocess, datetime
    now_str = datetime.datetime.now().strftime("%H:%M")

    try:
        # 1. cmux右ペインのYouTubeタイトルを正解ラベルとして取得
        ground_truth = ""
        try:
            gt_result = subprocess.run(
                ["cmux", "browser", "snapshot", "--surface", "surface:32"],
                capture_output=True, text=True, timeout=10
            )
            for line in gt_result.stdout.splitlines():
                if "document" in line and "YouTube" in line:
                    # 'document "タイトル - YouTube"' からタイトル抽出
                    import re as _re
                    m = _re.search(r'document "(.+?) - YouTube"', line)
                    if m:
                        ground_truth = m.group(1)
                        break
        except Exception as e:
            logger.debug(f"[improve_loop] cmux snapshot failed: {e}")

        # 2. 直近co_viewログ取得
        log_result = subprocess.run(
            ["grep", "-E", r"\[co_view\]|\[co_view/infer\]|\[co_view/stt\]",
             "/tmp/whisper-serve.log"],
            capture_output=True, text=True, timeout=5
        )
        lines = log_result.stdout.strip().splitlines()[-30:] if log_result.stdout else []
        log_summary = "\n".join(lines) if lines else "(ログなし)"

        # 3. 現在の推論結果と正解を比較
        inferred = f"{_media_ctx.inferred_type} / {_media_ctx.inferred_topic} (conf={_media_ctx.confidence:.2f})"
        accuracy = ""
        if ground_truth and _media_ctx.inferred_topic:
            accuracy = f"\n\n🎯 精度確認:\n正解: {ground_truth}\n推論: {inferred}"
        elif ground_truth:
            accuracy = f"\n\n🎯 正解ラベル: {ground_truth}\n推論: 未取得"

        # 4. Slackに投稿
        slack_text = (
            f"🎬 co_view 改善ループ [{now_str}]{accuracy}\n\n"
            f"📋 直近ログ:\n```\n{log_summary[:600]}\n```\n\n"
            f"改善案があれば 👍 で適用します。"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            slack_token = os.getenv("SLACK_BOT_TOKEN", "")
            if slack_token:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    json={"channel": "C0AP2BD5HBJ", "text": slack_text}
                )
                logger.info(f"[improve_loop] posted. ground_truth='{ground_truth}' inferred='{_media_ctx.inferred_type}'")
        return {"ok": True, "ground_truth": ground_truth}
    except Exception as e:
        logger.warning(f"[improve_loop] failed: {e}")
        return {"ok": False, "error": str(e)}


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
                if _TOOL_ROUTE_FAIL_COUNT >= _TOOL_ROUTE_FAIL_THRESHOLD:
                    _TOOL_ROUTE_COOLDOWN_UNTIL = time.time() + _TOOL_ROUTE_COOLDOWN_SEC
                    logger.warning(
                        f"[tool_route] Slack Bot error: {data.get('error')} "
                        f"(cooldown {_TOOL_ROUTE_COOLDOWN_SEC:.0f}s)"
                    )
                else:
                    logger.warning(f"[tool_route] Slack Bot error: {data.get('error')}")
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
        if _media_ctx.confidence >= 0.4 and _media_ctx.media_buffer:
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
