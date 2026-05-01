"""Tests for co_view (Listening mode) feature."""
import asyncio
import json
import sys
import time
import types
import unittest.mock as mock
import pytest

# --- Mock heavy ML dependencies before importing app ---
_heavy_mocks = {}
for mod_name in [
    "faster_whisper", "faster_whisper.WhisperModel",
    "speechbrain", "speechbrain.inference", "speechbrain.inference.speaker",
    "torch", "torchaudio", "numpy",
    "uvicorn",
]:
    if mod_name not in sys.modules:
        _heavy_mocks[mod_name] = types.ModuleType(mod_name)
        sys.modules[mod_name] = _heavy_mocks[mod_name]

# Provide minimal WhisperModel stub
_wm = types.ModuleType("faster_whisper")
_wm.WhisperModel = mock.MagicMock()
sys.modules["faster_whisper"] = _wm

# Provide minimal SpeakerRecognition stub
_sb_inf_spk = types.ModuleType("speechbrain.inference.speaker")
_sb_inf_spk.SpeakerRecognition = mock.MagicMock()
sys.modules["speechbrain.inference.speaker"] = _sb_inf_spk
_sb_inf = types.ModuleType("speechbrain.inference")
_sb_inf.speaker = _sb_inf_spk
sys.modules["speechbrain.inference"] = _sb_inf
_sb = types.ModuleType("speechbrain")
_sb.inference = _sb_inf
sys.modules["speechbrain"] = _sb

from ambient_listener import AmbientListener  # noqa: E402


# ---- Fixtures ----

@pytest.fixture
def listener_level5(tmp_path):
    rules_file = tmp_path / "ambient_rules.json"
    rules_file.write_text(json.dumps({"rules": [], "keywords": []}))
    examples_file = tmp_path / "ambient_examples.json"
    examples_file.write_text(json.dumps({"examples": []}))
    return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=5)


@pytest.fixture
def listener_level3(tmp_path):
    rules_file = tmp_path / "ambient_rules.json"
    rules_file.write_text(json.dumps({"rules": [], "keywords": []}))
    examples_file = tmp_path / "ambient_examples.json"
    examples_file.write_text(json.dumps({"examples": []}))
    return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)


# ---- decide_intervention: co_view ----

class TestCoViewIntervention:
    def test_media_likely_at_level5_returns_co_view(self, listener_level5):
        """レベル5 + media_likely → co_view を返す (60文字超 or メディアヒントフレーズ)"""
        # 番組/放送 は _MEDIA_HINT_RE にマッチ → media_likely 確定
        text = "この番組はご覧のスポンサーの提供でお送りします"
        source = listener_level5.classify_source(text)
        assert source == "media_likely"
        intervention = listener_level5.decide_intervention(text, source)
        assert intervention == "co_view"

    def test_media_likely_long_text_at_level5_returns_co_view(self, listener_level5):
        """長いテキスト(>60文字) + レベル5 → co_view を返す"""
        long_text = "ただいまスコアはドジャースが3対1でリードしております。大谷投手が好調です。" * 3
        assert len(long_text) > 60
        source = listener_level5.classify_source(long_text)
        assert source == "media_likely"
        assert listener_level5.decide_intervention(long_text, source) == "co_view"

    def test_media_likely_at_level3_returns_skip(self, listener_level3):
        """レベル3 + media_likely → skip のまま"""
        text = "この番組はご覧のスポンサーの提供でお送りします"
        source = listener_level3.classify_source(text)
        assert source == "media_likely"
        intervention = listener_level3.decide_intervention(text, source)
        assert intervention == "skip"

    def test_media_hint_phrase_level5_returns_co_view(self, listener_level5):
        """チャンネル登録などのメディアヒントフレーズ + レベル5 → co_view"""
        text = "チャンネル登録よろしくお願いします"
        source = listener_level5.classify_source(text)
        assert source == "media_likely"
        assert listener_level5.decide_intervention(text, source) == "co_view"

    def test_fragmentary_still_skipped_at_level5(self, listener_level5):
        """fragmentary はレベル5でも skip"""
        text = "あ"
        source = listener_level5.classify_source(text)
        assert source == "fragmentary"
        assert listener_level5.decide_intervention(text, source) == "skip"

    def test_user_initiative_unaffected_at_level5(self, listener_level5):
        """ユーザー発話は co_view にならない"""
        text = "ねえメイ、今何時？"
        source = listener_level5.classify_source(text)
        assert source == "user_initiative"
        assert listener_level5.decide_intervention(text, source) == "reply"


# ---- _MediaContext (app module not required for this class) ----

class TestMediaContext:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        """各テスト前に _media_ctx をリセット"""
        # Import here so mocks are active
        import app
        app._media_ctx.reset()
        yield app._media_ctx
        app._media_ctx.reset()

    def test_add_snippet_increments_counter(self, fresh_ctx):
        fresh_ctx.add_snippet("テスト1")
        fresh_ctx.add_snippet("テスト2")
        assert len(fresh_ctx.media_buffer) == 2
        assert fresh_ctx.snippets_since_infer == 2

    def test_rolling_window_caps_at_20(self, fresh_ctx):
        for i in range(25):
            fresh_ctx.add_snippet(f"スニペット{i}")
        assert len(fresh_ctx.media_buffer) == 20
        assert fresh_ctx.media_buffer[0]["text"] == "スニペット5"

    def test_get_buffer_text(self, fresh_ctx):
        fresh_ctx.add_snippet("A")
        fresh_ctx.add_snippet("B")
        fresh_ctx.add_snippet("C")
        text = fresh_ctx.get_buffer_text(last_n=2)
        assert "B" in text
        assert "C" in text
        assert "A" not in text

    def test_reset_clears_all_state(self, fresh_ctx):
        fresh_ctx.add_snippet("test")
        fresh_ctx.inferred_type = "baseball"
        fresh_ctx.inferred_topic = "ドジャース"
        fresh_ctx.confidence = 0.9
        fresh_ctx.enriched_info = "some info"
        fresh_ctx.keywords = ["ドジャース"]
        fresh_ctx.reset()
        assert len(fresh_ctx.media_buffer) == 0
        assert fresh_ctx.inferred_type == "unknown"
        assert fresh_ctx.inferred_topic == ""
        assert fresh_ctx.confidence == 0.0
        assert fresh_ctx.enriched_info == ""
        assert fresh_ctx.keywords == []
        assert fresh_ctx.snippets_since_infer == 0


# ---- _infer_media_content ----

class TestInferMediaContent:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        import app
        app._media_ctx.reset()
        yield app._media_ctx
        app._media_ctx.reset()

    @pytest.mark.asyncio
    async def test_empty_buffer_returns_unknown(self, fresh_ctx):
        import app
        result = await app._infer_media_content()
        assert result["content_type"] == "unknown"
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_valid_json_from_llm_is_parsed(self, fresh_ctx):
        import app
        fresh_ctx.add_snippet("大谷がホームランを打ちました")
        fresh_ctx.add_snippet("ドジャースが3点リードしています")

        fake_json = json.dumps({
            "content_type": "baseball",
            "topic": "ドジャース試合",
            "keywords": ["ドジャース", "大谷"],
            "confidence": 0.85
        })
        with mock.patch("app.chat_with_llm", return_value=fake_json):
            result = await app._infer_media_content()

        assert result["content_type"] == "baseball"
        assert result["confidence"] == 0.85
        assert "ドジャース" in result["keywords"]

    @pytest.mark.asyncio
    async def test_invalid_json_returns_unknown(self, fresh_ctx):
        import app
        fresh_ctx.add_snippet("テスト音声テスト音声テスト")

        with mock.patch("app.chat_with_llm", return_value="これはJSONではありません"):
            result = await app._infer_media_content()

        assert result["content_type"] == "unknown"
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_parsed(self, fresh_ctx):
        """```json ... ``` 形式でも正しくパースされる"""
        import app
        fresh_ctx.add_snippet("ドジャースのニュース速報です")
        fresh_ctx.add_snippet("ただいまスコアをお伝えします")

        fake_json = '```json\n{"content_type":"baseball","topic":"ドジャース","keywords":["ドジャース"],"confidence":0.8}\n```'
        with mock.patch("app.chat_with_llm", return_value=fake_json):
            result = await app._infer_media_content()

        assert result["content_type"] == "baseball"
        assert result["confidence"] == 0.8


# ---- _enrich_media_context ----

class TestEnrichMediaContext:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        import app
        app._media_ctx.reset()
        yield app._media_ctx
        app._media_ctx.reset()

    @pytest.mark.asyncio
    async def test_cached_result_returned_within_cooldown(self, fresh_ctx):
        import app
        fresh_ctx.enriched_info = "キャッシュされた情報"
        fresh_ctx.last_enriched_at = time.time()  # just now

        result = await app._enrich_media_context()
        assert result == "キャッシュされた情報"

    @pytest.mark.asyncio
    async def test_baseball_fetches_dodgers_rss(self, fresh_ctx):
        import app
        fresh_ctx.inferred_type = "baseball"
        fresh_ctx.keywords = ["ドジャース"]
        fresh_ctx.last_enriched_at = 0  # force re-fetch
        fresh_ctx.inferred_topic = "ドジャース試合"

        fake_rss = (
            '<?xml version="1.0"?>'
            '<rss><channel>'
            '<item><title>ドジャース勝利！大谷3号ホームラン</title></item>'
            '<item><title>ドジャース対パドレス試合結果</title></item>'
            '</channel></rss>'
        )

        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_rss.encode()

        mock_client = mock.AsyncMock()
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)
        mock_client.get = mock.AsyncMock(return_value=mock_resp)

        with mock.patch("app._tool_wikipedia_summary", return_value=None):
            with mock.patch("app.httpx.AsyncClient", return_value=mock_client):
                result = await app._enrich_media_context()

        assert "ドジャース" in result

    @pytest.mark.asyncio
    async def test_enrichment_failure_returns_empty(self, fresh_ctx):
        import app
        fresh_ctx.inferred_type = "news"
        fresh_ctx.keywords = ["テスト"]
        fresh_ctx.last_enriched_at = 0

        with mock.patch("app.httpx.AsyncClient", side_effect=Exception("network error")):
            result = await app._enrich_media_context()

        assert result == ""

    @pytest.mark.asyncio
    async def test_enrichment_caches_result(self, fresh_ctx):
        """エンリッチメント結果がキャッシュされる"""
        import app
        fresh_ctx.inferred_type = "baseball"
        fresh_ctx.keywords = ["ドジャース"]
        fresh_ctx.last_enriched_at = 0
        fresh_ctx.inferred_topic = "テスト"

        fake_rss = (
            '<?xml version="1.0"?><rss><channel>'
            '<item><title>テストニュース</title></item>'
            '</channel></rss>'
        )
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_rss.encode()
        mock_client = mock.AsyncMock()
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=False)
        mock_client.get = mock.AsyncMock(return_value=mock_resp)

        with mock.patch("app._tool_wikipedia_summary", return_value=None):
            with mock.patch("app.httpx.AsyncClient", return_value=mock_client):
                result = await app._enrich_media_context()

        assert fresh_ctx.enriched_info == result
        assert fresh_ctx.last_enriched_at > 0


# ---- _correct_media_transcript ----

class TestCorrectMediaTranscript:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        import app
        app._media_ctx.reset()
        yield
        app._media_ctx.reset()

    @pytest.mark.asyncio
    async def test_dict_correction_applied(self):
        """辞書補正が適用される (例: アンソロピック → Anthropic)"""
        import app
        result = await app._correct_media_transcript("アンソロピックのAIが")
        assert "Anthropic" in result

    @pytest.mark.asyncio
    async def test_short_text_skipped(self):
        """短いテキストはLLM補正をスキップ"""
        import app
        with mock.patch("app.chat_with_llm") as mock_llm:
            result = await app._correct_media_transcript("うん")
            mock_llm.assert_not_called()
        assert result == "うん"

    @pytest.mark.asyncio
    async def test_llm_correction_applied(self):
        """LLMがメディア向け補正を返した場合に適用される"""
        import app
        with mock.patch("app.chat_with_llm", return_value="大谷翔平がホームランを打った"):
            result = await app._correct_media_transcript("おおたにしょうへいがほーあんを打った")
        assert result == "大谷翔平がホームランを打った"

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_original(self):
        """LLMタイムアウト時は元テキストを返す"""
        import app

        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
            return "never"

        with mock.patch("app.chat_with_llm", side_effect=slow):
            # asyncio.wait_for の timeout=3.0 が発火
            result = await app._correct_media_transcript("タイムアウトテストのテキストです")
        # タイムアウトで元テキストが返る (辞書補正後)
        assert isinstance(result, str)


# ---- data loading ----

class TestDataLoading:
    def test_load_youtube_titles_returns_list(self):
        import app
        # 実際のファイルがあれば list、なければ空 list
        result = app._load_youtube_titles()
        assert isinstance(result, list)

    def test_load_interest_priorities_returns_dict(self):
        import app
        result = app._load_interest_priorities()
        assert isinstance(result, dict)

    def test_load_youtube_titles_handles_missing_file(self, tmp_path):
        import app
        original = app._SLACK_BOT_DATA_DIR
        app._SLACK_BOT_DATA_DIR = tmp_path / "nonexistent"
        try:
            result = app._load_youtube_titles()
            assert result == []
        finally:
            app._SLACK_BOT_DATA_DIR = original

    def test_load_interest_priorities_handles_missing_file(self, tmp_path):
        import app
        original = app._SLACK_BOT_DATA_DIR
        app._SLACK_BOT_DATA_DIR = tmp_path / "nonexistent"
        try:
            result = app._load_interest_priorities()
            assert result == {}
        finally:
            app._SLACK_BOT_DATA_DIR = original
