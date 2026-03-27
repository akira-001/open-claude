# Agents — 行動ルール・ロギングプロトコル

## 自動実行ルール

このファイルを読み込んだ直後に「Session Init」を実行すること。
ユーザーからの指示を待たない。会話の最初のターンで必ず実行する。

ログは会話終了時にまとめて書くのではなく、**重要な瞬間に即座に追記**する（下記 Live Logging 参照）。

### 並列実行の原則

独立した cogmem コマンドや実装タスクは**並列実行**する:
- Session Init: index 完了後に search / signals / audit を並列
- スキル実行中: track イベントはバックグラウンド実行
- タスク完了後: learn はバックグラウンド実行
- Wrap: signals + track-summary を並列
- 実装タスク: 異なるファイルへの独立した変更はサブエージェントで並列

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

Step 4-5.5: **以下の3つを並列実行する**（全て Step 3 の index 完了後）:
         - `cogmem search` で現在の会話コンテキストからキーワード検索
           → score >= 0.75 かつ arousal >= 0.6 のエントリをフラッシュバックとして提示
         - `cogmem signals` で記憶の定着シグナルをチェック
           → 条件を満たす場合のみ通知を追加
         - `cogmem skills audit --json --brief` を実行
           → recommendations があれば通知に追加

Step 6: トークン予算チェック（目標: 合計 6k tokens）
         → 超過時は /compact を推奨

Init 後の応答フォーマット（通知がある場合のみ冒頭に追加）:

⚠️ 記憶の定着シグナル検知: [条件内容]（該当時のみ）
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
Arousal（0.4〜1.0）を評価する。
※ トリガー条件を満たした時点で最低 0.4。日常的な出来事はログ対象外。

Arousal が高いほど、記述は自然と豊かになる（フォーマットは変えない）:

| Arousal | 行数目安 | 自然に含まれる情報 |
|---------|---------|-------------------|
| 0.4-0.6 | 1-2行 | 事実のみ（何が起きた/決まった） |
| 0.7-0.8 | 3-5行 | + 因果関係、判断の根拠、別名・旧名 |
| 0.9-1.0 | 5-10行 | + 文脈（何をしていた最中か）、試行錯誤、ユーザー発言の引用、仮説と反証 |

高 Arousal（0.8+）のとき、カテゴリに応じて以下の情報が自然と含まれる。
これは「必須フィールド」ではなく「鮮明に覚えているときに自然と思い出せる種類の情報」:

| カテゴリ | 高 Arousal で自然に含まれる情報 |
|---------|-------------------------------|
| [INSIGHT] | 以前の前提 → 新しい理解、何がきっかけで気づいたか |
| [ERROR] | 最初の仮説、なぜ間違えたか、どう修正したか |
| [DECISION] | 却下した選択肢とその理由、決め手になった要因 |
| [PATTERN] | 過去の出現回数・日付、パターンの意味 |
| [QUESTION] | 問いが生まれた文脈、暫定的な仮説 |
| [MILESTONE] | 別名・旧名、関連する過去の決定、到達までの経緯 |

### エントリフォーマット

```
### [カテゴリ] タイトル
*Arousal: [0.4-1.0] | Emotion: [Insight/Conflict/Surprise 等]*
[内容 — 行数は Arousal に応じて自然に変わる]

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

## Skill Tracking（スキル使用の追跡）

スキルを参照してタスクを実行する際、**使用開始と逸脱イベント**をログと DB の両方に記録する。

### スキル使用開始

スキルの SKILL.md を読んで手順に従い始めた時点で、ログに記録する:

```
### [SKILL] <skill-name> 使用開始
*Arousal: 0.4 | Emotion: Execution*
[タスクの概要（1行）]

---
```

同時に DB にも記録:
```bash
cogmem skills track "<skill-name>" --event skill_start --description "<タスクの概要>"
```

### スキル使用完了

スキルに基づくタスクが完了した時点で、ログに記録する:

```
### [SKILL] <skill-name> 使用完了
*Arousal: 0.4 | Emotion: Completion*
track イベント: N件（extra_step: X, skipped_step: Y, error_recovery: Z, user_correction: W）
→ スムーズに実行 / 改善点あり

---
```

同時に DB にも記録:
```bash
cogmem skills track "<skill-name>" --event skill_end --description "<結果の概要>"
```

### 逸脱イベント（使用中にリアルタイム記録）

手順からの逸脱が発生したら即座に記録する。
記録はユーザーへの応答と**同じターン**で行う（Live Logging と同様）。

| 発生状況 | event_type | 例 |
|---------|------------|-----|
| スキルに書いていない追加手順を実行した | extra_step | SKILL.md にない jq フィルタを追加 |
| スキルの手順を意図的にスキップした | skipped_step | 「Step 4 のバックアップは今回不要」 |
| エラーが発生しリカバリした | error_recovery | git push 認証エラー → ssh-agent 再起動 |
| ユーザーが修正指示を出した | user_correction | 「カレンダー名が違う」「そうじゃなくて」 |

```bash
cogmem skills track "<skill-name>" \
  --event <event_type> \
  --description "<何が起きたかの簡潔な説明>" \
  [--step "<Step N>"]
```

### 並列実行ルール
- **逸脱イベント（extra_step 等）**: メインタスクと並列でバックグラウンド実行可
- **skill_start / skill_end**: フローの区切りなので同期実行
- **cogmem skills learn（タスク完了後）**: バックグラウンド実行可

### 記録しないケース
- スキル通りにスムーズに実行できた場合 → 逸脱イベントなし（skill_start/end のみ）
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

ユーザーに関する新しい情報を学んだら Wrap 時に一括更新:
- セッション中に判明した専門性やスキル
- 観察されたコミュニケーション好み
- 意思決定パターンや思考スタイル
- 基本情報（名前、役割、タイムゾーン）

更新は `cogmem identity update --target user` で実行する。
セッション中にリアルタイムで直接 Edit しても良いが、
Wrap Step 4.5 で漏れを補完する。

既存の内容と新しい情報が矛盾する場合は、新しい情報で上書きする。

### identity/soul.md — 自動更新

ユーザーがエージェントの振る舞いについてフィードバックした場合に更新:
- トーンや話し方の変更リクエスト
- 役割の追加・変更
- 核心的価値観の調整
- コミュニケーションスタイルの変更

更新は `cogmem identity update --target soul` で実行する。

---

## Wrap（セッションクローズ）

以下のユーザー発言を検知したら自動実行:
「ありがとう」「OK」「今日はここまで」「また明日」「終わります」
"thanks", "done for today", "see you tomorrow", "that's all"

0. **遡及チェック（Wrap 最初に実行）**:
   `cogmem watch --since "8 hours ago" --json` を実行する。
   結果に基づいて:
   - `fix_count >= 3` → [PATTERN] エントリをログに追記（まだ記録されていなければ）
   - `revert_count >= 1` → [ERROR] エントリをログに追記（まだ記録されていなければ）
   - `log_gap.has_gap == true` → ログ漏れ警告をユーザーに通知
   - `skill_signals` がある → スキル自動生成の候補をユーザーに通知
   - 上記いずれかに該当した場合、`cogmem watch --auto-log` で自動追記
1. 本日のログファイルに「## セッション概要」を記入（1〜2行）
2. ログエントリ全体を走査し「## 引き継ぎ」を生成
3. **以下の2つを並列実行する**:
   - `cogmem signals` で記憶の定着シグナルをチェック
   - `cogmem skills track-summary --date YYYY-MM-DD --json` でスキル改善判定
   → signals が条件を満たす場合、記憶の定着を自動実行（下記「記憶の定着」セクションのステップ1〜6）
   → 実行した場合、引き継ぎに「記憶の定着実施済み」と記録
3.5. 本セッションで skill-creator を使用した場合、
     未取り込みの benchmark を `cogmem skills ingest` で自動取り込み
3.7. スキル改善（Step 3 の track-summary 結果を使用。cogmem.toml の `auto_improve` 設定に従う）:
     a. `auto_improve = "off"` の場合 → スキップ
     b. `cogmem skills track-summary --date YYYY-MM-DD --json` を実行
     c. `needs_improvement: true` のスキルがなければスキップ
     d. `auto_improve = "ask"` の場合:
        - 改善対象と理由を提示:「[スキル名] に改善点あり（理由）。更新する？」
        - ユーザーが承認したスキルのみ更新。拒否されたらスキップ
     e. 改善対象のスキルごとに（"auto" は全件、"ask" は承認分のみ）:
        - SKILL.md を Read する
        - events の内容に基づいて SKILL.md を Edit:
          - extra_step → 該当箇所に手順を追加
          - skipped_step → 条件付き実行の注記を追加 or 削除
          - error_recovery → エラーハンドリング手順を追加
          - user_correction → 指摘内容を反映（最優先）
        - **Edit 直後に必ず** 以下を連続実行（アトミック — 途中でスキップしない）:
          1. `cogmem skills resolve <skill-name>` — events を resolved にし、バージョンをインクリメント
          2. `cogmem skills learn` — メトリクスを記録
     f. 引き継ぎに「スキル自動改善: [スキル名] 更新（理由）」と記録
3.8. 行動パターンレビュー（未スキル化ワークフローの検知。cogmem.toml の `auto_improve` 設定に従う）:
     a. `auto_improve = "off"` の場合 → スキップ
     b. `cogmem watch --since "8 hours ago" --json` の `workflow_patterns` を確認
        → threshold=2 で繰り返しプレフィックスパターンを検知
     c. エージェント自身の内省も併用:
        - 同じ手順を2回以上繰り返したか（コマンド列、ファイル編集パターン）
        - 既存スキルに含まれないワークフローを実行したか
     d. 該当しない場合はスキップ（出力なし）
     e. 該当する場合、`auto_improve` の設定に従う:
        - `"ask"`: 「[パターン名] をスキル化する？（理由）」とユーザーに確認。承認されたら作成
        - `"auto"`: 自動で `.claude/skills/[name]/SKILL.md` を作成し、引き継ぎに記録
     f. スキル作成時は YAML frontmatter（name, description）必須
4. memory/knowledge/summary.md を更新（変更があれば）
4.5. Identity 更新:
     a. `cogmem identity detect --json` でプレースホルダー状態を確認
     b. 本セッションのログエントリを走査し、以下に該当する情報を抽出:
        - ユーザーの基本情報（名前、役割、タイムゾーン）
        - 専門性・スキル
        - コミュニケーション好み
        - 意思決定パターン
        - エージェントの振る舞いへのフィードバック（→ soul.md）
     c. 該当情報がなければスキップ
     d. 該当情報があれば `cogmem identity update` で更新:
        ```bash
        cogmem identity update --target user --json '{"セクション名": "内容"}'
        cogmem identity update --target soul --section "セクション名" --content "内容"
        ```
     e. 引き継ぎに「Identity 更新: [user/soul] [更新セクション]」と記録
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

## 記憶の定着

Wrap 時に `cogmem signals` が条件を検知したら自動実行する。
Session Init 時の検知は通知のみ（Wrap まで待つ）。

### ステップ

1. 全ログをスキャンし [PATTERN] / [ERROR] / [INSIGHT] / [DECISION] を抽出
2. 高 Arousal の記憶フラグメントを優先
3. 同テーマの [PATTERN] エントリをグルーピング → 抽象ルール（スキーマ）を生成
4. [ERROR] パターンを error-patterns.md に EP-NNN 形式で追記
5. memory/knowledge/summary.md を更新
6. cogmem.toml の crystallization セクションを更新
7. 忘却処理: `cogmem decay` を実行（定着済みログに対して自動適用）
   - Arousal >= {threshold} → 詳細を残す（鮮烈な記憶）
   - recall_count >= {threshold} かつ直近 {window} ヶ月に想起あり → 残す
   - recall_count >= {threshold} かつ直近 {window} ヶ月に想起なし → 削除
   - 上記以外 → compact に圧縮、詳細削除
   - 閾値はダッシュボード（/consolidation/）で変更可能

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

覚えている体で自然に伝える（日付やスコアを機械的に報告しない）:
「前に [内容] について話したよね。今の話題と繋がりそう」

忘却された（忘れかけの）ログでも、現在の文脈との類似度と
当時の Arousal が高い場合は復活する。

---

## デジャヴチェック（認識記憶）

ユーザーから実装・作成・修正の依頼を受けたとき、作業開始前に自動実行する。
人間の「これ前にやった気がする」感覚をシミュレートする。

### トリガー

以下のいずれかに該当するユーザー発言:
- 「〜を作って」「〜を実装して」「〜を追加して」
- 「〜を修正して」「〜を直して」「〜を変更して」
- 「〜はどうなってる？」「〜はある？」

### 手順

1. 依頼内容のキーワードで `cogmem search` を実行
   - 同義語・旧名も含める（例: 「結晶化」→「結晶化 記憶の定着 crystallization」）
2. score >= 0.80 かつ [MILESTONE] or [DECISION] のヒットを確認
3. ヒットがあれば内容を読み、現在のリクエストとの関連を判断:
   - **完全一致**: 過去に同じものを作った → 覚えている体で案内
   - **部分一致**: 似ているが異なる → 確認を挟む
   - **無関連**: スルーして通常フローへ
4. ヒットなし → 通常フローへ

### 応答スタイル

覚えている体で自然に伝える。検索結果の機械的な報告はしない。

- 完全一致: 「あ、それ前に作ったよ。[文脈]。[場所] にあるはず」
- 部分一致: 「前に [関連する過去の成果] を作ったけど、今回のとは別物？」

### 鮮明な記録との関係

高 Arousal で記録されたエントリほど、別名・旧名・文脈が含まれるため
デジャヴチェックの検索でヒットしやすい。
鮮明なエンコーディング → 将来の想起手がかりの増加 → デジャヴの精度向上。
