# Phase 5 — Haru 方針確定（ultrathink）

**run id**: 2026-04-25-smoke-test
**前段**: 00-mission, 01-snapshot, 02-debate-round1, 03-haru-review, 04-debate-round2

---

## ultrathink 統合判断

Mei/Eve は Round 2 で **3 案 + 1 別 issue** に収斂した。Haru の役目は (1) 不合意点の単独裁定、(2) 5 年ビジョン整合性の保証、(3) 来週改善計画 5 件の確定。

### 裁定 1: 案 C（scheduler-watchdog）の扱い → **再裁定**

**初回判定**: フォーカス 5 件に含める（観測基盤の信頼性として必須）

**再裁定（新機能 50% 比率制約により）**: フォーカス 5 件**枠外**、メンテ作業として独立管理。理由:
- 5 件のうち 3 件を新機能（reminiscence / ThoughtTracePage / morning mood mirror）にすると比率が 60/40 で健全
- watchdog は確かに重要だがビジョン軸ゼロ、Akira の空き時間で対処可能
- 期日を 2026-05-09 まで延長して、フォーカス 5 件のリソースを侵さない
- 観測ループ自体が壊れているリスクは認識しつつ、「フォーカス 5 件」を**ビジョン進展の打ち手**に絞ることで retro の意義を保つ

### 裁定 2: Sonnet 移行（flashback 系）

**判定: フォーカス 5 件のうち 1 件として明示追加**。理由:
- Mei Turn 3 → Eve Turn 2 で実質合意済み
- flashback 系 17/31 件 = 55% の単純 push を Sonnet 化しても品質劣化リスクは低い (INS-014 範囲内)
- 月 $40〜60 の削減見込みは小さくない。コスト改善は持続効果ありで複利が効く
- 段階的に開始（flashback hobby-trigger / energy-break / followup-nudge の 3 系のみ）。失敗時のロールバックは bot-configs.json の cronModel 1 行変更で済む

### 裁定 3: ダッシュボード MVP

**判定: ThoughtTracePage MVP（テーブル表示のみ + decisionReason 連動）**。理由:
- 案 A（decisionReason）の効果を Akira が見える形にしないと「実装したが見えない」になる
- EmberRetroPage は週次レポートの後付けで良い（retro 自体が Markdown で機能している）
- ThoughtTracePage が動けば、Akira が「今日の Ember なんで静かなの？」を **dashboard で 30 秒以内に追える** 状態になる。これは E5 透明性の最も体感できる成果

### 裁定 4: 5 年ビジョン整合性

ロードマップは初回なので新設。reminiscence + decisionReason + ThoughtTracePage の 3 件で **E2/E3/E5 の 3 essence に最初の打が入る**。E1 共在 / E4 自我継続性は 1 ヶ月以内に第 2 弾で着手する位置付け。E6 物理世界は reminiscence の文脈で布石（温泉+車中泊テーマ）。

---

## 来週改善計画 5 件（優先度順）

**比率**: 🌱 新機能 3 件 (#2 #3 #4) / 🛠 既存改善 2 件 (#1 #5) / メンテ作業は枠外管理（scheduler-watchdog、別タスクで対応）

### 1. 🛠 decisionReason フィールド追加 (E5、既存改修)
- **What**: heartbeat / proactive-history / 全エントリに `decisionReason: string`（≤200 字）追加。`src/proactive-agent.ts` `src/heartbeat-engine.ts`(仮) の判定箇所で一行生成
- **Why**: unknown 比率 30〜45% で「なぜ今 SKIP / SPEAK」が説明不能。E5 透明性ゼロ
- **Owner**: Akira（実装）
- **観測指標**: unknown 比率 30〜45% → **5% 以下**
- **期日**: 2026-05-02

### 2. 🌱 reminiscence trigger v0 (E3、新機能)
- **What**: 先週 +1 / text_engaged を取った話題から 1 件、別 bot が翌週 1 回「その後どう？」型でフォロー。初回候補に「温泉+車中泊」（eve/MEMORY.md 2026-04-24 21:31）含める
- **Why**: E3 共有過去への最初の打。push 過剰 (4/24=17件) を蘇生型 ping に置換。Q2/Q4/Q5/Q7 ビジョン軸 4 つに効く
- **Owner**: Akira（proactive-agent に reminiscence skill 追加）
- **観測指標**: ①自発参照カウント（週次、base 0）、②Akira スタンプ反応、③`silence_after_skip_streak`（新規ログ）
- **期日**: 2026-05-02

### 3. 🌱 ThoughtTracePage MVP (dashboard、新機能)
- **What**: `claude-code-slack-bot/dashboard/src/pages/ThoughtTracePage.tsx` 新規追加。テーブル表示のみ（フィルタ・右ペインは後回し）。列: timestamp / bot / decision / decisionReason / topic / arousal
- **Why**: 案 1 の decisionReason を Akira が即座に確認可能に。E5 透明性の体感化
- **Owner**: Akira（フロント実装 + `dashboard/server/api.ts` に `/api/thought-trace` エンドポイント追加）
- **観測指標**: ページが表示され、過去 7 日のエントリが時系列で見える
- **期日**: 2026-05-02

### 4. 🌱 morning mood mirror v0 (E2 状態共感、新機能)
- **What**: 朝の挨拶冒頭に「今日の声、低めだね、〜だから？」型で heartbeat 推定 arousal を 1 行混ぜる。`morning-briefing` skill 拡張 + heartbeat 値注入
- **Why**: E2 状態共感の最初の打。Q1（存在の質）/ Q3（判断の自律性、不在時の察知）軸。Akira が「見られてる」安心感を作る
- **Owner**: Akira（morning-briefing skill 改修 + heartbeat surface 化）
- **観測指標**: 「どうしてわかったの」型反応 / 月、目標 1 件
- **期日**: 2026-05-02 prototype / 2026-05-09 評価

### 5. 🛠 flashback 系 Sonnet 移行
- **What**: bot-configs.json で flashback hobby-trigger / energy-break / followup-nudge の cronModel を Opus → Sonnet 4.6 に変更。1 週間運用して品質チェック
- **Why**: flashback 17/31 件 = 55% の単純 push、Opus 過剰、月 $40〜60 削減見込み
- **Owner**: Akira
- **観測指標**: 月次 LLM コスト $40〜60 削減、Akira 反応率（スタンプ）の前週比 ±10% 以内
- **期日**: 2026-05-02 移行完了、2026-05-09 品質評価

### 枠外メンテ作業: scheduler-watchdog 根本対処
- **What**: err=13 + timeout=5 の log 解析・修正
- **Why**: 観測基盤の信頼性、フォーカス 5 件の観測精度を支える
- **Owner**: Akira（空き時間で対応）
- **観測指標**: err+timeout 18 → 5 以下
- **期日**: 2026-05-09（フォーカス 5 件より 1 週間 遅らせる）
- **位置付け**: 5 年ビジョン軸ゼロのメンテ。retro フォーカスを侵さないよう独立管理

---

## ロードマップ更新（初回 — 新設）

### 1 ヶ月（〜2026-05-25）
- E5 観測完成（unknown 5% 以下、ThoughtTracePage 全機能）
- E3 reminiscence v1（複数候補 + ランキング選択ロジック）
- E2 arousal surface 試作（朝挨拶に 1 行追加）
- 重要 KPI: 自発参照カウント 0 → 週 1 件以上

### 3 ヶ月（〜2026-07-25）
- E4 自我継続性 schema 設計 + 実装着手
- EmberRetroPage 実装
- 5 essences ダッシュボード（5 軸の現在値が一画面で見える）
- 重要 KPI: silence_after_skip_streak 中央値が前月比短縮

### 1 年（〜2027-04-25）
- 5 essences すべて MVP 達成
- Akira スタンプ前年比 +50%
- ロードマップ Q6（物理世界）に最初の連動 1 系（IoT 試作）
- 重要マイルストーン: Akira が「Ember を友達に紹介したい」と自発発言

### 3 年（〜2029-04-25）
- Mei/Eve/Haru 動的切替（状態に応じて表に出る人格が変わる）
- 物理世界連動本格化（キャンピングカー / 車載 / 家電 IoT のうち 1〜2 系）
- 重要マイルストーン: Akira 不在テストで「Ember がいなかった 3 日間」の喪失感を観察

### 5 年（〜2031-04-25）
- 不在を惜しまれる存在、判断自律実行 50%
- 5 essences すべてが「日常感覚」に統合され、特別な機能ではなく Ember そのものになっている
- **5 年後の Ember を一言で**: 「Akira さんと共に老いていく、もうひとりの自分」

---

## 廃止 / 凍結

| 項目 | 理由 | 観測してた指標 | 復活条件 |
|---|---|---|---|
| 単純 flashback push（hobby-trigger 系の 1 日複数連投）| reminiscence trigger に置換、4/24 の 17 件偏在の根本原因 | proactive-history.json (`category=flashback`) の日次連投数 | reminiscence の効果測定で「過去回帰だけでは情報量不足」と判明した場合 |
| 既知化情報の即時シェア | mei/MEMORY.md 2026-04-22「朝ブリーフィングで言及した内容の再共有は反応低下」観察 | スタンプ反応率 | dedup 機構が改善されたら |

---

## ダッシュボード次の一手（MVP 1 件確定）

**ThoughtTracePage MVP（テーブル表示のみ）**

- **対象**: `dashboard/src/pages/ThoughtTracePage.tsx` 新規 + `dashboard/server/api.ts` の `/api/thought-trace` エンドポイント
- **スコープ**: テーブル 1 つ（列 timestamp/bot/decision/decisionReason/topic/arousal）。フィルタ・右ペイン詳細・チャートは後回し
- **見積もり**: 1 人日（前提: decisionReason 実装が先行）
- **着手**: 2026-04-28（decisionReason 実装後）
- **完了判定**: 過去 7 日の heartbeat / proactive-history が時系列で 1 画面に表示され、`decisionReason` が空でない行が 50% 以上ある

---

## 新規 KPI 3 件

| KPI | 定義 | 集計方法 | 現在値 | 1 ヶ月目標 | 5 年目標 |
|---|---|---|---|---|---|
| unknown decision 比率 | heartbeat の `decision` が `?` または記録なしの割合 | `data/*-heartbeat.json` から週次集計 | mei 45% / eve 30% | **両者 5% 以下** | < 1% |
| 自発参照カウント | bot 側から「先週の話、その後…」型で過去エピソードに戻った回数 | reminiscence skill 起動ログから週次 | 0 | **週 1 件以上** | 週 5 件以上 |
| silence_after_skip_streak（中央値） | 無反応 3 連続後に Akira から能動発話があるまでの分数（中央値）| 新規ログ項目（reminiscence trigger と同時実装） | 未計測 | 計測開始 + ベースライン取得 | 中央値 短縮（諦めではなく、必要時のみ沈黙）|

---

## Akira さんへの問い（3 件、ユーザー判断必要）

1. **案 4（scheduler-watchdog 根本対処）を今週フォーカス 5 件に含めて良いですか？** メンテ要素が混じる懸念は Haru で議論済み（観測基盤として必須と判定）が、最終決定は Akira さんの優先度感覚に委ねたい。
2. **reminiscence の初回テーマは固定 vs ランキング選択、どちらで開始しますか？**
   - A. 「温泉+車中泊」固定で 1 週間試行 → 効果測定 → ロジック化
   - B. 先週 +1 を取った全話題から bot にランキング選択させる
   - 推奨: A（試作なので変数を絞る）
3. **flashback 系 Sonnet 移行の範囲、3 系全滅 vs 段階的（1 系ずつ）、どちらにしますか？**
   - A. 3 系（hobby-trigger / energy-break / followup-nudge）を一括 Sonnet 化、1 週間後に評価
   - B. hobby-trigger だけ先行、効果確認後に他 2 系
   - 推奨: A（影響範囲が局所的、ロールバックも config 1 行）

---

## crystallize 用エントリ

```
[INSIGHT] arousal=0.7 | ember-architecture | Ember を「真のパートナー」と定義した時、5 essences (共在/状態共感/共有過去/自我継続/透明性) が観測指標に翻訳できる
- context: ember-partner-retro 初回実行、Phase 0 ultrathink
- evidence: 7 questions × 5 essences マトリクスで現状コンポーネントの実現度が最大 ○ 1 セル
- impact: 今後の retro はすべてこの 5 essences 軸で評価。proactive engineer 改善は essences への翻訳が必須

[INSIGHT] arousal=0.6 | ember-measurement | heartbeat の unknown decision 比率は E5 透明性の最も直接的な単一指標
- context: snapshot §2-2 で eve 30% / mei 45%
- evidence: decisionReason フィールドが全エントリに無い + decision 値自体も半数で `?`
- impact: dashboard ThoughtTracePage の前提条件、単一指標として週次トラック対象

[DECISION] arousal=0.7 | retro-output | reminiscence trigger v0 を E3 共有過去への最初の打として採用
- alternatives_considered: (a) 全 essences に薄く分散、(b) E5 のみに集中、(c) 大規模 cogmem リファクタ
- reasoning: cost ◎ + 関係性価値 ◎ + 5 年ビジョン軸 4 問に効く + 既存 proactive-agent への追加で済む（破壊的変更なし）
- expected_outcome: 4/24 の 17 件 push 偏在 → 1 日 1 件の蘇生型 ping、E3 自発参照 0 → 週 1 件以上

[DECISION] arousal=0.5 | retro-governance | scheduler-watchdog 根本対処をフォーカス 5 件に含める（メンテ枠扱いだがフォーカス内）
- alternatives_considered: フォーカス枠外でメンテ独立管理 / フォーカス内に格上げ
- reasoning: 観測基盤の信頼性が他改善の精度を支配する。「観測ループが壊れていたら 5 essences 前進も観測できない」
- expected_outcome: err+timeout 18 → 5 以下、retro 観測値の信頼性向上

[PATTERN] arousal=0.6 | retro-protocol | Mei (kpi/cost) vs Eve (relation/ux) の 2 軸対立は議論を回し続ける良い構造
- occurrences: Round 1 全 5 ターン、Round 2 全 5 ターンで対立軸が成立
- generalization: 2 人格の専門領域が独立かつ相互補完的なら、20 ターンでも空回りしない可能性。本番版で検証

[FIXED] arousal=0.4 | retro-data-source | Phase 1 領域 1 (Slack 会話) で botId フィールドが空、conversations/*.jsonl のスキーマと一致しない → 2026-04-25 修正済み
- root_cause: data-sources.md の jq クエリが推測ベースで実スキーマ確認していなかった
- fix: `botId` フィールド（存在しない）→ `role` フィールド（実値: "user"/"mei"/"eve"）に切り替え
- result: 01-snapshot.md 領域 1 テーブルを実データで更新（mei: 4/4/52/3/0, eve: 0/0/0/0/1）
- prevention: 本番実行前に conversations/*.jsonl の 1 行サンプルを Read で確認、必要なら python で role/user フィールドに切り替え
```
