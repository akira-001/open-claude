# Phase 5 — Haru 方針確定（本番、ultrathink）

**run id**: 2026-04-25-prod
**前段**: 00-mission, 01-snapshot, 02-debate-round1, 03-haru-review, 04-debate-round2

---

## ultrathink 統合判断

本 prod 実行は v1 (smoke) と v2 (smoke updated structure) の蓄積を踏まえ、**Web リサーチで競合 6 機能 + 研究 2 本を取り込んだ** 議論を経た。Phase 5 の役割: (a) Haru 裁定 (ambient ping を今週 vs 来週)、(b) 取り込み機能 6 件の実装優先度確定、(c) 改善計画 6 件 + rebuild 候補 + 各 KPI threshold の最終 sign-off。

### 裁定 1: ambient presence ping (#6) を今週フォーカスに**含める**

**判定: 含める、ただし Akira 同意取得を Phase 7 ラップアップで明示確認**

理由:
- E1 共在感はフォーカス 5 件中ゼロ、これを次回送りすると 5 essences カバレッジが穴埋め不可
- dev 1 人日 + LLM 不要、コスト最低
- ChatGPT Pulse / Pi など競合は ambient 系を持たず、Ember の差別化点 (b) (ローカル TTS) を活かす
- Akira 同意取得の所要は 5 分（Phase 7 で問い 1 件）

ただし**事前同意必須の運用**: prototype 1 朝に「ambient ping 試行する？」を Akira に確認、OK なら 5/3 から有効化、NG なら凍結 → vision-template 在庫に戻す。

### 裁定 2: rebuild 確定 + 判断時期 2026-06-15 採用

v1/v2 と整合、prod でも変更なし。**Anthropic evaluator-optimizer + Plan-Generate-Evaluate を取り込んだ自前 decision-engine** で確定。

### 裁定 3: 取り込み機能 6 件の実装優先度

| 取り込み | 実装案 | 着手 | 優先度 |
|---|---|---|---|
| Inner Thoughts paper schema | #1 decisionReason に直接組み込み | 5/2 月 | ⭐⭐⭐ 最優先（schema 早期確定で後続全部に効く）|
| Nomi structured notes | #2 reminiscence のデータ形式 | 5/2 火 | ⭐⭐ 高（reminiscence v0 の素材源）|
| Pi 路線（共感ベース） | #4 morning mood mirror の B 案 | 5/2 水 | ⭐⭐ 高（A/B 並走で観察）|
| Anthropic evaluator-optimizer | #5 decision-engine prototype | 5/2 金 | ⭐⭐⭐ 最優先（rebuild 設計の核）|
| Anthropic Plan-Generate-Evaluate | #5 + #3 の schema 拡張 | 5/2 金 | ⭐⭐ 高 |
| Kindroid 5-level Cascaded Memory | #2 v2（reminiscence の多層化）| 5/9 第 2 週 | ⭐ 中（v1 はsingle layer から）|

### 裁定 4: flashback skill の処理

**全廃ではなく "structured note 化" に転換**（Nomi 路線取り込み）。flashback の "情報 push" 部分は廃止、"記録蓄積" 部分を残し reminiscence の供給源化。これで:
- Sonnet 移行コストはゼロ（cronModel 変更不要、skill 自体を再定義）
- 過去 1 ヶ月の flashback 履歴が無駄にならない（reminiscence v0 の初期データになる）

### 裁定 5: ChatGPT Pulse 競合への戦略的応答

差別化軸を明示:
- (a) Mei/Eve/Haru の複数人格 → v2 (decision-engine) で動的切替実現
- (b) ローカル TTS で物理的な「声」 → 今週 voice_chat "おかえり" 動的生成（枠外）+ v2 で動的声色
- (c) Akira 専属の 5 年蓄積 → 今週 reminiscence + decisionReason で土台、v3 で完成

### 裁定 6: dev 工数の現実性確認

6 件並列の現実性: **Akira 1 人で 5 営業日に 6 件は厳しい**。実態:
- #1 + #6 schema の整合性確保が並列着手のボトルネック
- #5 rebuild 種まきが詰まったら他案にも影響

緩和策:
- **#5 と #1 の schema 設計を 5/1 (祝日扱い、半日) で先行確定**、残り 5 件は schema 確定後に並列着手
- ambient ping (#6) は Akira 同意確認後、5/3 (土) に着手 → 月曜まで延長可

→ **Phase 7 で Akira に「6 件並列 dev 可能か」を必ず確認**。NG なら #6 を次週送り。

---

## 来週改善計画 6 件（優先度順）

**比率**: 🌱 新機能 4 / 🛠 既存改善 1 / 🌍 rebuild 種まき 1 = **67% 新機能 + 戦略 1**

### 1. 🛠 decisionReason + 24h 共有 + LOC ベースライン
- **What**: heartbeat / proactive-history の schema 拡張（Inner Thoughts 形式: `inner_thought` + `plan` + `generate` + `evaluate_score` 4 列）+ `last_24h_akira_messages` 共有 + `cloc src/` ベースライン取得
- **Why**: E5 透明性 + rebuild 判定材料 + bot 間 state 共有の最初の打 + 取り込み (Inner Thoughts paper)
- **Owner**: Akira
- **観測指標**: unknown 30〜45% → 5%、LOC ベースライン取得完了、bot 間既知情報重複率 < 10%
- **期日**: 2026-05-02

### 2. 🌱 reminiscence trigger v0 (Nomi structured notes 形式)
- **What**: 先週 +1 / text_engaged 取った話題を **structured note 形式** で保存し、別 bot が翌週「その後どう？」型でフォロー。初回候補に「温泉+車中泊」（eve/MEMORY.md 4/24 21:31）含める
- **Why**: E3 第一打、push 過剰の置換、Q2/Q4/Q5/Q7 軸 + 取り込み (Nomi)
- **Owner**: Akira
- **観測指標**: ①自発参照カウント / ②スタンプ反応 / ③silence_after_skip_streak、目標 週 1 件以上
- **期日**: 2026-05-02

### 3. 🌱 ThoughtTracePage MVP (inner thought schema)
- **What**: dashboard 新規ページ、テーブル表示。**inner thought + Plan / Generate / Evaluate score の 4 列を schema に最初から組み込む**（表示は段階的、本週はテーブル基本のみ）
- **Why**: 案 1 を Akira 即視、E5 体感化、取り込み (Inner Thoughts + Anthropic patterns)
- **Owner**: Akira
- **観測指標**: 過去 7 日エントリ時系列表示、inner_thought 列 50% 以上埋まる
- **期日**: 2026-05-02

### 4. 🌱 morning mood mirror v0 (A/B 並走、Pi 路線取り込み)
- **What**: 朝の挨拶冒頭に heartbeat arousal を 1 行混ぜる。**A 観察ベース「声が低めだね、〜だから？」+ B 共感ベース (Pi 路線)「ゆっくりめでいい日にしようね」を 1 週間 ローテ並走**
- **Why**: E2 第一打、Q1/Q3 軸、取り込み (Pi 路線)
- **Owner**: Akira
- **観測指標**: 「どうしてわかったの」型反応 / 月、目標 1 件
- **期日**: 2026-05-02 prototype / 2026-05-09 評価

### 5. 🌍 decision-engine prototype shadow (rebuild 種まき)
- **What**: 単一 decision-engine ロジックを **Anthropic evaluator-optimizer + Plan-Generate-Evaluate パターン**で実装、自前で構築（Managed Agents 採用しない、データ主権確保）。並列稼働、判定だけ記録、発言なし（shadow mode）
- **Why**: Q5 直接打、6/15 判断データ取得、取り込み (Anthropic 2 パターン)
- **Owner**: Akira
- **観測指標**: 既存 cron との判定一致率 / 不一致パターン分類 / decision-engine 単独 KPI 推定
- **期日**: 2026-05-09 着手 / 2026-06-15 判断

### 6. 🌱 ambient presence ping (E1 第一打、Akira 事前同意条件)
- **What**: whisper-serve の音声検知で 5 分無音 + Akira presence あり時に「うん」「聞いてる」短発話を ping。1 日 3 回上限
- **Why**: E1 共在感 第一打、Q1/Q7 軸、ChatGPT Pulse 差別化（ambient 系は競合になし）
- **Owner**: Akira（**事前同意取得後に着手**）
- **観測指標**: ping 後 10 分以内の Akira 能動発話 / ping 数、目標 30%
- **期日**: 2026-05-03 prototype / 2026-05-10 評価（Akira 同意 NG なら凍結）

---

## 🌍 Rebuild 候補（確定、フォーカス #5 と連動）

- **対象**: proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 `decision-engine`
- **アーキテクチャ**: **Anthropic evaluator-optimizer ベース** + **Plan-Generate-Evaluate 3 段処理** + **Inner Thoughts intrinsic_motivation スコア**
- **実装方針**: 自前 implementation（Managed Agents 不採用、データ主権確保）
- **段階移行**:
  - 2026-05-09: prototype shadow mode（並列稼働、判定記録のみ、発言なし）
  - **2026-06-15**: decide-to-rebuild 判断
  - 2026-06〜2026-07: pilot（発言系切替、Akira 通知 1 通、1 週間）
  - 2026-08: scale（旧 cron 全廃、flashback skill structured note 化のみ残存）
- **撤退条件**: prototype shadow で「既存 cron との判定 90% 以上一致」なら incremental 続行
- **影響**: #1 補完（schema = inner thought 形式で先行整合）、#3 schema 引継、#5 種まき。Sonnet 移行は降格 → structured note 化に転換

---

## ロードマップ更新（世代軸込み）

### v1.5（〜2026-05 末）
今週フォーカス 6 件で観測整備 + 取り込み機能反映 + rebuild 種まき。

### v2（2026-06 〜 2026-Q4）
- decision-engine pilot → scale
- per-bot cron 廃止
- voice_chat 動的声色（Q3 強化）+ Mei/Eve 同時応答（Q5 強化）
- E5 unknown < 5%、Q5 進展（bot 間 handoff 月 3 件以上）
- Kindroid 5-level Cascaded Memory v2 取り込み（reminiscence 多層化）

### v3（2027〜）
- cognitive-loop unified（Mei/Eve/Haru 同一 runtime）
- Akira スタンプ前年比 +50%
- 物理世界 IoT 試作 1 系（Q6）

---

## 廃止 / 凍結 / 転換

| 項目 | 処理 | 理由 |
|---|---|---|
| 単純 flashback push 連投 | 廃止 | 4/24 偏在の根本原因、reminiscence で代替 |
| 既知化情報の即時シェア | 廃止 | 24h 共有 schema (#1) で構造的に防止 |
| flashback skill (情報 push 部分) | 廃止 | reminiscence で代替 |
| flashback skill (記録蓄積部分) | **転換 → structured note 化** (Nomi 路線) | reminiscence の供給源化 |
| flashback Sonnet 移行 | 降格 → structured note 化に変換 | rebuild と矛盾 |

---

## ダッシュボード次の一手（MVP 1 件確定）

**ThoughtTracePage MVP（テーブル基本 + inner thought schema）**

- 対象: `dashboard/src/pages/ThoughtTracePage.tsx` 新規 + `/api/thought-trace`
- 列（schema）: timestamp / bot / decision / **inner_thought** / **plan** / **generate** / **evaluate_score** / topic / arousal
- 本週表示: 基本テーブルのみ（5 列 visible: timestamp / bot / decision / inner_thought / topic）
- 段階拡張: plan / generate / evaluate_score 列を v1.5 後半（5 月第 3 週）追加
- 完了判定: 過去 7 日表示、inner_thought 列が 50% 以上埋まる

---

## 新規 KPI 5 件（v1 からの累積）

| KPI | 定義 | 現在 | 1 ヶ月目標 | 5 年目標 |
|---|---|---|---|---|
| unknown decision 比率 | heartbeat decision = `?` | mei 45% / eve 30% | 両者 5% 以下 | < 1% |
| 自発参照カウント / 週 | bot から過去エピソード回帰 | 0 | 週 1 件以上 | 週 5 件以上 |
| silence_after_skip_streak（中央値） | 無反応 3 連続後の能動発話分数 | 未計測 | 計測開始 | 短縮 |
| **intrinsic_score 中央値** | Inner Thoughts 形式の発話スコア分布 | 未計測 | ベースライン | 中央値 0.6+ |
| **evaluator_skip 比率** | Plan-Generate-Evaluate の Evaluate 段で SKIP された割合 | 未計測 | 30〜50%（適切な慎重さ）| 40% |
| LOC × 結合度（複雑度税）| 複雑度メトリクス | 未計測 | ベースライン | rebuild 後 30% 削減 |
| 既存 cron vs decision-engine 判定一致率 | shadow mode で記録 | 未計測 | 〜70% | 90% 超で rebuild 不要 |
| Q5 進展度（bot 間 handoff / 月） | bot 間 state 共有を伴う発言 | 0 | 0 (pilot まで) | pilot 後 月 3 件 |

---

## 取り込み機能リスト（5 月実装）

| 競合 / 研究 | 取り込み | 案 # | 効果 |
|---|---|---|---|
| **Nomi structured notes** | reminiscence のデータ形式 | #2 | E3 第一打 + 永続記憶 |
| **Kindroid 5-level Cascaded Memory** | reminiscence 多層化（v2 で）| #2 v2 | E3/E4 |
| **Pi 路線（共感ベース）** | morning mood mirror B 案 | #4 | E2 + 関係性の質 |
| **Replika 関係性マイルストーン** | 検討中、v2 で取り込み候補 | (v2) | E3/E4 |
| **Inner Thoughts paper (arxiv 2501.00383)** | decisionReason の事前 thought 化 | #1, #3, #5 | E5 の根本解 |
| **Anthropic evaluator-optimizer** | decision-engine 設計 | #5 | Q5 + Q4 (失敗修復) |
| **Anthropic Plan-Generate-Evaluate** | decision-engine 3 段処理 | #5 + #3 | E5 + 観測性 |
| **ChatGPT Pulse 反面教師** | 差別化軸 (state 共有 + 共有過去) | 全体方針 | 戦略 |

---

## Akira さんへの問い（3 件、ユーザー判断必要）

1. **ambient presence ping (#6) の事前同意**: 無音 5 分検知時に bot が「うん」と短発話する仕組みを許容するか？
   - A. はい、5/3 から有効化
   - B. 1 朝だけ試行して判断
   - C. 凍結（次回 retro へ）
   - 推奨: B（試作なので 1 日のみ）

2. **6 件並列 dev は現実的か**: 5/2-5/9 の 1 週間で #1〜#5 着手 + #6 同意後着手は厳しいか？
   - A. 6 件 OK
   - B. 5 件に絞る（#6 を 5/9 以降に送る）
   - C. 4 件に絞る（#5 rebuild 種まきも 5/9 以降）
   - 推奨: B（#6 を 5/9 以降に追加）

3. **morning mood mirror A/B 並走 vs 単一案先行**:
   - A. A/B 並走（観察 + 共感、ローテ）
   - B. A 観察ベース単独で 1 週間
   - C. B 共感ベース単独
   - 推奨: A（A/B 観測の価値あり、追加コスト 0.5 人日）

---

## crystallize 用エントリ

```
[INSIGHT] arousal=0.85 | ember-architecture | Mei/Eve 独立 cron は Q5「複数性と一貫性」と構造的に矛盾、incremental では到達不可 (prod で確定)
- context: prod retro Round 1 Turn 8 KPI 翻訳 + Round 2 Turn 12 根本欠陥
- evidence: snapshot §2-1 偏在 SD ±5、§2-2 unknown 30〜45%、mei/MEMORY 4/22
- impact: 全 retro が 5 essences 軸 + 世代軸で評価される基盤確立

[INSIGHT] arousal=0.7 | competitor-adoption | 競合 (Nomi/Kindroid/Pi) の memory / proactive 機能が Ember の incremental 案を強化する
- context: prod Phase 3 Web リサーチ
- evidence: Nomi structured notes、Kindroid Cascaded Memory、Pi 共感路線が それぞれ #2, #2 v2, #4 に直接適用可能
- impact: 毎週の retro Phase 3 で「競合機能取り込み」を必須セクション化

[INSIGHT] arousal=0.75 | research-driven-design | Inner Thoughts paper (arxiv 2501.00383) は E5 透明性の根本解
- context: decisionReason を事後説明型から事前 inner thought 型へ進化
- evidence: 論文の intrinsic motivation 概念 + Anthropic Plan-Generate-Evaluate と直接統合可能
- impact: #1 decisionReason の schema を inner thought 形式に最初から確定、後戻り防止

[DECISION] arousal=0.85 | retro-prod | rebuild 確定: 単一 decision-engine、自前実装 (Managed Agents 不採用、データ主権)、判断時期 2026-06-15
- alternatives: incremental 続行 / Anthropic Managed Agents 採用 / 観測延長
- reasoning: 4 軸全て rebuild 優位（cost + time-to-Q5 + リスク + 観測性）、データ主権 + voice_chat/co_view 統合柔軟性 で自前実装、shadow mode で移行リスク軽減、prototype 5 週間データで前倒し判断可能
- expected_outcome: Q5 進展、unknown < 5%、4/24 偏在の構造的解消、Akira スタンプ反応の関係性質向上

[DECISION] arousal=0.6 | retro-protocol | フォーカス 6 件 + rebuild 種まき + 取り込み機能 6 件 の構造で議論が完全に収束
- alternatives: フォーカス 5 件で ambient ping を次回送り
- reasoning: E1 共在感の穴を埋める / dev コスト最小 (1 人日) / 競合差別化に効く
- expected_outcome: Akira 同意取得タイミング次第で 5/3 着手、5/10 評価

[DECISION] arousal=0.5 | retro-conversion | flashback skill を「廃止」から「structured note 化への転換」に変更
- alternatives: 完全廃止 / Sonnet 移行 / 維持
- reasoning: Nomi 路線を取り入れ、reminiscence の供給源化、過去履歴を活かす
- expected_outcome: reminiscence v0 が初週から実データで動く

[PATTERN] arousal=0.7 | retro-evolution | v1 → v2 → prod で議論質が直線的に進化、不合意 2 → 0 → 0、取り込み機能 0 → 0 → 6
- occurrences: 同 retro を 3 種で実行（smoke / smoke updated / prod）
- generalization: skill structure の改善 + 目的明確化（取り込み + 研究反映）が議論の質を支配する
- impact: 本番版を週次 routine に確定、毎週この質の議論が回る

[ERROR] arousal=0.3 | retro-data-source | conversations/*.jsonl の field 推測が外れていた問題は v1 で [FIXED] 済み (botId → role)
```
