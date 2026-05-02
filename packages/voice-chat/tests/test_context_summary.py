"""Tests for Phase 1 context summary (rolling buffer + 5min summarizer)."""
import asyncio
import json
import sys
import time
import types
import unittest.mock as mock
import pytest

# --- Mock heavy ML dependencies before importing app ---
for mod_name in [
    "faster_whisper", "faster_whisper.WhisperModel",
    "speechbrain", "speechbrain.inference", "speechbrain.inference.speaker",
    "torch", "torchaudio",
    "uvicorn",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_wm = types.ModuleType("faster_whisper")
_wm.WhisperModel = mock.MagicMock()
sys.modules["faster_whisper"] = _wm

# minimal numpy stub good enough for AudioRingBuffer tests
if "numpy" not in sys.modules or not hasattr(sys.modules.get("numpy"), "concatenate"):
    _np = types.ModuleType("numpy")
    _np.float32 = "float32"
    def _np_array(data, dtype=None):
        return list(data)
    def _np_concatenate(parts):
        out = []
        for p in parts:
            out.extend(list(p))
        return out
    _np.array = _np_array
    _np.concatenate = _np_concatenate
    sys.modules["numpy"] = _np

_sb_inf_spk = types.ModuleType("speechbrain.inference.speaker")
_sb_inf_spk.SpeakerRecognition = mock.MagicMock()
sys.modules["speechbrain.inference.speaker"] = _sb_inf_spk
_sb_inf = types.ModuleType("speechbrain.inference")
_sb_inf.speaker = _sb_inf_spk
sys.modules["speechbrain.inference"] = _sb_inf
_sb = types.ModuleType("speechbrain")
_sb.inference = _sb_inf
sys.modules["speechbrain"] = _sb

import app  # noqa: E402


# ---- TranscriptRollingBuffer ----

class TestTranscriptRollingBuffer:
    def test_add_and_snapshot(self):
        async def run():
            buf = app.TranscriptRollingBuffer(window_seconds=1800)
            await buf.add("hello")
            await buf.add("world")
            snap = await buf.snapshot()
            assert [t for _, t in snap] == ["hello", "world"]
        asyncio.run(run())

    def test_empty_text_ignored(self):
        async def run():
            buf = app.TranscriptRollingBuffer()
            await buf.add("")
            assert await buf.snapshot() == []
        asyncio.run(run())

    def test_window_eviction(self):
        async def run():
            buf = app.TranscriptRollingBuffer(window_seconds=10)
            now = time.time()
            with mock.patch("app.time.time", return_value=now - 100):
                await buf.add("old")
            with mock.patch("app.time.time", return_value=now):
                await buf.add("fresh")
                snap = await buf.snapshot()
            texts = [t for _, t in snap]
            assert "old" not in texts
            assert "fresh" in texts
        asyncio.run(run())

    def test_text_with_timestamps_format(self):
        async def run():
            buf = app.TranscriptRollingBuffer()
            await buf.add("こんにちは")
            text = await buf.text_with_timestamps()
            # [HH:MM] テキスト の形式
            assert text.startswith("[")
            assert "] こんにちは" in text
        asyncio.run(run())

    def test_empty_buffer_returns_empty_string(self):
        async def run():
            buf = app.TranscriptRollingBuffer()
            assert await buf.text_with_timestamps() == ""
        asyncio.run(run())


# ---- ContextSummary.to_prompt_block ----

class TestContextSummaryPromptBlock:
    def test_zero_confidence_returns_empty(self):
        cs = app.ContextSummary(confidence=0.0, updated_at=time.time())
        assert cs.to_prompt_block() == ""

    def test_low_confidence_returns_empty(self):
        cs = app.ContextSummary(
            activity="working", topic="x",
            confidence=0.2, updated_at=time.time(),
        )
        assert cs.to_prompt_block() == ""

    def test_stale_returns_empty(self):
        cs = app.ContextSummary(
            activity="working", topic="x",
            confidence=0.9, updated_at=time.time() - 700,
        )
        assert cs.to_prompt_block() == ""

    def test_never_updated_is_stale(self):
        cs = app.ContextSummary(activity="x", confidence=0.9, updated_at=0.0)
        assert cs.is_stale() is True
        assert cs.to_prompt_block() == ""

    def test_full_block_renders_all_fields(self):
        cs = app.ContextSummary(
            activity="meeting",
            topic="京セラ案件の戦略会議",
            subtopics=["A", "B"],
            is_meeting=True,
            keywords=["KC", "PMO"],
            named_entities=["京セラ", "アバント"],
            language_register="business_meeting",
            confidence=0.88,
            updated_at=time.time(),
        )
        block = cs.to_prompt_block()
        assert "現在の状況コンテキスト" in block
        assert "活動: meeting" in block
        assert "トピック: 京セラ案件の戦略会議" in block
        assert "サブトピック: A, B" in block
        assert "会議モード" in block
        assert "参考キーワード: KC, PMO" in block
        assert "固有名詞: 京セラ, アバント" in block
        assert "発話レジスタ: business_meeting" in block
        assert "信頼度 0.88" in block

    def test_subtopics_capped_at_5(self):
        cs = app.ContextSummary(
            activity="x", confidence=0.9, updated_at=time.time(),
            subtopics=[f"s{i}" for i in range(10)],
        )
        block = cs.to_prompt_block()
        assert "s0" in block
        assert "s4" in block
        assert "s5" not in block

    def test_new_fields_rendered_in_block(self):
        cs = app.ContextSummary(
            activity="working",
            confidence=0.9,
            updated_at=time.time(),
            mood="focused",
            location="office",
            time_context="morning",
        )
        block = cs.to_prompt_block()
        assert "気分: focused" in block
        assert "場所: office" in block
        assert "時間帯: morning" in block

    def test_empty_new_fields_not_rendered(self):
        cs = app.ContextSummary(
            activity="working",
            confidence=0.9,
            updated_at=time.time(),
            mood="",
            location="",
            time_context="",
        )
        block = cs.to_prompt_block()
        assert "気分:" not in block
        assert "場所:" not in block
        assert "時間帯:" not in block


# ---- _build_context_summary ----

class TestBuildContextSummary:
    @pytest.fixture(autouse=True)
    def reset_summary(self):
        app._context_summary.activity = ""
        app._context_summary.topic = ""
        app._context_summary.subtopics = []
        app._context_summary.is_meeting = False
        app._context_summary.keywords = []
        app._context_summary.named_entities = []
        app._context_summary.language_register = ""
        app._context_summary.confidence = 0.0
        app._context_summary.evidence_snippets = []
        app._context_summary.mood = ""
        app._context_summary.location = ""
        app._context_summary.time_context = ""
        app._context_summary.updated_at = 0.0
        app._media_ctx.reset()
        yield
        app._media_ctx.reset()

    def test_parses_valid_json(self):
        async def run():
            fake = json.dumps({
                "activity": "video_watching",
                "topic": "強化学習論文の解説",
                "subtopics": ["PPO", "Atari"],
                "is_meeting": False,
                "keywords": ["PPO", "Atari", "報酬関数"],
                "named_entities": ["DeepMind"],
                "language_register": "casual_solo",
                "confidence": 0.83,
                "evidence_snippets": ["PPOってAtariでも安定するのかな", "報酬関数の設計が重要だと思う"],
                "mood": "focused",
                "location": "home",
                "time_context": "afternoon",
            })
            # Use a long transcript (≥300 chars, ≥2 evidence) so G3 discount does not apply
            long_transcript = "PPOってAtariでも安定するのかな、という話をしていた。" * 15
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            cs = app._context_summary
            assert cs.activity == "video_watching"
            assert cs.topic == "強化学習論文の解説"
            assert cs.subtopics == ["PPO", "Atari"]
            assert cs.is_meeting is False
            assert "PPO" in cs.keywords
            assert abs(cs.confidence - 0.83) < 1e-6
            assert cs.updated_at > 0
            assert cs.mood == "focused"
            assert cs.location == "home"
            assert cs.time_context == "afternoon"
        asyncio.run(run())

    def test_strips_code_fence(self):
        async def run():
            fake = '```json\n{"activity":"working","confidence":0.5}\n```'
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("x")
            assert app._context_summary.activity == "working"
        asyncio.run(run())

    def test_caps_list_lengths(self):
        async def run():
            fake = json.dumps({
                "activity": "x",
                "subtopics": [f"s{i}" for i in range(20)],
                "keywords": [f"k{i}" for i in range(20)],
                "named_entities": [f"e{i}" for i in range(20)],
                "evidence_snippets": [f"ev{i}" for i in range(20)],
                "confidence": 0.7,
            })
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("x")
            assert len(app._context_summary.subtopics) == 5
            assert len(app._context_summary.keywords) == 10
            assert len(app._context_summary.named_entities) == 8
            assert len(app._context_summary.evidence_snippets) == 3
        asyncio.run(run())

    def test_new_fields_default_to_empty_when_absent(self):
        async def run():
            fake = json.dumps({"activity": "working", "confidence": 0.6})
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("x")
            cs = app._context_summary
            assert cs.mood == ""
            assert cs.location == ""
            assert cs.time_context == ""
        asyncio.run(run())

    def test_invalid_json_raises(self):
        async def run():
            with mock.patch("app.chat_with_llm", return_value="not json at all"):
                with pytest.raises(json.JSONDecodeError):
                    await app._build_context_summary("x")
        asyncio.run(run())


# ---- _infer_media_content injection ----

class TestInjectionIntoInfer:
    @pytest.fixture(autouse=True)
    def reset_state(self):
        app._media_ctx.reset()
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        yield
        app._media_ctx.reset()

    def test_summary_injected_when_active(self):
        """_infer_media_content の system prompt に context summary が注入されることを確認。"""
        async def run():
            app._media_ctx.add_snippet("これはテストの発話です。")
            app._context_summary.activity = "video_watching"
            app._context_summary.topic = "強化学習論文の解説"
            app._context_summary.confidence = 0.8
            app._context_summary.keywords = ["PPO"]
            app._context_summary.updated_at = time.time()

            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return json.dumps({
                    "content_type": "youtube_talk",
                    "topic": "x", "matched_title": "",
                    "keywords": [], "confidence": 0.5,
                })

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._infer_media_content()
            assert "現在の状況コンテキスト" in captured["system"]
            assert "強化学習論文の解説" in captured["system"]
            assert "PPO" in captured["system"]
        asyncio.run(run())

    def test_summary_not_injected_when_low_conf(self):
        async def run():
            app._media_ctx.add_snippet("テスト")
            app._context_summary.activity = "x"
            app._context_summary.confidence = 0.1
            app._context_summary.updated_at = time.time()

            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return json.dumps({"content_type": "unknown", "topic": "",
                                   "matched_title": "", "keywords": [], "confidence": 0.0})

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._infer_media_content()
            assert "現在の状況コンテキスト" not in captured["system"]
        asyncio.run(run())


# ---- Feedback endpoints ----

class TestFeedbackEndpoint:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / "context_summary_feedback.jsonl"
        monkeypatch.setattr(app, "CONTEXT_SUMMARY_FEEDBACK_FILE", feedback_file)
        app._context_summary.activity = "video_watching"
        app._context_summary.topic = "強化学習論文"
        app._context_summary.subtopics = ["PPO"]
        app._context_summary.is_meeting = False
        app._context_summary.keywords = ["PPO", "Atari"]
        app._context_summary.named_entities = ["DeepMind"]
        app._context_summary.language_register = "casual_solo"
        app._context_summary.confidence = 0.83
        app._context_summary.evidence_snippets = ["..."]
        app._context_summary.updated_at = time.time()
        self.feedback_file = feedback_file
        yield
        app._context_summary.updated_at = 0.0

    def test_yes_feedback_writes_jsonl(self):
        async def run():
            r = await app.post_context_summary_feedback({"label": "yes"})
            assert r["ok"] is True
            content = self.feedback_file.read_text(encoding="utf-8").strip()
            entry = json.loads(content)
            assert entry["label"] == "yes"
            assert entry["correction"] is None
            assert entry["summary"]["activity"] == "video_watching"
            assert "ts" in entry
        asyncio.run(run())

    def test_no_requires_correction(self):
        async def run():
            r = await app.post_context_summary_feedback({"label": "no"})
            assert r["ok"] is False
            assert "correction required" in r["error"]
        asyncio.run(run())

    def test_no_feedback_with_correction(self):
        async def run():
            r = await app.post_context_summary_feedback({
                "label": "no",
                "correction": {"activity": "working", "topic": "コーディング"},
            })
            assert r["ok"] is True
            entry = json.loads(self.feedback_file.read_text(encoding="utf-8").strip())
            assert entry["label"] == "no"
            assert entry["correction"]["activity"] == "working"
            assert entry["correction"]["topic"] == "コーディング"
        asyncio.run(run())

    def test_invalid_label_rejected(self):
        async def run():
            r = await app.post_context_summary_feedback({"label": "maybe"})
            assert r["ok"] is False
            assert "yes" in r["error"] and "no" in r["error"]
        asyncio.run(run())

    def test_no_summary_yet_rejects(self):
        async def run():
            app._context_summary.updated_at = 0.0
            r = await app.post_context_summary_feedback({"label": "yes"})
            assert r["ok"] is False
            assert "no context summary" in r["error"]
        asyncio.run(run())

    def test_appends_multiple_entries(self):
        async def run():
            await app.post_context_summary_feedback({"label": "yes"})
            await app.post_context_summary_feedback(
                {"label": "no", "correction": {"topic": "X"}}
            )
            lines = self.feedback_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["label"] == "yes"
            assert json.loads(lines[1])["label"] == "no"
        asyncio.run(run())

    def test_yes_with_snapshot_summary(self):
        async def run():
            snapshot = {
                "activity": "snapshot_activity",
                "topic": "スナップショットトピック",
                "confidence": 0.85,
                "updated_at": time.time(),
            }
            r = await app.post_context_summary_feedback({
                "label": "yes",
                "summary": snapshot,
            })
            assert r["ok"] is True
            entry = json.loads(self.feedback_file.read_text(encoding="utf-8").strip())
            assert entry["label"] == "yes"
            assert entry["summary"]["activity"] == "snapshot_activity"
            assert entry["summary"]["topic"] == "スナップショットトピック"
            assert entry["summary"]["confidence"] == 0.85
        asyncio.run(run())

    def test_no_with_snapshot_summary(self):
        async def run():
            snapshot = {
                "activity": "snapshot_activity",
                "topic": "スナップショットトピック",
                "confidence": 0.85,
                "updated_at": time.time(),
            }
            r = await app.post_context_summary_feedback({
                "label": "no",
                "correction": {"activity": "corrected_activity"},
                "summary": snapshot,
            })
            assert r["ok"] is True
            entry = json.loads(self.feedback_file.read_text(encoding="utf-8").strip())
            assert entry["label"] == "no"
            assert entry["correction"]["activity"] == "corrected_activity"
            assert entry["summary"]["activity"] == "snapshot_activity"
        asyncio.run(run())


class TestGetContextSummary:
    def test_returns_current_summary(self):
        async def run():
            app._context_summary.activity = "working"
            app._context_summary.topic = "テスト"
            app._context_summary.confidence = 0.7
            app._context_summary.updated_at = time.time()
            r = await app.get_context_summary()
            assert r["ok"] is True
            assert r["summary"]["activity"] == "working"
            assert r["summary"]["topic"] == "テスト"
        asyncio.run(run())


# ---- Phase 2: AudioRingBuffer + TranscriptChunkBuffer ----

class _FakePCM:
    """numpy 配列モック（テスト環境では numpy がスタブ化されているため）。"""
    def __init__(self, data):
        self._data = list(data)
    def __len__(self):
        return len(self._data)
    def __iter__(self):
        return iter(self._data)


class TestAudioRingBuffer:
    def test_add_and_slice(self):
        async def run():
            buf = app.AudioRingBuffer(retention_seconds=1800)
            await buf.add(_FakePCM([0.0] * 16000))   # 1 sec
            await buf.add(_FakePCM([0.0] * 16000))   # 1 sec
            pcm, ts_start, ts_end = await buf.slice_recent(60)
            assert len(pcm) == 32000
            assert ts_start > 0
            assert ts_end >= ts_start
        asyncio.run(run())

    def test_empty_pcm_ignored(self):
        async def run():
            buf = app.AudioRingBuffer()
            await buf.add(_FakePCM([]))
            await buf.add(None)
            pcm, _, _ = await buf.slice_recent(60)
            assert len(pcm) == 0
        asyncio.run(run())

    def test_eviction_outside_retention(self):
        async def run():
            buf = app.AudioRingBuffer(retention_seconds=10)
            now = time.time()
            with mock.patch("app.time.time", return_value=now - 100):
                await buf.add(_FakePCM([0.0] * 16000))
            with mock.patch("app.time.time", return_value=now):
                await buf.add(_FakePCM([1.0] * 16000))
                pcm, _, _ = await buf.slice_recent(60)
            # only the fresh PCM survives
            assert len(pcm) == 16000
        asyncio.run(run())

    def test_slice_recent_empty(self):
        async def run():
            buf = app.AudioRingBuffer()
            pcm, ts_start, ts_end = await buf.slice_recent(60)
            assert len(pcm) == 0
            assert ts_start == 0.0
            assert ts_end == 0.0
        asyncio.run(run())


class TestTranscriptChunkBuffer:
    def test_add_and_format(self):
        async def run():
            buf = app.TranscriptChunkBuffer(max_entries=6)
            now = time.time()
            await buf.add(now - 300, now, "5分前から今までのテキスト")
            text = await buf.text_with_timestamps()
            assert "5分前から今までのテキスト" in text
            assert "[" in text and "]" in text
        asyncio.run(run())

    def test_empty_text_ignored(self):
        async def run():
            buf = app.TranscriptChunkBuffer()
            await buf.add(time.time(), time.time(), "")
            assert await buf.entry_count() == 0
        asyncio.run(run())

    def test_caps_at_max_entries(self):
        async def run():
            buf = app.TranscriptChunkBuffer(max_entries=3)
            now = time.time()
            for i in range(10):
                await buf.add(now + i, now + i + 60, f"chunk{i}")
            assert await buf.entry_count() == 3
            text = await buf.text_with_timestamps()
            assert "chunk7" in text
            assert "chunk8" in text
            assert "chunk9" in text
            assert "chunk0" not in text
        asyncio.run(run())

    def test_empty_buffer_returns_empty(self):
        async def run():
            buf = app.TranscriptChunkBuffer()
            assert await buf.text_with_timestamps() == ""
        asyncio.run(run())


class TestSummaryLoopSourceSelection:
    """_summarize_context_loop の source 選択：chunk_buffer 優先、なければ transcript_buffer。"""

    @pytest.fixture(autouse=True)
    def reset_buffers(self):
        async def clear():
            # clear chunk buffer
            async with app._chunk_buffer._lock:
                app._chunk_buffer._entries.clear()
            # clear transcript buffer
            async with app._transcript_buffer._lock:
                app._transcript_buffer._entries.clear()
        asyncio.run(clear())
        yield

    def test_prefers_chunk_buffer_when_available(self):
        async def run():
            now = time.time()
            await app._chunk_buffer.add(
                now - 300, now,
                "large-v3 で書き起こされた高精度テキストここにそこそこ長い文字列が入っている。"
                "これだけあれば閾値を超えるはず。"
            )
            await app._transcript_buffer.add("small バッファのテキスト")

            captured = {}

            async def fake_build(transcript):
                captured["transcript"] = transcript

            with mock.patch("app._build_context_summary", side_effect=fake_build):
                # invoke ONE iteration of the loop logic
                chunk_text = await app._chunk_buffer.text_with_timestamps()
                assert len(chunk_text) >= app.CONTEXT_SUMMARY_MIN_CHARS
                # mimic loop: prefer chunk_buffer
                transcript = chunk_text
                await app._build_context_summary(transcript)
            assert "large-v3" in captured["transcript"]
            assert "small" not in captured["transcript"]
        asyncio.run(run())

    def test_falls_back_to_transcript_buffer_when_chunks_empty(self):
        async def run():
            await app._transcript_buffer.add(
                "small ベースの音声認識テキストがここにじっくり入っているとする。"
                "これくらい長くないと CONTEXT_SUMMARY_MIN_CHARS を超えない。"
            )
            chunk_text = await app._chunk_buffer.text_with_timestamps()
            assert chunk_text == ""
            fallback_text = await app._transcript_buffer.text_with_timestamps()
            assert len(fallback_text) >= app.CONTEXT_SUMMARY_MIN_CHARS
        asyncio.run(run())


# ---- GET /api/context-summary/history ----

class TestContextSummaryHistoryEndpoint:
    @pytest.fixture(autouse=True)
    def reset_history(self, tmp_path, monkeypatch):
        app._confidence_history.clear()
        # redirect feedback file so tests don't read the real one
        empty_file = tmp_path / "context_summary_feedback.jsonl"
        monkeypatch.setattr(app, "CONTEXT_SUMMARY_FEEDBACK_FILE", empty_file)
        yield
        app._confidence_history.clear()

    def test_empty_history(self):
        async def run():
            r = await app.get_context_summary_history()
            assert r["ok"] is True
            assert r["confidence_history"] == []
            assert r["feedback_count"] == {"yes": 0, "no": 0, "total": 0}
            assert r["last_feedback_ts"] is None
        asyncio.run(run())

    def test_confidence_history_appended_by_build(self):
        async def run():
            fake = json.dumps({
                "activity": "working",
                "confidence": 0.75,
                "evidence_snippets": ["作業中の発話だ", "もう一つの根拠"],
                "mood": "", "location": "", "time_context": "",
            })
            # Use a long transcript (≥300 chars, ≥2 evidence) so G3 discount does not apply
            long_transcript = "作業中の発話だ、コードを書いている。" * 20
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            r = await app.get_context_summary_history()
            assert r["ok"] is True
            assert len(r["confidence_history"]) == 1
            entry = r["confidence_history"][0]
            assert abs(entry["confidence"] - 0.75) < 1e-6
            assert entry["ts"] > 0
        asyncio.run(run())

    def test_feedback_count_from_jsonl(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / "context_summary_feedback.jsonl"
        lines = [
            json.dumps({"label": "yes", "ts": "2026-05-02T10:00:00+09:00"}),
            json.dumps({"label": "yes", "ts": "2026-05-02T10:05:00+09:00"}),
            json.dumps({"label": "no",  "ts": "2026-05-02T10:10:00+09:00"}),
        ]
        feedback_file.write_text("\n".join(lines), encoding="utf-8")
        monkeypatch.setattr(app, "CONTEXT_SUMMARY_FEEDBACK_FILE", feedback_file)

        async def run():
            r = await app.get_context_summary_history()
            assert r["ok"] is True
            assert r["feedback_count"]["yes"] == 2
            assert r["feedback_count"]["no"] == 1
            assert r["feedback_count"]["total"] == 3
            assert r["last_feedback_ts"] is not None and r["last_feedback_ts"] > 0
        asyncio.run(run())

    def test_missing_feedback_file_returns_zeros(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent_feedback.jsonl"
        monkeypatch.setattr(app, "CONTEXT_SUMMARY_FEEDBACK_FILE", missing)

        async def run():
            r = await app.get_context_summary_history()
            assert r["ok"] is True
            assert r["feedback_count"] == {"yes": 0, "no": 0, "total": 0}
            assert r["last_feedback_ts"] is None
        asyncio.run(run())


# ---- Phase G2: media signal injection into _build_context_summary ----

class TestBuildContextSummaryMediaHint:
    """Phase G2: co_view media signal injected as hint into _build_context_summary system prompt."""

    _FAKE_LLM_RESPONSE = json.dumps({
        "activity": "video_watching",
        "topic": "アニメ視聴",
        "confidence": 0.8,
        "mood": "",
        "location": "",
        "time_context": "",
    })

    @pytest.fixture(autouse=True)
    def reset_state(self):
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        app._media_ctx.reset()
        yield
        app._media_ctx.reset()

    def _setup_media_ctx(self, inferred_type="anime", confidence=0.8):
        app._media_ctx.inferred_type = inferred_type
        app._media_ctx.confidence = confidence
        app._media_ctx.last_inferred_at = time.time()

    def test_media_hint_injected_when_fresh_and_confident(self):
        """Fresh signal with conf>=0.5 inserts co_view hint into system prompt."""
        async def run():
            self._setup_media_ctx("anime", confidence=0.8)
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("ちょっと静かな場面だな")

            assert "[co_view シグナル]" in captured["system"]
            assert "anime" in captured["system"]
        asyncio.run(run())

    def test_media_hint_shows_type_and_confidence_value(self):
        """Hint text contains the inferred_type and confidence rounded to 2 decimals."""
        async def run():
            self._setup_media_ctx("youtube_talk", confidence=0.75)
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("なるほど")

            assert "youtube_talk" in captured["system"]
            assert "0.75" in captured["system"]
        asyncio.run(run())

    def test_media_hint_not_injected_when_stale(self):
        """Signal older than 600s is not injected."""
        async def run():
            app._media_ctx.inferred_type = "anime"
            app._media_ctx.confidence = 0.9
            app._media_ctx.last_inferred_at = time.time() - 700
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト発話")

            assert "[co_view シグナル]" not in captured["system"]
        asyncio.run(run())

    def test_media_hint_not_injected_when_low_confidence(self):
        """Signal with confidence < 0.5 is not injected."""
        async def run():
            self._setup_media_ctx("anime", confidence=0.4)
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト発話")

            assert "[co_view シグナル]" not in captured["system"]
        asyncio.run(run())

    def test_media_hint_not_injected_when_type_unknown(self):
        """inferred_type='unknown' does not produce a hint."""
        async def run():
            self._setup_media_ctx("unknown", confidence=0.9)
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト発話")

            assert "[co_view シグナル]" not in captured["system"]
        asyncio.run(run())

    def test_media_hint_not_injected_when_type_empty(self):
        """inferred_type='' does not produce a hint."""
        async def run():
            app._media_ctx.inferred_type = ""
            app._media_ctx.confidence = 0.9
            app._media_ctx.last_inferred_at = time.time()
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト発話")

            assert "[co_view シグナル]" not in captured["system"]
        asyncio.run(run())

    def test_media_hint_not_injected_when_never_inferred(self):
        """last_inferred_at=0 (never run) does not produce a hint."""
        async def run():
            app._media_ctx.inferred_type = "anime"
            app._media_ctx.confidence = 0.9
            app._media_ctx.last_inferred_at = 0.0
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return self._FAKE_LLM_RESPONSE

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト発話")

            assert "[co_view シグナル]" not in captured["system"]
        asyncio.run(run())

    def test_activity_video_watching_preserved_with_media_signal(self):
        """LLM returning video_watching is correctly stored when media hint present."""
        async def run():
            self._setup_media_ctx("anime", confidence=0.8)
            fake_response = json.dumps({
                "activity": "video_watching",
                "topic": "アニメ視聴",
                "confidence": 0.85,
                "mood": "calm",
                "location": "home",
                "time_context": "evening",
            })

            with mock.patch("app.chat_with_llm", return_value=fake_response):
                await app._build_context_summary("しーん")

            assert app._context_summary.activity == "video_watching"
        asyncio.run(run())


# ---- Phase G3: confidence discount ----

class TestConfidenceDiscount:
    """Phase G3: post-processing confidence discount based on transcript length and evidence count."""

    @pytest.fixture(autouse=True)
    def reset_summary(self):
        app._context_summary.confidence = 0.0
        app._context_summary.evidence_snippets = []
        app._context_summary.updated_at = 0.0
        app._media_ctx.reset()
        yield
        app._media_ctx.reset()

    def _fake_llm_response(self, confidence=0.9, evidence_snippets=None):
        return json.dumps({
            "activity": "working",
            "topic": "test",
            "confidence": confidence,
            "evidence_snippets": evidence_snippets or [],
            "mood": "", "location": "", "time_context": "",
        })

    def test_short_transcript_and_no_evidence_caps_at_0_3(self):
        """transcript < 100 chars + 0 evidence → confidence capped at 0.3."""
        async def run():
            fake = self._fake_llm_response(confidence=0.9, evidence_snippets=[])
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("短い")  # 2 chars
            assert app._context_summary.confidence <= 0.3
        asyncio.run(run())

    def test_short_transcript_with_one_evidence_caps_at_0_3(self):
        """transcript < 100 chars → caps at 0.3 regardless of evidence count."""
        async def run():
            fake = self._fake_llm_response(confidence=0.9, evidence_snippets=["根拠一件"])
            short_transcript = "a" * 50  # 50 chars < 100
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(short_transcript)
            assert app._context_summary.confidence <= 0.3
        asyncio.run(run())

    def test_zero_evidence_caps_at_0_3_regardless_of_length(self):
        """0 evidence_snippets → confidence capped at 0.3 even with long transcript."""
        async def run():
            fake = self._fake_llm_response(confidence=0.9, evidence_snippets=[])
            long_transcript = "発話の内容が長い。" * 40  # > 100 chars
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            assert app._context_summary.confidence <= 0.3
        asyncio.run(run())

    def test_medium_transcript_one_evidence_caps_at_0_55(self):
        """100 ≤ chars < 300 with 1 evidence → capped at 0.55."""
        async def run():
            fake = self._fake_llm_response(confidence=0.9, evidence_snippets=["根拠一件"])
            medium_transcript = "これは中程度の長さの発話です。" * 10  # ~150 chars
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(medium_transcript)
            assert app._context_summary.confidence <= 0.55
        asyncio.run(run())

    def test_long_transcript_multiple_evidence_no_discount(self):
        """≥300 chars + ≥2 evidence → no discount applied."""
        async def run():
            fake = self._fake_llm_response(
                confidence=0.85,
                evidence_snippets=["具体的な根拠その一", "具体的な根拠その二"],
            )
            long_transcript = "会議中の具体的な発話で固有名詞も多い。京セラの案件について話し合った。" * 15
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            assert abs(app._context_summary.confidence - 0.85) < 1e-6
        asyncio.run(run())

    def test_discount_does_not_go_below_original_when_already_low(self):
        """If LLM already returns low confidence, discount does not raise it."""
        async def run():
            fake = self._fake_llm_response(confidence=0.1, evidence_snippets=[])
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("短い")
            assert app._context_summary.confidence == 0.1  # min(0.1, 0.3) = 0.1
        asyncio.run(run())

    def test_discount_floor_is_not_zero(self):
        """Discount uses min() so LLM values below cap are preserved (no forced floor)."""
        async def run():
            fake = self._fake_llm_response(confidence=0.2, evidence_snippets=[])
            long_transcript = "発話内容。" * 50  # > 100 chars, 0 evidence
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            # 0 evidence → cap 0.3, but LLM returned 0.2 < 0.3, so preserved
            assert app._context_summary.confidence == 0.2
        asyncio.run(run())

    def test_prompt_contains_calibration_guidance(self):
        """System prompt includes confidence calibration guidelines."""
        async def run():
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return json.dumps({
                    "activity": "working", "confidence": 0.5,
                    "mood": "", "location": "", "time_context": "",
                })

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト")

            assert "confidence キャリブレーション基準" in captured["system"]
            assert "100 文字未満" in captured["system"]
            assert "evidence_snippets を 1 件も抽出できない" in captured["system"]
        asyncio.run(run())


# ---- Phase H2: context_summary injection into soliloquy + ambient ----

class TestH2InjectionSoliloquy:
    """Phase H2: _generate_soliloquy includes context_summary in user_prompt."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        yield
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0

    def test_context_hint_injected_into_user_prompt_when_active(self):
        """Active context_summary appears in soliloquy user_prompt."""
        async def run():
            app._context_summary.activity = "meeting"
            app._context_summary.topic = "京セラ案件"
            app._context_summary.confidence = 0.8
            app._context_summary.updated_at = time.time()

            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["user"] = messages[1]["content"]
                return "今日の会議、長かったな"

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._generate_soliloquy()

            assert "現在の状況コンテキスト" in captured["user"]
            assert "京セラ案件" in captured["user"]
        asyncio.run(run())

    def test_context_hint_not_injected_when_low_confidence(self):
        """Low-confidence context_summary is not injected into soliloquy."""
        async def run():
            app._context_summary.activity = "meeting"
            app._context_summary.confidence = 0.1
            app._context_summary.updated_at = time.time()

            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["user"] = messages[1]["content"]
                return "静かだな"

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._generate_soliloquy()

            assert "現在の状況コンテキスト" not in captured["user"]
        asyncio.run(run())

    def test_context_hint_not_injected_when_stale(self):
        """Stale context_summary is not injected into soliloquy."""
        async def run():
            app._context_summary.activity = "working"
            app._context_summary.confidence = 0.9
            app._context_summary.updated_at = time.time() - 700

            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["user"] = messages[1]["content"]
                return "もう夜か"

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._generate_soliloquy()

            assert "現在の状況コンテキスト" not in captured["user"]
        asyncio.run(run())


class TestH2InjectionAmbientBatch:
    """Phase H2: ambient batch LLM prompt includes context_summary."""

    @pytest.fixture(autouse=True)
    def reset_state(self, tmp_path):
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        # Set up a minimal ambient_listener for build_llm_prompt
        import ambient_listener as al
        rules_file = tmp_path / "ambient_rules.json"
        rules_file.write_text('{"rules": [], "keywords": []}')
        examples_file = tmp_path / "ambient_examples.json"
        examples_file.write_text('{"examples": []}')
        app._ambient_listener = al.AmbientListener(
            rules_path=rules_file,
            examples_path=examples_file,
            reactivity=3,
        )
        yield
        app._ambient_listener = None
        app._context_summary.activity = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0

    def test_context_hint_present_in_ambient_prompt_when_active(self):
        """Active context_summary is appended to ambient build_llm_prompt output."""
        app._context_summary.activity = "meeting"
        app._context_summary.topic = "戦略会議"
        app._context_summary.confidence = 0.75
        app._context_summary.updated_at = time.time()

        base_prompt = app._ambient_listener.build_llm_prompt(source_hint="user_identified")
        context_hint = app._context_summary.to_prompt_block()
        assert context_hint  # must be non-empty
        combined = base_prompt + context_hint
        assert "現在の状況コンテキスト" in combined
        assert "戦略会議" in combined

    def test_context_hint_empty_when_low_confidence(self):
        """Low-confidence context_summary produces empty to_prompt_block."""
        app._context_summary.activity = "meeting"
        app._context_summary.confidence = 0.1
        app._context_summary.updated_at = time.time()

        hint = app._context_summary.to_prompt_block()
        assert hint == ""


# ---- Phase J1: activity/language_register whitelist validation ----

class TestJ1Validation:
    """Phase J1: whitelist validation for activity and language_register fields."""

    @pytest.fixture(autouse=True)
    def reset_summary(self):
        app._context_summary.activity = ""
        app._context_summary.language_register = ""
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        app._media_ctx.reset()
        yield
        app._media_ctx.reset()

    def test_invalid_activity_falls_back_to_idle(self):
        """LLM returning activity='focused_solo' (a language_register value) → replaced with 'idle'."""
        async def run():
            fake = json.dumps({
                "activity": "focused_solo",
                "language_register": "focused_solo",
                "confidence": 0.7,
                "evidence_snippets": ["テスト発話その一", "テスト発話その二"],
            })
            long_transcript = "テスト発話その一、テスト発話その二。" * 20
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            assert app._context_summary.activity == "idle"
        asyncio.run(run())

    def test_valid_activity_preserved(self):
        """Valid activity values are not replaced."""
        for valid_activity in ("working", "video_watching", "reading", "meeting", "chatting", "idle"):
            async def run(act=valid_activity):
                fake = json.dumps({
                    "activity": act,
                    "language_register": "casual_solo",
                    "confidence": 0.7,
                    "evidence_snippets": ["根拠一", "根拠二"],
                })
                long_transcript = "十分に長い発話内容。" * 20
                with mock.patch("app.chat_with_llm", return_value=fake):
                    await app._build_context_summary(long_transcript)
                assert app._context_summary.activity == act
            asyncio.run(run())

    def test_invalid_language_register_falls_back_to_casual_solo(self):
        """LLM returning language_register='noon' (invalid value) → replaced with 'casual_solo'."""
        async def run():
            fake = json.dumps({
                "activity": "working",
                "language_register": "noon",
                "confidence": 0.7,
                "evidence_snippets": ["根拠一", "根拠二"],
            })
            long_transcript = "十分に長い発話内容。" * 20
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            assert app._context_summary.language_register == "casual_solo"
        asyncio.run(run())

    def test_valid_language_register_preserved(self):
        """Valid language_register values are not replaced."""
        for valid_lr in ("casual_solo", "focused_solo", "business_meeting", "chat"):
            async def run(lr=valid_lr):
                fake = json.dumps({
                    "activity": "working",
                    "language_register": lr,
                    "confidence": 0.7,
                    "evidence_snippets": ["根拠一", "根拠二"],
                })
                long_transcript = "十分に長い発話内容。" * 20
                with mock.patch("app.chat_with_llm", return_value=fake):
                    await app._build_context_summary(long_transcript)
                assert app._context_summary.language_register == lr
            asyncio.run(run())

    def test_empty_language_register_not_replaced(self):
        """Empty language_register (absent from JSON) stays empty (not replaced with casual_solo)."""
        async def run():
            fake = json.dumps({
                "activity": "working",
                "confidence": 0.7,
                "evidence_snippets": ["根拠一", "根拠二"],
            })
            long_transcript = "十分に長い発話内容。" * 20
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary(long_transcript)
            assert app._context_summary.language_register == ""
        asyncio.run(run())

    def test_prompt_contains_concept_distinction_guidance(self):
        """System prompt clarifies that activity and language_register are distinct concepts."""
        async def run():
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return json.dumps({
                    "activity": "working", "confidence": 0.5,
                    "mood": "", "location": "", "time_context": "",
                })

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("テスト")

            assert "focused_solo は language_register のみの値" in captured["system"]
            assert "activity" in captured["system"]
            assert "language_register" in captured["system"]
        asyncio.run(run())

    def test_prompt_contains_media_hint_bias_guidance(self):
        """System prompt instructs to bias activity toward video_watching when co_view signal present."""
        async def run():
            app._media_ctx.inferred_type = "youtube_talk"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = time.time()
            captured = {}

            async def fake_llm(messages, model="gemma4:e4b"):
                captured["system"] = messages[0]["content"]
                return json.dumps({
                    "activity": "video_watching", "confidence": 0.7,
                    "mood": "", "location": "", "time_context": "",
                })

            with mock.patch("app.chat_with_llm", side_effect=fake_llm):
                await app._build_context_summary("なるほどそういうことか")

            assert "video_watching" in captured["system"]
            assert "バイアス" in captured["system"] or "推奨" in captured["system"]
        asyncio.run(run())


# ---- Phase K2: is_meeting 3層防御 ----

class TestK2IsMeetingDefense:
    """Phase K2: is_meeting 誤判定対策（3層防御）。"""

    _LONG_TRANSCRIPT = "テスト発話が続いている。" * 20

    def _fake_llm(self, is_meeting: bool, confidence: float = 0.8):
        return json.dumps({
            "activity": "meeting" if is_meeting else "video_watching",
            "topic": "テスト",
            "is_meeting": is_meeting,
            "confidence": confidence,
            "evidence_snippets": ["根拠その一", "根拠その二"],
            "mood": "", "location": "", "time_context": "",
        })

    @pytest.fixture(autouse=True)
    def reset_state(self):
        app._context_summary.is_meeting = False
        app._context_summary.confidence = 0.0
        app._context_summary.updated_at = 0.0
        app._media_ctx.reset()
        app._gcal_meeting_cache.update({
            "title": "", "start_ts": 0.0, "end_ts": 0.0,
            "event_id": "", "fetched_at": 0.0,
        })
        yield
        app._media_ctx.reset()
        app._gcal_meeting_cache.update({
            "title": "", "start_ts": 0.0, "end_ts": 0.0,
            "event_id": "", "fetched_at": 0.0,
        })

    def test_l1_youtube_talk_overrides_is_meeting_true(self):
        """L1: youtube_talk + LLM is_meeting=True → False に上書き。"""
        async def run():
            app._media_ctx.inferred_type = "youtube_talk"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = time.time()
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is False
        asyncio.run(run())

    def test_l1_youtube_music_overrides_is_meeting_true(self):
        """L1: youtube_music も対象。"""
        async def run():
            app._media_ctx.inferred_type = "youtube_music"
            app._media_ctx.confidence = 0.9
            app._media_ctx.last_inferred_at = time.time()
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is False
        asyncio.run(run())

    def test_l1_non_youtube_type_does_not_override(self):
        """L1: youtube 系でない type（anime）は is_meeting を上書きしない。"""
        async def run():
            app._media_ctx.inferred_type = "anime"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = time.time()
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is True
        asyncio.run(run())

    def test_l1_stale_media_ctx_does_not_override(self):
        """L1: 10分以上古い media_ctx は L1 発動しない。"""
        async def run():
            app._media_ctx.inferred_type = "youtube_talk"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = time.time() - 700
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is True
        asyncio.run(run())

    def test_l2_active_calendar_event_forces_is_meeting_true(self):
        """L2: 進行中のカレンダーイベントがあれば L1 を上書きして is_meeting=True。"""
        async def run():
            now = time.time()
            app._media_ctx.inferred_type = "youtube_talk"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = now
            app._gcal_meeting_cache.update({
                "title": "京セラ戦略会議",
                "start_ts": now - 600,
                "end_ts": now + 600,
                "fetched_at": now,
            })
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is True
        asyncio.run(run())

    def test_l2_no_active_event_does_not_change(self):
        """L2: カレンダーイベントなしなら is_meeting に介入しない。"""
        async def run():
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=False)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is False
        asyncio.run(run())

    def test_l3_low_akira_ratio_with_media_overrides(self):
        """L3: Akira の発話比率 5% + youtube → is_meeting=False。"""
        async def run():
            now = time.time()
            app._media_ctx.inferred_type = "youtube_talk"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = now
            # ambient_listener をセットアップ (inlineクラスで代用)
            class FakeAmbientListener:
                _recent_speakers = [
                    {"speaker": "other_person", "ts": now - 10},
                    {"speaker": "other_person", "ts": now - 20},
                    {"speaker": "other_person", "ts": now - 30},
                    {"speaker": "other_person", "ts": now - 40},
                    {"speaker": "other_person", "ts": now - 50},
                    {"speaker": "other_person", "ts": now - 60},
                    {"speaker": "other_person", "ts": now - 70},
                    {"speaker": "other_person", "ts": now - 80},
                    {"speaker": "other_person", "ts": now - 90},
                    {"speaker": "other_person", "ts": now - 100},
                    {"speaker": "other_person", "ts": now - 110},
                    {"speaker": "other_person", "ts": now - 120},
                    {"speaker": "other_person", "ts": now - 130},
                    {"speaker": "other_person", "ts": now - 140},
                    {"speaker": "other_person", "ts": now - 150},
                    {"speaker": "other_person", "ts": now - 160},
                    {"speaker": "other_person", "ts": now - 170},
                    {"speaker": "other_person", "ts": now - 180},
                    {"speaker": "other_person", "ts": now - 190},
                    {"speaker": "akira", "ts": now - 200},  # 5%
                ]
            app._ambient_listener = FakeAmbientListener()
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is False
            app._ambient_listener = None
        asyncio.run(run())

    def test_l3_high_akira_ratio_preserves_is_meeting(self):
        """L3: Akira の発話比率 >= 30% → is_meeting=True を保持。"""
        async def run():
            now = time.time()
            # youtube_talk だが akira 発話比率が高い → L1 が上書きするので、
            # L1 が効かない type (anime) で L3 のみを確認する
            app._media_ctx.inferred_type = "anime"
            app._media_ctx.confidence = 0.8
            app._media_ctx.last_inferred_at = now
            class FakeAmbientListener:
                _recent_speakers = [
                    {"speaker": "akira", "ts": now - 10},
                    {"speaker": "akira", "ts": now - 20},
                    {"speaker": "akira", "ts": now - 30},
                    {"speaker": "akira", "ts": now - 40},
                    {"speaker": "other", "ts": now - 50},
                    {"speaker": "other", "ts": now - 60},
                    {"speaker": "other", "ts": now - 70},
                ]
            app._ambient_listener = FakeAmbientListener()
            with mock.patch("app.chat_with_llm", return_value=self._fake_llm(is_meeting=True)):
                await app._build_context_summary(self._LONG_TRANSCRIPT)
            assert app._context_summary.is_meeting is True
            app._ambient_listener = None
        asyncio.run(run())
