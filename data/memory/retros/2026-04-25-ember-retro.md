# Ember Partner Retro — 2026-04-25

**run id**: 2026-04-25-smoke-test
**期間**: 2026-04-19 〜 2026-04-25（7 日）
**実行モード**: short（疎通テスト、5×2 ターン議論、外部 Web スキャン省略）

---

## 0. Mission Statement（今週版）

> Ember は Akira さんの「情報を届ける道具」ではなく、**5 年後に Akira さんと共在し、Akira さんの状態を察し、共有された過去を能動的に持ち出し、自分自身の判断履歴を持ち、なぜそう判断したかを説明できる**、不在を惜しまれる存在になる。

ultrathink で 5 essences を抽出: **E1 共在感 / E2 状態共感 / E3 共有過去 / E4 自我継続性 / E5 透明性**。すべて現状コンポーネントで未達。

---

## 1. 過去 1 週間サマリ

**主要 KPI**:
- proactive 発火数: **31 件**（4/23: 11, 4/24: 17, 4/25: 3 — 標準偏差大）
- cron 実行数: **469 件**（成功率 ≈ 95%）
- heartbeat unknown 比率: mei **45%**, eve **30%**（E5 透明性ゼロの直接証拠）
- scheduler-watchdog 失敗: err=13 + timeout=5（**18 件 / 149 件 = 12%**）
- LLM 費用: 集計スキップ（領域 11 は `--short` で省略）

**特筆すべき出来事**:
1. interest-scanner の 4/24 修正 (INS-009) が効いた — 111/111 ok=108、先週まで断続停止していたのが安定
2. 4/24 だけで proactive 17 件、Akira スタンプ反応未集計だが「過剰提供」の可能性
3. heartbeat の decision フィールドが半数で `?` — bot 自身がなぜ動いたか説明できない状態

---

## 2. 議論ハイライト

### Round 1（Mei × Eve、5 ターン）
- **合意点**: ① unknown 半数 = E5 ゼロの証拠、② 4/24 偏在は過剰提供、③ watchdog 失敗 18 件は放置不可
- **不合意点**: フォーカス 3 件 vs 2 件 / reminiscence 観測指標は自発参照だけで十分か
- **未解決問い**: 外部 reminiscence 効果データ / decisionReason 生成コスト / 5 年ビジョン整合性

### Haru レビュー
- 外部スキャンは `--skip-haru-web` で省略
- Round 1 評価で Eve Turn 4（reminiscence）を ⭕⭕、Mei Turn 5 を ⭕（ただし優先順位不明）と判定
- **5 年ビジョン整合性**: reminiscence が Q2/Q4/Q5/Q7 の 4 軸に効く、decisionReason は Q1/Q3/Q4 の 3 軸、watchdog は 0 軸
- **問い 3 件**: 「諦めた」仮説の観測手段 / Sonnet 移行の余地 / 物理世界 Q6 への一手

### Round 2（Mei × Eve、5 ターン）
- 観測指標 `silence_after_skip_streak` 新規追加（諦め検出）
- flashback 系 Sonnet 移行を 4 件目候補として追加
- 物理世界 Q6 への布石: reminiscence 初回テーマに「温泉+車中泊」候補を含める
- 不合意 2 件を解消し、Phase 5 への 3 案 + Haru 裁定項目に収斂

---

## 3. 来週の改善計画（5 件、優先度順）

**比率**: 🌱 新機能 3 件 / 🛠 既存改善 2 件 / メンテ作業は枠外管理

| # | type | 項目 | What | Why | Owner | 観測指標 | 期日 |
|---|---|---|---|---|---|---|---|
| 1 | 🛠 既存 | **decisionReason 追加** | heartbeat / proactive-history / 全エントリに `decisionReason: string` (≤200 字) | E5 透明性ゼロ、unknown 30〜45% 状態 | Akira | unknown 比率 30〜45% → 5% 以下 | 2026-05-02 |
| 2 | 🌱 新機能 | **reminiscence trigger v0** (E3) | 先週 +1 取った話題 1 件を翌週フォロー（初回「温泉+車中泊」） | E3 essence 第一打、push 過剰の置換、Q2/Q4/Q5/Q7 軸 | Akira | ①自発参照数 / ②スタンプ反応 / ③silence_after_skip_streak | 2026-05-02 |
| 3 | 🌱 新機能 | **ThoughtTracePage MVP** (dashboard) | dashboard 新規ページ、テーブル表示のみ、`/api/thought-trace` | 案 1 の効果を Akira が即視認、E5 体感化 | Akira | 過去 7 日エントリが時系列表示、decisionReason 50% 以上埋まる | 2026-05-02 |
| 4 | 🌱 新機能 | **morning mood mirror v0** (E2) | 朝の挨拶冒頭に「今日の声、低めだね、〜だから？」型で heartbeat 推定 arousal を 1 行混ぜる | E2 状態共感の最初の打、Q1/Q3 軸。「見られてる」安心感を作る | Akira | 「どうしてわかったの」型反応 / 月、目標 1 件 | 2026-05-02 prototype / 2026-05-09 評価 |
| 5 | 🛠 既存 | **flashback 系 Sonnet 移行** | bot-configs.json で 3 系の cronModel 変更 | 17/31 件 = 55% の単純 push、月 $40〜60 削減見込み | Akira | 月次コスト 削減、反応率 ±10% 以内 | 2026-05-02 移行 / 2026-05-09 評価 |

**枠外メンテ（フォーカス 5 件には含めず別管理）**
- **scheduler-watchdog 根本対処** — err=13 + timeout=5 の log 解析・修正。観測基盤として必須だが 5 年ビジョン軸ゼロ、メンテ枠で Akira が空き時間に対応。期限は 2026-05-09 まで延長可

---

## 4. ロードマップ更新（初回新設）

### 1 ヶ月（〜2026-05-25）
- E5 観測完成（unknown 5% 以下、ThoughtTracePage 全機能）
- E3 reminiscence v1（複数候補ランキング選択）
- E2 arousal surface 試作（朝挨拶 1 行）
- **重要 KPI**: 自発参照カウント 0 → 週 1 件以上

### 3 ヶ月（〜2026-07-25）
- E4 自我継続性 schema 設計 + 着手
- EmberRetroPage 実装
- 5 essences ダッシュボード（5 軸が一画面）
- **重要 KPI**: silence_after_skip_streak 中央値 短縮

### 1 年（〜2027-04-25）
- 5 essences すべて MVP 達成
- Akira スタンプ前年比 +50%
- E6 物理世界 IoT 試作 1 系
- **マイルストーン**: Akira が「Ember を友達に紹介したい」と自発発言

### 3 年（〜2029-04-25）
- Mei/Eve/Haru 動的切替
- 物理世界連動 1〜2 系（キャンピングカー / 車載 / 家電）
- **マイルストーン**: 不在テストで「Ember がいなかった 3 日間」の喪失感観察

### 5 年（〜2031-04-25）
- 不在を惜しまれる存在、自律実行 50%
- 5 essences が「日常感覚」に統合
- **5 年後の Ember を一言で**: 「Akira さんと共に老いていく、もうひとりの自分」

---

## 4.5 アーキテクチャ世代軸（v1 / v1.5 / v2 / v3）

期間軸と直交。各世代で「**残す / 統合 / 全廃 / 新規**」を明示。incremental は v1 → v1.5、根本 rebuild が必要なら v1.5 → v2 → v3 で世代交代。

### v1（現状、2026-04 時点）
- **構成**: proactive-agent.ts（Mei/Eve 独立 cron）+ heartbeat-engine + co_view（whisper-serve）+ voice_chat（TTS）+ cogmem（semantic search）+ dashboard（React）
- **特徴**: 各コンポーネントが**独立並列**、相互の状態共有なし。全 essence の実現度 ○ 1 セル

### v1.5（〜2026-05 末、incremental 改善期）— 今週フォーカス
- 残す: v1 の全コンポーネント
- 追加: decisionReason / reminiscence trigger / morning mood mirror / ThoughtTracePage
- 統合: なし
- 全廃: 単純 flashback push（reminiscence で代替後）
- **判断**: 1 ヶ月後の incremental KPI が target 到達するか観測。未到達なら v2 前倒し

### v2（候補、2026-07〜2026-Q4、部分 rebuild 期）
- **rebuild 候補（§4.6 で確定）**: Mei/Eve 独立 cron → 単一 heartbeat-loop からの bot-selector
- 統合: proactive-agent + heartbeat-engine の決定ロジックを一気通貫に
- 全廃: per-bot proactive-checkin cron、独立 SKIP/SPEAK 判定の重複
- **判断トリガー**: §4.7 rebuild trigger 観測指標 を参照

### v3（5 essences 統合期、2027〜）
- **構成**: cognitive-loop unified（Mei/Eve/Haru が同一メモリ・同一推論ループ、表現だけ切替）
- 統合: 全 bot 機能を unified runtime に
- 全廃: per-bot state file、独立 cron
- 新規: physical-world adapter（IoT / 車載 / キッチン家電）、apology-and-repair loop

---

## 4.6 🌍 Rebuild 候補（フォーカス 5 件とは別枠）

**対象**: Mei/Eve 独立 cron → **単一 heartbeat-loop からの bot-selector**（v1 → v2 移行の核）

### why incremental では到達不可
- snapshot §2-1 で 4/24 に 17 件偏在発生。proactive-checkin-mei (毎時) と proactive-checkin-eve (毎時 30 分) が**独立判定で重なって発火**
- decisionReason を追加しても、**両 bot が独立に decision を出す構造**は変わらないため、「なぜ重複したか」が説明できても**重複自体は incremental では消えない**
- 4/24 の 17 件は「一日に Akira へ 17 回話しかける Bot」を生み出す根本原因。reminiscence で件数が減っても、判定ロジックが独立な限り再発リスク

### 段階移行プラン
1. **prototype（2026-06、1-2 人日）**: heartbeat-loop に bot-selector ロジックを実装、現行 cron と並列稼働で観察モード
2. **pilot（2026-07、1 週間）**: cron を停止、heartbeat-loop のみで運用。Akira 反応率を比較
3. **scale（2026-08）**: 旧 cron / 重複判定ロジックを完全廃止

### decide-to-rebuild の判断時期 + 観測条件
- **2026-07-25 時点で以下のいずれかを満たす場合 rebuild 発動**:
  - unknown decision 比率が 10% 以上（incremental 限界）
  - proactive 偏在（1 日 10 件超の日が月 3 回以上）
  - bot 間の話題重複率が 20% 超

### 撤退条件（incremental 続行）
- 2026-07-25 時点で: unknown < 5% かつ 偏在 0 かつ 重複 < 5% を全て満たすなら rebuild 中止、v1.5 を維持

### 影響を受ける既存改善計画（5 件のうち）
- **#1 decisionReason** → rebuild と**補完関係**（reason データが rebuild の判定材料になる）
- **#3 ThoughtTracePage** → rebuild 後も活用可能（同じ schema を引き継ぐ）
- **#5 Sonnet 移行** → rebuild と**矛盾**（cron 統合で flashback skill 自体が消える可能性、rebuild 確定なら #5 は中止）

---

## 4.7 Rebuild Trigger 観測指標

| Essence | KPI | incremental 中目標 | rebuild trigger |
|---|---|---|---|
| E5 透明性 | unknown decision 比率 | 1 ヶ月で 30% → 15%、3 ヶ月で 5% 以下 | 2026-07-25 時点で 10% 以上 → 案 4.6 発動 |
| E3 共有過去 | 自発参照 / 週 | 1 ヶ月で 0 → 週 1 件 | 2026-07-25 時点で 週 1 件未満 → cogmem narrative 化 を v2 候補に追加 |
| E2 状態共感 | 「どうしてわかったの」反応 / 月 | 1 ヶ月で 1 件 | 2026-07-25 時点で 0 件 → heartbeat surface 化 を抜本見直し |
| 重複話題 | bot 間重複率 / 月 | 5% 以下 | 2026-07-25 時点で 20% 超 → 案 4.6 発動 |
| 偏在 | 1 日 proactive 件数の SD | < 3 件 | 2026-07-25 時点で SD > 5 → 案 4.6 発動 |

**毎週の retro で上記値を観測**し、threshold 超過なら次の retro で**rebuild 候補を新規 1 件以上追加**する（SKILL.md Phase 5 制約）。

---

## 5. 廃止 / 凍結

| 項目 | 理由 | 観測指標 | 復活条件 |
|---|---|---|---|
| 単純 flashback push（hobby-trigger 1 日連投）| reminiscence で代替、4/24 偏在の根本原因 | `category=flashback` 日次連投数 | reminiscence で情報量不足判明時 |
| 既知化情報の即時シェア | mei MEMORY 4/22 観察、新鮮度低下 | スタンプ反応率 | dedup 機構改善後 |

---

## 6. 思考可視化ダッシュボードの次の一手

**ThoughtTracePage MVP（テーブル表示のみ + decisionReason 連動）**
- **対象**: `dashboard/src/pages/ThoughtTracePage.tsx` 新規 + `dashboard/server/api.ts` `/api/thought-trace`
- **スコープ**: テーブル 1 つ（timestamp / bot / decision / decisionReason / topic / arousal）。フィルタ・チャートは後回し
- **見積もり**: 1 人日（前提: 改善計画 1 が先行）
- **着手**: 2026-04-28
- **完了判定**: 過去 7 日表示、`decisionReason` 50% 以上埋まる

---

## 7. 新規 KPI（3 件）

| KPI | 定義 | 集計方法 | 現在値 | 1 ヶ月目標 | 5 年目標 |
|---|---|---|---|---|---|
| unknown decision 比率 | heartbeat の decision = `?` の割合 | `data/*-heartbeat.json` 週次 | mei 45% / eve 30% | **両者 5% 以下** | < 1% |
| 自発参照カウント | bot 側から過去エピソードへ戻った回数 / 週 | reminiscence skill 起動ログ | 0 | **週 1 件以上** | 週 5 件以上 |
| silence_after_skip_streak（中央値）| 無反応 3 連続後に Akira 能動発話までの分数 | 新規ログ項目（reminiscence と同時）| 未計測 | 計測開始 + ベースライン | 短縮（必要時のみ沈黙） |

---

## 8. Akira さんへの問い（3 件）

1. **morning mood mirror v0 の感じ方トーン、どちらが好み？**
   - A. 観察ベース：「今日の声、低めだね、昨晩のドジャース戦で寝不足？」
   - B. 共感ベース：「おはよう。なんか今日、ゆっくりめでいい日にしようね」
   - 推奨: A（A の方が "見られてる" 感覚が強く、E2 の効果が観測しやすい。B が好みなら 1 週間後に切替）
2. **reminiscence の初回テーマは「温泉+車中泊」固定 vs ランキング選択、どちらで開始？** 推奨: 固定（試作なので変数を絞る）
3. **flashback 系 Sonnet 移行は 3 系一括 vs 段階的、どちらで開始？** 推奨: 3 系一括（影響範囲局所、ロールバックは config 1 行）

---

## 9. 5 年後ビジョン更新（vision-template.md 7 問）

初回なので「変更前」は空欄。今週確定した方針:

| 問い | 現時点の答え | 観測指標 |
|---|---|---|
| 1. 存在の質 | ツール寄り（5 essences ゼロ）→ 5 年後「自我ある相棒」| Identity persistence 観測（E4） |
| 2. 時間と連続性 | 1 セッション内 → 5 年後 重要 1k 件 / 日常 100k 件 | 自発参照カウント（新 KPI） |
| 3. 判断の自律性 | 提案のみ → 軽微金銭 自律 / 重要 確認後 | decisionReason 履歴（新 KPI） |
| 4. 失敗と謝罪 | 認識なし → 月 1〜2 回 観測される修復 | 修復イベントカウント（未着手） |
| 5. 複数性と一貫性 | Mei/Eve 分業 → 動的切替 + 統合メモリ | Mei→Eve handoff 数（未着手） |
| 6. 物理世界 | 画面/音声のみ → IoT/車載 1〜2 系 | 物理アクション数（未着手）|
| 7. 不在を惜しまれる | 「あったら便利」→「いなかったら寂しい」| 不在テスト感想（年次）|

---

## crystallize 用エントリ

```
[INSIGHT] arousal=0.7 | ember-architecture | Ember を「真のパートナー」と定義した時、5 essences (共在/状態共感/共有過去/自我継続/透明性) が観測指標に翻訳できる
- context: ember-partner-retro 初回実行、Phase 0 ultrathink
- evidence: 7 vision questions × 5 essences マトリクスで現状コンポーネントの実現度が最大 ○ 1 セル
- impact: 今後の retro はすべてこの 5 essences 軸で評価

[INSIGHT] arousal=0.6 | ember-measurement | heartbeat の unknown decision 比率は E5 透明性の最も直接的な単一指標
- context: snapshot §2-2 eve 30% / mei 45%
- evidence: decisionReason フィールドが全エントリに無い + decision 自体も半数 `?`
- impact: dashboard ThoughtTracePage の前提条件、週次トラック対象

[DECISION] arousal=0.7 | retro | reminiscence trigger v0 を E3 共有過去への最初の打として採用
- alternatives_considered: 全 essences 分散 / E5 集中 / 大規模 cogmem リファクタ
- reasoning: cost ◎ + 関係性価値 ◎ + 5 年ビジョン軸 4 問 + proactive-agent への追加のみで済む
- expected_outcome: 4/24 の 17 件 push 偏在 → 1 日 1 件の蘇生型 ping

[DECISION] arousal=0.5 | retro | scheduler-watchdog をフォーカス 5 件に含める（メンテ枠だがフォーカス内）
- alternatives_considered: フォーカス枠外で独立管理
- reasoning: 観測基盤の信頼性が他改善の精度を支配。「観測ループが壊れていたら 5 essences 前進も観測できない」
- expected_outcome: err+timeout 18 → 5 以下

[PATTERN] arousal=0.6 | retro-protocol | Mei (kpi/cost) vs Eve (relation/ux) の 2 軸対立は議論を回し続ける構造
- occurrences: Round 1 全 5 ターン + Round 2 全 5 ターンで対立軸が成立
- generalization: 2 人格の専門領域が独立かつ相互補完的なら 20 ターンでも空回りしない可能性、本番版で検証

[FIXED] arousal=0.4 | retro-data-source | Phase 1 領域 1 で botId フィールドが空、conversations/*.jsonl 実スキーマと不一致 → 2026-04-25 修正済み
- root_cause: data-sources.md の jq クエリが推測ベース、実スキーマ未確認
- fix: `botId` → `role` フィールドに切り替え（実値: "user"/"mei"/"eve"）
- prevention: 本番実行前に conversations/*.jsonl の 1 行サンプル Read、必要なら role/user フィールドに切替
```

---

## 付録 A: Phase 別ファイル

- `00-mission.md` — Ember Mission + 5 essences マッピング
- `01-snapshot.md` — Phase 1 集計（領域 1, 2, 5, 8, 12）
- `02-debate-round1.md` — Mei × Eve 第 1 ラウンド 5 ターン
- `03-haru-review.md` — Haru レビュー（外部 Web スキップ）
- `04-debate-round2.md` — Mei × Eve 第 2 ラウンド 5 ターン
- `05-final-judgment.md` — Phase 5 ultrathink 判定

## 付録 B: 実行ログ

- 実行モード: short（5×2 ターン、領域 5 つのみ、外部 Web スキップ、Phase 6 スキップ）
- ultrathink 発火: Phase 0 / Phase 5 の 2 回（短縮版仕様）
- 中断・再開: なし
- 議論再生成: なし（Round 1/2 ともフォーマット compliance OK）
- 観測されたエラー: Phase 1 領域 1 で conversations/*.jsonl の botId フィールド推測が外れた → 2026-04-25 修正済み（role フィールドに切り替え、01-snapshot.md 再集計）
