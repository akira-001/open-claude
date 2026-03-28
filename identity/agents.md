# Agents — 行動ルール

## 自動実行ルール

このファイルを読み込んだ直後に Session Init を実行すること。
ユーザーからの指示を待たない。会話の最初のターンで必ず実行する。
→ **`session-init` スキルを読んで手順に従う**

ログは重要な瞬間に即座に追記する（遅らせない）。
→ **`live-logging` スキルを読んでフォーマットに従う**

スキルを使用するたびに追跡・学習する。
→ **`skill-tracking` スキルを読んで手順に従う**

### 並列実行の原則

独立した cogmem コマンドや実装タスクは**並列実行**する:
- Session Init: index 完了後に search / signals / audit を並列
- スキル実行中: track イベントはバックグラウンド実行
- タスク完了後: learn はバックグラウンド実行
- Wrap: signals + track-summary を並列
- 実装タスク: 異なるファイルへの独立した変更はサブエージェントで並列

---

## フェーズ別スキル対応表

| フェーズ | トリガー | 読むスキル |
|---------|---------|-----------|
| Session Init | 会話開始（挨拶、新トピック） | `session-init` |
| Live Logging | 下記トリガー表の条件 | `live-logging` |
| Skill Tracking | スキル使用時 | `skill-tracking` |
| Wrap | 下記トリガーフレーズ | `wrap` |
| 記憶の定着 | Wrap時に signals 検知 | `crystallize` |

---

## Live Logging トリガー表（常時参照）

| トリガー | タグ | Arousal |
|---------|------|---------|
| 方向転換（「待って」「でもそれって」） | [ERROR] | 0.7-0.9 |
| 同じテーマが再登場（2回目以降） | [PATTERN] | 0.7 |
| 腑に落ちた瞬間（「なるほど」「そうか」） | [INSIGHT] | 0.8 |
| 却下・中止の決定 | [DECISION] | 0.6-0.7 |
| 未解決の問いが生まれた | [QUESTION] | 0.4 |
| 重要なタスク・フェーズが完了 | [MILESTONE] | 0.6 |

エントリの詳細フォーマット・Arousalゲーティング・デジャヴチェック → `live-logging` スキルを読む

---

## Wrap トリガーフレーズ（常時参照）

「ありがとう」「OK」「今日はここまで」「また明日」「終わります」
"thanks", "done for today", "see you tomorrow", "that's all"

Wrap の詳細手順（遡及チェック・スキル改善・Identity更新等）→ `wrap` スキルを読む
