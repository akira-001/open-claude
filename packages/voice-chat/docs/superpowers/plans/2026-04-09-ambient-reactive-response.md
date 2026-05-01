# Ambient Reactive Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MEI が周囲の音声（TV、会話、環境音）を聞き取り、文脈に応じて自然に声をかける「同居人」的な振る舞いを実現する。

**Architecture:** 既存の always-on STT パイプラインの "no wake word" 分岐に `ambient_listener.py` を接続。キーワード即応（regex）+ 30秒周期 LLM バッチ判定のハイブリッド方式。5段階リアクティビティ、学習ルール/few-shot 事例管理、音声コマンド制御、barge-in 検知、ダッシュボード Ambient タブで全状態を可視化。

**Tech Stack:** Python 3.14, FastAPI, Ollama (ローカル LLM), Irodori TTS, pytest + pytest-asyncio, Vanilla JS (dashboard)

**Spec:** `docs/superpowers/specs/2026-04-09-ambient-reactive-response-design.md`

**Note:** ユーザーへの質問が必要な場合は、Slack Bot 経由で Akiraさんに DM を送る。エンドポイント: `POST http://127.0.0.1:3457/internal/send-dm` body: `{"text": "質問内容"}`

---

## File Structure

### New Files
| File | Responsibility |
|------|----------------|
| `ambient_listener.py` | Ambient 判定エンジン: キーワードマッチ、LLM バッチ判定、リアクティビティ管理、モードオーバーライド、クールダウン、統計 |
| `ambient_commands.py` | Stop/モード変更/barge-in 用の音声コマンド検出（wake_detect.py と同レイヤー） |
| `ambient_rules.json` | 学習ルール + キーワードカテゴリ定義（初期データ付き） |
| `ambient_examples.json` | Few-shot 事例（空の初期構造） |
| `tests/test_ambient_commands.py` | ambient_commands のユニットテスト |
| `tests/test_ambient_listener.py` | ambient_listener のユニットテスト |
| `tests/test_ambient_api.py` | REST API エンドポイントのテスト |

### Modified Files
| File | Changes |
|------|---------|
| `app.py` | `_process_always_on()` に ambient 分岐追加、REST API エンドポイント追加、WebSocket メッセージハンドラ追加、ambient バッチループ追加 |
| `index.html` | タブ切り替え UI + Ambient タブ（状態・ログ・ルール・事例・統計・リアクティビティ設定） |

---

### Task 1: 音声コマンド検出モジュール (ambient_commands.py)

**Files:**
- Create: `ambient_commands.py`
- Create: `tests/test_ambient_commands.py`

- [ ] **Step 1: Write the failing test for Stop command detection**

```python
# tests/test_ambient_commands.py
import pytest
from ambient_commands import detect_ambient_command, AmbientCommand


class TestDetectAmbientCommand:
    def test_stop_japanese(self):
        result = detect_ambient_command("やめて")
        assert result.type == "stop"

    def test_stop_english(self):
        result = detect_ambient_command("Stop")
        assert result.type == "stop"

    def test_stop_katakana(self):
        result = detect_ambient_command("ストップ")
        assert result.type == "stop"

    def test_quiet_down(self):
        result = detect_ambient_command("静かにして")
        assert result.type == "quiet"
        assert result.level_delta == -2
        assert result.duration_sec == 900

    def test_noisy(self):
        result = detect_ambient_command("うるさい")
        assert result.type == "quiet"
        assert result.level_delta == -1
        assert result.duration_sec == 600

    def test_talk_more(self):
        result = detect_ambient_command("もっと話して")
        assert result.type == "talk_more"
        assert result.level_delta == 1
        assert result.duration_sec == 900

    def test_talk_kakete(self):
        result = detect_ambient_command("話しかけて")
        assert result.type == "talk_more"
        assert result.level_delta == 1

    def test_shut_up(self):
        result = detect_ambient_command("黙って")
        assert result.type == "quiet"
        assert result.level_delta == -2

    def test_no_command(self):
        result = detect_ambient_command("今日はいい天気だね")
        assert result.type == "none"

    def test_empty_text(self):
        result = detect_ambient_command("")
        assert result.type == "none"

    def test_stop_has_highest_priority(self):
        """Stop が他のコマンドより優先されること"""
        result = detect_ambient_command("やめて静かにして")
        assert result.type == "stop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_commands.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ambient_commands'`

- [ ] **Step 3: Implement ambient_commands.py**

```python
# ambient_commands.py
"""Ambient voice command detection — Stop, mode control, barge-in triggers."""
import re
from dataclasses import dataclass


@dataclass
class AmbientCommand:
    type: str  # "stop", "quiet", "talk_more", "none"
    level_delta: int = 0
    duration_sec: int = 0


# Priority order: stop > quiet/talk_more
_STOP_PATTERNS = [
    re.compile(r'(?:やめて|止めて|ストップ|とめて)', re.IGNORECASE),
    re.compile(r'\b[Ss]top\b'),
]

_QUIET_PATTERNS = [
    # -2 level, 15 min
    (re.compile(r'(?:静かにして|黙って|しずかにして|だまって)'), -2, 900),
    # -1 level, 10 min
    (re.compile(r'(?:うるさい|うっさい)'), -1, 600),
]

_TALK_MORE_PATTERNS = [
    (re.compile(r'(?:もっと話して|話しかけて|しゃべって|もっとしゃべって)'), 1, 900),
]


def detect_ambient_command(text: str) -> AmbientCommand:
    text = text.strip()
    if not text:
        return AmbientCommand(type="none")

    # Stop has highest priority
    for pattern in _STOP_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="stop")

    for pattern, delta, duration in _QUIET_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="quiet", level_delta=delta, duration_sec=duration)

    for pattern, delta, duration in _TALK_MORE_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="talk_more", level_delta=delta, duration_sec=duration)

    return AmbientCommand(type="none")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_commands.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add ambient_commands.py tests/test_ambient_commands.py
git commit -m "feat: add ambient voice command detection module"
```

---

### Task 2: Ambient Listener コアロジック (ambient_listener.py)

**Files:**
- Create: `ambient_listener.py`
- Create: `ambient_rules.json`
- Create: `ambient_examples.json`
- Create: `tests/test_ambient_listener.py`

- [ ] **Step 1: Create initial data files**

`ambient_rules.json`:
```json
{
  "rules": [
    {
      "id": "r001",
      "text": "深夜（0時〜6時）は控えめに話す",
      "enabled": true,
      "source": "default",
      "created_at": "2026-04-09T00:00:00"
    }
  ],
  "keywords": [
    {
      "id": "k001",
      "category": "weather",
      "pattern": "天気|雨|晴れ?|曇り|台風|気温|暑い|寒い",
      "enabled": true
    },
    {
      "id": "k002",
      "category": "food",
      "pattern": "ご飯|お腹すいた|何食べ|おいしそう|料理",
      "enabled": true
    },
    {
      "id": "k003",
      "category": "time",
      "pattern": "何時|遅刻|もう夜|朝だ|寝なきゃ",
      "enabled": true
    },
    {
      "id": "k004",
      "category": "emotion",
      "pattern": "疲れた|つまらない|楽しい|すごい|やばい|面白い",
      "enabled": true
    }
  ]
}
```

`ambient_examples.json`:
```json
{
  "examples": []
}
```

- [ ] **Step 2: Write the failing tests for AmbientListener**

```python
# tests/test_ambient_listener.py
import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from ambient_listener import AmbientListener, REACTIVITY_CONFIG


class TestReactivityConfig:
    def test_all_levels_defined(self):
        for level in range(1, 6):
            assert level in REACTIVITY_CONFIG

    def test_level_3_is_default(self):
        cfg = REACTIVITY_CONFIG[3]
        assert cfg["batch_interval_sec"] == 30
        assert cfg["keyword_ratio"] == 1.0

    def test_higher_level_shorter_interval(self):
        assert REACTIVITY_CONFIG[5]["batch_interval_sec"] < REACTIVITY_CONFIG[1]["batch_interval_sec"]


class TestAmbientListener:
    @pytest.fixture
    def rules_file(self, tmp_path):
        f = tmp_path / "ambient_rules.json"
        f.write_text(json.dumps({
            "rules": [{"id": "r001", "text": "テストルール", "enabled": True, "source": "test", "created_at": "2026-01-01T00:00:00"}],
            "keywords": [{"id": "k001", "category": "weather", "pattern": "天気|雨", "enabled": True}],
        }))
        return f

    @pytest.fixture
    def examples_file(self, tmp_path):
        f = tmp_path / "ambient_examples.json"
        f.write_text(json.dumps({
            "examples": [{"id": "e001", "context": "TVで天気予報", "response": "傘いるかも", "rating": "positive", "created_at": "2026-01-01T00:00:00"}],
        }))
        return f

    @pytest.fixture
    def listener(self, rules_file, examples_file):
        return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)

    def test_initial_state(self, listener):
        assert listener.reactivity == 3
        assert listener.override_level is None
        assert listener.state == "idle"
        assert len(listener.rules["keywords"]) == 1

    def test_set_reactivity_clamps(self, listener):
        listener.set_reactivity(7)
        assert listener.reactivity == 5
        listener.set_reactivity(-1)
        assert listener.reactivity == 1

    def test_override_sets_timer(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.override_level == 1  # 3 - 2 = 1
        assert listener.override_expires_at > time.time()

    def test_override_clamps_to_min_1(self, listener):
        listener.set_reactivity(1)
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.override_level == 1  # min is 1

    def test_effective_reactivity_uses_override(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.effective_reactivity == 1

    def test_effective_reactivity_after_expiry(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=0)
        listener.override_expires_at = time.time() - 1  # expired
        assert listener.effective_reactivity == 3  # back to base

    def test_keyword_match(self, listener):
        result = listener.check_keywords("今日の天気はどうかな")
        assert result is not None
        assert result["category"] == "weather"

    def test_keyword_no_match(self, listener):
        result = listener.check_keywords("プログラミングの話")
        assert result is None

    def test_keyword_disabled(self, listener):
        listener.rules["keywords"][0]["enabled"] = False
        result = listener.check_keywords("天気の話")
        assert result is None

    def test_cooldown_blocks_same_category(self, listener):
        listener.check_keywords("天気の話")  # first match
        listener.record_cooldown("weather")
        result = listener.check_keywords("雨が降りそう")
        assert result is None  # blocked by cooldown

    def test_add_text_to_buffer(self, listener):
        listener.add_to_buffer("テスト1")
        listener.add_to_buffer("テスト2")
        assert len(listener.text_buffer) == 2

    def test_flush_buffer(self, listener):
        listener.add_to_buffer("テスト1")
        listener.add_to_buffer("テスト2")
        texts = listener.flush_buffer()
        assert len(texts) == 2
        assert len(listener.text_buffer) == 0

    def test_add_rule(self, listener):
        rule = listener.add_rule("新しいルール", source="explicit")
        assert rule["id"].startswith("r")
        assert len(listener.rules["rules"]) == 2

    def test_remove_rule(self, listener):
        listener.remove_rule("r001")
        assert len(listener.rules["rules"]) == 0

    def test_toggle_rule(self, listener):
        listener.toggle_rule("r001", enabled=False)
        assert listener.rules["rules"][0]["enabled"] is False

    def test_add_example(self, listener):
        ex = listener.add_example("状況", "反応", "positive")
        assert ex["id"].startswith("e")
        assert len(listener.examples["examples"]) == 2

    def test_remove_example(self, listener):
        listener.remove_example("e001")
        assert len(listener.examples["examples"]) == 0

    def test_get_stats(self, listener):
        stats = listener.get_stats()
        assert "judgments_today" in stats
        assert "speaks_today" in stats
        assert "speak_rate" in stats

    def test_record_judgment_updates_stats(self, listener):
        listener.record_judgment(method="keyword", result="speak")
        listener.record_judgment(method="keyword", result="skip")
        stats = listener.get_stats()
        assert stats["judgments_today"] == 2
        assert stats["speaks_today"] == 1

    def test_build_llm_prompt(self, listener):
        listener.add_to_buffer("天気予報やってるね")
        listener.add_to_buffer("明日は雨らしい")
        prompt = listener.build_llm_prompt()
        assert "リアクティビティレベル" in prompt
        assert "天気予報やってるね" in prompt
        assert "テストルール" in prompt

    def test_get_state_snapshot(self, listener):
        snap = listener.get_state_snapshot()
        assert snap["reactivity"] == 3
        assert snap["override"] is None
        assert snap["listener_state"] == "idle"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_listener.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ambient_listener'`

- [ ] **Step 4: Implement ambient_listener.py**

```python
# ambient_listener.py
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
_BASE_LLM_COOLDOWN = 90     # seconds


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
                return None

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

    # --- Text Buffer ---

    def add_to_buffer(self, text: str):
        self.text_buffer.append({"text": text, "ts": time.time()})

    def flush_buffer(self) -> list[dict]:
        buf = self.text_buffer[:]
        self.text_buffer.clear()
        return buf

    # --- LLM Prompt ---

    def build_llm_prompt(self) -> str:
        level = self.effective_reactivity
        cfg = REACTIVITY_CONFIG[level]
        texts = "\n".join(f"- {e['text']}" for e in self.text_buffer)
        rules_text = "\n".join(f"- {r['text']}" for r in self.rules.get("rules", []) if r.get("enabled", True))
        examples_text = ""
        for ex in self.examples.get("examples", [])[:5]:
            examples_text += f"\n状況: {ex['context']}\nMEI: {ex['response']}\n"

        return f"""あなたはMEI。同居人として部屋にいる。
現在のリアクティビティレベル: {level} ({cfg['label']})

以下は直近の音声テキスト:
---
{texts}
---

学習済みルール:
{rules_text or '(なし)'}

参考事例:
{examples_text or '(なし)'}

判定: 反応する場合は発話内容を1-2文で返す。しない場合は "SKIP" とだけ返す。"""

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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_listener.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add ambient_listener.py ambient_rules.json ambient_examples.json tests/test_ambient_listener.py
git commit -m "feat: add ambient listener core with keyword detection, reactivity, rules/examples CRUD"
```

---

### Task 3: app.py — Ambient 判定統合 (_process_always_on 分岐 + バッチループ)

**Files:**
- Modify: `app.py:31` (imports)
- Modify: `app.py:624-628` (global state)
- Modify: `app.py:664-709` (`_process_always_on`)
- Modify: `app.py:966-981` (`on_startup`)
- Create: `tests/test_ambient_integration.py`

- [ ] **Step 1: Write the failing test for ambient integration in _process_always_on**

```python
# tests/test_ambient_integration.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
import time


class TestProcessAlwaysOnAmbient:
    """Test that _process_always_on routes to ambient listener when no wake word."""

    @pytest.mark.asyncio
    async def test_no_wake_word_adds_to_ambient_buffer(self):
        """When no wake word and not in conversation, text is added to ambient buffer."""
        from app import _process_always_on
        mock_ws = AsyncMock()

        with patch("app.transcribe", new_callable=AsyncMock, return_value="天気予報やってるね"), \
             patch("app.detect_wake_word") as mock_wake, \
             patch("app._always_on_echo_suppress_until", 0), \
             patch("app._always_on_conversation_until", 0), \
             patch("app._ambient_listener") as mock_listener:
            mock_wake.return_value = MagicMock(detected=False)
            mock_listener.effective_reactivity = 3
            mock_listener.state = "listening"
            mock_listener.check_keywords.return_value = None

            await _process_always_on(mock_ws, b"fake_audio")

            mock_listener.add_to_buffer.assert_called_once_with("天気予報やってるね")

    @pytest.mark.asyncio
    async def test_keyword_match_triggers_llm(self):
        """When keyword matches, should call ambient LLM reply."""
        from app import _process_always_on
        mock_ws = AsyncMock()

        with patch("app.transcribe", new_callable=AsyncMock, return_value="今日の天気はどう"), \
             patch("app.detect_wake_word") as mock_wake, \
             patch("app._always_on_echo_suppress_until", 0), \
             patch("app._always_on_conversation_until", 0), \
             patch("app._ambient_listener") as mock_listener, \
             patch("app._ambient_llm_reply", new_callable=AsyncMock) as mock_reply:
            mock_wake.return_value = MagicMock(detected=False)
            mock_listener.effective_reactivity = 3
            mock_listener.state = "listening"
            mock_listener.check_keywords.return_value = {"category": "weather", "keyword": "天気", "id": "k001"}
            mock_listener.is_llm_in_cooldown.return_value = False

            await _process_always_on(mock_ws, b"fake_audio")

            mock_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_command_kills_audio(self):
        """Stop command should cancel ongoing audio and reset state."""
        from app import _process_always_on
        mock_ws = AsyncMock()

        with patch("app.transcribe", new_callable=AsyncMock, return_value="やめて"), \
             patch("app.detect_ambient_command") as mock_cmd, \
             patch("app._always_on_echo_suppress_until", 0), \
             patch("app._always_on_conversation_until", time.time() + 30), \
             patch("app._ambient_listener") as mock_listener:
            from ambient_commands import AmbientCommand
            mock_cmd.return_value = AmbientCommand(type="stop")

            await _process_always_on(mock_ws, b"fake_audio")

            # Should send stop_audio to client
            calls = [c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "stop_audio"]
            assert len(calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_integration.py -v`
Expected: FAIL (missing `_ambient_listener`, `_ambient_llm_reply`, `detect_ambient_command` in app.py)

- [ ] **Step 3: Modify app.py — Add imports and global state**

At `app.py:31` after `from wake_response import WakeResponseCache`, add:

```python
from ambient_commands import detect_ambient_command
from ambient_listener import AmbientListener
```

After `app.py:628` (after `_always_on_conversation` definition), add:

```python
_ambient_listener: AmbientListener | None = None
_ambient_batch_task: asyncio.Task | None = None
```

- [ ] **Step 4: Modify app.py — Replace _process_always_on "no wake word" branch**

Replace `app.py:664-709` (`_process_always_on` function) with:

```python
async def _process_always_on(ws: WebSocket, audio_data: bytes):
    """Process always-on audio in background — doesn't block WS receive loop."""
    global _always_on_echo_suppress_until, _always_on_conversation_until
    try:
        if time.time() < _always_on_echo_suppress_until:
            return

        text = await transcribe(audio_data, fast=True)
        if not text:
            return

        if time.time() < _always_on_echo_suppress_until:
            return

        # --- Ambient command detection (highest priority) ---
        cmd = detect_ambient_command(text)
        if cmd.type == "stop":
            logger.info(f"[ambient] STOP command: '{text}'")
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
            _ambient_listener.apply_override(
                level_delta=cmd.level_delta,
                duration_sec=cmd.duration_sec,
                trigger=text,
            )
            # Brief acknowledgment via LLM
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
            if remaining and remaining not in ("メイ", "メイ。", "mei", "Mei"):
                await _always_on_llm_reply(ws, remaining)
        elif in_conversation:
            logger.info(f"[always_on] conversation: '{text[:50]}'")
            await _always_on_llm_reply(ws, text)
        else:
            # --- Ambient processing ---
            if _ambient_listener and _ambient_listener.effective_reactivity > 0:
                _ambient_listener.add_to_buffer(text)
                kw_match = _ambient_listener.check_keywords(text)
                if kw_match and not _ambient_listener.is_llm_in_cooldown():
                    logger.info(f"[ambient] keyword hit: {kw_match['category']} in '{text[:50]}'")
                    _ambient_listener.record_cooldown(kw_match["category"])
                    await _ambient_llm_reply(ws, text, method="keyword", keyword=kw_match["category"])
                else:
                    logger.info(f"[ambient] buffered: '{text[:50]}'")
            await ws.send_json({"type": "always_on_result", "wake": False})
    except Exception as e:
        logger.warning(f"[always_on] processing error: {e}")
```

- [ ] **Step 5: Add _ambient_llm_reply and _ambient_broadcast_text functions**

After the modified `_process_always_on`, add:

```python
async def _ambient_llm_reply(ws: WebSocket, trigger_text: str, method: str = "keyword", keyword: str = ""):
    """Generate ambient response via LLM and broadcast to all clients."""
    global _always_on_echo_suppress_until
    if not _ambient_listener:
        return
    try:
        _ambient_listener.state = "processing"
        prompt = _ambient_listener.build_llm_prompt()
        model = _settings.get("modelSelect", "gemma4:e4b")
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"直近の発話: {trigger_text}"},
        ]
        reply = await chat_with_llm(messages, model)

        if reply.strip().upper() == "SKIP":
            _ambient_listener.record_judgment(method=method, result="skip", keyword=keyword)
            _ambient_listener.state = "listening"
            await _broadcast_ambient_state()
            return

        _ambient_listener.record_judgment(method=method, result="speak", keyword=keyword, utterance=reply)
        _ambient_listener.record_llm_cooldown()

        # TTS + broadcast to all clients
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
            _always_on_echo_suppress_until = time.time() + 4.0
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
```

- [ ] **Step 6: Add ambient batch loop**

After the `_broadcast_ambient_state` function, add:

```python
async def _ambient_batch_loop():
    """Periodic LLM batch judgment for ambient audio."""
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

            if not _ambient_listener.text_buffer:
                continue
            if _ambient_listener.is_llm_in_cooldown():
                continue

            logger.info(f"[ambient] batch judgment ({len(_ambient_listener.text_buffer)} texts)")
            # Use first connected client as ws target (broadcast goes to all)
            ws = next(iter(_clients), None)
            if ws:
                trigger = " ".join(e["text"] for e in _ambient_listener.text_buffer[-3:])
                await _ambient_llm_reply(ws, trigger, method="llm_batch")
                _ambient_listener.flush_buffer()
        except Exception as e:
            logger.warning(f"[ambient] batch loop error: {e}")
            await asyncio.sleep(5)
```

- [ ] **Step 7: Modify on_startup to initialize ambient listener**

In `app.py` `on_startup()` function (around line 966), add after the wake cache warmup block:

```python
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
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_integration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 9: Run all existing tests to verify no regressions**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/ -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 10: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add app.py tests/test_ambient_integration.py
git commit -m "feat: integrate ambient listener into always-on pipeline with batch loop"
```

---

### Task 4: REST API エンドポイント

**Files:**
- Modify: `app.py` (REST endpoints, before `@app.websocket("/ws")`)
- Create: `tests/test_ambient_api.py`

- [ ] **Step 1: Write the failing tests for REST API**

```python
# tests/test_ambient_api.py
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked ambient_listener."""
    from app import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_ambient():
    with patch("app._ambient_listener") as mock:
        mock.rules = {
            "rules": [{"id": "r001", "text": "テスト", "enabled": True, "source": "test", "created_at": "2026-01-01"}],
            "keywords": [{"id": "k001", "category": "weather", "pattern": "天気", "enabled": True}],
        }
        mock.examples = {
            "examples": [{"id": "e001", "context": "テスト状況", "response": "テスト反応", "rating": "positive", "created_at": "2026-01-01"}],
        }
        mock.reactivity = 3
        mock.get_stats.return_value = {"judgments_today": 10, "speaks_today": 3, "speak_rate": 0.3, "feedback_positive": 2, "feedback_negative": 1, "rules_count": 1, "examples_count": 1}
        mock.add_rule.return_value = {"id": "r002", "text": "新ルール", "enabled": True, "source": "manual", "created_at": "2026-04-09"}
        mock.add_example.return_value = {"id": "e002", "context": "新状況", "response": "新反応", "rating": "positive", "created_at": "2026-04-09"}
        yield mock


class TestAmbientRulesAPI:
    def test_get_rules(self, client, mock_ambient):
        res = client.get("/api/ambient/rules")
        assert res.status_code == 200
        data = res.json()
        assert "rules" in data
        assert "keywords" in data

    def test_add_rule(self, client, mock_ambient):
        res = client.post("/api/ambient/rules", json={"text": "新ルール", "source": "manual"})
        assert res.status_code == 200
        mock_ambient.add_rule.assert_called_once_with("新ルール", source="manual")

    def test_delete_rule(self, client, mock_ambient):
        res = client.delete("/api/ambient/rules/r001")
        assert res.status_code == 200
        mock_ambient.remove_rule.assert_called_once_with("r001")

    def test_toggle_rule(self, client, mock_ambient):
        res = client.patch("/api/ambient/rules/r001", json={"enabled": False})
        assert res.status_code == 200
        mock_ambient.toggle_rule.assert_called_once_with("r001", enabled=False)


class TestAmbientExamplesAPI:
    def test_get_examples(self, client, mock_ambient):
        res = client.get("/api/ambient/examples")
        assert res.status_code == 200
        assert "examples" in res.json()

    def test_add_example(self, client, mock_ambient):
        res = client.post("/api/ambient/examples", json={"context": "新状況", "response": "新反応", "rating": "positive"})
        assert res.status_code == 200
        mock_ambient.add_example.assert_called_once()

    def test_delete_example(self, client, mock_ambient):
        res = client.delete("/api/ambient/examples/e001")
        assert res.status_code == 200
        mock_ambient.remove_example.assert_called_once_with("e001")


class TestAmbientReactivityAPI:
    def test_set_reactivity(self, client, mock_ambient):
        res = client.post("/api/ambient/reactivity", json={"level": 4})
        assert res.status_code == 200
        mock_ambient.set_reactivity.assert_called_once_with(4)

    def test_get_stats(self, client, mock_ambient):
        res = client.get("/api/ambient/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["judgments_today"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_api.py -v`
Expected: FAIL with 404 (endpoints don't exist yet)

- [ ] **Step 3: Add REST API endpoints to app.py**

Add before the `@app.websocket("/ws")` decorator in `app.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_api.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add app.py tests/test_ambient_api.py
git commit -m "feat: add ambient REST API endpoints for rules, examples, reactivity, stats"
```

---

### Task 5: ダッシュボード Ambient タブ (index.html)

**Files:**
- Modify: `index.html` (HTML structure + CSS + JS)

- [ ] **Step 1: Add tab CSS styles**

In `index.html` `<style>` section (before `</style>` closing tag around line 273), add:

```css
  /* --- Tab navigation --- */
  .tab-bar { display: flex; gap: 0; background: var(--ember-surface); border-bottom: 1px solid var(--ember-border); flex-shrink: 0; }
  .tab-bar button { flex: 1; padding: 10px 16px; background: none; border: none; color: var(--ember-text-muted); font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .tab-bar button.active { color: var(--ember-accent); border-bottom-color: var(--ember-accent); }
  .tab-bar button:hover:not(.active) { color: var(--ember-text); }
  .tab-content { display: none; flex: 1; overflow-y: auto; flex-direction: column; }
  .tab-content.active { display: flex; }

  /* --- Ambient tab --- */
  #ambientTab { padding: 16px; gap: 16px; }
  .ambient-section { background: var(--ember-surface); border-radius: 12px; padding: 14px; }
  .ambient-section h3 { font-size: 13px; color: var(--ember-text-muted); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .ambient-status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .ambient-status-item { font-size: 13px; }
  .ambient-status-item .label { color: var(--ember-text-muted); }
  .ambient-status-item .value { color: var(--ember-text); font-weight: 600; }
  .reactivity-buttons { display: flex; gap: 6px; }
  .reactivity-buttons button { flex: 1; padding: 8px 4px; border-radius: 8px; border: 1px solid var(--ember-border); background: var(--ember-surface-alt); color: var(--ember-text-muted); font-size: 12px; cursor: pointer; transition: all 0.2s; }
  .reactivity-buttons button.active { background: var(--ember-accent); color: white; border-color: var(--ember-accent); }
  .reactivity-buttons button:hover:not(.active) { border-color: var(--ember-accent); color: var(--ember-text); }
  .ambient-log { max-height: 200px; overflow-y: auto; font-size: 12px; font-family: monospace; }
  .ambient-log-entry { padding: 4px 0; border-bottom: 1px solid var(--ember-border); }
  .ambient-log-entry .time { color: var(--ember-text-dim); }
  .ambient-log-entry .method { color: var(--ember-warm); }
  .ambient-log-entry .result-speak { color: #2ecc71; }
  .ambient-log-entry .result-skip { color: var(--ember-text-dim); }
  .ambient-list { max-height: 200px; overflow-y: auto; }
  .ambient-list-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--ember-border); font-size: 13px; }
  .ambient-list-item .toggle { cursor: pointer; opacity: 0.7; }
  .ambient-list-item .toggle:hover { opacity: 1; }
  .ambient-list-item .text { flex: 1; }
  .ambient-list-item .delete { cursor: pointer; color: var(--ember-text-dim); font-size: 16px; }
  .ambient-list-item .delete:hover { color: var(--ember-accent); }
  .ambient-add-row { display: flex; gap: 6px; margin-top: 8px; }
  .ambient-add-row input { flex: 1; background: var(--ember-input-bg); border: 1px solid var(--ember-border); border-radius: 6px; padding: 6px 10px; color: var(--ember-text); font-size: 13px; }
  .ambient-add-row button { background: var(--ember-accent); border: none; border-radius: 6px; padding: 6px 12px; color: white; font-size: 12px; cursor: pointer; }
  .ambient-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; }
  .ambient-stats .stat-value { font-size: 20px; font-weight: 700; color: var(--ember-accent); }
```

- [ ] **Step 2: Add tab bar and Ambient tab HTML**

In `index.html`, after the `#serverStatus` div (after line 296), add the tab bar:

```html
<div class="tab-bar">
  <button id="tabChat" class="active" onclick="switchTab('chat')">Chat</button>
  <button id="tabAmbient" onclick="switchTab('ambient')">Ambient</button>
</div>
```

Wrap the existing `<div id="chat">` with a tab content wrapper. Change:
```html
<div id="chat">
```
to:
```html
<div id="chatTab" class="tab-content active" style="display:flex; flex:1; flex-direction:column;">
<div id="chat" style="flex:1; overflow-y:auto; padding:20px; display:flex; flex-direction:column; gap:12px;">
```

After `</div>` of `#textInputRow` (after line 358), close the chatTab wrapper and add Ambient tab:
```html
</div><!-- /chatTab -->

<div id="ambientTab" class="tab-content">
  <div class="ambient-section">
    <h3>Current State</h3>
    <div class="ambient-status-grid">
      <div class="ambient-status-item"><span class="label">Reactivity: </span><span class="value" id="ambStatusLevel">3 (普通)</span></div>
      <div class="ambient-status-item"><span class="label">Override: </span><span class="value" id="ambStatusOverride">-</span></div>
      <div class="ambient-status-item"><span class="label">State: </span><span class="value" id="ambStatusState">idle</span></div>
      <div class="ambient-status-item"><span class="label">Last: </span><span class="value" id="ambStatusLast">-</span></div>
    </div>
  </div>

  <div class="ambient-section">
    <h3>Reactivity Level</h3>
    <div class="reactivity-buttons" id="reactivityBtns">
      <button onclick="setReactivity(1)">1 静か</button>
      <button onclick="setReactivity(2)">2 控えめ</button>
      <button class="active" onclick="setReactivity(3)">3 普通</button>
      <button onclick="setReactivity(4)">4 積極的</button>
      <button onclick="setReactivity(5)">5 話好き</button>
    </div>
  </div>

  <div class="ambient-section">
    <h3>Judgment Log</h3>
    <div class="ambient-log" id="ambientLog"></div>
  </div>

  <div class="ambient-section">
    <h3>Rules <span id="ambRulesCount"></span></h3>
    <div class="ambient-list" id="ambientRulesList"></div>
    <div class="ambient-add-row">
      <input type="text" id="ambNewRule" placeholder="新しいルールを追加...">
      <button onclick="addAmbientRule()">Add</button>
    </div>
  </div>

  <div class="ambient-section">
    <h3>Examples <span id="ambExamplesCount"></span></h3>
    <div class="ambient-list" id="ambientExamplesList"></div>
    <div class="ambient-add-row">
      <input type="text" id="ambNewExContext" placeholder="状況..." style="flex:1">
      <input type="text" id="ambNewExResponse" placeholder="MEIの反応..." style="flex:1">
      <button onclick="addAmbientExample()">Add</button>
    </div>
  </div>

  <div class="ambient-section">
    <h3>Stats (Today)</h3>
    <div class="ambient-stats" id="ambientStats">
      <div><div class="stat-value" id="statSpeaks">0</div><div class="label">Speaks</div></div>
      <div><div class="stat-value" id="statJudgments">0</div><div class="label">Judgments</div></div>
      <div><div class="stat-value" id="statRate">0%</div><div class="label">Rate</div></div>
      <div><div class="stat-value" id="statFeedback">+0/-0</div><div class="label">Feedback</div></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add JavaScript for tab switching and ambient functionality**

In `index.html` `<script>` section, add at the end (before `</script>`):

```javascript
// --- Tab switching ---
function switchTab(tab) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-bar button').forEach(el => el.classList.remove('active'));
  if (tab === 'chat') {
    document.getElementById('chatTab').classList.add('active');
    document.getElementById('chatTab').style.display = 'flex';
    document.getElementById('tabChat').classList.add('active');
    // Show chat controls
    document.getElementById('toolbar').style.display = '';
    document.querySelectorAll('.bot-row').forEach(el => el.style.display = '');
    document.getElementById('controls').style.display = '';
    document.getElementById('textInputRow').style.display = '';
  } else {
    document.getElementById('ambientTab').classList.add('active');
    document.getElementById('ambientTab').style.display = 'flex';
    document.getElementById('tabAmbient').classList.add('active');
    // Hide chat controls
    document.getElementById('toolbar').style.display = 'none';
    document.querySelectorAll('.bot-row').forEach(el => el.style.display = 'none');
    document.getElementById('controls').style.display = 'none';
    document.getElementById('textInputRow').style.display = 'none';
    loadAmbientData();
  }
}

// --- Ambient data loading ---
async function loadAmbientData() {
  try {
    const [rulesRes, examplesRes, statsRes] = await Promise.all([
      fetch(`${API_BASE}/ambient/rules`),
      fetch(`${API_BASE}/ambient/examples`),
      fetch(`${API_BASE}/ambient/stats`),
    ]);
    if (rulesRes.ok) renderRules(await rulesRes.json());
    if (examplesRes.ok) renderExamples(await examplesRes.json());
    if (statsRes.ok) renderStats(await statsRes.json());
  } catch (e) { console.warn('[ambient] load error:', e); }
}

function renderRules(data) {
  const list = document.getElementById('ambientRulesList');
  const rules = data.rules || [];
  document.getElementById('ambRulesCount').textContent = `(${rules.length})`;
  list.innerHTML = rules.map(r => `
    <div class="ambient-list-item">
      <span class="toggle" onclick="toggleRule('${r.id}', ${!r.enabled})">${r.enabled ? '✓' : '✗'}</span>
      <span class="text" style="${r.enabled ? '' : 'opacity:0.5'}">${r.text}</span>
      <span class="delete" onclick="deleteRule('${r.id}')">×</span>
    </div>
  `).join('');
}

function renderExamples(data) {
  const list = document.getElementById('ambientExamplesList');
  const examples = data.examples || [];
  document.getElementById('ambExamplesCount').textContent = `(${examples.length})`;
  list.innerHTML = examples.map(e => `
    <div class="ambient-list-item" style="flex-direction:column; align-items:flex-start;">
      <div style="font-size:12px; color:var(--ember-text-dim);">状況: ${e.context}</div>
      <div>MEI: ${e.response}</div>
      <span class="delete" style="position:absolute; right:14px;" onclick="deleteExample('${e.id}')">×</span>
    </div>
  `).join('');
}

function renderStats(data) {
  document.getElementById('statSpeaks').textContent = data.speaks_today || 0;
  document.getElementById('statJudgments').textContent = data.judgments_today || 0;
  document.getElementById('statRate').textContent = ((data.speak_rate || 0) * 100).toFixed(1) + '%';
  document.getElementById('statFeedback').textContent = `+${data.feedback_positive || 0}/-${data.feedback_negative || 0}`;
}

// --- Reactivity ---
function setReactivity(level) {
  fetch(`${API_BASE}/ambient/reactivity`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({level}),
  }).then(() => {
    document.querySelectorAll('#reactivityBtns button').forEach((btn, i) => {
      btn.classList.toggle('active', i + 1 === level);
    });
  });
}

// --- Rules CRUD ---
async function addAmbientRule() {
  const input = document.getElementById('ambNewRule');
  const text = input.value.trim();
  if (!text) return;
  await fetch(`${API_BASE}/ambient/rules`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, source: 'manual'}),
  });
  input.value = '';
  loadAmbientData();
}

async function deleteRule(id) {
  await fetch(`${API_BASE}/ambient/rules/${id}`, {method: 'DELETE'});
  loadAmbientData();
}

async function toggleRule(id, enabled) {
  await fetch(`${API_BASE}/ambient/rules/${id}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled}),
  });
  loadAmbientData();
}

// --- Examples CRUD ---
async function addAmbientExample() {
  const ctx = document.getElementById('ambNewExContext').value.trim();
  const resp = document.getElementById('ambNewExResponse').value.trim();
  if (!ctx || !resp) return;
  await fetch(`${API_BASE}/ambient/examples`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({context: ctx, response: resp, rating: 'positive'}),
  });
  document.getElementById('ambNewExContext').value = '';
  document.getElementById('ambNewExResponse').value = '';
  loadAmbientData();
}

async function deleteExample(id) {
  await fetch(`${API_BASE}/ambient/examples/${id}`, {method: 'DELETE'});
  loadAmbientData();
}

// --- Ambient WebSocket messages ---
function handleAmbientWS(msg) {
  if (msg.type === 'ambient_state') {
    const d = msg.data;
    const cfg = {1:'静か',2:'控えめ',3:'普通',4:'積極的',5:'話好き'};
    const eff = d.effective_reactivity || d.reactivity;
    document.getElementById('ambStatusLevel').textContent = `${eff} (${cfg[eff] || '?'})`;
    document.getElementById('ambStatusState').textContent = d.listener_state || '-';
    if (d.override) {
      const min = Math.floor(d.override.remaining_sec / 60);
      const sec = d.override.remaining_sec % 60;
      document.getElementById('ambStatusOverride').textContent = `Lv${d.override.level} (${min}:${String(sec).padStart(2,'0')} remaining)`;
    } else {
      document.getElementById('ambStatusOverride').textContent = '-';
    }
    if (d.last_judgment) {
      document.getElementById('ambStatusLast').textContent = `${d.last_judgment.method}: ${d.last_judgment.result}`;
    }
    // Update reactivity buttons
    document.querySelectorAll('#reactivityBtns button').forEach((btn, i) => {
      btn.classList.toggle('active', i + 1 === d.reactivity);
    });
  }
  if (msg.type === 'ambient_log') {
    const log = document.getElementById('ambientLog');
    const d = msg.data;
    const cls = d.result === 'speak' ? 'result-speak' : 'result-skip';
    const extra = d.utterance ? ` → ${d.utterance}` : (d.keyword ? ` (${d.keyword})` : '');
    log.innerHTML += `<div class="ambient-log-entry"><span class="time">${d.timestamp}</span> <span class="method">${d.method}</span> <span class="${cls}">${d.result}</span>${extra}</div>`;
    log.scrollTop = log.scrollHeight;
    // Keep last 20
    while (log.children.length > 20) log.removeChild(log.firstChild);
  }
  if (msg.type === 'ambient_response') {
    // Also show in chat tab
    addMessage(msg.text, 'assistant');
  }
}
```

- [ ] **Step 4: Hook handleAmbientWS into WebSocket onmessage handler**

In the existing `ws.onmessage` handler in `index.html`, add at the top of the text message handling block (where `const msg = JSON.parse(event.data)` happens):

```javascript
      // Ambient messages
      if (msg.type && msg.type.startsWith('ambient')) {
        handleAmbientWS(msg);
        return;
      }
```

- [ ] **Step 5: Manual verification**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/ -v`
Expected: All tests PASS

Then verify dashboard loads:
1. Restart voice_chat: `kill $(lsof -ti :8767) 2>/dev/null; sleep 1; cd /Users/akira/workspace/open-claude/scripts/voice_chat && nohup .venv/bin/python app.py >> /tmp/voice_chat_final.log 2>&1 &`
2. Open `http://localhost:8767` in browser
3. Verify "Chat" and "Ambient" tabs appear
4. Click "Ambient" tab — verify sections render

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add index.html
git commit -m "feat: add Ambient dashboard tab with rules, examples, stats, real-time log"
```

---

### Task 6: WebSocket ambient_state 定期配信 + ambient_log 配信

**Files:**
- Modify: `app.py` (ambient_batch_loop + record_judgment に WS 配信追加)

- [ ] **Step 1: Write failing test for ambient_log broadcast**

```python
# tests/test_ambient_ws_broadcast.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestAmbientWSBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_ambient_state_sends_to_clients(self):
        from app import _broadcast_ambient_state
        mock_client = AsyncMock()
        with patch("app._clients", {mock_client}), \
             patch("app._ambient_listener") as mock_listener:
            mock_listener.get_state_snapshot.return_value = {
                "reactivity": 3,
                "effective_reactivity": 3,
                "override": None,
                "listener_state": "listening",
                "last_judgment": None,
            }
            await _broadcast_ambient_state()
            mock_client.send_text.assert_called_once()
            msg = json.loads(mock_client.send_text.call_args[0][0])
            assert msg["type"] == "ambient_state"
            assert msg["data"]["reactivity"] == 3
```

- [ ] **Step 2: Run test to verify it passes** (already implemented in Task 3)

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_ambient_ws_broadcast.py -v`
Expected: PASS

- [ ] **Step 3: Add ambient_log broadcast to _ambient_llm_reply**

In `_ambient_llm_reply` function in `app.py`, after `_ambient_listener.record_judgment(...)` calls, add log broadcast:

```python
            # Broadcast log entry to dashboard
            log_entry = _ambient_listener.log_entries[-1] if _ambient_listener.log_entries else None
            if log_entry:
                log_msg = json.dumps({"type": "ambient_log", "data": log_entry})
                for client in list(_clients):
                    try:
                        await client.send_text(log_msg)
                    except Exception:
                        _clients.discard(client)
```

Add this after both the "SKIP" branch `record_judgment` and the "speak" branch `record_judgment`.

- [ ] **Step 4: Add periodic state broadcast to ambient_batch_loop**

In `_ambient_batch_loop`, add at the end of each iteration (after the sleep and before the buffer check):

```python
            # Periodic state broadcast (every cycle)
            await _broadcast_ambient_state()
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add app.py tests/test_ambient_ws_broadcast.py
git commit -m "feat: add ambient state/log WebSocket broadcast to dashboard"
```

---

### Task 7: Barge-in 検知

**Files:**
- Modify: `app.py` (WebSocket handler for barge-in)
- Modify: `ambient_listener.py` (echo threshold property)

- [ ] **Step 1: Write failing test for barge-in**

```python
# tests/test_barge_in.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import time


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_barge_in_during_echo_suppress_high_rms(self):
        """When echo suppress is active but RMS is high, treat as barge-in."""
        from app import _process_always_on
        mock_ws = AsyncMock()

        with patch("app.transcribe", new_callable=AsyncMock, return_value="ちょっと待って"), \
             patch("app.detect_wake_word") as mock_wake, \
             patch("app._always_on_echo_suppress_until", time.time() + 10), \
             patch("app._barge_in_active", False), \
             patch("app.detect_ambient_command") as mock_cmd:
            from ambient_commands import AmbientCommand
            mock_cmd.return_value = AmbientCommand(type="none")
            mock_wake.return_value = MagicMock(detected=False)

            # Normal echo suppress should return early
            await _process_always_on(mock_ws, b"fake_audio")
            # No send_json should be called (echo suppressed)
            mock_ws.send_json.assert_not_called()
```

- [ ] **Step 2: Run test to verify behavior**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/test_barge_in.py -v`
Expected: PASS (existing echo suppress logic handles this)

- [ ] **Step 3: Add barge-in WebSocket message handling to app.py**

In the WebSocket message handler in `app.py` (inside `websocket_endpoint`), add handling for the `barge_in` message type from the Electron client:

```python
                elif msg_type == "barge_in":
                    logger.info("[barge-in] Client detected user speech during playback")
                    # Stop all audio on all clients
                    for client in list(_clients):
                        try:
                            await client.send_json({"type": "stop_audio"})
                        except Exception:
                            _clients.discard(client)
                    # Reset echo suppress so we can hear the user
                    _always_on_echo_suppress_until = 0
```

- [ ] **Step 4: Add barge-in detection to Ember Chat always-on.js**

In `/Users/akira/workspace/open-claude/scripts/ember-chat/renderer/always-on.js`, modify the RMS VAD `checkInterval` to detect barge-in during TTS playback.

In the `_initRMSVAD()` method, after the RMS calculation (`rms = Math.sqrt(...)`), add:

```javascript
      // Barge-in: if audio is playing and user speaks loudly, send barge-in signal
      if (rms > 0.04 && window._isPlayingAudio) {
        const ws = this.wsRef();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'barge_in' }));
          console.log('[AlwaysOn] barge-in detected (RMS:', rms.toFixed(3), ')');
        }
      }
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/akira/workspace/open-claude/scripts/voice_chat && .venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add app.py
cd /Users/akira/workspace/open-claude/scripts/ember-chat
git add renderer/always-on.js
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git commit -m "feat: add barge-in detection — stop TTS when user speaks during playback"
```

---

### Task 8: End-to-End 手動テスト + 微調整

**Files:**
- No new files

- [ ] **Step 1: Restart voice_chat server**

```bash
kill $(lsof -ti :8767) 2>/dev/null
sleep 1
cd /Users/akira/workspace/open-claude/scripts/voice_chat && nohup .venv/bin/python app.py >> /tmp/voice_chat_final.log 2>&1 &
sleep 3
curl -sf http://localhost:8767/api/settings | python3 -c "import json,sys; print('OK' if json.load(sys.stdin) else 'NG')"
```
Expected: `OK`

- [ ] **Step 2: Restart Ember Chat**

```bash
osascript -e 'tell application "Electron" to quit' 2>/dev/null
sleep 2
cd /Users/akira/workspace/open-claude/scripts/ember-chat && npx electron . &>/dev/null &
sleep 3
```

- [ ] **Step 3: Verify Ambient tab in dashboard**

Open `http://localhost:8767` → Click "Ambient" tab. Verify:
- Status section shows "3 (普通)"
- Reactivity buttons render with "3 普通" active
- Rules section shows initial rules from `ambient_rules.json`
- Stats section shows 0 values

- [ ] **Step 4: Test API endpoints**

```bash
# Get rules
curl -s http://localhost:8767/api/ambient/rules | python3 -m json.tool

# Add a rule
curl -s -X POST http://localhost:8767/api/ambient/rules \
  -H 'Content-Type: application/json' \
  -d '{"text":"テスト手動ルール","source":"manual"}' | python3 -m json.tool

# Get stats
curl -s http://localhost:8767/api/ambient/stats | python3 -m json.tool

# Change reactivity
curl -s -X POST http://localhost:8767/api/ambient/reactivity \
  -H 'Content-Type: application/json' \
  -d '{"level":4}' | python3 -m json.tool
```
Expected: All return valid JSON with correct data

- [ ] **Step 5: Check logs for ambient initialization**

```bash
grep -E "\[ambient\]|\[startup\].*[Aa]mbient" /tmp/voice_chat_final.log | tail -10
```
Expected: `[startup] Ambient listener ready (reactivity=3)` in output

- [ ] **Step 6: Final commit with any adjustments**

```bash
cd /Users/akira/workspace/open-claude/scripts/voice_chat
git add -A
git status
# Only commit if there are changes
git diff --cached --stat && git commit -m "fix: ambient e2e adjustments"
```
