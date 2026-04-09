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
