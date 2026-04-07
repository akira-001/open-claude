"""Ember Chat Web App - STT (Whisper) + LLM (Ollama) + TTS (VOICEVOX)"""
import asyncio
import json
import os
import struct
import tempfile
import time
from pathlib import Path

import emoji as emoji_lib
import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

from faster_whisper import WhisperModel

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI()

_tts_locks: dict[str, asyncio.Lock] = {}

def _get_tts_lock(engine: str) -> asyncio.Lock:
    if engine not in _tts_locks:
        _tts_locks[engine] = asyncio.Lock()
    return _tts_locks[engine]

# TTS 結果の短期キャッシュ（重複リクエスト防止）
_tts_cache: dict[str, tuple[float, bytes]] = {}
_TTS_CACHE_TTL = 30  # seconds

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


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        print("Whisper large-v3 読み込み中...")
        _whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        print("Whisper 準備完了")
    return _whisper_model


async def transcribe(audio_bytes: bytes) -> str:
    """音声バイト列をテキストに変換"""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        model = get_whisper()
        segments, info = model.transcribe(f.name, language="ja", beam_size=5)
        text = "".join(seg.text for seg in segments).strip()
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
            print(f"[YOMIGANA] '{pattern.pattern}' -> '{yomi}' | before='{before[:60]}' | after='{text[:60]}'")
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
    cache_key = f"{tts_engine}:{speaker_id}:{speed}:{text}"
    now = time.time()
    cached = _tts_cache.get(cache_key)
    if cached and now - cached[0] < _TTS_CACHE_TTL:
        print(f"[synthesize_speech] cache hit, engine={tts_engine}, speaker_id={speaker_id}")
        return cached[1]
    lock = _get_tts_lock(tts_engine)
    async with lock:
        now = time.time()
        cached = _tts_cache.get(cache_key)
        if cached and now - cached[0] < _TTS_CACHE_TTL:
            print(f"[synthesize_speech] cache hit (after lock), engine={tts_engine}, speaker_id={speaker_id}")
            return cached[1]
        print(f"[synthesize_speech] engine={tts_engine}, speaker_id={speaker_id}, speed={speed}")
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
                print(f"[TTS QUALITY ERROR] duration={duration:.1f}s, size={len(audio)} bytes, text_len={len(text)}, engine={tts_engine}, speaker={speaker_id}")
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
        print(f"[IRODORI TTS LoRA] voice_id={voice_id}, num_steps={num_steps}, text_len={len(text)}")
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

    print(f"[IRODORI TTS] voice_id={voice_id}, speed={speed}, num_steps={num_steps}, caption={caption[:30]}..., text_len={len(text)}")

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
    print(f"[GPT-SoVITS] voice_id={voice_id}, ref={ref_audio}, text_len={len(text)}")
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
    spd = 0 if speed == "auto" else float(speed)
    audio = await synthesize_speech(text, speaker, spd)
    return Response(content=audio, media_type="audio/wav")


import re


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
    spd = 0 if speed == "auto" else float(speed)
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
    spd = 0 if speed == "auto" else float(speed)
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


@app.get("/")
async def index():
    html = (Path(__file__).parent / "index.html").read_text()
    return HTMLResponse(html)


_proactive_task: asyncio.Task | None = None


def _ensure_proactive_polling():
    """最初の WebSocket 接続時にポーリングタスクを開始"""
    global _proactive_task, _settings
    if _proactive_task is None or _proactive_task.done():
        _settings = _load_settings()
        _proactive_task = asyncio.create_task(_proactive_polling_loop())
        print("Proactive polling started")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    print(f"[WS] new connection. total: {len(_clients)}")
    _ensure_proactive_polling()

    # 接続時に現在の設定を送信
    if _settings:
        await ws.send_json({"type": "sync_settings", "settings": _settings})

    raw_voice = _settings.get("voiceSelect", VOICEVOX_SPEAKER)
    speaker_id = int(raw_voice) if str(raw_voice).isdigit() else raw_voice
    _spd_raw = _settings.get("speedSelect", "auto")
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
                    _sv2 = data["speed"]
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
                        _sv = _settings["speedSelect"]
                        speed = 0 if _sv == "auto" else float(_sv)
                    if "modelSelect" in data.get("settings", {}):
                        model = _settings["modelSelect"]
                    await _broadcast_settings(exclude=ws)
                    continue
                elif data.get("type") == "slack_reply":
                    slack_reply_bot = data.get("bot_id")
                    slack_reply_speaker = data.get("speaker_id", 2)
                    _srv = data.get("speed", "auto")
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

    except WebSocketDisconnect:
        _clients.discard(ws)
        print(f"[WS] disconnected. total: {len(_clients)}")


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
                            audio_bytes = await synthesize_speech(msg_item["text"], speaker, 0 if speed == "auto" else float(speed), engine=engine)
                            print(f"[proactive] TTS generated {len(audio_bytes)} bytes for {bot_id}")
                        except TTSQualityError as e:
                            print(f"[proactive] TTS quality error for {bot_id}: {e}")
                        except Exception as e:
                            print(f"[proactive] TTS failed: {e}")
                    else:
                        print(f"[proactive] skipping TTS for older msg ({i+1}/{len(sorted_msgs)}) {bot_id}")
                    active_clients = len(_clients)
                    sent_count = 0
                    for client in list(_clients):
                        try:
                            await client.send_text(payload)
                            if audio_bytes:
                                await client.send_bytes(audio_bytes)
                            sent_count += 1
                        except Exception as exc:
                            print(f"[proactive] WS send failed: {exc}")
                            _clients.discard(client)
                    print(f"[proactive] sent to {sent_count}/{active_clients} clients ({'audio+text' if audio_bytes else 'text only'})")
                    # lastSeen を更新
                    if "lastSeen" not in _settings:
                        _settings["lastSeen"] = {}
                    _settings["lastSeen"][bot_id] = msg_item["ts"]
                _save_settings(_settings)
            except Exception as e:
                print(f"proactive poll {bot_id}: {e}")


async def _warmup_irodori():
    """起動時にダミー推論してGPUウォームアップ"""
    try:
        print("[warmup] Irodori TTS warming up...")
        await _synthesize_irodori_unlocked("ウォームアップ", "irodori-bright-female", 20.0)
        print("[warmup] Irodori TTS ready")
    except Exception as e:
        print(f"[warmup] Irodori TTS warmup failed (non-fatal): {e}")


@app.on_event("startup")
async def on_startup():
    await _warmup_irodori()


if __name__ == "__main__":
    get_whisper()
    uvicorn.run(app, host="0.0.0.0", port=8767)
