"""Ambient enrichment provider — co_view / meeting context に有益情報を補強する。

設計思想:
- 暫定: LLM 自身に検索させる (LLMSearchProvider) — claude/codex CLI の組込み tool で web/Slack 検索
- 将来: 決め打ちプリフェッチ (PrefetchProvider) — Slack RAG / Wikipedia / AniList を並列 fetch

両者は EnrichmentProvider ABC を満たすので、起動時の `_provider = ...` 切替で実装入替可能。

ambient 経路はキャッシュから読むだけ (TTL 内なら同期参照)。
裏で enrichment_loop が周期的に provider.enrich() を呼んで cache を更新する。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voice-chat")


# --- Context model ---

@dataclass
class EnrichmentContext:
    """プロバイダに渡す入力。context_summary + media_ctx + calendar の主要情報を集約。"""
    activity: str = ""              # working / meeting / video_watching / etc
    is_meeting: bool = False
    topic: str = ""
    keywords: list[str] = field(default_factory=list)
    named_entities: list[str] = field(default_factory=list)
    inferred_type: str = ""         # youtube_talk / anime / vtuber / news / meeting / etc
    matched_title: str = ""         # 推定された動画/作品タイトル
    calendar_event: str = ""        # 進行中ミーティングのタイトル
    transcript_excerpt: str = ""    # 直近 5 件の音声断片（重複検出用）

    def signature(self) -> str:
        """キャッシュキー用の安定 hash。topic / matched_title / activity が同じなら同じ key。"""
        h = hashlib.sha1()
        for v in (
            self.activity, self.is_meeting, self.inferred_type,
            self.matched_title, self.topic, self.calendar_event,
            "|".join(sorted(self.named_entities[:5])),
        ):
            h.update(str(v).encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()[:16]


# --- Cache ---

@dataclass
class CacheEntry:
    signature: str
    enrichment: str
    fetched_at: float
    ttl_sec: float

    def is_fresh(self) -> bool:
        return time.time() - self.fetched_at < self.ttl_sec


class EnrichmentCache:
    """signature ベースのシンプルキャッシュ。TTL 経過で stale 判定。"""

    def __init__(self, max_entries: int = 16):
        self._entries: dict[str, CacheEntry] = {}
        self._max = max_entries

    def get(self, signature: str) -> Optional[CacheEntry]:
        entry = self._entries.get(signature)
        if entry and entry.is_fresh():
            return entry
        return None

    def set(self, signature: str, enrichment: str, ttl_sec: float = 1800.0) -> None:
        self._entries[signature] = CacheEntry(
            signature=signature,
            enrichment=enrichment,
            fetched_at=time.time(),
            ttl_sec=ttl_sec,
        )
        if len(self._entries) > self._max:
            # 最古を削除
            oldest = min(self._entries.values(), key=lambda e: e.fetched_at)
            del self._entries[oldest.signature]

    def latest(self) -> Optional[CacheEntry]:
        if not self._entries:
            return None
        return max(self._entries.values(), key=lambda e: e.fetched_at)


# --- Provider ABC ---

class EnrichmentProvider(ABC):
    """ambient 文脈の補強情報を生成する provider。"""

    @abstractmethod
    async def enrich(self, ctx: EnrichmentContext) -> str:
        """markdown ブロックを返す。空文字なら enrichment 失敗 / 不要。"""
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.__class__.__name__


# --- LLM Search Provider (暫定実装) ---

class LLMSearchProvider(EnrichmentProvider):
    """LLM (claude / codex CLI) に web/Slack 検索させる。

    CLI subprocess を経由するため latency は数十秒級。背景ループで実行する前提。"""

    def __init__(self, *, prefer_claude: bool = True, timeout_sec: int = 90):
        self.prefer_claude = prefer_claude
        self.timeout_sec = timeout_sec

    async def enrich(self, ctx: EnrichmentContext) -> str:
        prompt = self._build_research_prompt(ctx)
        if not prompt:
            return ""

        if self.prefer_claude:
            result = await self._claude_research(prompt)
            if result:
                return result
            # fallback to codex
            return await self._codex_research(prompt)
        else:
            result = await self._codex_research(prompt)
            if result:
                return result
            return await self._claude_research(prompt)

    def _build_research_prompt(self, ctx: EnrichmentContext) -> str:
        """ctx の内容によって用途別の研究プロンプトを構築。"""
        if ctx.is_meeting or ctx.activity == "meeting" or ctx.calendar_event:
            return self._meeting_prompt(ctx)
        if ctx.inferred_type in ("anime", "vtuber", "drama"):
            return self._media_prompt(ctx)
        if ctx.inferred_type in ("youtube_talk", "news"):
            return self._knowledge_prompt(ctx)
        # フォールバック: 一般トピック
        if ctx.topic or ctx.named_entities:
            return self._knowledge_prompt(ctx)
        return ""

    def _meeting_prompt(self, ctx: EnrichmentContext) -> str:
        target = ctx.calendar_event or ctx.topic or "現在の会議"
        entities = ", ".join(ctx.named_entities[:5]) if ctx.named_entities else "（不明）"
        return (
            f"ユーザー（Akiraさん）が今、'{target}' という打ち合わせ中です。\n"
            f"会議内で言及された主な人名・企業名・案件: {entities}\n\n"
            "以下の観点で関連情報を 200 字以内の簡潔な日本語 markdown でまとめてください。\n"
            "- 該当顧客/企業の最新ニュース（直近 1 ヶ月）\n"
            "- 過去の Slack やり取り / Notion 議事録があれば要約\n"
            "- 顧客から想定される質問への回答候補\n"
            "Slack や Web 検索ツールを必要に応じて呼び、根拠を抑えた内容のみ。\n"
            "情報が見つからなければ 'ENRICHMENT_NONE' と返してください。"
        )

    def _media_prompt(self, ctx: EnrichmentContext) -> str:
        title = ctx.matched_title or ctx.topic
        if not title:
            return ""
        return (
            f"ユーザーが今 '{title}' を視聴中です（種別: {ctx.inferred_type}）。\n\n"
            "以下を 200 字以内の日本語 markdown で簡潔にまとめてください。\n"
            "- 主要キャラクター 2-3 名と声優\n"
            "- 制作スタジオ / 監督 / 原作\n"
            "- 直近の関連イベント（放送/配信予定、コラボ等）\n"
            "Wikipedia / AniList / Web 検索を活用。spoiler は避ける。\n"
            "情報が見つからなければ 'ENRICHMENT_NONE' と返してください。"
        )

    def _knowledge_prompt(self, ctx: EnrichmentContext) -> str:
        topic = ctx.topic or "今のトピック"
        entities = ", ".join(ctx.named_entities[:5]) if ctx.named_entities else ""
        return (
            f"ユーザーが視聴/会話中のトピック: '{topic}'\n"
            f"言及された固有名詞: {entities}\n\n"
            "以下を 200 字以内の日本語 markdown で簡潔にまとめてください。\n"
            "- 上記固有名詞の背景情報（業界、製品概要、最新動向）\n"
            "- ユーザーが知っておくと有益な関連知識\n"
            "Web 検索 / Wikipedia を活用。\n"
            "情報が見つからなければ 'ENRICHMENT_NONE' と返してください。"
        )

    async def _claude_research(self, prompt: str) -> str:
        """claude CLI subprocess で実行。組込み WebSearch / Slack tool を活用させる。"""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", "--model", "sonnet",
                "--dangerously-skip-permissions",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=self.timeout_sec,
            )
            if proc.returncode != 0:
                err = stderr_b.decode("utf-8", errors="replace")[:200]
                logger.warning(f"[enrichment/claude] CLI exit {proc.returncode}: {err}")
                return ""
            text = stdout_b.decode("utf-8", errors="replace").strip()
            if "ENRICHMENT_NONE" in text:
                return ""
            return text
        except asyncio.TimeoutError:
            logger.warning(f"[enrichment/claude] CLI timeout ({self.timeout_sec}s)")
            return ""
        except FileNotFoundError:
            logger.warning("[enrichment/claude] claude CLI not found")
            return ""

    async def _codex_research(self, prompt: str) -> str:
        """codex CLI subprocess で実行（fallback）。"""
        out_path = Path(f"/tmp/enrichment_codex_{os.getpid()}_{int(time.time())}.txt")
        try:
            proc = await asyncio.create_subprocess_exec(
                "codex", "exec",
                "--skip-git-repo-check",
                "--model", "gpt-5.5",
                "--output-last-message", str(out_path),
                "--dangerously-bypass-approvals-and-sandbox",
                prompt,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            if out_path.exists():
                text = out_path.read_text(encoding="utf-8").strip()
                if "ENRICHMENT_NONE" in text:
                    return ""
                return text
            return ""
        except asyncio.TimeoutError:
            logger.warning(f"[enrichment/codex] CLI timeout ({self.timeout_sec}s)")
            return ""
        except FileNotFoundError:
            logger.warning("[enrichment/codex] codex CLI not found")
            return ""
        finally:
            try:
                if out_path.exists():
                    out_path.unlink()
            except OSError:
                pass


# --- Prefetch Provider (将来実装のスケルトン) ---

class PrefetchProvider(EnrichmentProvider):
    """事前並列フェッチ実装（未実装スタブ）。

    将来: ctx.activity / inferred_type で分岐し、Slack/AniList/Wiki/Web search を asyncio.gather で並列 fetch。
    現時点では未実装のため LLMSearchProvider を使うこと。
    """

    async def enrich(self, ctx: EnrichmentContext) -> str:
        logger.warning("[enrichment] PrefetchProvider not implemented yet, returning empty")
        return ""


# --- Orchestrator ---

class EnrichmentOrchestrator:
    """背景ループから呼ばれて cache を更新する。ambient flow は同期的に latest() を読む。"""

    def __init__(self, provider: EnrichmentProvider, cache: EnrichmentCache):
        self.provider = provider
        self.cache = cache
        self._last_signature: str = ""
        self._inflight: bool = False

    async def maybe_refresh(self, ctx: EnrichmentContext) -> None:
        """signature が前回と違えば enrich を実行。並走防止。"""
        sig = ctx.signature()
        if not sig or sig == self._last_signature:
            return
        existing = self.cache.get(sig)
        if existing:
            self._last_signature = sig
            return
        if self._inflight:
            logger.debug("[enrichment] already in-flight, skip")
            return
        self._inflight = True
        try:
            logger.info(
                f"[enrichment] refreshing via {self.provider.name} "
                f"(activity={ctx.activity}, type={ctx.inferred_type}, sig={sig})"
            )
            text = await self.provider.enrich(ctx)
            if text:
                # is_meeting は鮮度重視で短め TTL、それ以外は 30 分
                ttl = 600.0 if ctx.is_meeting else 1800.0
                self.cache.set(sig, text, ttl_sec=ttl)
                self._last_signature = sig
                logger.info(f"[enrichment] cached ({len(text)} chars, ttl={int(ttl)}s)")
            else:
                logger.debug("[enrichment] empty result, not caching")
        except Exception as e:
            logger.warning(f"[enrichment] refresh error: {e}")
        finally:
            self._inflight = False

    def get_for_prompt(self) -> str:
        """ambient プロンプトに注入する markdown ブロック。fresh cache がなければ空文字。"""
        entry = self.cache.latest()
        if not entry or not entry.is_fresh():
            return ""
        return f"\n\n## 関連情報（{self.provider.name}）\n{entry.enrichment}\n"


# --- Loop entry ---

async def enrichment_loop(
    orchestrator: EnrichmentOrchestrator,
    ctx_provider,  # callable returning EnrichmentContext
    interval_sec: int = 60,
):
    """背景ループ。`ctx_provider()` は app 側で context_summary/media_ctx を集約して返す。"""
    while True:
        try:
            await asyncio.sleep(interval_sec)
            ctx = ctx_provider()
            if ctx is None:
                continue
            await orchestrator.maybe_refresh(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[enrichment_loop] error: {e}")
            await asyncio.sleep(30)
