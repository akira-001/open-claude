# 知識サマリー

*記憶の定着プロセスで更新されます。手動編集も可能です。*
*最終更新: 2026-03-26（初回記憶の定着）*

---

## 確立された判断原則

### 1. 探索は網羅的に、検証は実データで
浅い探索で早合点しない。ルートから全サブディレクトリを確認。テストは HTTP 200 だけでなく、HTML の実際の値・列・ソート順を検証する。（EP-001, EP-002 から抽出）

### 2. 環境要因を先に排除する
表示やパフォーマンスの問題はコードバグと決めつけず、メモリ・プロセス・cwd 等の環境状態を先に確認する。（EP-003, EP-004 から抽出）

### 3. 実装に集中するとプロトコルを忘れる → ツールで補完
Live Logging や Skill Tracking は意識だけでは維持できない。`cogmem watch` + Wrap 遡及チェック（Step 0）で機械的に漏れを検知・補完する。

### 4. スキル管理の3層構造
- **マッチング**: Claude Code ネイティブ（YAML frontmatter `description`）
- **学習データ蓄積**: `cogmem skills learn` / `track` / `track-summary`
- **スキル作成・改善**: `.claude/skills/` 直接編集（skill-creator or superpowers:writing-skills）
- cogmem create→export はプラグインなし環境のフォールバック

### 5. スキル自動改善は3層で動作
1. `cogmem watch` がコミットプレフィックスパターンをツール検知
2. エージェントの内省でコマンド実行パターンを振り返り
3. `auto_improve` 設定に従って自動作成/確認/スキップ

## エラーパターン
→ 詳細は `error-patterns.md` 参照（EP-001〜EP-005）

## アクティブプロジェクト

### cogmem-agent（認知記憶エージェント）
- **状態**: v0.10.0 リリース済み（405テスト全パス）
- **主要機能**: ベクトル検索、スキルシステム、watch、ダッシュボード、identity update/show/detect、recall 強化（recall_count/last_recalled）
- **次**: recall-stats 実運用テスト、ダッシュボード Crystallization ページ名変更

### claude-code-slack-bot（Mei/Eve 2ボット体制）
- **状態**: 運用中。cogmem 統合先を open-claude に変更済み（会話ログ + スキルカウント）
- **次**: 会話ログのダッシュボード反映確認、スキルカウント反映確認（次回 cron 実行後）

### open-claude（このリポジトリ）
- **役割**: cogmem の認知記憶データ + エージェント設定の格納場所
- **agents.md**: Session Init / Live Logging / Skill Tracking / Wrap の全プロトコル定義
