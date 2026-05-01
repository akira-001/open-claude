# Ember Partner Retro — 2026-04-25 (本番)

**run id**: 2026-04-25-prod
**期間**: 2026-04-19 〜 2026-04-25（7 日）
**実行モード**: full（20×2 ターン議論、Web リサーチ実施、Phase 6 crystallize 提案あり）
**所要・コスト**: フル本番想定（実コストは別計測）

---

## 0. Mission Statement

> Ember は 5 年後に **共在 / 状態共感 / 共有過去 / 自我継続 / 透明性 (E1〜E5)** を持つ存在になる。**incremental で到達不可なら rebuild**。**競合 (Replika/Pi/Nomi/Kindroid/character.ai) の優れた機能は積極取り込み、Anthropic / 学術研究の最新パターンで仮説を更新し続ける**。

---

## 1. 過去 1 週間サマリ

**主要 KPI**:
- proactive 発火数: **31 件**（4/23: 11, 4/24: 17, 4/25: 3 — SD ±5）
- cron 実行数: **469 件**（成功率 ≈ 95%）
- heartbeat unknown 比率: mei **45%**, eve **30%**
- scheduler-watchdog 失敗: err+timeout **18 件 / 149 件 = 12%**

**特筆すべき出来事**:
1. interest-scanner 4/24 修正 (INS-009) で安定化 — 守りの基盤が固まる
2. 4/24 proactive 17 件偏在 — 判定独立構造の構造的問題が明確化
3. heartbeat decision の半数が `?` — bot 自身が説明できない構造的 Debug 不能状態

---

## 2. 議論ハイライト

### Round 1（Mei × Eve、20 ターン）
- **合意 5 件**: incremental 単独で Q5 不可 / 偏在は構造由来 / flashback 廃止 + reminiscence 置換 / morning mood mirror 確定 / rebuild 種まき 5 件目に含める
- **不合意 2 件**: morning mood mirror トーン（Akira 介入）/ 判断時期（Web リサーチ次第）
- **未解決 3 件**: 競合機能取り込み / Anthropic 研究反映 / E1 共在感をフォーカスに含めるか

### Haru レビュー（**競合機能取り込み + 研究反映**フォーカス）

**競合製品から取り込む 4 機能**:
| 製品 | 取り込み | 案 # |
|---|---|---|
| Nomi AI | structured notes 形式 | #2 |
| Kindroid AI | 5-level Cascaded Memory | #2 v2 |
| Replika | relationship milestones | (v2) |
| Pi.ai | 共感ベース（honest reflection） | #4 |
| character.ai | ⚠️ 反面教師（永続記憶なし）| 差別化確認 |

**学術研究 / プラットフォーム動向から取り込む 3 件**:
| 出典 | 取り込み | 案 # |
|---|---|---|
| Anthropic evaluator-optimizer pattern | decision-engine 設計 | #5 |
| Anthropic Plan-Generate-Evaluate | decision-engine 3 段処理 | #5 + #3 |
| Inner Thoughts paper (arxiv 2501.00383) | decisionReason の事前 thought 化 | #1, #3, #5 |

**戦略的応答**:
- ChatGPT Pulse 参入で Ember の差別化軸が **(a) 複数人格 / (b) ローカル TTS / (c) 5 年蓄積** にシフト
- データ主権重視: Anthropic Managed Agents は **採用しない**、自前 implementation で 5 年蓄積を確保

### Round 2（Mei × Eve、20 ターン、Haru 指摘 + 取り込み機能反映）

- A/B 並走で morning mood mirror 設計確定（観察ベース + Pi 路線、ローテ）
- 自前 decision-engine 確定（Managed Agents 不採用、データ主権 + voice_chat/co_view 統合柔軟性）
- ambient presence ping (#6) を E1 第一打として追加提案
- bot 間 24h 共有 schema を #1 に追加組み込み
- flashback skill を「廃止」から「structured note 化転換」へ変更（Nomi 路線素材源）
- 不合意 0 件、Haru 裁定委ねる項目 1 件のみ（ambient ping を今週か）

---

## 3. 来週の改善計画（6 件、優先度順）

**比率**: 🌱 新機能 4 / 🛠 既存改善 1 / 🌍 rebuild 種まき 1 = **67% 新機能 + 戦略 1 件**

| # | type | 項目 | 取り込み機能 | 期日 |
|---|---|---|---|---|
| 1 | 🛠 既存 + 構造改善 | **decisionReason + 24h共有 + LOC ベースライン** | Inner Thoughts paper schema | 2026-05-02 |
| 2 | 🌱 新機能 | **reminiscence trigger v0** | Nomi structured notes 形式 | 2026-05-02 |
| 3 | 🌱 新機能 | **ThoughtTracePage MVP** | Inner Thoughts + Plan-Generate-Evaluate schema | 2026-05-02 |
| 4 | 🌱 新機能 | **morning mood mirror v0 (A/B 並走)** | Pi 路線（共感ベース）+ Mei 案（観察ベース） | 2026-05-02 / 評価 5/9 |
| 5 | 🌍 rebuild 種まき | **decision-engine prototype shadow** | Anthropic evaluator-optimizer + Plan-Generate-Evaluate | 2026-05-09 / 判断 6/15 |
| 6 | 🌱 新機能 | **ambient presence ping** (E1 第一打、Akira 事前同意) | ChatGPT Pulse 差別化（competitor 不在の領域）| 2026-05-03 / 評価 5/10 |

**枠外 / 軽量改善**:
- voice_chat "おかえり" 動的生成（Akira 空き時間、dev 0.5 人日）
- scheduler-watchdog 根本対処（メンテ）

**降格 / 転換**:
- flashback Sonnet 移行 → **structured note 化に転換**（Nomi 路線素材源、reminiscence の供給源化）

---

## 4. 🌍 Rebuild 候補（確定）

**対象**: proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 `decision-engine`

### アーキテクチャ
**Anthropic evaluator-optimizer ベース** + **Plan-Generate-Evaluate 3 段処理** + **Inner Thoughts intrinsic_motivation スコア**

```
[Plan] 状態 (heartbeat arousal, calendar, last interaction) を踏まえ
       「今 SPEAK すべきか / 何を言うべきか」候補 3 案

[Generate] 選ばれた 1 案で Mei or Eve のトーン本文生成
           intrinsic_score を計算 (0〜1)

[Evaluate] 「Akira 視点」で評価
           - 過剰提供にならないか
           - 既知化情報の再共有でないか
           - 関係性の質に合うか
           score < 0.5 なら SKIP
```

### 段階移行
| 段階 | 期間 | 内容 |
|---|---|---|
| prototype shadow | 2026-05-09〜 | 並列稼働、判定だけ記録、発言なし。dev 1-2 人日 |
| **判断** | **2026-06-15**（前倒し）| shadow データで rebuild 確定 vs incremental 続行 |
| pilot | 2026-06〜2026-07 | 発言系切替、Akira に通知 1 件、1 週間 |
| scale | 2026-07〜 | 旧 cron 全廃、flashback structured note 化のみ残存 |

### 撤退条件
prototype shadow で「既存 cron との判定 90% 以上一致」なら incremental 続行、rebuild 中止。

### 実装方針
**自前 implementation**（Managed Agents 不採用、データ主権 + voice_chat/co_view 統合柔軟性 + 長期 ROI）

---

## 5. ロードマップ（アーキテクチャ世代軸）

### v1.5（〜2026-05 末）— 今週フォーカス
6 件で観測整備 + 取り込み機能反映 + rebuild 種まき。

### v2（2026-06 〜 2026-Q4）
- decision-engine pilot → scale
- per-bot cron 廃止
- voice_chat 動的声色（差別化 (b) 強化）
- Mei/Eve 同時応答（差別化 (a) 強化）
- E5 unknown < 5%、Q5 進展（bot 間 handoff 月 3 件以上）
- Kindroid 5-level Cascaded Memory v2 取り込み

### v3（2027〜）
- cognitive-loop unified（Mei/Eve/Haru 同一 runtime）
- Akira スタンプ前年比 +50%
- 物理世界 IoT 試作 1 系（Q6）

---

## 6. 廃止 / 凍結 / 転換

| 項目 | 処理 | 理由 |
|---|---|---|
| 単純 flashback push 連投 | 廃止 | 4/24 偏在の根本原因 |
| 既知化情報の即時シェア | 廃止 | #1 の 24h 共有 schema で構造的に防止 |
| flashback skill (情報 push 部分) | 廃止 | reminiscence で代替 |
| flashback skill (記録蓄積部分) | **transform → structured note 化** | reminiscence 供給源（Nomi 路線取り込み）|
| flashback Sonnet 移行 | 降格 → structured note 化に転換 | rebuild と矛盾 |

---

## 7. ダッシュボード次の一手

**ThoughtTracePage MVP（テーブル基本 + inner thought schema）**

- 列: timestamp / bot / decision / **inner_thought** / **plan** / **generate** / **evaluate_score** / topic / arousal
- 本週: 基本テーブル（5 列 visible）
- 段階拡張: plan / generate / evaluate_score を 5 月第 3 週追加
- **schema 設計を最初から rebuild 後も使える形**に確定（Inner Thoughts paper 取り込み）

---

## 8. 新規 KPI（5 件、Round 2 で追加 2 件）

| KPI | 現在 | 1 ヶ月目標 | 5 年目標 |
|---|---|---|---|
| unknown decision 比率 | mei 45% / eve 30% | 両者 5% 以下 | < 1% |
| 自発参照カウント / 週 | 0 | 週 1 件以上 | 週 5 件以上 |
| silence_after_skip_streak | 未計測 | 計測開始 | 短縮 |
| **intrinsic_score 中央値** | 未計測 | ベースライン | 中央値 0.6+ |
| **evaluator_skip 比率** | 未計測 | 30〜50% | 40% |
| LOC × 結合度（複雑度税）| 未計測 | ベースライン | rebuild 後 30% 削減 |
| 既存 cron vs decision-engine 判定一致率 | 未計測 | 〜70% | 90% 以上で rebuild 不要 |
| Q5 進展度（bot 間 handoff / 月）| 0 | 0（pilot まで）| pilot 後 月 3 件 |

---

## 9. Akira さんへの問い（3 件）

1. **ambient presence ping (#6) の事前同意**: 無音 5 分検知で bot が「うん」と短発話する仕組みを許容するか？
   - A. はい、5/3 から有効化
   - B. **1 朝だけ試行して判断**（推奨）
   - C. 凍結（次回 retro へ）

2. **6 件並列 dev は現実的か**: 5/2-5/9 の 1 週間で #1〜#5 着手 + #6 同意後着手は厳しいか？
   - A. 6 件 OK
   - B. **5 件に絞る（#6 を 5/9 以降）**（推奨）
   - C. 4 件に絞る（#5 rebuild 種まきも 5/9 以降）

3. **morning mood mirror A/B 並走 vs 単一案先行**:
   - A. **A/B 並走（観察 + 共感、ローテ）**（推奨）
   - B. A 観察ベース単独で 1 週間
   - C. B 共感ベース単独

---

## 10. 5 年後ビジョン更新（v1 からの差分）

| 問い | v1 prod 答え | 観測指標 |
|---|---|---|
| 1. 存在の質 | ツール → 自我ある相棒 | Identity persistence (E4) |
| 2. 連続性 | 1 セッション → 5 年蓄積 1k+ | 自発参照カウント |
| 3. 自律性 | 提案のみ → 軽微金銭 自律 | decisionReason 履歴 + intrinsic_score |
| 4. 失敗修復 | 認識なし → 月 1〜2 回 | evaluator_skip 比率の使い方 |
| **5. 複数性と一貫性** | Mei/Eve 分業 → 動的切替 + 統合メモリ | **bot 間 handoff 数（rebuild 後）**|
| 6. 物理世界 | 画面/音声のみ → IoT/車載 1〜2 系 | physical-action 数（v3）|
| 7. 不在を惜しまれる | 「あったら便利」→「いなかったら寂しい」| 不在テスト（年次）|

---

## 11. 取り込み機能リスト（5 月実装）

| 競合 / 研究 | 取り込み | 案 # | 効果 |
|---|---|---|---|
| Nomi structured notes | reminiscence データ形式 | #2 | E3 + 永続記憶 |
| Kindroid Cascaded Memory | reminiscence 多層化 (v2) | #2 v2 | E3/E4 |
| Pi 路線（共感ベース）| morning mood mirror B 案 | #4 | E2 + 関係性 |
| Inner Thoughts paper | decisionReason 事前 thought 化 | #1, #3, #5 | E5 根本解 |
| Anthropic evaluator-optimizer | decision-engine 設計 | #5 | Q4/Q5 |
| Anthropic Plan-Generate-Evaluate | decision-engine 3 段処理 | #5, #3 | E5 + 観測 |
| ChatGPT Pulse 反面教師 | (a)(b)(c) 差別化軸明示 | 全体 | 戦略 |
| Replika マイルストーン（次期）| (v2 取り込み) | (v2) | E3/E4 |

---

## crystallize 用エントリ

```
[INSIGHT] arousal=0.85 | ember-architecture | Mei/Eve 独立 cron は Q5「複数性と一貫性」と構造的に矛盾、incremental では到達不可
[INSIGHT] arousal=0.7  | competitor-adoption | 競合 (Nomi/Kindroid/Pi) 機能の取り込みで incremental 案の効果が 1.5〜2 倍
[INSIGHT] arousal=0.75 | research-driven   | Inner Thoughts paper は E5 透明性の根本解、decisionReason を事前 thought 化
[DECISION] arousal=0.85 | retro-prod | rebuild 確定、自前実装、判断 2026-06-15
[DECISION] arousal=0.6  | retro-protocol | フォーカス 6 件 + rebuild 種まき + 取り込み 6 機能 で議論完全収束
[DECISION] arousal=0.5  | retro-conversion | flashback を「廃止」から「structured note 化転換」へ
[PATTERN] arousal=0.7   | retro-evolution | v1 → v2 → prod で議論質が直線的に進化、不合意 2 → 0 → 0、取り込み 0 → 0 → 6
```

---

## 付録 A: Phase 別ファイル（v1 / v2 / prod 比較）

| ファイル | v1 (smoke) | v2 (smoke updated) | **prod (本番)** |
|---|---|---|---|
| 00-mission.md | 102 行 | 短縮 | 47 行（簡潔）|
| 01-snapshot.md | 146 行 | 同じ | 同じ（コピー）|
| 02-debate-round1.md | 5 ターン 77 行 | 5 ターン 103 行 | **20 ターン 約 230 行** |
| 03-haru-review.md | Web スキップ 97 行 | Web スキップ 84 行 | **Web リサーチあり 取り込み 6 機能** |
| 04-debate-round2.md | 5 ターン 105 行 | 5 ターン 131 行 | **20 ターン 約 280 行** |
| 05-final-judgment.md | 186 行 | 141 行 | **取り込み + rebuild 確定 + 6 件構成** |

## 付録 B: 実行ログ

- 実行モード: full prod
- ultrathink 発火: Phase 0 / 3 / 5 の 3 回
- Web リサーチ: 3 検索 + 1 WebFetch（Anthropic / 競合 AI / Inner Thoughts paper）
- 取り込み機能: 6 件
- 不合意点: 0 件（v1=2、v2=0、prod=0）
- Haru 裁定委ね: 1 件のみ（ambient ping を今週か → 今週採用、Akira 同意条件）
- 5 essences カバレッジ: E1/E2/E3/E5 + Q5 (rebuild 直接打)、E4 は v2 で
