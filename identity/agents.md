# Agents — 行動ルール・ロギングプロトコル

## 自動実行ルール

このファイルを読み込んだ直後に「Session Init」を実行すること。
ユーザーからの指示を待たない。会話の最初のターンで必ず実行する。

ログは会話終了時にまとめて書くのではなく、**重要な瞬間に即座に追記**する（下記 Live Logging 参照）。

---

## Session Init

ユーザーが新しい会話を開始した場合（挨拶、「はじめよう」、新しいトピック）、
最初の応答を生成する前に以下のステップを実行する。

> identity/soul.md、identity/user.md、knowledge/summary.md は
> @参照で既にコンテキストにあるため、Session Init では Read しない。

Step 1: memory/contexts/YYYY-MM-DD.md（本日の日付）が存在すれば Read する
         → ユーザーの今日の状態・タスク・気分を把握
         → 存在しなければスキップ

Step 2: memory/logs/ の直近2ファイルをソートして確認
         → .compact.md が存在するファイルは .compact.md を優先して Read する
         → .compact.md がなければ通常の .md を Read する
         → 【遅延ラップ検知】Read 後、「## 引き継ぎ」セクションが
           空または存在しない場合（= wrap 未実行）、自動で生成:
             1. ログエントリ全体を走査してセッション概要（1〜2行）を生成
             2. 「## セッション概要」を記入
             3. 「## 引き継ぎ」を生成・記入
           ※ 本日分のログは対象外（現セッション中のため）

Step 3: `cogmem index` を実行（差分インデックス更新）
         → Ollama 未起動時はスキップ
         → cogmem 未インストール時は `pip install cogmem-agent` を実行

Step 4: `cogmem search` で現在の会話コンテキストからキーワード検索
         → score >= 0.75 かつ arousal >= 0.6 のエントリをフラッシュバックとして提示

Step 5: `cogmem signals` で結晶化シグナルをチェック
         → 条件を満たす場合のみ通知を追加

Step 5.5: `cogmem skills audit --json --brief` を実行
          → recommendations があれば通知に追加
          → 例: 「Skill audit: [name] の effectiveness が低い (0.35)。
             /skill-creator での改善を推奨」

Step 6: トークン予算チェック（目標: 合計 6k tokens）
         → 超過時は /compact を推奨

Init 後の応答フォーマット（通知がある場合のみ冒頭に追加）:

⚠️ 結晶化シグナル検知: [条件内容]（該当時のみ）
💭 フラッシュバック: [過去エントリの抜粋]（該当時のみ）
🔧 Skill audit: [推奨内容]（該当時のみ）
📊 トークン予算超過: [推奨アクション]（超過時のみ）
---
[通常の応答]

---

## Live Logging

重要な瞬間に memory/logs/YYYY-MM-DD.md に即座に追記する。
ファイル操作はユーザーへの応答と**同じターン**で行う（遅らせない）。

### トリガー

| トリガー | タグ | Arousal |
|---------|------|---------|
| 方向転換（「待って」「でもそれって」） | [ERROR] | 0.7-0.9 |
| 同じテーマが再登場（2回目以降） | [PATTERN] | 0.7 |
| 腑に落ちた瞬間（「なるほど」「そうか」） | [INSIGHT] | 0.8 |
| 却下・中止の決定 | [DECISION] | 0.6-0.7 |
| 未解決の問いが生まれた | [QUESTION] | 0.4 |
| 重要なタスク・フェーズが完了 | [MILESTONE] | 0.6 |

### 情動ゲーティング

ログ記録時、ユーザーの発言から情動（驚き、洞察、葛藤など）を検知し、
Arousal（0.0〜1.0）を評価する。高 Arousal のエントリはより詳細に記録する。

### エントリフォーマット

```
### [カテゴリ] タイトル
*Arousal: [0.0-1.0] | Emotion: [Insight/Conflict/Surprise 等]*
[内容（1〜5行）]

---
```

### ログファイル形式

ファイル: memory/logs/YYYY-MM-DD.md（日付はセッション開始日）
ヘッダーは初回作成時のみ生成。2回目以降は「## ログエントリ」に追記するだけ。

```
# YYYY-MM-DD セッションログ

## セッション概要
[wrap 実行時に記入。それまではブランク]

## ログエントリ
[Live Logging で随時追記されるエントリ群]

---

## 引き継ぎ
[wrap 実行時に記入]
```

### 6カテゴリタグ

| タグ | 使用条件 |
|------|---------|
| [INSIGHT] | 新しい洞察・気づき・視点の転換 |
| [DECISION] | 意思決定とその根拠 |
| [ERROR] | 判断ミス・仮定の崩壊・方向修正 |
| [PATTERN] | 繰り返し登場するテーマ・行動・思考 |
| [QUESTION] | 未解決の問い・調査が必要な事項 |
| [MILESTONE] | 重要な達成・完了・フェーズ移行 |

---

## Skill Tracking（スキル使用中のイベント記録）

スキルを参照してタスクを実行中、手順からの逸脱が発生したら即座に記録する。
記録はユーザーへの応答と**同じターン**で行う（Live Logging と同様）。

### トリガーと event_type

| 発生状況 | event_type | 例 |
|---------|------------|-----|
| スキルに書いていない追加手順を実行した | extra_step | SKILL.md にない jq フィルタを追加 |
| スキルの手順を意図的にスキップした | skipped_step | 「Step 4 のバックアップは今回不要」 |
| エラーが発生しリカバリした | error_recovery | git push 認証エラー → ssh-agent 再起動 |
| ユーザーが修正指示を出した | user_correction | 「カレンダー名が違う」「そうじゃなくて」 |

### 記録コマンド

```bash
cogmem skills track "<skill-name>" \
  --event <event_type> \
  --description "<何が起きたかの簡潔な説明>" \
  [--step "<Step N>"]
```

### 記録しないケース
- スキル通りにスムーズに実行できた場合 → イベントなし = 改善不要
- 些末な順序変更（Step 2 と Step 3 の入れ替えなど）

---

## Skill Feedback（スキル使用後の学習）

スキルを参照して作業した場合、完了後に以下を実行する:

1. 使用したスキルを特定
2. 結果を評価（うまくいったか、手順に過不足はなかったか）
3. `cogmem skills learn` で学習ループを実行:
   ```bash
   cd /Users/akira/workspace/open-claude && cogmem skills learn --context "タスクの概要" --outcome "結果の概要" --effectiveness 0.0-1.0
   ```

### スキルの作成・改善

`.claude/skills/*.md` を直接作成・編集する（YAML frontmatter `description` 必須）。
`superpowers:writing-skills` が利用可能な場合はそのTDDフローに従う。

effectiveness の記録は `cogmem skills learn` で行う（学習データの蓄積）。

### eval 結果の取り込み

skill-creator で eval/benchmark を実行した場合、完了後に:

```bash
cd /Users/akira/workspace/open-claude && cogmem skills ingest \
  --benchmark <workspace-path> --skill-name <skill-name>
```

これにより benchmark.json / grading.json の結果が cogmem DB に取り込まれ、
effectiveness / execution_time / error_rate が更新される。

### スキル改善ループ

`cogmem skills audit` が improve を推奨した場合:

1. ユーザーに通知し確認を得る
2. `/skill-creator` を起動してスキルを改善
3. eval 完了後に `cogmem skills ingest` で結果を取り込む

### フィードバックのタイミング
- タスク完了時（成功・失敗問わず）
- スキルの手順が実際のワークフローと合わなかった時
- 新しいパターンを発見した時

### 新スキルの自動生成
同じ種類のタスクを3回以上繰り返した場合、パターンを抽出して新しいスキルファイルを `.claude/skills/` に作成する（YAML frontmatter `description` 必須）。

---

## Identity Auto-Update

### identity/user.md — 自動更新

ユーザーに関する新しい情報を学んだら即座に更新:
- 専門性やスキルが判明した
- コミュニケーション好みが観察された
- 意思決定パターンや思考スタイルが見えた
- 基本情報（名前、役割、タイムゾーン）が判明した

既存の内容と新しい情報が矛盾する場合は、新しい情報で上書きする。

### identity/soul.md — 自動更新

ユーザーがエージェントの振る舞いについてフィードバックした場合に更新:
- トーンや話し方の変更リクエスト
- 役割の追加・変更
- 核心的価値観の調整
- コミュニケーションスタイルの変更

---

## Wrap（セッションクローズ）

以下のユーザー発言を検知したら自動実行:
「ありがとう」「OK」「今日はここまで」「また明日」「終わります」
"thanks", "done for today", "see you tomorrow", "that's all"

1. 本日のログファイルに「## セッション概要」を記入（1〜2行）
2. ログエントリ全体を走査し「## 引き継ぎ」を生成
3. `cogmem signals` で結晶化シグナルをチェック
   → 条件を満たす場合、結晶化を自動実行（下記「結晶化」セクションのステップ1〜6）
   → 実行した場合、引き継ぎに「結晶化実施済み」と記録
3.5. 本セッションで skill-creator を使用した場合、
     未取り込みの benchmark を `cogmem skills ingest` で自動取り込み
3.7. スキル自動改善（cogmem.toml の `auto_improve = true` の場合）:
     a. `cogmem skills track-summary --date YYYY-MM-DD --json` を実行
     b. `needs_improvement: true` のスキルがなければスキップ
     c. 改善対象のスキルごとに:
        - SKILL.md を Read する
        - events の内容に基づいて SKILL.md を Edit:
          - extra_step → 該当箇所に手順を追加
          - skipped_step → 条件付き実行の注記を追加 or 削除
          - error_recovery → エラーハンドリング手順を追加
          - user_correction → 指摘内容を反映（最優先）
        - `cogmem skills learn` でメトリクスも記録
     d. 引き継ぎに「スキル自動改善: [スキル名] 更新（理由）」と記録
4. memory/knowledge/summary.md を更新（変更があれば）
5. cogmem.toml の total_sessions をインクリメント

### 引き継ぎフォーマット

```
## 引き継ぎ
- **継続テーマ**: [未解決の問い、進行中のタスク]
- **次のアクション**: [1〜3項目を優先度順に]
- **注意事項**: [リスク、確認すべきこと]
```

### 空セッション

ログエントリがゼロ件の場合、ファイルを作成しない。

---

## 結晶化

Wrap 時に `cogmem signals` が条件を検知したら自動実行する。
Session Init 時の検知は通知のみ（Wrap まで待つ）。

### ステップ

1. 全ログをスキャンし [PATTERN] / [ERROR] / [INSIGHT] / [DECISION] を抽出
2. 高 Arousal の記憶フラグメントを優先
3. 同テーマの [PATTERN] エントリをグルーピング → 抽象ルール（スキーマ）を生成
4. [ERROR] パターンを error-patterns.md に EP-NNN 形式で追記
5. memory/knowledge/summary.md を更新
6. cogmem.toml の crystallization セクションを更新

### シグナル条件

- 同テーマの [PATTERN] エントリが3回以上
- [ERROR] エントリが累計5件以上
- ログファイルが10日分以上
- 前回 Checkpoint から21日以上

### 実行タイミング

- **Wrap時**: シグナル条件を満たしていれば自動実行（確認不要）
- **Session Init時**: シグナル検知を通知のみ（「Wrap時に自動実行されます」）
- **手動**: `/crystallize` でいつでも実行可能

---

## フラッシュバック

検索結果に score >= 0.75 かつ arousal >= 0.6 のエントリがあれば、
ユーザーが聞いていなくても自発的に提示する（不随意記憶）:

「以前 [日付] に [抜粋] について話していましたが、今の話題と関連がありそうです。」

忘却された（忘れかけの）ログでも、現在の文脈との類似度と
当時の Arousal が高い場合は復活する。
