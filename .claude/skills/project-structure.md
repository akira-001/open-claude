---
description: プロジェクトの構成・ディレクトリ構造・ファイルの役割について質問された時に説明するスキル
---

# プロジェクト構造説明スキル

## 手順
1. まずプロジェクトルートの構造を`ls`で確認する
2. `README.md`、`package.json`、`cogmem.toml`等のメタファイルを読む
3. 質問に関連するディレクトリの内容を確認してから回答する

## 主要ディレクトリ
- `cron_jobs/` - 定期実行ジョブの管理
- `ir_news_cron/` - IRニュース自動収集
- `tech_news_cron/` - テックニュース自動収集
- `memory/` - cogmem記憶データ（logs, knowledge, skills.db）
- `identity/` - エージェントのアイデンティティ定義
- `.claude/skills/` - Claude Codeスキルファイル
