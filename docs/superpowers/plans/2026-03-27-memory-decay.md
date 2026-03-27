# Memory Decay（記憶の忘却）実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 記憶の定着（consolidation）完了後に、人間の忘却メカニズムに基づいて詳細ログを自動削除/圧縮する機能を実装する

**Architecture:** cogmem.toml に decay 設定を追加し、consolidation 実行時に各エントリの arousal / recall_count / last_recalled を評価して詳細ログの保持/削除を判定する。ダッシュボードの記憶の定着ページに設定 UI を追加する。

**Tech Stack:** Python, FastAPI, Jinja2, HTMX, SQLite, pytest

---

## 忘却ルール

| 条件 | 処理 | 人間の対応 |
|---|---|---|
| Arousal >= 0.7 | 詳細を残す | 鮮烈な体験は長期保持 |
| recall_count >= 2 かつ 直近18ヶ月に想起あり | 残す | 使う記憶は強化される |
| recall_count >= 2 かつ 直近18ヶ月に想起なし | 削除 | 使わない記憶は薄れる |
| 上記以外 | compact に圧縮、詳細削除 | 平凡な出来事は要点だけ残る |

---

## ファイル構成

| ファイル | 責務 |
|---|---|
| `src/cognitive_memory/decay.py` (新規) | 忘却ロジック（エントリ評価、ログ圧縮/削除） |
| `src/cognitive_memory/cli/decay_cmd.py` (新規) | `cogmem decay` CLI コマンド |
| `src/cognitive_memory/cli/__init__.py` (修正) | decay サブコマンド登録 |
| `src/cognitive_memory/templates/cogmem.toml` (修正) | `[cogmem.decay]` セクション追加 |
| `src/cognitive_memory/config.py` (修正) | decay 設定の読み込み |
| `src/cognitive_memory/dashboard/routes/consolidation.py` (修正) | 設定 UI エンドポイント追加 |
| `src/cognitive_memory/dashboard/services/consolidation_service.py` (修正) | decay 設定データ提供 |
| `src/cognitive_memory/dashboard/templates/consolidation/index.html` (修正) | 設定 UI 追加 |
| `src/cognitive_memory/dashboard/i18n.py` (修正) | 忘却関連の翻訳追加 |
| `tests/test_decay.py` (新規) | 忘却ロジックのテスト |
| `tests/dashboard/test_consolidation_decay.py` (新規) | ダッシュボード設定 UI のテスト |

---

### Task 1: cogmem.toml に decay 設定を追加

**Files:**
- Modify: `src/cognitive_memory/templates/cogmem.toml`
- Modify: `src/cognitive_memory/config.py`

- [ ] **Step 1: テンプレートに `[cogmem.decay]` セクションを追加**

```toml
[cogmem.decay]
arousal_threshold = 0.7          # この値以上の Arousal は詳細を永久保持
recall_threshold = 2             # この回数以上想起された記憶は保持候補
recall_window_months = 18        # この期間内に想起がなければ削除
enabled = true                   # false で忘却を無効化
```

- [ ] **Step 2: config.py に decay 設定の読み込みを追加**

`CogMemConfig` クラスに以下のフィールドを追加:
```python
decay_arousal_threshold: float = 0.7
decay_recall_threshold: int = 2
decay_recall_window_months: int = 18
decay_enabled: bool = True
```

`from_toml()` メソッドに `[cogmem.decay]` セクションの読み込みを追加。

- [ ] **Step 3: コミット**

```bash
git add src/cognitive_memory/templates/cogmem.toml src/cognitive_memory/config.py
git commit -m "feat: add [cogmem.decay] config section"
```

---

### Task 2: 忘却ロジックの実装（TDD）

**Files:**
- Create: `src/cognitive_memory/decay.py`
- Create: `tests/test_decay.py`

- [ ] **Step 1: テストファイルを作成**

```python
"""Tests for memory decay logic."""
import pytest
from datetime import datetime, timedelta
from cognitive_memory.decay import evaluate_entry, DecayAction


class TestEvaluateEntry:
    """Test evaluate_entry() returns correct decay action."""

    def test_high_arousal_always_kept(self):
        """Arousal >= threshold → KEEP regardless of recall."""
        action = evaluate_entry(
            arousal=0.8, recall_count=0, last_recalled=None,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.KEEP

    def test_arousal_at_threshold_kept(self):
        """Arousal exactly at threshold → KEEP."""
        action = evaluate_entry(
            arousal=0.7, recall_count=0, last_recalled=None,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.KEEP

    def test_recalled_recently_kept(self):
        """recall_count >= threshold and recalled within window → KEEP."""
        recent = (datetime.now() - timedelta(days=30)).isoformat()
        action = evaluate_entry(
            arousal=0.5, recall_count=3, last_recalled=recent,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.KEEP

    def test_recalled_but_stale_deleted(self):
        """recall_count >= threshold but no recall in 18 months → DELETE."""
        old = (datetime.now() - timedelta(days=600)).isoformat()
        action = evaluate_entry(
            arousal=0.5, recall_count=5, last_recalled=old,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.DELETE

    def test_low_arousal_low_recall_compacted(self):
        """Low arousal + low recall → COMPACT."""
        action = evaluate_entry(
            arousal=0.5, recall_count=0, last_recalled=None,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.COMPACT

    def test_recall_count_below_threshold_compacted(self):
        """recall_count=1 (below threshold) → COMPACT."""
        recent = (datetime.now() - timedelta(days=10)).isoformat()
        action = evaluate_entry(
            arousal=0.5, recall_count=1, last_recalled=recent,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.COMPACT

    def test_recalled_enough_but_never_recalled_deleted(self):
        """recall_count >= threshold but last_recalled is None → DELETE."""
        action = evaluate_entry(
            arousal=0.5, recall_count=2, last_recalled=None,
            arousal_threshold=0.7, recall_threshold=2, recall_window_months=18,
        )
        assert action == DecayAction.DELETE
```

- [ ] **Step 2: テスト実行 → 全 FAIL 確認**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib
pytest tests/test_decay.py -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: decay.py を実装**

```python
"""Memory decay logic — human-like forgetting mechanism."""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum


class DecayAction(Enum):
    KEEP = "keep"        # 詳細を残す（鮮烈な記憶 or 活発に想起）
    COMPACT = "compact"  # compact に圧縮して詳細削除
    DELETE = "delete"     # 詳細削除（compact 済みなら何もしない）


def evaluate_entry(
    arousal: float,
    recall_count: int,
    last_recalled: str | None,
    arousal_threshold: float = 0.7,
    recall_threshold: int = 2,
    recall_window_months: int = 18,
) -> DecayAction:
    """Evaluate whether a memory entry should be kept, compacted, or deleted.

    Rules (modeled after human memory):
    1. High arousal → always keep (vivid memories persist)
    2. Frequently recalled AND recently recalled → keep (active memories)
    3. Frequently recalled BUT not recalled in window → delete (faded memories)
    4. Everything else → compact (mundane events lose detail, keep gist)
    """
    # Rule 1: Vivid memories persist
    if arousal >= arousal_threshold:
        return DecayAction.KEEP

    # Rule 2 & 3: Recall-based retention
    if recall_count >= recall_threshold:
        if last_recalled is None:
            return DecayAction.DELETE
        last_dt = datetime.fromisoformat(last_recalled)
        window = datetime.now() - timedelta(days=recall_window_months * 30)
        if last_dt >= window:
            return DecayAction.KEEP
        return DecayAction.DELETE

    # Rule 4: Mundane memories → compact
    return DecayAction.COMPACT
```

- [ ] **Step 4: テスト実行 → 全 PASS 確認**

```bash
pytest tests/test_decay.py -v
```
Expected: 7 passed

- [ ] **Step 5: コミット**

```bash
git add src/cognitive_memory/decay.py tests/test_decay.py
git commit -m "feat: add memory decay logic with human-like forgetting rules"
```

---

### Task 3: decay コマンドでログファイルに適用

**Files:**
- Modify: `src/cognitive_memory/decay.py` (apply_decay 関数追加)
- Create: `src/cognitive_memory/cli/decay_cmd.py`
- Modify: `src/cognitive_memory/cli/__init__.py`
- Modify: `tests/test_decay.py` (統合テスト追加)

- [ ] **Step 1: apply_decay のテストを追加**

```python
class TestApplyDecay:
    """Test apply_decay() processes log files correctly."""

    def test_consolidated_log_with_low_arousal_gets_compacted(self, tmp_path):
        """Consolidated log with all low-arousal entries → compact created, detail removed."""
        log = tmp_path / "2026-01-01.md"
        log.write_text(
            "# 2026-01-01 セッションログ\n\n"
            "## セッション概要\nテスト\n\n"
            "## ログエントリ\n\n"
            "### [DECISION] テスト決定\n"
            "*Arousal: 0.5 | Emotion: Test*\n"
            "テスト内容\n\n---\n\n"
            "## 引き継ぎ\nなし\n"
        )
        from cognitive_memory.decay import apply_decay
        from cognitive_memory.config import CogMemConfig

        config = CogMemConfig()
        config.logs_path = str(tmp_path)
        config.last_checkpoint = "2026-01-15"  # consolidated after this log

        result = apply_decay(config, dry_run=False)
        assert result["compacted"] == 1
        assert (tmp_path / "2026-01-01.compact.md").exists()
        assert not (tmp_path / "2026-01-01.md").exists()

    def test_high_arousal_entry_preserves_detail(self, tmp_path):
        """Log with high-arousal entry → detail file preserved."""
        log = tmp_path / "2026-01-01.md"
        log.write_text(
            "# 2026-01-01 セッションログ\n\n"
            "## セッション概要\nテスト\n\n"
            "## ログエントリ\n\n"
            "### [ERROR] 重大エラー\n"
            "*Arousal: 0.9 | Emotion: Shock*\n"
            "重大な内容\n\n---\n\n"
            "## 引き継ぎ\nなし\n"
        )
        from cognitive_memory.decay import apply_decay
        from cognitive_memory.config import CogMemConfig

        config = CogMemConfig()
        config.logs_path = str(tmp_path)
        config.last_checkpoint = "2026-01-15"

        result = apply_decay(config, dry_run=False)
        assert result["kept"] >= 1
        assert (tmp_path / "2026-01-01.md").exists()

    def test_dry_run_does_not_modify(self, tmp_path):
        """dry_run=True → no files modified."""
        log = tmp_path / "2026-01-01.md"
        log.write_text(
            "# 2026-01-01 セッションログ\n\n"
            "## セッション概要\nテスト\n\n"
            "## ログエントリ\n\n"
            "### [DECISION] テスト\n"
            "*Arousal: 0.5 | Emotion: Test*\nテスト\n\n---\n\n"
            "## 引き継ぎ\nなし\n"
        )
        from cognitive_memory.decay import apply_decay
        from cognitive_memory.config import CogMemConfig

        config = CogMemConfig()
        config.logs_path = str(tmp_path)
        config.last_checkpoint = "2026-01-15"

        result = apply_decay(config, dry_run=True)
        assert (tmp_path / "2026-01-01.md").exists()  # not deleted

    def test_unconsolidated_log_skipped(self, tmp_path):
        """Log newer than last_checkpoint → skipped."""
        log = tmp_path / "2026-02-01.md"
        log.write_text("# 2026-02-01 セッションログ\n\n## ログエントリ\n")
        from cognitive_memory.decay import apply_decay
        from cognitive_memory.config import CogMemConfig

        config = CogMemConfig()
        config.logs_path = str(tmp_path)
        config.last_checkpoint = "2026-01-15"

        result = apply_decay(config, dry_run=False)
        assert result["skipped"] == 1
        assert (tmp_path / "2026-02-01.md").exists()
```

- [ ] **Step 2: テスト実行 → FAIL 確認**

- [ ] **Step 3: apply_decay() を decay.py に実装**

apply_decay の処理フロー:
1. logs_path のログファイル一覧を取得（.compact.md 除く）
2. last_checkpoint より古いファイルだけ処理（未定着はスキップ）
3. 各ファイルの全エントリを parse_entries() で解析
4. 各エントリを evaluate_entry() で判定
5. ファイル内の全エントリが COMPACT or DELETE → compact 生成 & 詳細削除
6. 1つでも KEEP → 詳細ファイルを残す
7. DB の recall_count / last_recalled を参照して判定に使う

- [ ] **Step 4: decay_cmd.py を作成**

```python
"""cogmem decay — apply memory forgetting to consolidated logs."""

def register(subparsers):
    p = subparsers.add_parser("decay", help="Apply memory decay to consolidated logs")
    p.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    p.add_argument("--json", action="store_true", help="Output results as JSON")
    p.set_defaults(func=run)

def run(args):
    ...
```

- [ ] **Step 5: cli/__init__.py に decay サブコマンドを登録**

- [ ] **Step 6: テスト実行 → 全 PASS 確認**

- [ ] **Step 7: コミット**

```bash
git add src/cognitive_memory/decay.py src/cognitive_memory/cli/decay_cmd.py src/cognitive_memory/cli/__init__.py tests/test_decay.py
git commit -m "feat: cogmem decay command — apply forgetting to consolidated logs"
```

---

### Task 4: ダッシュボードに decay 設定 UI を追加

**Files:**
- Modify: `src/cognitive_memory/dashboard/routes/consolidation.py`
- Modify: `src/cognitive_memory/dashboard/services/consolidation_service.py`
- Modify: `src/cognitive_memory/dashboard/templates/consolidation/index.html`
- Modify: `src/cognitive_memory/dashboard/i18n.py`
- Create: `tests/dashboard/test_consolidation_decay.py`

- [ ] **Step 1: i18n に翻訳キーを追加**

```python
# Decay settings
"decay.title": {"en": "Memory Decay Settings", "ja": "記憶の忘却設定"},
"decay.arousal_threshold": {"en": "Arousal Threshold", "ja": "Arousal 閾値"},
"decay.arousal_desc": {"en": "Entries with arousal >= this value are kept permanently", "ja": "この値以上の Arousal を持つエントリは永久保持"},
"decay.recall_threshold": {"en": "Recall Threshold", "ja": "想起回数閾値"},
"decay.recall_desc": {"en": "Entries recalled >= this many times are retention candidates", "ja": "この回数以上想起された記憶は保持候補"},
"decay.recall_window": {"en": "Recall Window (months)", "ja": "想起ウィンドウ（月）"},
"decay.recall_window_desc": {"en": "If not recalled within this period, memory fades", "ja": "この期間内に想起がなければ記憶は薄れる"},
"decay.enabled": {"en": "Decay Enabled", "ja": "忘却 有効"},
"decay.save": {"en": "Save", "ja": "保存"},
"decay.saved": {"en": "Settings saved", "ja": "設定を保存しました"},
```

- [ ] **Step 2: ダッシュボードテストを作成**

```python
"""Tests for decay settings UI on consolidation page."""
import pytest

class TestDecaySettingsUI:
    def test_decay_settings_displayed(self, client):
        """Consolidation page shows decay settings section."""
        resp = client.get("/consolidation/")
        assert resp.status_code == 200
        assert "0.7" in resp.text  # arousal_threshold default
        assert "18" in resp.text   # recall_window_months default

    def test_update_decay_settings(self, client):
        """POST /consolidation/decay updates cogmem.toml."""
        resp = client.post("/consolidation/decay", data={
            "arousal_threshold": "0.8",
            "recall_threshold": "3",
            "recall_window_months": "12",
            "enabled": "on",
        })
        assert resp.status_code in (200, 303)
```

- [ ] **Step 3: テスト実行 → FAIL 確認**

- [ ] **Step 4: consolidation_service.py に decay 設定データ取得を追加**

- [ ] **Step 5: consolidation.py に POST エンドポイント追加**

```python
@router.post("/decay")
async def update_decay_settings(request: Request):
    form = await request.form()
    # cogmem.toml の [cogmem.decay] セクションを更新
    ...
```

- [ ] **Step 6: consolidation/index.html に設定フォームを追加**

記憶の定着ページの下部に「記憶の忘却設定」セクションを追加。
HTMX で POST → 保存完了メッセージ表示。
入力フィールド: arousal_threshold (number), recall_threshold (number), recall_window_months (number), enabled (checkbox)

- [ ] **Step 7: テスト実行 → 全 PASS 確認**

- [ ] **Step 8: /browse で UI 確認**

```bash
$B goto http://127.0.0.1:8765/consolidation/
$B snapshot -i
```

- [ ] **Step 9: コミット**

```bash
git commit -m "feat: add decay settings UI to consolidation dashboard page"
```

---

### Task 5: agents.md に忘却ルールを追記

**Files:**
- Modify: `/Users/akira/workspace/open-claude/identity/agents.md`

- [ ] **Step 1: 「記憶の定着」セクションに忘却ルールを追加**

記憶の定着ステップの最後に:
```
7. 忘却処理: `cogmem decay` を実行（consolidated ログに対して自動適用）
   - Arousal >= {threshold} → 詳細を残す
   - recall_count >= {threshold} かつ直近 {window} ヶ月に想起あり → 残す
   - recall_count >= {threshold} かつ直近 {window} ヶ月に想起なし → 削除
   - 上記以外 → compact に圧縮、詳細削除
   - 閾値はダッシュボード（/consolidation/）で変更可能
```

- [ ] **Step 2: コミット**

```bash
git commit -m "docs: add memory decay rules to agents.md"
```

---

### Task 6: 全テスト実行 & 結合確認

- [ ] **Step 1: cogmem フルテストスイート実行**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib
pytest -v
```
Expected: 全テスト PASS（既存 435 + 新規 ~15 = ~450）

- [ ] **Step 2: dry-run で動作確認**

```bash
cd /Users/akira/workspace/open-claude
cogmem decay --dry-run --json
```

- [ ] **Step 3: ダッシュボードで設定変更を確認（/browse）**

- [ ] **Step 4: コミット（必要なら）**
