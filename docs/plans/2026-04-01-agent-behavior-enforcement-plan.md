# Agent Behavior Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cogmem に Hook ベースのリアルタイム警告と Watch ベースの事後検知を追加し、エージェントの行動ルール遵守を設定駆動で強制する

**Architecture:** `cogmem.toml` の `[behavior]` セクションと `[[skill_triggers]]` 配列で設定を定義。`cogmem hook` サブコマンドが Claude Code hooks から呼ばれ、`cogmem watch` が wrap 時に同じ設定を参照してギャップを検出する。

**Tech Stack:** Python 3.9+, argparse, sqlite3, fnmatch, tomllib

**Spec:** `docs/plans/2026-04-01-agent-behavior-enforcement.md`

---

### Task 1: CogMemConfig に behavior 設定を追加

**Files:**
- Modify: `src/cognitive_memory/config.py:75-138` (CogMemConfig dataclass)
- Modify: `src/cognitive_memory/config.py:239-329` (from_toml)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py に追加

def test_behavior_defaults(tmp_path):
    """behavior セクション未定義でもデフォルト値が設定される"""
    toml_file = tmp_path / "cogmem.toml"
    toml_file.write_text('[cogmem]\nlogs_dir = "memory/logs"\n')
    config = CogMemConfig.from_toml(toml_file)
    assert config.consecutive_failure_threshold == 2
    assert config.skill_triggers == []
    assert config.skill_gate_enabled is True


def test_behavior_from_toml(tmp_path):
    """behavior セクションが正しく読み込まれる"""
    toml_file = tmp_path / "cogmem.toml"
    toml_file.write_text('''[cogmem]
logs_dir = "memory/logs"

[cogmem.behavior]
consecutive_failure_threshold = 3
skill_gate = false

[[cogmem.skill_triggers]]
pattern = "src/dashboard/**"
skills = ["tdd-dashboard-dev"]

[[cogmem.skill_triggers]]
pattern = "cron-jobs.json"
skills = ["cron-automation"]
''')
    config = CogMemConfig.from_toml(toml_file)
    assert config.consecutive_failure_threshold == 3
    assert config.skill_gate_enabled is False
    assert len(config.skill_triggers) == 2
    assert config.skill_triggers[0]["pattern"] == "src/dashboard/**"
    assert config.skill_triggers[0]["skills"] == ["tdd-dashboard-dev"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_config.py::test_behavior_defaults tests/test_config.py::test_behavior_from_toml -v`
Expected: FAIL with `AttributeError: 'CogMemConfig' object has no attribute 'consecutive_failure_threshold'`

- [ ] **Step 3: Add fields to CogMemConfig dataclass**

```python
# config.py — CogMemConfig dataclass 内、skills_auto_improve の後に追加

    # Behavior enforcement
    consecutive_failure_threshold: int = 2
    skill_gate_enabled: bool = True
    skill_triggers: list = field(default_factory=list)
```

- [ ] **Step 4: Parse behavior section in from_toml**

```python
# config.py — from_toml 内、skills = section.get("skills", {}) の後に追加

        behavior = section.get("behavior", {})
        skill_triggers_raw = section.get("skill_triggers", [])
```

```python
# config.py — cls() 呼び出し内、skills_auto_improve の後に追加

            consecutive_failure_threshold=behavior.get(
                "consecutive_failure_threshold", 2
            ),
            skill_gate_enabled=behavior.get("skill_gate", True),
            skill_triggers=skill_triggers_raw,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/config.py tests/test_config.py && git commit -m "feat: add behavior enforcement config (skill_triggers, failure threshold)"
```

---

### Task 2: SkillsStore に skill_triggers 照合ロジックを追加

**Files:**
- Modify: `src/cognitive_memory/skills/store.py`
- Test: `tests/test_skills_audit_ingest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_skills_audit_ingest.py に追加

class TestSkillTriggers:
    def test_get_all_triggers_merges_defaults_and_user(self, skills_manager):
        """組み込みデフォルト + ユーザー定義がマージされる"""
        user_triggers = [{"pattern": "dashboard/**", "skills": ["tdd"]}]
        triggers = skills_manager.store.get_all_triggers(user_triggers)
        # デフォルト2件 + ユーザー1件
        patterns = [t["pattern"] for t in triggers]
        assert ".claude/skills/**/SKILL.md" in patterns  # デフォルト
        assert "memory/logs/**" in patterns  # デフォルト
        assert "dashboard/**" in patterns  # ユーザー定義

    def test_match_triggers_finds_matching_skill(self, skills_manager):
        """ファイルパスにマッチするスキルが返される"""
        triggers = [
            {"pattern": "dashboard/templates/**", "skills": ["tdd-dashboard-dev"]},
            {"pattern": "cron-jobs.json", "skills": ["cron-automation"]},
        ]
        result = skills_manager.store.match_triggers(
            "dashboard/templates/skills/list.html", triggers
        )
        assert result == ["tdd-dashboard-dev"]

    def test_match_triggers_no_match(self, skills_manager):
        """マッチしない場合は空リスト"""
        triggers = [
            {"pattern": "dashboard/**", "skills": ["tdd"]},
        ]
        result = skills_manager.store.match_triggers("src/config.py", triggers)
        assert result == []

    def test_check_skill_gaps_detects_unused(self, skills_manager):
        """skill_start がないスキルがギャップとして検出される"""
        triggers = [
            {"pattern": "dashboard/**", "skills": ["tdd-dashboard-dev"]},
        ]
        edited_files = ["dashboard/templates/list.html", "dashboard/i18n.py"]
        gaps = skills_manager.store.check_skill_gaps(edited_files, triggers)
        assert len(gaps) == 1
        assert gaps[0]["expected_skill"] == "tdd-dashboard-dev"

    def test_check_skill_gaps_no_gap_when_used(self, skills_manager):
        """skill_start がある場合はギャップなし"""
        # skill_start を記録
        skills_manager.store.add_session_event(
            skill_name="tdd-dashboard-dev",
            event_type="skill_start",
            description="test",
        )
        triggers = [
            {"pattern": "dashboard/**", "skills": ["tdd-dashboard-dev"]},
        ]
        gaps = skills_manager.store.check_skill_gaps(
            ["dashboard/templates/list.html"], triggers
        )
        assert len(gaps) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_skills_audit_ingest.py::TestSkillTriggers -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add default triggers constant and methods to SkillsStore**

```python
# store.py — クラス定数として追加（_SITUATIONAL_KEYWORDS の近くに）

_DEFAULT_SKILL_TRIGGERS = [
    {"pattern": ".claude/skills/**/SKILL.md", "skills": ["skill-improve"]},
    {"pattern": "memory/logs/**", "skills": ["live-logging"]},
]
```

```python
# store.py — SkillsStore クラス内に追加

@classmethod
def get_all_triggers(cls, user_triggers: list[dict] | None = None) -> list[dict]:
    """Merge default and user-defined skill triggers."""
    triggers = list(cls._DEFAULT_SKILL_TRIGGERS)
    if user_triggers:
        triggers.extend(user_triggers)
    return triggers

@staticmethod
def match_triggers(file_path: str, triggers: list[dict]) -> list[str]:
    """Return skill names that match the given file path."""
    from fnmatch import fnmatch
    matched_skills: list[str] = []
    for trigger in triggers:
        if fnmatch(file_path, trigger["pattern"]):
            for skill in trigger["skills"]:
                if skill not in matched_skills:
                    matched_skills.append(skill)
    return matched_skills

def check_skill_gaps(
    self, edited_files: list[str], triggers: list[dict]
) -> list[dict]:
    """Check which expected skills were not used today."""
    import sqlite3
    expected_skills: dict[str, str] = {}  # skill_name -> first matching file
    for f in edited_files:
        for skill in self.match_triggers(f, triggers):
            if skill not in expected_skills:
                expected_skills[skill] = f

    if not expected_skills:
        return []

    gaps = []
    with sqlite3.connect(self.db_path) as conn:
        for skill_name, example_file in expected_skills.items():
            row = conn.execute(
                "SELECT 1 FROM skill_session_events "
                "WHERE skill_name = ? AND event_type = 'skill_start' "
                "AND date(timestamp, 'localtime') = date('now', 'localtime')",
                (skill_name,),
            ).fetchone()
            if row is None:
                gaps.append({
                    "file": example_file,
                    "expected_skill": skill_name,
                    "reason": "skill_start not found for today",
                })
    return gaps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_skills_audit_ingest.py::TestSkillTriggers -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/skills/store.py tests/test_skills_audit_ingest.py && git commit -m "feat: add skill_triggers matching and gap detection to SkillsStore"
```

---

### Task 3: cogmem hook サブコマンド — failure-breaker

**Files:**
- Create: `src/cognitive_memory/cli/hook_cmd.py`
- Modify: `src/cognitive_memory/cli/main.py`
- Test: `tests/test_hook.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hook.py（新規作成）
"""Tests for cogmem hook subcommands."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cognitive_memory.cli.hook_cmd import run_failure_breaker


class TestFailureBreaker:
    @pytest.fixture(autouse=True)
    def setup_state_dir(self, tmp_path):
        """一時ディレクトリを状態管理用に使う"""
        self.state_file = tmp_path / "cogmem-failure-count"
        with patch.dict(os.environ, {"COGMEM_HOOK_STATE": str(self.state_file)}):
            yield

    def test_first_failure_no_warning(self, tmp_path, capsys):
        """1回目の失敗では警告しない（閾値=2）"""
        hook_input = {"tool_name": "Bash", "tool_result": {"exit_code": 1}}
        with patch.dict(os.environ, {"COGMEM_HOOK_STATE": str(self.state_file)}):
            run_failure_breaker(hook_input, threshold=2)
        assert capsys.readouterr().err == ""

    def test_consecutive_failures_warns(self, tmp_path, capsys):
        """閾値到達で stderr に警告を出力"""
        hook_input = {"tool_name": "Bash", "tool_result": {"exit_code": 1}}
        with patch.dict(os.environ, {"COGMEM_HOOK_STATE": str(self.state_file)}):
            run_failure_breaker(hook_input, threshold=2)
            run_failure_breaker(hook_input, threshold=2)
        err = capsys.readouterr().err
        assert "2回連続で失敗" in err
        assert "根本原因" in err

    def test_success_resets_counter(self, tmp_path, capsys):
        """成功でカウンタリセット"""
        fail_input = {"tool_name": "Bash", "tool_result": {"exit_code": 1}}
        ok_input = {"tool_name": "Bash", "tool_result": {"exit_code": 0}}
        with patch.dict(os.environ, {"COGMEM_HOOK_STATE": str(self.state_file)}):
            run_failure_breaker(fail_input, threshold=2)
            run_failure_breaker(ok_input, threshold=2)
            run_failure_breaker(fail_input, threshold=2)
        # リセット後の1回目なので警告なし
        assert capsys.readouterr().err == ""

    def test_warns_every_threshold(self, tmp_path, capsys):
        """閾値の倍数でも警告が出る"""
        hook_input = {"tool_name": "Bash", "tool_result": {"exit_code": 1}}
        with patch.dict(os.environ, {"COGMEM_HOOK_STATE": str(self.state_file)}):
            for _ in range(4):
                run_failure_breaker(hook_input, threshold=2)
        err = capsys.readouterr().err
        assert err.count("連続で失敗") == 2  # 2回目と4回目
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_hook.py::TestFailureBreaker -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement hook_cmd.py — failure-breaker**

```python
# src/cognitive_memory/cli/hook_cmd.py（新規作成）
"""cogmem hook — Claude Code hook handlers."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _get_state_file() -> Path:
    """Get the state file path for failure counter."""
    override = os.environ.get("COGMEM_HOOK_STATE")
    if override:
        return Path(override)
    ppid = os.getppid()
    return Path(f"/tmp/cogmem-failure-count-{ppid}")


def run_failure_breaker(hook_input: dict, threshold: int = 2) -> None:
    """Handle PostToolUse Bash — detect consecutive failures."""
    exit_code = hook_input.get("tool_result", {}).get("exit_code", 0)

    state_file = _get_state_file()

    if exit_code == 0:
        # Success: reset counter
        if state_file.exists():
            state_file.unlink()
        return

    # Failure: increment counter
    count = 0
    if state_file.exists():
        try:
            count = int(state_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    count += 1
    state_file.write_text(str(count))

    if count >= threshold and count % threshold == 0:
        msg = (
            f"\u26a0 コマンドが{count}回連続で失敗しています。\n"
            "1. 同じアプローチを繰り返さず、エラーメッセージを読んで根本原因を特定してください\n"
            "2. 環境要因（パス、権限、プロセス状態）を先に排除してください\n"
            "3. 解決後、再発防止策を検討してください:\n"
            "   - 既存スキルに手順追加が必要 → cogmem skills track で extra_step を記録\n"
            "   - 新しいパターン → cogmem skills suggest で記録"
        )
        print(msg, file=sys.stderr)


def run_hook(args) -> None:
    """Entry point for cogmem hook subcommands."""
    hook_input = json.load(sys.stdin)

    if args.hook_command == "failure-breaker":
        try:
            from ..config import CogMemConfig
            config = CogMemConfig.find_and_load()
            threshold = config.consecutive_failure_threshold
        except Exception:
            threshold = 2
        run_failure_breaker(hook_input, threshold=threshold)
    elif args.hook_command == "skill-gate":
        run_skill_gate(hook_input)
    else:
        pass  # Unknown hook, silently ignore
```

- [ ] **Step 4: Register hook subcommand in main.py**

```python
# main.py — wrap の後（identity の前あたり）に追加

    # hook subcommand group
    hook_parser = subparsers.add_parser("hook", help="Claude Code hook handlers")
    hook_subparsers = hook_parser.add_subparsers(dest="hook_command")
    hook_subparsers.add_parser("failure-breaker", help="Detect consecutive command failures")
    hook_subparsers.add_parser("skill-gate", help="Check skill usage for edited files")
```

```python
# main.py — コマンドディスパッチに追加

    elif args.command == "hook":
        from .hook_cmd import run_hook
        run_hook(args)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_hook.py::TestFailureBreaker -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/cli/hook_cmd.py src/cognitive_memory/cli/main.py tests/test_hook.py && git commit -m "feat: add cogmem hook failure-breaker"
```

---

### Task 4: cogmem hook サブコマンド — skill-gate

**Files:**
- Modify: `src/cognitive_memory/cli/hook_cmd.py`
- Test: `tests/test_hook.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_hook.py に追加

class TestSkillGate:
    @pytest.fixture
    def config_dir(self, tmp_path):
        """cogmem.toml + skills.db がある一時ディレクトリ"""
        toml = tmp_path / "cogmem.toml"
        toml.write_text('''[cogmem]
logs_dir = "memory/logs"

[[cogmem.skill_triggers]]
pattern = "dashboard/templates/**"
skills = ["tdd-dashboard-dev"]
''')
        (tmp_path / "memory").mkdir()
        return tmp_path

    def test_warns_when_skill_not_used(self, config_dir, capsys, monkeypatch):
        """スキル未使用時に警告が出る"""
        monkeypatch.chdir(config_dir)
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(config_dir / "dashboard/templates/list.html")},
        }
        from cognitive_memory.cli.hook_cmd import run_skill_gate
        run_skill_gate(hook_input, base_dir=str(config_dir))
        err = capsys.readouterr().err
        assert "tdd-dashboard-dev" in err
        assert "未使用" in err

    def test_no_warn_when_skill_used(self, config_dir, capsys, monkeypatch):
        """skill_start 記録済みなら警告なし"""
        monkeypatch.chdir(config_dir)
        from cognitive_memory.config import CogMemConfig
        from cognitive_memory.skills.store import SkillsStore
        config = CogMemConfig.from_toml(config_dir / "cogmem.toml")
        store = SkillsStore(config)
        store.add_session_event(
            skill_name="tdd-dashboard-dev",
            event_type="skill_start",
            description="test",
        )
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(config_dir / "dashboard/templates/list.html")},
        }
        from cognitive_memory.cli.hook_cmd import run_skill_gate
        run_skill_gate(hook_input, base_dir=str(config_dir))
        assert capsys.readouterr().err == ""

    def test_no_warn_for_unmatched_file(self, config_dir, capsys, monkeypatch):
        """マッチしないファイルでは警告なし"""
        monkeypatch.chdir(config_dir)
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(config_dir / "src/main.py")},
        }
        from cognitive_memory.cli.hook_cmd import run_skill_gate
        run_skill_gate(hook_input, base_dir=str(config_dir))
        assert capsys.readouterr().err == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_hook.py::TestSkillGate -v`
Expected: FAIL with `ImportError: cannot import name 'run_skill_gate'`

- [ ] **Step 3: Implement run_skill_gate in hook_cmd.py**

```python
# hook_cmd.py に追加

def run_skill_gate(hook_input: dict, base_dir: str | None = None) -> None:
    """Handle PreToolUse Edit|Write — check skill usage for the file."""
    file_path = hook_input.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return

    try:
        from ..config import CogMemConfig
        from ..skills.store import SkillsStore

        config = CogMemConfig.find_and_load(start_dir=base_dir)
        store = SkillsStore(config)

        # Make file_path relative to base_dir for matching
        try:
            rel_path = str(Path(file_path).relative_to(config._base_dir))
        except ValueError:
            rel_path = file_path

        triggers = store.get_all_triggers(config.skill_triggers)
        matched_skills = store.match_triggers(rel_path, triggers)

        if not matched_skills:
            return

        # Check which matched skills have skill_start today
        gaps = store.check_skill_gaps([rel_path], triggers)
        for gap in gaps:
            msg = (
                f"\u26a0 このファイルに関連するスキル [{gap['expected_skill']}] "
                "が未使用です。先にスキルを確認してください。"
            )
            print(msg, file=sys.stderr)
    except Exception:
        pass  # Hook must never break the editor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_hook.py::TestSkillGate -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/cli/hook_cmd.py tests/test_hook.py && git commit -m "feat: add cogmem hook skill-gate"
```

---

### Task 5: cogmem watch 拡張 — skill_gaps 検出

**Files:**
- Modify: `src/cognitive_memory/cli/watch_cmd.py`
- Modify: `src/cognitive_memory/watch.py`
- Test: `tests/test_watch.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_watch.py に追加

class TestSkillGapDetection:
    def test_watch_includes_skill_gaps(self, tmp_path, monkeypatch):
        """watch --json 出力に skill_gaps が含まれる"""
        # cogmem.toml を作成
        toml = tmp_path / "cogmem.toml"
        toml.write_text('''[cogmem]
logs_dir = "memory/logs"

[[cogmem.skill_triggers]]
pattern = "dashboard/**"
skills = ["tdd-dashboard-dev"]
''')
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "logs").mkdir()
        monkeypatch.chdir(tmp_path)

        # git init + 変更ファイルを模擬
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        # dashboard/templates/list.html をコミット
        (tmp_path / "dashboard" / "templates").mkdir(parents=True)
        (tmp_path / "dashboard" / "templates" / "list.html").write_text("<h1>test</h1>")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: add dashboard"], cwd=tmp_path, capture_output=True)

        from cognitive_memory.watch import get_changed_files_since
        files = get_changed_files_since("1 day ago", str(tmp_path))
        assert "dashboard/templates/list.html" in files

    def test_watch_json_includes_skill_gaps(self, tmp_path, monkeypatch):
        """watch --json の出力に skill_gaps が含まれる"""
        import subprocess
        toml = tmp_path / "cogmem.toml"
        toml.write_text('''[cogmem]
logs_dir = "memory/logs"

[[cogmem.skill_triggers]]
pattern = "dashboard/**"
skills = ["tdd-dashboard-dev"]
''')
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "logs").mkdir()
        monkeypatch.chdir(tmp_path)

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "dashboard").mkdir()
        (tmp_path / "dashboard" / "x.html").write_text("test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: dash"], cwd=tmp_path, capture_output=True)

        from cognitive_memory.cli.watch_cmd import run_watch
        import io, contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            run_watch(since="1 day ago", json_output=True)
        import json
        output = json.loads(f.getvalue())
        assert "skill_gaps" in output
        assert any(g["expected_skill"] == "tdd-dashboard-dev" for g in output["skill_gaps"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_watch.py::TestSkillGapDetection -v`
Expected: FAIL with `ImportError: cannot import name 'get_changed_files_since'`

- [ ] **Step 3: Add get_changed_files_since to watch.py**

```python
# watch.py に追加

def get_changed_files_since(since: str, cwd: str = ".") -> list[str]:
    """Get list of files changed in commits since the given time + staged changes."""
    import subprocess
    files: set[str] = set()

    # Committed changes
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--name-only", "--pretty=format:"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                files.add(line.strip())

    # Staged but uncommitted
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                files.add(line.strip())

    return sorted(files)
```

- [ ] **Step 4: Integrate skill_gaps into watch_cmd.py output**

```python
# watch_cmd.py — run_watch 関数内、analysis["log_gap"] = gap の後に追加

    # Skill gap detection
    from ..watch import get_changed_files_since
    from ..skills.store import SkillsStore
    changed_files = get_changed_files_since(since, config._base_dir)
    skill_gaps = []
    if changed_files:
        try:
            store = SkillsStore(config)
            triggers = store.get_all_triggers(config.skill_triggers)
            skill_gaps = store.check_skill_gaps(changed_files, triggers)
        except Exception:
            pass
    analysis["skill_gaps"] = skill_gaps
```

```python
# watch_cmd.py — テキスト出力部分に追加（gap 表示の後）

        if skill_gaps:
            for sg in skill_gaps:
                print(f"  ⚠ Skill gap: [{sg['expected_skill']}] not used (file: {sg['file']})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_watch.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/watch.py src/cognitive_memory/cli/watch_cmd.py tests/test_watch.py && git commit -m "feat: add skill_gaps detection to cogmem watch"
```

---

### Task 6: cogmem init — hooks 自動セットアップ

**Files:**
- Modify: `src/cognitive_memory/cli/init_cmd.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py に追加

def test_init_creates_settings_json_hooks(tmp_path, monkeypatch):
    """cogmem init が .claude/settings.json に hooks を登録する"""
    monkeypatch.chdir(tmp_path)
    from cognitive_memory.cli.init_cmd import setup_hooks
    settings_dir = tmp_path / ".claude"
    setup_hooks(str(settings_dir))

    settings_file = settings_dir / "settings.json"
    assert settings_file.exists()
    import json
    settings = json.loads(settings_file.read_text())
    assert "hooks" in settings
    assert "PreToolUse" in settings["hooks"]
    assert "PostToolUse" in settings["hooks"]
    # matcher の確認
    pre = settings["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "Edit|Write"
    assert "cogmem hook skill-gate" in pre["command"]


def test_init_merges_existing_settings_json(tmp_path, monkeypatch):
    """既存の settings.json がある場合はマージする"""
    monkeypatch.chdir(tmp_path)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text('{"existing_key": true}')

    from cognitive_memory.cli.init_cmd import setup_hooks
    setup_hooks(str(settings_dir))

    import json
    settings = json.loads(settings_file.read_text())
    assert settings["existing_key"] is True
    assert "hooks" in settings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_cli.py::test_init_creates_settings_json_hooks tests/test_cli.py::test_init_merges_existing_settings_json -v`
Expected: FAIL with `ImportError: cannot import name 'setup_hooks'`

- [ ] **Step 3: Implement setup_hooks in init_cmd.py**

```python
# init_cmd.py に追加

def setup_hooks(settings_dir: str) -> None:
    """Register cogmem hooks in .claude/settings.json."""
    import json
    settings_path = Path(settings_dir) / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    hooks = settings.setdefault("hooks", {})

    # Add skill-gate hook (PreToolUse)
    pre_hooks = hooks.setdefault("PreToolUse", [])
    if not any("cogmem hook skill-gate" in h.get("command", "") for h in pre_hooks):
        pre_hooks.append({
            "matcher": "Edit|Write",
            "command": "cogmem hook skill-gate",
        })

    # Add failure-breaker hook (PostToolUse)
    post_hooks = hooks.setdefault("PostToolUse", [])
    if not any("cogmem hook failure-breaker" in h.get("command", "") for h in post_hooks):
        post_hooks.append({
            "matcher": "Bash",
            "command": "cogmem hook failure-breaker",
        })

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 4: Call setup_hooks from run_init**

```python
# init_cmd.py — run_init 関数の末尾（.gitignore 更新後）に追加

    # Setup Claude Code hooks
    claude_dir = Path(target_dir) / ".claude"
    setup_hooks(str(claude_dir))
    print(f"  hooks → {claude_dir / 'settings.json'}")
```

- [ ] **Step 5: Add behavior section to scaffold template**

`src/cognitive_memory/templates/cogmem.toml` の末尾に追加:

```toml
[cogmem.behavior]
consecutive_failure_threshold = 2
# skill_gate = true  # デフォルト有効

# ファイル編集時にスキル使用を促すトリガー設定
# [[cogmem.skill_triggers]]
# pattern = "src/components/**"
# skills = ["your-skill-name"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/cli/init_cmd.py tests/test_cli.py && git commit -m "feat: cogmem init auto-registers Claude Code hooks"
```

---

### Task 7: 結合テスト & editable install

**Files:**
- Test: `tests/test_hook.py`

- [ ] **Step 1: Write end-to-end test**

```python
# tests/test_hook.py に追加

class TestHookEndToEnd:
    def test_failure_breaker_via_cli(self, tmp_path):
        """CLI 経由で failure-breaker が動作する"""
        import subprocess
        hook_input = json.dumps({
            "tool_name": "Bash",
            "tool_result": {"exit_code": 1},
        })
        env = os.environ.copy()
        env["COGMEM_HOOK_STATE"] = str(tmp_path / "state")

        # 1回目: 警告なし
        r1 = subprocess.run(
            ["cogmem", "hook", "failure-breaker"],
            input=hook_input, capture_output=True, text=True, env=env,
        )
        assert r1.returncode == 0
        assert r1.stderr == ""

        # 2回目: 警告あり
        r2 = subprocess.run(
            ["cogmem", "hook", "failure-breaker"],
            input=hook_input, capture_output=True, text=True, env=env,
        )
        assert r2.returncode == 0
        assert "連続で失敗" in r2.stderr
```

- [ ] **Step 2: Run editable install**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && pip3 install -e .`

- [ ] **Step 3: Run end-to-end test**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_hook.py::TestHookEndToEnd -v`
Expected: ALL PASS

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -x -q`
Expected: 508+ tests pass, 0 failures

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add tests/test_hook.py && git commit -m "test: add end-to-end hook tests"
```

---

### Task 8: Akira のプロジェクトに skill_triggers を設定

**Files:**
- Modify: `/Users/akira/workspace/open-claude/cogmem.toml`

- [ ] **Step 1: Add behavior section and skill_triggers**

```toml
# cogmem.toml に追加

[cogmem.behavior]
consecutive_failure_threshold = 2

[[cogmem.skill_triggers]]
pattern = "dashboard/templates/**"
skills = ["tdd-dashboard-dev"]

[[cogmem.skill_triggers]]
pattern = "dashboard/services/**"
skills = ["tdd-dashboard-dev"]

[[cogmem.skill_triggers]]
pattern = "dashboard/i18n.py"
skills = ["tdd-dashboard-dev"]

[[cogmem.skill_triggers]]
pattern = "cron-jobs.json"
skills = ["cron-automation"]

# 注: .claude/skills/**/SKILL.md → skill-improve は _DEFAULT_SKILL_TRIGGERS に含まれるため不要
```

- [ ] **Step 2: Verify cogmem loads the config**

Run: `cd /Users/akira/workspace/open-claude && python3 -c "from cognitive_memory.config import CogMemConfig; c = CogMemConfig.find_and_load(); print(f'threshold={c.consecutive_failure_threshold}, triggers={len(c.skill_triggers)}')"` 
Expected: `threshold=2, triggers=4`

- [ ] **Step 3: Setup hooks in settings.json**

Run: `cd /Users/akira/workspace/open-claude && python3 -c "from cognitive_memory.cli.init_cmd import setup_hooks; setup_hooks('.claude')"`

- [ ] **Step 4: Verify hooks are registered**

Read `.claude/settings.json` and confirm `hooks.PreToolUse` and `hooks.PostToolUse` entries exist.

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/open-claude && git add cogmem.toml .claude/settings.json && git commit -m "feat: configure behavior enforcement hooks and skill_triggers"
```
