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
| proactive-checkin | 毎日 9,11,14,17,20時 | proactive-agent が状況を判断し、必要に応じて Akira に話しかける（LLM 判断で NO_REPLY もあり） | DM (U3SFGQXNH) |

## 週次

| ジョブ名 | スケジュール | 概要 | 送信先 |
|---------|------------|------|--------|
| ir-news-check | 毎週月曜 9:00 | company_list.md の企業リストを元に、最新の決算短信を Web 検索で確認。新着があればサマリを送信 | DM (U3SFGQXNH) |
| gmail-to-drive | 毎週月曜 9:00 | Gmail (motogami@gmail.com) から領収書・請求書 PDF を検索し、Google Drive (redperth@gmail.com) に自動保存してアーカイブ | #general (C0AHQV1ME4S) |
| campingcar-search-weekly | 毎週金曜 9:05 | campnofuji.jp からキャンピングカーの新着物件をスクレイピングし、SOLD OUT 除外・装備分離表示・ローカル LLM おすすめピック付きで投稿 | DM (U3SFGQXNH) |

---

## スクリプト一覧

| スクリプト | パス | 依存 |
|-----------|------|------|
| tech_news.py | /Users/akira/workspace/ai-dev/web-search/tech_news.py | Python venv |
| campingcar_search.py | /Users/akira/workspace/ai-dev/web-search/campingcar_search.py | Python venv |
| gmail_to_drive.py | /Users/akira/workspace/claude-code-slack-bot/scripts/gmail_to_drive.py | Gmail API (motogami), Drive API (redperth) |

## 外部データファイル

| ファイル | パス | 用途 |
|---------|------|------|
| company_list.md | /Users/akira/workspace/open-claude/ir_news_cron/company_list.md | IR チェック対象企業リスト（行ごとに企業名） |
