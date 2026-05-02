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
        app._context_summary.updated_at = 0.0
        yield

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
                "evidence_snippets": ["PPOってAtariでも安定するのかな"],
            })
            with mock.patch("app.chat_with_llm", return_value=fake):
                await app._build_context_summary("dummy transcript")
            cs = app._context_summary
            assert cs.activity == "video_watching"
            assert cs.topic == "強化学習論文の解説"
            assert cs.subtopics == ["PPO", "Atari"]
            assert cs.is_meeting is False
            assert "PPO" in cs.keywords
            assert abs(cs.confidence - 0.83) < 1e-6
            assert cs.updated_at > 0
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
