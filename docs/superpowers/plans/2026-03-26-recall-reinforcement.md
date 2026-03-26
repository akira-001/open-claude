# 想起による記憶定着強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 検索やフラッシュバックで記憶が呼び出された時に recall_count / last_recalled を記録し、arousal を引き上げて忘却曲線をリセットする。「何度も思い出す記憶は定着する」を実装する。

**Architecture:** memories テーブルに `recall_count` / `last_recalled` カラムを追加。SearchResult に `content_hash` フィールドを追加し、semantic_search は DB から直接、grep_search は DB 逆引きで hash を取得。search() / context_search() の結果返却時に、content_hash がある記憶の recall メタデータを更新する。arousal boost はデフォルト +0.1（ダッシュボードで変更可能）。

**Tech Stack:** Python, SQLite, pytest

**Repo:** `/Users/akira/workspace/ai-dev/cognitive-memory-lib`

---

## File Structure

| ファイル | 責務 | 変更種別 |
|---------|------|---------|
| `src/cognitive_memory/types.py` | SearchResult に content_hash 追加 | Modify |
| `src/cognitive_memory/store.py` | DB スキーマ + reinforce_recall + search ラッパー | Modify |
| `src/cognitive_memory/search.py` | semantic/grep が content_hash を返す | Modify |
| `src/cognitive_memory/cli/recall_cmd.py` | recall-stats CLI | Create |
| `src/cognitive_memory/cli/main.py` | サブコマンド登録 | Modify |
| `src/cognitive_memory/dashboard/services/memory_service.py` | 想起統計クエリ | Modify |
| `src/cognitive_memory/dashboard/templates/memory/overview.html` | 想起セクション表示 | Modify |
| `src/cognitive_memory/dashboard/i18n.py` | 翻訳キー追加 | Modify |
| `tests/test_recall.py` | 全テスト | Create |

---

### Task 1: DB スキーマ — recall_count / last_recalled 追加

**Files:**
- Modify: `src/cognitive_memory/store.py:61-82`
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recall.py
"""Tests for recall reinforcement."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from cognitive_memory.config import CogMemConfig
from cognitive_memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    (tmp_path / "memory" / "logs").mkdir(parents=True)
    (tmp_path / "cogmem.toml").write_text(
        '[cogmem]\nlogs_dir = "memory/logs"\ndb_path = "memory/vectors.db"\n',
        encoding="utf-8",
    )
    config = CogMemConfig.from_toml(tmp_path / "cogmem.toml")
    with MemoryStore(config) as s:
        yield s


class TestSchema:
    def test_new_db_has_recall_columns(self, store):
        """New DB has recall_count=0 and last_recalled=NULL by default."""
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'test', 0.5, '[]')"
        )
        row = store.conn.execute(
            "SELECT recall_count, last_recalled FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["recall_count"] == 0
        assert row["last_recalled"] is None

    def test_existing_db_migration(self, tmp_path):
        """Opening a DB without recall columns adds them via ALTER TABLE."""
        db_path = tmp_path / "memory" / "old.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY, content_hash TEXT UNIQUE,
                date TEXT, content TEXT, arousal REAL, vector BLOB
            )
        """)
        conn.execute("""
            CREATE TABLE indexed_files (
                filename TEXT PRIMARY KEY, indexed_at TEXT, entry_count INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO memories VALUES (1, 'old1', '2026-03-20', 'old entry', 0.7, '[]')"
        )
        conn.commit()
        conn.close()

        (tmp_path / "cogmem.toml").write_text(
            '[cogmem]\nlogs_dir = "memory/logs"\ndb_path = "memory/old.db"\n',
            encoding="utf-8",
        )
        config = CogMemConfig.from_toml(tmp_path / "cogmem.toml")
        with MemoryStore(config) as s:
            row = s.conn.execute(
                "SELECT recall_count, last_recalled FROM memories WHERE content_hash = 'old1'"
            ).fetchone()
            assert row["recall_count"] == 0
            assert row["last_recalled"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestSchema -v`
Expected: FAIL — `OperationalError: table memories has no column named recall_count`

- [ ] **Step 3: Write minimal implementation**

`store.py` の `_init_db` を変更:

```python
# CREATE TABLE に 2 カラム追加
self._conn.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id           INTEGER PRIMARY KEY,
        content_hash TEXT UNIQUE,
        date         TEXT,
        content      TEXT,
        arousal      REAL,
        vector       BLOB,
        recall_count INTEGER DEFAULT 0,
        last_recalled TEXT
    )
""")

# 既存DBマイグレーション（_init_db の末尾、commit の前に追加）
for col, col_def in [
    ("recall_count", "INTEGER DEFAULT 0"),
    ("last_recalled", "TEXT"),
]:
    try:
        self._conn.execute(f"ALTER TABLE memories ADD COLUMN {col} {col_def}")
    except sqlite3.OperationalError:
        pass  # column already exists
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestSchema -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add tests/test_recall.py src/cognitive_memory/store.py && git commit -m "feat: add recall_count and last_recalled columns to memories table"
```

---

### Task 2: reinforce_recall メソッド

**Files:**
- Modify: `src/cognitive_memory/store.py` (新メソッド追加)
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recall.py に追加

class TestReinforceRecall:
    def test_increments_count(self, store):
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'test', 0.5, '[]')"
        )
        store.conn.commit()
        store.reinforce_recall("h1")
        row = store.conn.execute(
            "SELECT recall_count FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["recall_count"] == 1

    def test_updates_timestamp(self, store):
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'test', 0.5, '[]')"
        )
        store.conn.commit()
        store.reinforce_recall("h1")
        row = store.conn.execute(
            "SELECT last_recalled FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["last_recalled"] is not None
        assert "2026" in row["last_recalled"]

    def test_boosts_arousal(self, store):
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'test', 0.5, '[]')"
        )
        store.conn.commit()
        store.reinforce_recall("h1")
        row = store.conn.execute(
            "SELECT arousal FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["arousal"] == pytest.approx(0.6)

    def test_arousal_caps_at_1(self, store):
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'high', 0.95, '[]')"
        )
        store.conn.commit()
        store.reinforce_recall("h1")
        row = store.conn.execute(
            "SELECT arousal FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["arousal"] == pytest.approx(1.0)

    def test_multiple_recalls(self, store):
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES ('h1', '2026-03-26', 'repeated', 0.5, '[]')"
        )
        store.conn.commit()
        for _ in range(3):
            store.reinforce_recall("h1")
        row = store.conn.execute(
            "SELECT recall_count, arousal FROM memories WHERE content_hash = 'h1'"
        ).fetchone()
        assert row["recall_count"] == 3
        assert row["arousal"] == pytest.approx(0.8)

    def test_nonexistent_hash(self, store):
        store.reinforce_recall("nonexistent")  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestReinforceRecall -v`
Expected: FAIL — `AttributeError: 'MemoryStore' object has no attribute 'reinforce_recall'`

- [ ] **Step 3: Write minimal implementation**

```python
# store.py の MemoryStore クラスに追加
def reinforce_recall(self, content_hash: str, arousal_boost: float = 0.1) -> None:
    """Record a recall event: increment count, boost arousal, update timestamp."""
    self.conn.execute(
        """
        UPDATE memories
        SET recall_count = recall_count + 1,
            last_recalled = ?,
            arousal = MIN(arousal + ?, 1.0)
        WHERE content_hash = ?
        """,
        (datetime.now().isoformat(), arousal_boost, content_hash),
    )
    self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestReinforceRecall -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/store.py tests/test_recall.py && git commit -m "feat: add reinforce_recall method to MemoryStore"
```

---

### Task 3: SearchResult に content_hash 追加 + semantic_search が hash を返す

**Files:**
- Modify: `src/cognitive_memory/types.py:20-30`
- Modify: `src/cognitive_memory/search.py:40-62` (semantic_search)
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recall.py に追加

from cognitive_memory.types import SearchResult


class TestSearchResultHash:
    def test_search_result_has_content_hash(self):
        """SearchResult accepts content_hash field."""
        r = SearchResult(
            score=0.9, date="2026-03-26", content="test",
            arousal=0.5, source="semantic", content_hash="abc123",
        )
        assert r.content_hash == "abc123"

    def test_search_result_hash_default_none(self):
        """content_hash defaults to None."""
        r = SearchResult(
            score=0.9, date="2026-03-26", content="test",
            arousal=0.5, source="grep",
        )
        assert r.content_hash is None
```

```python
# tests/test_recall.py に追加

class TestSemanticSearchHash:
    def test_semantic_returns_content_hash(self, store):
        """semantic_search includes content_hash from DB."""
        content = "### [INSIGHT] テスト洞察"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        vec = [0.1] * 384  # match embedding dimension
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES (?, ?, ?, ?, ?)",
            (content_hash, "2026-03-26", content, 0.8, json.dumps(vec)),
        )
        store.conn.commit()

        from cognitive_memory.search import semantic_search
        from cognitive_memory.scoring import normalize

        query_vec = normalize([0.1] * 384)
        results, status = semantic_search(
            query_vec, store.config.database_path, store.config, top_k=5
        )
        assert status == "ok"
        assert len(results) >= 1
        assert results[0].content_hash == content_hash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestSearchResultHash tests/test_recall.py::TestSemanticSearchHash -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'content_hash'`

- [ ] **Step 3: Implement**

types.py:
```python
@dataclass
class SearchResult:
    score: float
    date: str
    content: str
    arousal: float
    source: str
    cosine_sim: Optional[float] = None
    time_decay: Optional[float] = None
    content_hash: Optional[str] = None  # 追加
```

search.py の semantic_search — SELECT に content_hash を追加し、SearchResult に渡す:
```python
# L40-42: SELECT に content_hash を追加
for row in conn.execute(
    "SELECT content_hash, date, content, arousal, vector FROM memories"
):
    # ...
    results.append(
        SearchResult(
            # ... 既存フィールド ...
            content_hash=row["content_hash"],  # 追加
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestSearchResultHash tests/test_recall.py::TestSemanticSearchHash -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -q --timeout=30`
Expected: 全パス

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/types.py src/cognitive_memory/search.py tests/test_recall.py && git commit -m "feat: add content_hash to SearchResult, semantic_search returns hash"
```

---

### Task 4: grep_search が DB 逆引きで hash を返す

**Files:**
- Modify: `src/cognitive_memory/search.py:78-134` (grep_search)
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recall.py に追加

class TestGrepSearchHash:
    def test_grep_returns_content_hash(self, store, tmp_path):
        """grep_search looks up content_hash from DB by matching content."""
        content = "### [ERROR] テスト用エラーエントリ\n*Arousal: 0.9 | Emotion: Correction*\ngrep で見つかるテスト。"
        content_clean = content.replace("---", "").strip()
        content_hash = hashlib.sha256(content_clean.encode()).hexdigest()

        # Write log file
        log_file = store.config.logs_path / "2026-03-26.md"
        log_file.write_text(
            f"# 2026-03-26\n\n## ログエントリ\n\n{content}\n\n---\n\n## 引き継ぎ\n",
            encoding="utf-8",
        )

        # Index so DB has the hash
        store.index_file(log_file, force=True)

        from cognitive_memory.search import grep_search
        results = grep_search("テスト用エラー", store.config.logs_path, store.config)
        assert len(results) >= 1
        assert results[0].content_hash == content_hash

    def test_grep_returns_none_hash_when_not_indexed(self, store):
        """grep result has content_hash=None when entry is not in DB."""
        log_file = store.config.logs_path / "2026-03-27.md"
        log_file.write_text(
            "# 2026-03-27\n\n## ログエントリ\n\n### [INSIGHT] DB未登録エントリ\n*Arousal: 0.7*\nインデックスされていない。\n\n---\n\n## 引き継ぎ\n",
            encoding="utf-8",
        )
        from cognitive_memory.search import grep_search
        results = grep_search("DB未登録", store.config.logs_path, store.config)
        assert len(results) >= 1
        assert results[0].content_hash is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestGrepSearchHash -v`
Expected: FAIL — `content_hash` が None（grep_search がまだ hash を返さないため）

- [ ] **Step 3: Implement**

grep_search に `db_path` パラメータを追加し、content_hash を逆引き:

```python
def grep_search(
    query: str,
    logs_dir: Path,
    config: CogMemConfig,
    top_k: int = 5,
) -> List[SearchResult]:
    """Keyword search over raw log files (grep-equivalent)."""
    # ... 既存ロジック ...

    # DB 接続（hash 逆引き用）
    db_path = config.database_path
    db_conn = None
    if db_path.exists():
        try:
            db_conn = sqlite3.connect(str(db_path))
            db_conn.row_factory = sqlite3.Row
        except sqlite3.Error:
            db_conn = None

    # ... entries ループ内で ...
    # content_hash の逆引き
    found_hash = None
    if db_conn is not None:
        try:
            row = db_conn.execute(
                "SELECT content_hash FROM memories WHERE content = ? AND date = ?",
                (e_clean, date),
            ).fetchone()
            if row:
                found_hash = row["content_hash"]
        except sqlite3.Error:
            pass

    results.append(
        SearchResult(
            # ... 既存フィールド ...
            content_hash=found_hash,  # 追加
        )
    )

    # ... ループ後 ...
    if db_conn is not None:
        db_conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestGrepSearchHash -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -q --timeout=30`

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/search.py tests/test_recall.py && git commit -m "feat: grep_search returns content_hash via DB reverse lookup"
```

---

### Task 5: search() / context_search() で自動想起

**Files:**
- Modify: `src/cognitive_memory/store.py:203-290` (search, context_search)
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recall.py に追加

from cognitive_memory.types import SearchResponse


class TestSearchReinforcement:
    def test_search_reinforces_with_hash(self, store, monkeypatch):
        """search() calls reinforce_recall for results with content_hash."""
        content = "### [INSIGHT] 想起対象"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES (?, ?, ?, ?, ?)",
            (content_hash, "2026-03-26", content, 0.5, "[]"),
        )
        store.conn.commit()

        def fake_execute(query, top_k=5):
            return SearchResponse(
                results=[
                    SearchResult(
                        score=0.9, date="2026-03-26", content=content,
                        arousal=0.5, source="semantic", content_hash=content_hash,
                    )
                ],
                status="ok",
            )
        monkeypatch.setattr(store, "_execute_search", fake_execute)
        store.search("想起")

        row = store.conn.execute(
            "SELECT recall_count, arousal FROM memories WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        assert row["recall_count"] == 1
        assert row["arousal"] == pytest.approx(0.6)

    def test_search_skips_none_hash(self, store, monkeypatch):
        """search() does NOT reinforce results with content_hash=None."""
        reinforced = []
        original = store.reinforce_recall
        def tracking(h, **kw):
            reinforced.append(h)
            original(h, **kw)
        monkeypatch.setattr(store, "reinforce_recall", tracking)

        def fake_execute(query, top_k=5):
            return SearchResponse(
                results=[
                    SearchResult(
                        score=0.5, date="2026-03-26", content="no hash",
                        arousal=0.5, source="grep", content_hash=None,
                    )
                ],
                status="ok",
            )
        monkeypatch.setattr(store, "_execute_search", fake_execute)
        store.search("test")
        assert len(reinforced) == 0

    def test_search_no_results_no_reinforce(self, store, monkeypatch):
        """search() with 0 results does not call reinforce."""
        reinforced = []
        original = store.reinforce_recall
        def tracking(h, **kw):
            reinforced.append(h)
            original(h, **kw)
        monkeypatch.setattr(store, "reinforce_recall", tracking)

        def fake_execute(query, top_k=5):
            return SearchResponse(results=[], status="ok")
        monkeypatch.setattr(store, "_execute_search", fake_execute)
        store.search("empty")
        assert len(reinforced) == 0

    def test_search_skipped_no_reinforce(self, store, monkeypatch):
        """Gate-skipped search does not reinforce."""
        reinforced = []
        original = store.reinforce_recall
        def tracking(h, **kw):
            reinforced.append(h)
            original(h, **kw)
        monkeypatch.setattr(store, "reinforce_recall", tracking)

        def fake_execute(query, top_k=5):
            return SearchResponse(results=[], status="skipped_by_gate")
        monkeypatch.setattr(store, "_execute_search", fake_execute)
        store.search("a")
        assert len(reinforced) == 0


class TestContextSearchReinforcement:
    def test_context_search_reinforces(self, store, monkeypatch):
        """context_search() reinforces results with content_hash."""
        content = "### [INSIGHT] フラッシュバック対象"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        store.conn.execute(
            "INSERT INTO memories (content_hash, date, content, arousal, vector) "
            "VALUES (?, ?, ?, ?, ?)",
            (content_hash, "2026-03-26", content, 0.8, "[]"),
        )
        store.conn.commit()

        def fake_execute(query, top_k=5):
            return SearchResponse(
                results=[
                    SearchResult(
                        score=0.9, date="2026-03-26", content=content,
                        arousal=0.8, source="semantic", cosine_sim=0.9,
                        content_hash=content_hash,
                    )
                ],
                status="ok",
            )
        monkeypatch.setattr(store, "_execute_search", fake_execute)
        monkeypatch.setattr(store.config, "context_search_enabled", True)
        store.context_search("フラッシュバック")

        row = store.conn.execute(
            "SELECT recall_count FROM memories WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        assert row["recall_count"] == 1

    def test_context_search_disabled_no_reinforce(self, store, monkeypatch):
        """Disabled context_search does not reinforce."""
        reinforced = []
        original = store.reinforce_recall
        def tracking(h, **kw):
            reinforced.append(h)
            original(h, **kw)
        monkeypatch.setattr(store, "reinforce_recall", tracking)
        monkeypatch.setattr(store.config, "context_search_enabled", False)
        store.context_search("test")
        assert len(reinforced) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py::TestSearchReinforcement tests/test_recall.py::TestContextSearchReinforcement -v`
Expected: FAIL — `AttributeError: '_execute_search'`

- [ ] **Step 3: Refactor search and add reinforcement**

store.py: search() の内部ロジックを `_execute_search` に抽出、search() はラッパー:

```python
def _execute_search(self, query: str, top_k: int = 5) -> SearchResponse:
    """Internal search pipeline without recall reinforcement."""
    if not should_search(query):
        return SearchResponse(status="skipped_by_gate")

    query_vec = self.embedder.embed(query)
    if query_vec is not None:
        sem_results, sem_status = semantic_search(
            query_vec, self.config.database_path, self.config, top_k
        )
        if sem_status == "ok":
            grep_results = grep_search(
                query, self.config.logs_path, self.config, top_k
            )
            merged = merge_and_dedup(grep_results, sem_results, top_k)
            return SearchResponse(results=merged, status="ok")
        status_reason = sem_status
    else:
        status_reason = "ollama_unavailable"

    grep_results = grep_search(query, self.config.logs_path, self.config, top_k)
    return SearchResponse(
        results=grep_results, status=f"degraded ({status_reason})"
    )

def _reinforce_results(self, results: List[SearchResult]) -> None:
    """Reinforce recall for search results that have a content_hash."""
    for result in results:
        if result.content_hash is not None:
            self.reinforce_recall(result.content_hash)

def search(self, query: str, top_k: int = 5) -> SearchResponse:
    """Full search pipeline with recall reinforcement."""
    response = self._execute_search(query, top_k)
    self._reinforce_results(response.results)
    return response
```

context_search: 結果返却前に `_reinforce_results` を呼ぶ（`return response` の前に追加）:
```python
self._reinforce_results(response.results)
return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_recall.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -q --timeout=30`

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add src/cognitive_memory/store.py tests/test_recall.py && git commit -m "feat: search and context_search reinforce recalled memories via content_hash"
```

---

### Task 6: ダッシュボードに想起情報を表示

**Files:**
- Modify: `src/cognitive_memory/dashboard/services/memory_service.py`
- Modify: `src/cognitive_memory/dashboard/templates/memory/overview.html`
- Modify: `src/cognitive_memory/dashboard/i18n.py`
- Test: `tests/test_dashboard/test_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard/test_routes.py の TestRoutes クラスに追加

def test_home_shows_recall_section(self, client):
    """Memory overview page has a recall/想起 section."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "recall" in html or "想起" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_dashboard/test_routes.py::TestRoutes::test_home_shows_recall_section -v`

- [ ] **Step 3: Implement**

memory_service.py の `get_overview_data()` に most_recalled クエリを追加:
```python
most_recalled = []
try:
    rows = conn.execute(
        "SELECT content, recall_count, last_recalled, arousal "
        "FROM memories WHERE recall_count > 0 "
        "ORDER BY recall_count DESC LIMIT 5"
    ).fetchall()
    most_recalled = [
        {
            "title": r["content"].split("\n")[0][:80],
            "recall_count": r["recall_count"],
            "last_recalled": r["last_recalled"],
            "arousal": r["arousal"],
        }
        for r in rows
    ]
except sqlite3.OperationalError:
    pass
# return dict に "most_recalled": most_recalled を追加
```

i18n.py に翻訳キー追加:
```python
"memory.most_recalled": {"en": "Most Recalled", "ja": "よく想起される記憶"},
"memory.recall_count": {"en": "Recalls", "ja": "想起回数"},
"memory.no_recalls": {"en": "No recalled memories yet.", "ja": "想起された記憶はまだありません。"},
```

overview.html にセクション追加（既存の signals panel の前に）。

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Run full dashboard tests**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_dashboard/ -q`

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add -A && git commit -m "feat: show most recalled memories on dashboard overview"
```

---

### Task 7: cogmem recall-stats CLI コマンド

**Files:**
- Create: `src/cognitive_memory/cli/recall_cmd.py`
- Modify: `src/cognitive_memory/cli/main.py`
- Test: `tests/test_recall.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recall.py に追加

class TestRecallStats:
    def test_sorted_by_count(self, store):
        """Memories returned sorted by recall_count descending."""
        store.conn.execute(
            "INSERT INTO memories VALUES (NULL, 'rs1', '2026-03-26', '### [INSIGHT] よく思い出す', 0.8, '[]', 5, '2026-03-26T10:00:00')"
        )
        store.conn.execute(
            "INSERT INTO memories VALUES (NULL, 'rs2', '2026-03-25', '### [DECISION] 一度だけ', 0.6, '[]', 1, NULL)"
        )
        store.conn.commit()

        rows = store.conn.execute(
            "SELECT content, recall_count FROM memories "
            "WHERE recall_count > 0 ORDER BY recall_count DESC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["recall_count"] == 5
        assert rows[1]["recall_count"] == 1

    def test_no_recalls(self, store):
        """No rows returned when all recall_count = 0."""
        store.conn.execute(
            "INSERT INTO memories VALUES (NULL, 'rs3', '2026-03-26', 'no recall', 0.5, '[]', 0, NULL)"
        )
        store.conn.commit()

        rows = store.conn.execute(
            "SELECT * FROM memories WHERE recall_count > 0"
        ).fetchall()
        assert len(rows) == 0
```

- [ ] **Step 2: Run test to verify it passes** (DB 層は Task 1 で実装済み)

- [ ] **Step 3: Implement CLI command**

```python
# src/cognitive_memory/cli/recall_cmd.py
"""cogmem recall-stats — show recall statistics."""

from __future__ import annotations

import json
import sys

from ..config import CogMemConfig
from ..store import MemoryStore


def run_recall_stats(json_output: bool = False):
    config = CogMemConfig.find_and_load()

    with MemoryStore(config) as store:
        try:
            rows = store.conn.execute(
                "SELECT content, recall_count, last_recalled, arousal, date "
                "FROM memories WHERE recall_count > 0 "
                "ORDER BY recall_count DESC LIMIT 10"
            ).fetchall()
        except Exception:
            rows = []

    if not rows:
        print("No recalled memories yet.")
        return

    if json_output:
        data = [
            {
                "title": r["content"].split("\n")[0][:80],
                "recall_count": r["recall_count"],
                "last_recalled": r["last_recalled"],
                "arousal": r["arousal"],
                "date": r["date"],
            }
            for r in rows
        ]
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"{'Recalls':>8}  {'Arousal':>7}  {'Date':>10}  Title")
        print("-" * 70)
        for r in rows:
            title = r["content"].split("\n")[0][:50]
            print(f"{r['recall_count']:>8}  {r['arousal']:>7.2f}  {r['date']:>10}  {title}")
```

- [ ] **Step 4: Register in main.py**

main.py のサブコマンドに `recall-stats` を追加（`--json` フラグ付き）。

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -q --timeout=30`

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add -A && git commit -m "feat: add cogmem recall-stats CLI command"
```

---

### Task 8: 既存 DB のマイグレーション実行

**Files:** なし（手動実行ステップ）

- [ ] **Step 1: open-claude の DB をマイグレーション**

```bash
cd /Users/akira/workspace/open-claude && python3 -c "
from cognitive_memory.config import CogMemConfig
from cognitive_memory.store import MemoryStore
config = CogMemConfig.find_and_load()
with MemoryStore(config) as store:
    row = store.conn.execute('SELECT COUNT(*) as n FROM memories').fetchone()
    print(f'Migrated: {row[\"n\"]} memories now have recall_count column')
"
```

- [ ] **Step 2: Verify**

```bash
cd /Users/akira/workspace/open-claude && python3 -c "
import sqlite3
conn = sqlite3.connect('memory/vectors.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT recall_count, last_recalled FROM memories LIMIT 1').fetchone()
print(f'recall_count={row[\"recall_count\"]}, last_recalled={row[\"last_recalled\"]}')
"
```
Expected: `recall_count=0, last_recalled=None`

---

### Task 9: 3段階記憶パイプライン統合テスト

**Files:**
- Create: `tests/test_memory_pipeline.py`
- Create: `tests/fixtures/session_auth_debug.md` (ダミー長文ログ)

**目的:** リアルな長文セッションログが、鮮明→薄れる→定着の3段階で正しく抽象化され、想起により arousal が変化することを検証する。LLM を使って結晶化の抽象度を評価する。

- [ ] **Step 1: ダミーの長文セッションログを作成**

```python
# tests/fixtures/session_auth_debug.md
# 「認証システムのバグ修正」2時間セッションのリアルなログ
```

```markdown
# 2026-03-20 セッションログ

## セッション概要
認証システムのセッショントークン期限切れバグを修正。最初の仮説（トークン生成ロジック）は外れ、実際の原因はタイムゾーン変換のミスだった。同じパターンが決済モジュールにも存在することを発見し、両方修正。

## ログエントリ

### [QUESTION] セッショントークンが突然期限切れになる報告
*Arousal: 0.4 | Emotion: Curiosity*
ユーザーから「ログイン後30分で強制ログアウトされる」との報告。設定上は24時間有効のはず。エラーログに「token_expired」が頻出。まず再現を試みる。

---

### [DECISION] トークン生成ロジックを調査する方針
*Arousal: 0.5 | Emotion: Planning*
仮説: generateToken() の有効期限計算が間違っている。auth/token.py の expiry 計算を確認する。テスト環境で再現できたので、デバッグログを仕込む。

---

### [ERROR] 仮説が間違っていた — トークン生成は正常
*Arousal: 0.8 | Emotion: Surprise*
generateToken() のコードを精査した結果、有効期限の計算は正しかった。デバッグログで確認: トークン生成時の expiry は正しく24時間後に設定されている。しかし検証時に「期限切れ」と判定される。生成と検証で別の問題がある。30分の無駄。仮説を検証せずにコードを読み始めたのが原因。

---

### [INSIGHT] 本当の原因はタイムゾーン変換 — UTC vs JST の不一致
*Arousal: 0.9 | Emotion: Discovery*
validateToken() が datetime.now() を使っていた（JST）が、トークンの expiry は UTC で保存されていた。9時間のズレで、UTC 15:00 以降に生成されたトークンは即座に「期限切れ」と判定される。datetime.now() → datetime.utcnow() に修正。

---

### [MILESTONE] 修正完了 — テスト追加
*Arousal: 0.5 | Emotion: Relief*
validateToken() を datetime.utcnow() に修正。タイムゾーン関連のテストを3件追加: UTC生成+UTC検証、JST時間帯での検証、日付境界でのエッジケース。全パス。

---

### [DECISION] 決済モジュールにも同じコードレビューを実施
*Arousal: 0.6 | Emotion: Caution*
auth/token.py の datetime.now() が問題だったなら、他のモジュールにも同じパターンがあるかもしれない。grep で datetime.now() を全ファイル検索する。

---

### [PATTERN] 決済モジュールにも同じタイムゾーンバグを発見
*Arousal: 0.8 | Emotion: Recognition*
payment/receipt.py の領収書発行日時も datetime.now() を使っていた。UTC で保存された取引日時と JST の発行日時が混在し、日次集計レポートの金額が1日ずれるバグの原因だった。同じ修正を適用。チーム内で「datetime.now() 禁止、必ず datetime.utcnow() または timezone-aware を使う」のルール策定を提案。

---

### [MILESTONE] PR作成 — 認証+決済のタイムゾーン統一
*Arousal: 0.5 | Emotion: Completion*
auth/token.py と payment/receipt.py の修正 + テスト6件。PR #142 作成。レビュー依頼済み。

---

## 引き継ぎ
- **継続テーマ**: datetime.now() の全ファイル置換（残り3箇所）
- **次のアクション**: PR #142 のレビュー対応、残り3箇所の修正
- **注意事項**: datetime.now() 禁止ルールをコーディングガイドラインに追加する
```

- [ ] **Step 2: 統合テストを作成**

```python
# tests/test_memory_pipeline.py
"""Integration tests for 3-stage memory pipeline:
   鮮明 (vivid) → 薄れる (fading) → 定着 (crystallized)
   + recall reinforcement across stages.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from cognitive_memory.config import CogMemConfig
from cognitive_memory.parser import parse_entries
from cognitive_memory.store import MemoryStore

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pipeline_store(tmp_path):
    """Store with a realistic session log indexed."""
    logs_dir = tmp_path / "memory" / "logs"
    logs_dir.mkdir(parents=True)

    # Copy fixture log
    fixture = FIXTURE_DIR / "session_auth_debug.md"
    log_file = logs_dir / "2026-03-20.md"
    log_file.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    (tmp_path / "cogmem.toml").write_text(
        '[cogmem]\nlogs_dir = "memory/logs"\ndb_path = "memory/vectors.db"\n'
        '[cogmem.crystallization]\npattern_threshold = 1\nerror_threshold = 1\n',
        encoding="utf-8",
    )
    config = CogMemConfig.from_toml(tmp_path / "cogmem.toml")

    with MemoryStore(config) as s:
        # Use a dummy embedder that returns fixed vectors
        class DummyEmbedder:
            def embed(self, text):
                return [0.1] * 384
            def embed_batch(self, texts):
                # Return slightly different vectors for each text
                return [
                    [0.1 + i * 0.01] * 384 for i in range(len(texts))
                ]
        s._embedder = DummyEmbedder()
        s.index_file(log_file, force=True)
        yield s


class TestStage1Vivid:
    """鮮明（直近）: 全エントリが保持され、arousal が正しい。"""

    def test_all_entries_indexed(self, pipeline_store):
        """All 8 log entries are parsed and indexed."""
        rows = pipeline_store.conn.execute(
            "SELECT COUNT(*) as n FROM memories WHERE date = '2026-03-20'"
        ).fetchone()
        assert rows["n"] == 8

    def test_arousal_distribution(self, pipeline_store):
        """Arousal values match the log entries."""
        rows = pipeline_store.conn.execute(
            "SELECT arousal FROM memories WHERE date = '2026-03-20' ORDER BY id"
        ).fetchall()
        arousals = [r["arousal"] for r in rows]
        # Expected: 0.4, 0.5, 0.8, 0.9, 0.5, 0.6, 0.8, 0.5
        assert arousals == pytest.approx(
            [0.4, 0.5, 0.8, 0.9, 0.5, 0.6, 0.8, 0.5]
        )

    def test_categories_correct(self, pipeline_store):
        """Each entry has the correct category tag."""
        rows = pipeline_store.conn.execute(
            "SELECT content FROM memories WHERE date = '2026-03-20' ORDER BY id"
        ).fetchall()
        categories = []
        for r in rows:
            m = re.search(r"\[([A-Z]+)\]", r["content"])
            categories.append(m.group(1) if m else None)
        assert categories == [
            "QUESTION", "DECISION", "ERROR", "INSIGHT",
            "MILESTONE", "DECISION", "PATTERN", "MILESTONE",
        ]

    def test_high_arousal_entries_have_detail(self, pipeline_store):
        """High arousal entries (>=0.8) contain multi-line detail."""
        rows = pipeline_store.conn.execute(
            "SELECT content, arousal FROM memories "
            "WHERE date = '2026-03-20' AND arousal >= 0.8 ORDER BY id"
        ).fetchall()
        assert len(rows) == 3  # ERROR(0.8), INSIGHT(0.9), PATTERN(0.8)
        for r in rows:
            lines = r["content"].strip().split("\n")
            assert len(lines) >= 3, f"High arousal entry should have detail: {lines[0]}"


class TestStage2Fading:
    """薄れる（compact化）: 高 arousal のみ残る。"""

    def test_compact_preserves_high_arousal(self, pipeline_store):
        """After compact, only entries with arousal >= 0.6 would survive."""
        rows = pipeline_store.conn.execute(
            "SELECT content, arousal FROM memories "
            "WHERE date = '2026-03-20' AND arousal >= 0.6 ORDER BY arousal DESC"
        ).fetchall()
        # Should be: INSIGHT(0.9), ERROR(0.8), PATTERN(0.8), DECISION(0.6)
        assert len(rows) == 4
        assert rows[0]["arousal"] == 0.9  # INSIGHT — highest
        assert rows[1]["arousal"] == 0.8  # ERROR or PATTERN

    def test_low_arousal_would_be_dropped(self, pipeline_store):
        """Low arousal entries (< 0.6) would not survive compact."""
        rows = pipeline_store.conn.execute(
            "SELECT content, arousal FROM memories "
            "WHERE date = '2026-03-20' AND arousal < 0.6"
        ).fetchall()
        assert len(rows) == 4  # QUESTION(0.4), DECISION(0.5), MILESTONE(0.5), MILESTONE(0.5)
        for r in rows:
            assert r["arousal"] < 0.6


class TestStage3Crystallized:
    """定着（結晶化）: パターンが抽象ルールに変換される。"""

    def test_signals_detect_patterns(self, pipeline_store):
        """Crystallization signals detect PATTERN and ERROR entries."""
        from cognitive_memory.signals import check_signals
        signals = check_signals(pipeline_store.config)
        assert signals.pattern_count >= 1  # [PATTERN] entry
        assert signals.error_count >= 1    # [ERROR] entry

    def test_error_pattern_extractable(self, pipeline_store):
        """The ERROR entry contains enough info to extract an error pattern."""
        row = pipeline_store.conn.execute(
            "SELECT content FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.8 "
            "AND content LIKE '%ERROR%'"
        ).fetchone()
        assert row is not None
        content = row["content"]
        # Should contain: what went wrong and why
        assert "仮説" in content  # mentions the wrong hypothesis
        assert "無駄" in content or "原因" in content  # mentions wasted effort or cause

    def test_pattern_entry_is_abstractable(self, pipeline_store):
        """The PATTERN entry identifies a repeating issue across modules."""
        row = pipeline_store.conn.execute(
            "SELECT content FROM memories "
            "WHERE date = '2026-03-20' AND content LIKE '%PATTERN%'"
        ).fetchone()
        assert row is not None
        content = row["content"]
        # Should contain: the pattern that repeats
        assert "datetime.now()" in content or "タイムゾーン" in content
        # Should contain: the rule/recommendation
        assert "禁止" in content or "ルール" in content


class TestRecallReinforcement:
    """想起による arousal 変化の検証。"""

    def test_never_recalled_stays_same(self, pipeline_store):
        """Entry with no recalls keeps original arousal."""
        row = pipeline_store.conn.execute(
            "SELECT arousal, recall_count FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.4"
        ).fetchone()
        assert row["recall_count"] == 0
        assert row["arousal"] == pytest.approx(0.4)

    def test_single_recall_boosts(self, pipeline_store):
        """One recall bumps arousal by 0.1."""
        row = pipeline_store.conn.execute(
            "SELECT content_hash, arousal FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.5 LIMIT 1"
        ).fetchone()
        original_arousal = row["arousal"]
        pipeline_store.reinforce_recall(row["content_hash"])

        updated = pipeline_store.conn.execute(
            "SELECT arousal, recall_count FROM memories WHERE content_hash = ?",
            (row["content_hash"],),
        ).fetchone()
        assert updated["recall_count"] == 1
        assert updated["arousal"] == pytest.approx(original_arousal + 0.1)

    def test_repeated_recalls_accumulate(self, pipeline_store):
        """3 recalls on arousal=0.6 entry → arousal=0.9."""
        row = pipeline_store.conn.execute(
            "SELECT content_hash FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.6 LIMIT 1"
        ).fetchone()
        for _ in range(3):
            pipeline_store.reinforce_recall(row["content_hash"])

        updated = pipeline_store.conn.execute(
            "SELECT arousal, recall_count FROM memories WHERE content_hash = ?",
            (row["content_hash"],),
        ).fetchone()
        assert updated["recall_count"] == 3
        assert updated["arousal"] == pytest.approx(0.9)

    def test_arousal_cap_on_high_entry(self, pipeline_store):
        """Recalling arousal=0.9 entry twice → caps at 1.0."""
        row = pipeline_store.conn.execute(
            "SELECT content_hash FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.9 LIMIT 1"
        ).fetchone()
        pipeline_store.reinforce_recall(row["content_hash"])
        pipeline_store.reinforce_recall(row["content_hash"])

        updated = pipeline_store.conn.execute(
            "SELECT arousal, recall_count FROM memories WHERE content_hash = ?",
            (row["content_hash"],),
        ).fetchone()
        assert updated["recall_count"] == 2
        assert updated["arousal"] == pytest.approx(1.0)

    def test_recall_promotes_low_to_survival(self, pipeline_store):
        """A low-arousal entry (0.4) recalled 3 times reaches 0.7,
        crossing the compact survival threshold (0.6)."""
        row = pipeline_store.conn.execute(
            "SELECT content_hash FROM memories "
            "WHERE date = '2026-03-20' AND arousal = 0.4 LIMIT 1"
        ).fetchone()
        for _ in range(3):
            pipeline_store.reinforce_recall(row["content_hash"])

        updated = pipeline_store.conn.execute(
            "SELECT arousal FROM memories WHERE content_hash = ?",
            (row["content_hash"],),
        ).fetchone()
        assert updated["arousal"] == pytest.approx(0.7)
        assert updated["arousal"] >= 0.6  # would survive compact


class TestLLMAbstractionQuality:
    """LLM を使って結晶化の抽象度を評価する。
    Ollama が起動していない環境ではスキップ。"""

    @pytest.fixture
    def llm_available(self):
        """Check if Ollama is running."""
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            return True
        except Exception:
            pytest.skip("Ollama not available")

    def test_pattern_abstracts_to_rule(self, pipeline_store, llm_available):
        """LLM can abstract the PATTERN entry into a general rule."""
        import urllib.request

        row = pipeline_store.conn.execute(
            "SELECT content FROM memories "
            "WHERE date = '2026-03-20' AND content LIKE '%PATTERN%'"
        ).fetchone()

        prompt = (
            "以下のログエントリから、再利用可能な抽象ルールを1行で抽出してください。\n\n"
            f"{row['content']}\n\n"
            "ルール:"
        )
        payload = json.dumps({
            "model": "qwen3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())["response"].strip()

        # The abstracted rule should mention timezone or datetime
        assert any(
            kw in result for kw in ["タイムゾーン", "timezone", "UTC", "datetime", "時刻"]
        ), f"LLM rule should mention timezone concept, got: {result}"
        # Should be concise (1-2 sentences, not a paragraph)
        assert len(result) < 200, f"Rule too long ({len(result)} chars): {result}"

    def test_error_abstracts_to_lesson(self, pipeline_store, llm_available):
        """LLM can abstract the ERROR entry into a lesson learned."""
        import urllib.request

        row = pipeline_store.conn.execute(
            "SELECT content FROM memories "
            "WHERE date = '2026-03-20' AND content LIKE '%ERROR%'"
        ).fetchone()

        prompt = (
            "以下のエラーログから、次回同じ状況を避けるための教訓を1行で抽出してください。\n\n"
            f"{row['content']}\n\n"
            "教訓:"
        )
        payload = json.dumps({
            "model": "qwen3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())["response"].strip()

        # The lesson should mention hypothesis verification
        assert any(
            kw in result for kw in ["仮説", "検証", "確認", "先に", "hypothesis", "verify"]
        ), f"LLM lesson should mention verification, got: {result}"
        assert len(result) < 200, f"Lesson too long ({len(result)} chars): {result}"
```

- [ ] **Step 3: fixtures ディレクトリとログファイルを作成**

```bash
mkdir -p /Users/akira/workspace/ai-dev/cognitive-memory-lib/tests/fixtures
```

`session_auth_debug.md` を Step 1 の内容で作成。

- [ ] **Step 4: Run tests**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/test_memory_pipeline.py -v --timeout=60
```

Expected:
- TestStage1Vivid: 4 PASS
- TestStage2Fading: 2 PASS
- TestStage3Crystallized: 3 PASS
- TestRecallReinforcement: 5 PASS
- TestLLMAbstractionQuality: 2 PASS (Ollama 起動時) or 2 SKIP (未起動時)

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && python3 -m pytest tests/ -q --timeout=60
```

- [ ] **Step 6: Commit**

```bash
cd /Users/akira/workspace/ai-dev/cognitive-memory-lib && git add tests/test_memory_pipeline.py tests/fixtures/session_auth_debug.md && git commit -m "test: add 3-stage memory pipeline integration tests with LLM evaluation"
```
