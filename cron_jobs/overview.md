# 定期実行ジョブ一覧

実行基盤: claude-code-slack-bot（pm2 常時起動）
設定ファイル: `/Users/akira/workspace/claude-code-slack-bot/cron-jobs.json`
タイムゾーン: Asia/Tokyo

---

## 日次

| ジョブ名 | スケジュール | 概要 | 送信先 |
|---------|------------|------|--------|
| tech-news-digest | 毎日 9:00 | Google News RSS / HN / GitHub からテックニュースを収集し、ローカル LLM で翻訳して投稿 | #tech-news (C0AJT8XU8G0) |
| haru-nightly-reflection | 毎日 19:30 | 前回の定期実行以降の Slack やり取りを振り返り、Akira について新しく分かったこと（趣味・興味・好み・行動パターンなど）があれば Claude Code memory に保存 | DM (U3SFGQXNH) |
| interest-scanner | 毎日 9:50〜20:50（毎時 :50、9-20時） | Akiraさんの興味カテゴリ（AI、ドジャース、キャンピングカー等9カテゴリ）を Google News RSS でスキャン。スコアリングして interest-cache.json に保存 | DM (U3SFGQXNH) |
| proactive-checkin | 毎日 9,11,14,17,20時 | ニーズアセスメント型。カレンダー + メール + cogmem記憶 + interest-cache を総合判断し、最も届けるべき情報を選択して話しかける | DM (U3SFGQXNH) |

## 週次

| ジョブ名 | スケジュール | 概要 | 送信先 |
|---------|------------|------|--------|
| ir-news-check | 毎週月曜 9:00 | company_list.md の企業リストを元に、最新の決算短信を Web 検索で確認。新着があればサマリを送信 | DM (U3SFGQXNH) |
| ~~gmail-to-drive~~ | ~~毎週月曜 9:00~~ | **【2026-04-24 移行・無効化】** GitHub Actions (`akira-001/claude-code-slack-bot/.github/workflows/gmail-to-drive.yml`) に移行済み。月曜 0:00 UTC (= 9:00 JST) に発火 | DM (U3SFGQXNH) |
| ~~paper-digest-weekly~~ | ~~毎週土曜 8:00~~ | **【2026-04-24 移行・無効化】** claude.ai routine `daily-arxiv-digest` (trig_015a5QVcbrVpKNFpisGaFLx7) に統合。毎日 8:00 JST 実行、7カテゴリ（AIエージェント/ローカルLLM/AI動画生成/コード生成/マルチモーダル/RAG/AI安全性）から TOP5 を日本語要約投稿 | #secretary (C0AHPJMS5QE) |
| campingcar-search-weekly | 毎週金曜 9:05 | campnofuji.jp からキャンピングカーの新着物件をスクレイピングし、SOLD OUT 除外・装備分離表示・ローカル LLM おすすめピック付きで投稿 | DM (U3SFGQXNH) |

---

## スクリプト一覧

| スクリプト | パス | 依存 |
|-----------|------|------|
| tech_news.py | /Users/akira/workspace/ai-dev/web-search/tech_news.py | Python venv |
| campingcar_search.py | /Users/akira/workspace/ai-dev/web-search/campingcar_search.py | Python venv |
| interest_scanner.py | /Users/akira/workspace/ai-dev/web-search/interest_scanner.py | Python venv |
| gmail_to_drive.py | /Users/akira/workspace/claude-code-slack-bot/scripts/gmail_to_drive.py | Gmail API (motogami), Drive API (redperth) |

## 外部データファイル

| ファイル | パス | 用途 |
|---------|------|------|
| company_list.md | /Users/akira/workspace/open-claude/ir_news_cron/company_list.md | IR チェック対象企業リスト（行ごとに企業名） |
