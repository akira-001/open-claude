"""Ember Chat Web App - STT (Whisper) + LLM (Ollama) + TTS (VOICEVOX)"""
import asyncio
import json
import logging
import os
import re
import struct
import sys
import tempfile
import time
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


async def _broadcast_settings(exclude: WebSocket | None = None):
    msg = json.dumps({"type": "sync_settings", "settings": _settings})
    for client in list(_clients):
        if client is exclude:
            continue
        try:
            await client.send_text(msg)
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


class TTSQualityError(Exception):
    """TTS 生成結果が品質基準を満たさない場合の例外"""
    def __init__(self, message: str, duration: float, size: int, text_len: int):
        self.duration = duration
        self.size = size
        self.text_len = text_len
        super().__init__(message)


_YOMIGANA_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'Akira', re.IGNORECASE), 'あきら'),
]


def _clean_text_for_tts(text: str) -> str:
    """TTS 用テキスト前処理: URL・絵文字を除去し空行を整理、名前を読み仮名に変換"""
    text = re.sub(r'https?://\S+', '', text)
    text = emoji_lib.replace_emoji(text, replace='')
    text = re.sub(r'\n{3,}', '\n\n', text)
    for pattern, yomi in _YOMIGANA_MAP:
        if pattern.search(text):
            before = text
            text = pattern.sub(yomi, text)
            logger.info(f"[YOMIGANA] '{pattern.pattern}' -> '{yomi}' | before='{before[:60]}' | after='{text[:60]}'")
    return text.strip()


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


_MIN_DURATION_SEC = 3.0
_MIN_SIZE_BYTES = 50_000  # ~50KB
_MIN_TEXT_LEN_FOR_CHECK = 30  # 短いテキストはチェック不要


async def synthesize_speech(text: str, speaker_id: int | str, speed: float = 1.0, engine: str | None = None) -> bytes:
    """TTS エンジンでテキストを音声に変換（ロック内 double-check キャッシュ）"""
    text = _clean_text_for_tts(text)
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
_always_on_conversation: list[dict] = [
    {"role": "system", "content": "あなたはメイという名前のフレンドリーな日本語の会話アシスタントです。音声会話なので、簡潔に1-2文で返答してください。"}
]
_ambient_listener: AmbientListener | None = None
_ambient_batch_task: asyncio.Task | None = None
_speaker_id: SpeakerIdentifier | None = None
_enrollment_active: bool = False
_enrollment_queue: asyncio.Queue | None = None  # audio bytes queue for guided enrollment


async def _always_on_llm_reply(ws: WebSocket, text: str):
    """Process text through LLM and send TTS response."""
    global _always_on_echo_suppress_until, _always_on_conversation_until
    try:
        _always_on_conversation.append({"role": "user", "content": text})
        if len(_always_on_conversation) > 11:  # system + 5 turns
            _always_on_conversation[1:3] = []

        await ws.send_json({"type": "status", "text": "考え中..."})
        model = _settings.get("modelSelect", "gemma4:e4b")
        reply = await chat_with_llm(_always_on_conversation, model)
        _always_on_conversation.append({"role": "assistant", "content": reply})
        logger.info(f"[always_on] LLM reply: '{reply[:80]}'")
        if _ambient_listener:
            _ambient_listener.record_mei_utterance(reply)

        # TTS
        mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
        mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
        mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
        try:
            audio = await synthesize_speech(reply, mei_speaker, mei_speed)
            await ws.send_json({"type": "assistant_text", "text": reply})
            await ws.send_bytes(audio)
            duration = _wav_duration(audio)
            _always_on_echo_suppress_until = time.time() + max(4.0, duration + 2.0)
        except Exception as e:
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
            await ws.send_json({"type": "listening_debug", "text": f"{_debug_ts()} {info}"})
        except Exception:
            pass


async def _broadcast_debug(info: str):
    """Broadcast listening debug info to all clients."""
    if not _settings.get("listeningDebug"):
        return
    payload = json.dumps({"type": "listening_debug", "text": f"{_debug_ts()} {info}"})
    for client in list(_clients):
        try:
            await client.send_text(payload)
        except Exception:
            _clients.discard(client)


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

        if time.time() < _always_on_echo_suppress_until:
            return

        if _whisper_busy:
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

        # Log speaker identification and track for multi-speaker detection
        spk_name_global = None
        if speaker_result and speaker_result.get("speaker"):
            spk_name_global = speaker_result["display_name"]
            sim = speaker_result["similarity"]
            logger.info(f"[speaker_id] identified: {spk_name_global} (sim={sim:.3f}) | '{text[:40]}'")
        elif speaker_result:
            sim = speaker_result["similarity"]
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
        in_conversation = time.time() < _always_on_conversation_until
        wake_result = detect_wake_word(text)

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
            # Only send to LLM if remaining is a real question/request (>10 chars)
            # Short remainders like "聞こえる?" "起きてる?" are covered by wake response
            if remaining and len(remaining) > 10:
                await _always_on_llm_reply(ws, remaining)
        elif in_conversation:
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
    """Generate ambient response via LLM and broadcast to all clients."""
    global _always_on_echo_suppress_until
    if not _ambient_listener:
        return
    try:
        _ambient_listener.state = "processing"
        source_hint = _ambient_listener.classify_source(trigger_text)
        logger.info(f"[ambient] source: {source_hint} | '{trigger_text[:40]}'")
        source_label = {"user_response": "User(応答)", "user_initiative": "User(呼びかけ)",
                        "user_likely": "User(推定)", "user_identified": "User(声紋)",
                        "media_likely": "Media(TV等)", "unknown": "不明"}.get(source_hint, source_hint)
        await _broadcast_debug(f"[ambient LLM] method={method} source={source_label} text='{trigger_text[:50]}'")
        prompt = _ambient_listener.build_llm_prompt(source_hint=source_hint)
        model = _settings.get("modelSelect", "gemma4:e4b")
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"直近の発話: {trigger_text}"},
        ]
        try:
            logger.info(f"[ambient] LLM request starting (model={model})")
            reply = await asyncio.wait_for(chat_with_llm(messages, model), timeout=60)
            logger.info(f"[ambient] LLM response received ({len(reply)} chars)")
        except asyncio.TimeoutError:
            logger.warning(f"[ambient] LLM timeout (60s), skipping")
            await _broadcast_debug(f"[ambient LLM] TIMEOUT (60s)")
            _ambient_listener.record_judgment(method=method, result="timeout", keyword=keyword)
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        if reply.strip().upper() == "SKIP":
            logger.info(f"[ambient] judgment: SKIP (method={method}, keyword={keyword})")
            await _broadcast_debug(f"[ambient LLM] → SKIP")
            _ambient_listener.record_judgment(method=method, result="skip", keyword=keyword)
            await _broadcast_ambient_log()
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        logger.info(f"[ambient] judgment: SPEAK '{reply[:60]}' (method={method})")
        await _broadcast_debug(f"[ambient LLM] → SPEAK '{reply[:40]}'")
        _ambient_listener.record_judgment(method=method, result="speak", keyword=keyword, utterance=reply)
        _ambient_listener.record_mei_utterance(reply)
        await _broadcast_ambient_log()
        _ambient_listener.record_llm_cooldown()

        mei_speaker = _settings.get("meiVoice", "irodori-lora-emilia")
        mei_speed_raw = _settings.get("meiSpeed", "auto") or "auto"
        mei_speed = 0 if mei_speed_raw == "auto" else float(mei_speed_raw)
        try:
            audio = await synthesize_speech(reply, mei_speaker, mei_speed)
            payload = json.dumps({"type": "ambient_response", "text": reply, "method": method})
            for client in list(_clients):
                try:
                    await client.send_text(payload)
                    await client.send_bytes(audio)
                except Exception:
                    _clients.discard(client)
            duration = _wav_duration(audio)
            _always_on_echo_suppress_until = time.time() + max(4.0, duration + 2.0)
        except Exception as e:
            logger.warning(f"[ambient] TTS error: {e}")
            payload = json.dumps({"type": "ambient_response", "text": reply, "method": method, "tts_fallback": True})
            for client in list(_clients):
                try:
                    await client.send_text(payload)
                except Exception:
                    _clients.discard(client)

        _ambient_listener.state = "listening"
        await _broadcast_ambient_state()
    except Exception as e:
        logger.warning(f"[ambient] LLM error: {e}")
        if _ambient_listener:
            _ambient_listener.state = "listening"


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
                trigger = " ".join(e["text"] for e in _ambient_listener.text_buffer[-3:])
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
        await _wake_cache.warmup(speaker_id=_mei_speaker, speed=_mei_speed)
        logger.info(f"[startup] Wake response cache ready ({_wake_cache.is_ready})")
    except Exception as e:
        logger.warning(f"[startup] Wake response cache warmup failed: {e}")

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
    uvicorn.run(app, host="0.0.0.0", port=8767)
