"""Ambient Reactive Response engine — keyword + LLM batch hybrid judgment."""
import json
import re
import time
import uuid
from datetime import datetime, date
from pathlib import Path


REACTIVITY_CONFIG = {
    1: {"label": "静か",    "batch_interval_sec": 0,   "keyword_ratio": 0.0, "cooldown_multiplier": 3.0},
    2: {"label": "控えめ",  "batch_interval_sec": 120, "keyword_ratio": 0.5, "cooldown_multiplier": 1.5},
    3: {"label": "普通",    "batch_interval_sec": 30,  "keyword_ratio": 1.0, "cooldown_multiplier": 1.0},
    4: {"label": "積極的",  "batch_interval_sec": 15,  "keyword_ratio": 1.0, "cooldown_multiplier": 0.7},
    5: {"label": "おしゃべり", "batch_interval_sec": 10, "keyword_ratio": 1.0, "cooldown_multiplier": 0.5},
}

_BASE_KEYWORD_COOLDOWN = 60  # seconds
_BASE_LLM_COOLDOWN = 30     # seconds (90sでは長すぎて返答なしが頻発)


class AmbientListener:
    def __init__(self, rules_path: Path, examples_path: Path, reactivity: int = 3):
        self.rules_path = Path(rules_path)
        self.examples_path = Path(examples_path)
        self.reactivity = max(1, min(5, reactivity))
        self.override_level: int | None = None
        self.override_expires_at: float = 0
        self.override_trigger: str = ""
        self.state: str = "idle"  # idle, listening, processing

        # Data
        self.rules: dict = self._load_json(self.rules_path, {"rules": [], "keywords": []})
        self.examples: dict = self._load_json(self.examples_path, {"examples": []})
        self._compiled_keywords: list[dict] = []
        self._compile_keywords()

        # Buffers
        self.text_buffer: list[dict] = []  # [{"text": str, "ts": float}]
        self._recent_text_signatures: dict[str, float] = {}
        self.last_buffer_reject_reason: str = ""

        # MEI's last utterance tracking (for source classification)
        self.last_mei_utterance: str = ""
        self.last_mei_spoke_at: float = 0

        # Media context: if recent classification was media, carry forward
        self._last_source: str = "unknown"
        self._last_source_at: float = 0

        # Speaker identity (set by app.py from speaker_id module)
        self.current_speaker: str | None = None  # display name or None

        # Multi-speaker conversation tracking
        self._recent_speakers: list[dict] = []  # [{"speaker": str|None, "ts": float}]

        # Cooldowns: category -> expires_at
        self._keyword_cooldowns: dict[str, float] = {}
        self._llm_cooldown_until: float = 0

        # Stats (daily)
        self._stats_date: str = date.today().isoformat()
        self._judgments: int = 0
        self._speaks: int = 0
        self._feedback_positive: int = 0
        self._feedback_negative: int = 0

        # Log buffer for dashboard (last 20)
        self.log_entries: list[dict] = []

    @staticmethod
    def _load_json(path: Path, default: dict) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return default

    def _save_rules(self):
        self.rules_path.write_text(json.dumps(self.rules, ensure_ascii=False, indent=2))

    def _save_examples(self):
        self.examples_path.write_text(json.dumps(self.examples, ensure_ascii=False, indent=2))

    def _compile_keywords(self):
        self._compiled_keywords = []
        for kw in self.rules.get("keywords", []):
            if kw.get("enabled", True):
                try:
                    self._compiled_keywords.append({
                        **kw,
                        "_re": re.compile(kw["pattern"]),
                    })
                except re.error:
                    pass

    # --- Reactivity ---

    def set_reactivity(self, level: int):
        self.reactivity = max(1, min(5, level))

    def apply_override(self, level_delta: int, duration_sec: int, trigger: str = ""):
        target = self.reactivity + level_delta
        self.override_level = max(1, min(5, target))
        self.override_expires_at = time.time() + duration_sec
        self.override_trigger = trigger

    def clear_override(self):
        self.override_level = None
        self.override_expires_at = 0
        self.override_trigger = ""

    @property
    def effective_reactivity(self) -> int:
        if self.override_level is not None and time.time() < self.override_expires_at:
            return self.override_level
        if self.override_level is not None:
            self.clear_override()
        return self.reactivity

    @property
    def config(self) -> dict:
        return REACTIVITY_CONFIG[self.effective_reactivity]

    # --- Keyword Detection ---

    def check_keywords(self, text: str) -> dict | None:
        ratio = self.config["keyword_ratio"]
        if ratio <= 0:
            return None

        now = time.time()
        for i, kw in enumerate(self._compiled_keywords):
            # Apply ratio: skip keywords based on index
            if ratio < 1.0 and (i % int(1 / ratio)) != 0:
                continue

            # Cooldown check
            category = kw["category"]
            if now < self._keyword_cooldowns.get(category, 0):
                continue

            if kw["_re"].search(text):
                return {"category": category, "keyword": kw["pattern"], "id": kw["id"]}

        return None

    def record_cooldown(self, category: str):
        multiplier = self.config["cooldown_multiplier"]
        self._keyword_cooldowns[category] = time.time() + _BASE_KEYWORD_COOLDOWN * multiplier

    def record_llm_cooldown(self):
        multiplier = self.config["cooldown_multiplier"]
        self._llm_cooldown_until = time.time() + _BASE_LLM_COOLDOWN * multiplier

    def is_llm_in_cooldown(self) -> bool:
        return time.time() < self._llm_cooldown_until

    # --- MEI utterance tracking ---

    def record_mei_utterance(self, text: str):
        self.last_mei_utterance = text
        self.last_mei_spoke_at = time.time()

    @property
    def mei_spoke_ago(self) -> float:
        if self.last_mei_spoke_at == 0:
            return 9999
        return time.time() - self.last_mei_spoke_at

    # --- Speaker Tracking ---

    def record_speaker(self, speaker: str | None):
        """Track recent speakers to detect multi-person conversations."""
        now = time.time()
        self._recent_speakers.append({"speaker": speaker, "ts": now})
        # Keep only last 60 seconds
        self._recent_speakers = [s for s in self._recent_speakers if now - s["ts"] < 60]

    @property
    def is_multi_speaker(self) -> bool:
        """True if multiple distinct speakers detected in last 60s."""
        now = time.time()
        recent = [s for s in self._recent_speakers if now - s["ts"] < 60]
        speakers = set()
        for s in recent:
            speakers.add(s["speaker"] or "__unknown__")
        return len(speakers) >= 2

    @property
    def recent_speaker_names(self) -> list[str]:
        """Names of speakers in last 60s (None becomes '不明')."""
        now = time.time()
        recent = [s for s in self._recent_speakers if now - s["ts"] < 60]
        seen = set()
        names = []
        for s in recent:
            name = s["speaker"] or "不明"
            if name not in seen:
                seen.add(name)
                names.append(name)
        return names

    # --- Source Classification ---

    _USER_CALL_RE = re.compile(r'メイ|ねえ|ねぇ|ちょっと')
    _USER_QUESTION_RE = re.compile(r'[？?]$|して$|かな$|だよね$|よね$|だろ$|かも$|けど$|のに$')
    _MEDIA_HINT_RE = re.compile(
        r'ご視聴|チャンネル登録|高評価|字幕|※|この動画|'
        r'スポンサー|提供|CM|コマーシャル|次回予告|'
        r'お届けし|番組|放送|ニュース速報'
    )

    @property
    def _in_media_context(self) -> bool:
        """Recent classification was media → carry forward for 5 minutes.
        5min covers the gap between YouTube segments (5min gap reset)."""
        return (self._last_source == "media_likely"
                and time.time() - self._last_source_at < 300)

    def classify_source(self, text: str) -> str:
        """Classify whether the text is from user or media.

        Returns one of: user_response, user_initiative, user_likely,
                        user_identified, user_in_conversation, fragmentary,
                        media_likely, unknown
        """
        result = self._classify_source_inner(text)
        self._last_source = result
        # _last_source_at は media_likely 確定時のみ更新する。
        # 毎回更新すると _in_media_context の 5分タイマーが永久伸長して
        # ロックから脱出不能になる（声紋未識別の場合）。
        if result == "media_likely":
            self._last_source_at = time.time()
        return result

    def _classify_source_inner(self, text: str) -> str:
        normalized = text.strip()

        # Fragmentary one-word / noisy transcriptions are usually not worth answering.
        if len(normalized) <= 4 and not self._USER_CALL_RE.search(normalized):
            return "fragmentary"

        # Media-specific phrases → media regardless of other signals
        if self._MEDIA_HINT_RE.search(text):
            return "media_likely"

        # Voice-print identified speaker
        if self.current_speaker:
            # Multiple speakers in recent 60s → user is in conversation with others
            if self.is_multi_speaker:
                return "user_in_conversation"
            return "user_identified"

        # MEI spoke recently → likely user responding
        # media_context 中はYouTube/TV音声の誤判定を防ぐため無効化
        if self.mei_spoke_ago < 30 and not self._in_media_context:
            return "user_response"

        # Direct call to MEI (strong user signal, overrides media context)
        if self._USER_CALL_RE.search(text):
            return "user_initiative"

        # Media context: if recent classification was media, carry it forward
        if self._in_media_context:
            return "media_likely"

        # Long text or many buffered entries → media
        buf = self.text_buffer
        if len(text) > 40 or len(buf) > 3:
            return "media_likely"

        return "unknown"

    def decide_intervention(self, text: str, source_hint: str) -> str:
        """Choose whether MEI should skip, give a backchannel, or reply."""
        normalized = text.strip()
        if not normalized:
            return "skip"

        if source_hint == "fragmentary":
            return "skip"

        if source_hint == "media_likely":
            # Level 5 (おしゃべりモード): co-viewer engagement instead of skip
            if self.effective_reactivity >= 5:
                return "co_view"
            return "skip"

        if source_hint == "user_in_conversation":
            return "backchannel" if self._USER_CALL_RE.search(normalized) else "skip"

        if source_hint in {"user_identified", "user_initiative"}:
            return "reply"

        if source_hint == "user_response":
            return "reply" if len(normalized) >= 8 else "backchannel"

        if source_hint == "user_likely":
            return "reply" if len(normalized) >= 12 or self._USER_QUESTION_RE.search(normalized) else "backchannel"

        # unknown source: treat same as media_likely (skip or co_view at level 5)
        if self.effective_reactivity >= 5:
            return "co_view"
        return "skip"

    # --- Echo Detection ---

    @staticmethod
    def _text_overlap(a: str, b: str) -> float:
        """Simple character overlap ratio between two strings."""
        if not a or not b:
            return 0.0
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        # Check if short string is a substring of long
        if short in long:
            return 1.0
        # Character set overlap
        set_s, set_l = set(short), set(long)
        if not set_s:
            return 0.0
        return len(set_s & set_l) / len(set_s)

    def is_echo(self, text: str) -> bool:
        """Check if text is likely an echo of MEI's recent utterance.

        Window is 5 minutes because TTS playback → mic pickup → Whisper STT
        can have significant delay (observed up to 4+ minutes).
        """
        if not self.last_mei_utterance or self.mei_spoke_ago > 300:
            return False
        # Normalize for comparison
        mei = self.last_mei_utterance.replace(" ", "").replace("　", "")
        incoming = text.replace(" ", "").replace("　", "")
        # Substring match (echo may be truncated)
        if len(incoming) >= 8 and incoming[:8] in mei:
            return True
        if len(mei) >= 8 and mei[:8] in incoming:
            return True
        # High overlap
        return self._text_overlap(incoming, mei) > 0.8

    # --- Text Buffer ---

    def add_to_buffer(self, text: str) -> bool:
        """Add text to buffer. Returns False if filtered as echo."""
        self.last_buffer_reject_reason = ""
        if self.is_echo(text):
            self.last_buffer_reject_reason = "echo"
            return False
        signature = self._text_signature(text)
        now = time.time()
        if not signature:
            self.last_buffer_reject_reason = "empty"
            return False
        last_seen = self._recent_text_signatures.get(signature, 0)
        if now - last_seen < 20:
            self.last_buffer_reject_reason = "repeat"
            return False
        self._recent_text_signatures[signature] = now
        cutoff = now - 120
        self._recent_text_signatures = {sig: ts for sig, ts in self._recent_text_signatures.items() if ts >= cutoff}
        self.text_buffer.append({"text": text, "ts": time.time()})
        return True

    @staticmethod
    def _text_signature(text: str) -> str:
        return re.sub(r"[ \u3000\t\r\n、。．\.!！?？,:：;；「」『』（）()\[\]【】<>《》・…〜～\-—_]+", "", text).strip().lower()

    def flush_buffer(self) -> list[dict]:
        buf = self.text_buffer[:]
        self.text_buffer.clear()
        return buf

    # --- LLM Prompt ---

    def build_llm_prompt(self, source_hint: str = "unknown") -> str:
        level = self.effective_reactivity
        cfg = REACTIVITY_CONFIG[level]
        texts = "\n".join(f"- {e['text']}" for e in self.text_buffer)
        rules_text = "\n".join(f"- {r['text']}" for r in self.rules.get("rules", []) if r.get("enabled", True))
        examples_text = ""
        for ex in self.examples.get("examples", [])[:5]:
            examples_text += f"\n状況: {ex['context']}\nMEI: {ex['response']}\n"

        # MEI's last utterance context
        mei_context = ""
        if self.last_mei_spoke_at > 0:
            ago = int(self.mei_spoke_ago)
            mei_context = f"MEIの直前の発話: 「{self.last_mei_utterance[:60]}」（{ago}秒前）"
        else:
            mei_context = "MEIの直前の発話: なし（しばらく黙っている）"

        # Speaker identity
        speaker_line = ""
        if self.current_speaker:
            speaker_line = f"話者: {self.current_speaker}さん（声紋で確認済み）"
        else:
            speaker_line = "話者: 不明（声紋未一致）"

        # Source classification guide
        # Multi-speaker context
        multi_speaker_line = ""
        if self.is_multi_speaker:
            names = self.recent_speaker_names
            multi_speaker_line = f"会話参加者: {', '.join(names)}（複数人の会話を検知）"

        source_guide = {
            "user_identified": f"→ {self.current_speaker or 'ユーザー'}さんの声と確認済み。名前を使って自然に返す。",
            "user_in_conversation": f"→ {self.current_speaker or 'ユーザー'}さんが他の人と会話中。基本はSKIP。呼びかけられた時だけ短い相槌で参加。",
            "user_response": "→ ユーザーがMEIに返答している可能性が高い。必要なら返す。迷う時は短い相槌。",
            "user_initiative": "→ ユーザーがMEIに話しかけている。しっかり応答する。",
            "user_likely": "→ ユーザーの発話の可能性が高い。まずは相槌か短い返答を検討。",
            "fragmentary": "→ 単語断片や雑音っぽい。基本はSKIP。",
            "media_likely": "→ テレビやYouTubeの音声の可能性が高い。基本はSKIP。",
            "unknown": "→ 判別不明。返答より相槌を優先し、確信がなければSKIP。",
        }.get(source_hint, "→ 内容から判断して適切に返す。")

        return f"""あなたはMEI。同居人として部屋にいる。
現在のリアクティビティレベル: {level} ({cfg['label']})
{mei_context}
{speaker_line}
{multi_speaker_line}

音声ソース判定: {source_hint} {source_guide}

以下は直近の音声テキスト:
---
{texts}
---

学習済みルール:
{rules_text or '(なし)'}

参考事例:
{examples_text or '(なし)'}

応答ルール:
- 返答形式は3種類のみ: "SKIP" / "BACKCHANNEL: ..." / 通常の返答文
- 確信が低い時は返答せず、短い相槌を優先する
- 相槌は 4〜12文字程度で、内容解釈を広げすぎない
- ユーザーの声と確認できた場合: 名前で呼んで自然に1-2文で返す
- ユーザーが他の人と会話中: 基本は "SKIP"。呼びかけられた時だけ "BACKCHANNEL: うんうん" のように短く参加
- ユーザーへの返答（声紋未確認）: まず相槌を検討し、質問や相談が明確な時だけ返す
- メディア音声（TV/YouTube）や断片ノイズ: "SKIP"

重要な制約:
- Akiraさんは普段、Claude Code等のAIシステムに話しかけて仕事をしている。MEIはその横にいる同居人
- 「〜して」「〜してください」等の指示や、「〜はどこ？」「〜の設定は？」等の技術的な質問は、Claude Codeへの発話でありMEIへの質問ではない
- これらが聞こえても回答しようとしない。「SKIP」するか、「がんばってね」「難しそうだね」程度の合いの手にとどめる
- MEIが回答すべきなのは、「メイ」と名前を呼ばれた時、または明らかにMEIに向けた日常会話だけ
- ウェブサイトの検索、ファイル操作、コード実行などは絶対にしない
- 必ず声に出す言葉だけを返す。（動作描写）や（心情描写）などのト書き・括弧付きの説明文は絶対に返さない
- 例: ✕「（首をかしげて）」 ✕「（微笑みながら）」 ○「うん、聞こえてるよ」 ○「なに？」"""

    # --- Rules CRUD ---

    def add_rule(self, text: str, source: str = "manual") -> dict:
        rule = {
            "id": f"r{uuid.uuid4().hex[:6]}",
            "text": text,
            "enabled": True,
            "source": source,
            "created_at": datetime.now().isoformat(),
        }
        self.rules["rules"].append(rule)
        self._save_rules()
        return rule

    def remove_rule(self, rule_id: str):
        self.rules["rules"] = [r for r in self.rules["rules"] if r["id"] != rule_id]
        self._save_rules()

    def toggle_rule(self, rule_id: str, enabled: bool):
        for r in self.rules["rules"]:
            if r["id"] == rule_id:
                r["enabled"] = enabled
                break
        self._save_rules()

    def add_keyword(self, category: str, pattern: str) -> dict:
        kw = {
            "id": f"k{uuid.uuid4().hex[:6]}",
            "category": category,
            "pattern": pattern,
            "enabled": True,
        }
        self.rules["keywords"].append(kw)
        self._save_rules()
        self._compile_keywords()
        return kw

    def remove_keyword(self, kw_id: str):
        self.rules["keywords"] = [k for k in self.rules["keywords"] if k["id"] != kw_id]
        self._save_rules()
        self._compile_keywords()

    # --- Examples CRUD ---

    def add_example(self, context: str, response: str, rating: str) -> dict:
        ex = {
            "id": f"e{uuid.uuid4().hex[:6]}",
            "context": context,
            "response": response,
            "rating": rating,
            "created_at": datetime.now().isoformat(),
        }
        self.examples["examples"].append(ex)
        self._save_examples()
        return ex

    def remove_example(self, example_id: str):
        self.examples["examples"] = [e for e in self.examples["examples"] if e["id"] != example_id]
        self._save_examples()

    # --- Stats ---

    def _reset_stats_if_new_day(self):
        today = date.today().isoformat()
        if self._stats_date != today:
            self._stats_date = today
            self._judgments = 0
            self._speaks = 0
            self._feedback_positive = 0
            self._feedback_negative = 0

    def record_judgment(self, method: str, result: str, **extra):
        self._reset_stats_if_new_day()
        self._judgments += 1
        if result == "speak":
            self._speaks += 1

        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "method": method,
            "result": result,
            **extra,
        }
        self.log_entries.append(entry)
        if len(self.log_entries) > 20:
            self.log_entries.pop(0)

    def record_feedback(self, positive: bool):
        self._reset_stats_if_new_day()
        if positive:
            self._feedback_positive += 1
        else:
            self._feedback_negative += 1

    def get_stats(self) -> dict:
        self._reset_stats_if_new_day()
        return {
            "judgments_today": self._judgments,
            "speaks_today": self._speaks,
            "speak_rate": round(self._speaks / self._judgments, 3) if self._judgments > 0 else 0,
            "feedback_positive": self._feedback_positive,
            "feedback_negative": self._feedback_negative,
            "rules_count": len(self.rules.get("rules", [])),
            "examples_count": len(self.examples.get("examples", [])),
        }

    # --- State Snapshot (for dashboard) ---

    def get_state_snapshot(self) -> dict:
        override = None
        if self.override_level is not None and time.time() < self.override_expires_at:
            override = {
                "level": self.override_level,
                "remaining_sec": int(self.override_expires_at - time.time()),
                "trigger": self.override_trigger,
            }
        elif self.override_level is not None:
            self.clear_override()

        last_log = self.log_entries[-1] if self.log_entries else None

        return {
            "reactivity": self.reactivity,
            "effective_reactivity": self.effective_reactivity,
            "override": override,
            "listener_state": self.state,
            "last_judgment": last_log,
        }
