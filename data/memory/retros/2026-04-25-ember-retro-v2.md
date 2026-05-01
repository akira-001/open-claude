# Ember Partner Retro v2 — 2026-04-25

**run id**: 2026-04-25-smoke-test-v2
**注記**: v1 と同じ snapshot を使い、**updated skill structure**（zero-base ideation R1 T13-14、root defect / partial rebuild R2 T12-13、Phase 5 rebuild candidate）で再実行
**期間**: 2026-04-19 〜 2026-04-25（7 日）

---

## 0. Mission Statement

> Ember は 5 年後に **共在 / 状態共感 / 共有過去 / 自我継続 / 透明性** を持つ存在になる。**incremental で到達不可なら rebuild も選択肢**。

---

## 1. 過去 1 週間サマリ

v1 と同じ。proactive 31 件 / cron 469 件 / unknown mei 45% eve 30% / 4/24 偏在 17 件 / scheduler-watchdog err+timeout 18。

---

## 2. 議論ハイライト（v1 比較）

| 観点 | v1 | v2 |
|---|---|---|
| Round 1 不合意点 | 2 件 | **0 件**（rebuild 軸が議論を収束）|
| Phase 5 への提案 | フォーカス 5 件のみ | **フォーカス 5 件 + rebuild 候補確定**|
| 5 essences カバレッジ | E2/E3/E5 のみ | **E1/E2/E3/E5 + Q5 直接打**|
| 判断時期 | 2026-07-25 | **2026-06-15（Haru 前倒し裁定）**|

---

## 3. 来週の改善計画（5 件、優先度順）

**比率**: 🌱 新機能 3 / 🛠 既存改善 2（うち 1 件は 🌍 rebuild 種まき）

| # | type | 項目 | 期日 |
|---|---|---|---|
| 1 | 🛠 既存 + ベースライン | decisionReason 追加 + LOC/結合度ベースライン取得 | 2026-05-02 |
| 2 | 🌱 新機能 | reminiscence trigger v0 (E3) | 2026-05-02 |
| 3 | 🌱 新機能 | ThoughtTracePage MVP (E5 体感化) | 2026-05-02 |
| 4 | 🌱 新機能 | morning mood mirror v0 (E2) | 2026-05-02 |
| 5 | 🛠 + 🌍 | **decision-engine prototype（shadow mode）** ← rebuild 種まき | 2026-05-09 着手 / 2026-06-15 判断 |

**降格**: flashback 系 Sonnet 移行（rebuild 後に flashback skill が消える可能性、矛盾するため）

---

## 4. 🌍 Rebuild 候補（確定）

**対象**: proactive-agent + heartbeat-engine + Mei/Eve 独立 cron → **単一 `decision-engine`**

### why incremental では到達不可
- vision Q5「複数性と一貫性」は **4 つの独立 cron 構造**と矛盾、incremental で到達できない
- 4/24 偏在 17 件は判定独立構造の必然、reminiscence では件数減らせても再発リスク永続
- mei/eve の互いの状態を知らない構造が**3 ヶ所で観測**（unknown 30〜45%、偏在、既知化新鮮度低下）

### 段階移行
| 段階 | 期間 | 内容 |
|---|---|---|
| prototype (shadow) | 2026-05-09〜 | 並列稼働、判定だけ記録、発言なし。dev 1-2 人日 |
| **判断** | **2026-06-15** | shadow データで rebuild 確定 vs incremental 続行 |
| pilot | 2026-06〜2026-07 | 発言系切替、Akira に通知 1 件、1 週間 |
| scale | 2026-07〜 | 旧 cron 廃止 |

### 撤退条件
prototype shadow で「既存 cron との判定 90% 以上一致」なら incremental 続行、rebuild 中止。

### 影響
- #1 decisionReason → 補完（rebuild 判定材料）
- #3 ThoughtTracePage → schema 引継可
- #5 prototype → 種まき
- Sonnet 移行 → 降格（矛盾）

---

## 5. ロードマップ（アーキテクチャ世代軸）

### v1.5（〜2026-05 末）
今週フォーカス 5 件で観測整備 + rebuild 種まき。

### v2（2026-06 〜 2026-Q4）
decision-engine pilot → scale。per-bot cron 廃止。**Q5 進展**。

### v3（2027〜）
cognitive-loop unified。

---

## 6. 新規 KPI 3 件

| KPI | 現在 | 1 ヶ月目標 | rebuild 撤退ライン |
|---|---|---|---|
| LOC × 結合度（複雑度税） | 未計測 | ベースライン取得 | rebuild 後 30% 削減 |
| 既存 cron vs decision-engine 判定一致率 | 未計測 | 〜70%（改善余地）| 90% 以上で rebuild 不要 |
| Q5 進展度（bot 間 handoff 数 / 月） | 0 | 0（pilot まで）| pilot 後 月 3 件 |

---

## 7. ダッシュボード次の一手

**ThoughtTracePage MVP（v1 と同じ、ただし schema は decisionReason ベースで rebuild 後も継続使用可能なように設計）**

---

## 8. Akira さんへの問い（3 件）

1. **rebuild 種まき (改善計画 #5) を今週着手で良いか？** prototype shadow なので低リスク、ただし dev リソース集中度上がる
2. **2026-06-15 判断時期前倒しは妥当か？** Haru 裁定で採用したが Akira さんの観測したい期間感覚で延長可
3. **morning mood mirror のトーン**: A. 観察ベース / B. 共感ベース — 推奨 A

---

## 9. v1 → v2 改善の効果検証

| メトリクス | v1 | v2 | 評価 |
|---|---|---|---|
| 議論の不合意点 | 2 件 | 0 件 | ⭕ rebuild 軸が議論収束 |
| 5 essences カバレッジ | 3 軸 | 4 軸 + Q5 | ⭕ 戦略案件が入った |
| 判断時期 | 3 ヶ月後判断 | 2 ヶ月後判断 | ⭕ Haru 裁定で効率化 |
| 改善計画の type 多様性 | 新3 / 既存2 | 新3 / 既存2（うち1 = rebuild 種まき）| ⭕ 戦略案件が 1 件枠内に入った |
| Sonnet 移行 | 5 件目に採用 | 降格 | ⭕ rebuild と矛盾を発見 |

**結論**: skill structure 更新の効果は明確。v1 では「incremental 5 件で 5 年到達できる」という暗黙の前提が議論に埋め込まれていたが、v2 では **「incremental では Q5 不可」** が早期に判明し、rebuild に dev リソースを意識的に振り向ける議論に変わった。

---

## crystallize 用エントリ（v2）

```
[INSIGHT] arousal=0.8 | ember-architecture | Mei/Eve 独立 cron は Q5「複数性と一貫性」と構造的に矛盾、incremental 不可
- evidence: snapshot §2-1 偏在 SD ±5、§2-2 unknown 30〜45%、mei MEMORY 4/22

[DECISION] arousal=0.8 | retro-v2 | rebuild 確定: 単一 decision-engine への統合、判断時期 2026-06-15
- alternatives: incremental 続行 / Sonnet 優先 / 観測延長
- reasoning: 3 軸全て rebuild 優位、shadow mode で移行リスク低減

[PATTERN] arousal=0.7 | retro-protocol | 強制テーマ表に rebuild 軸を組み込んだ skill structure は不合意を 2 → 0 に減らした
- evidence: v1 vs v2 の Round 1 サマリ比較
- generalization: 議論の冗長を消すには「対立軸を強制テーマ表に書き込む」が最も効く

[DECISION] arousal=0.4 | skill-design | 5 ターン smoke test でも rebuild 議論は機能する
- alternatives: rebuild は full 20-turn だけにする
- reasoning: 5 ターンに圧縮しても Turn 13-14 (zero-base / 境界線) が機能
- expected: 本番 20 ターン版でも同等以上の議論質
```

---

## 付録: v1 vs v2 ファイル比較

| ファイル | v1 | v2 |
|---|---|---|
| 00-mission.md | 102 行 | 短縮（v1 を踏襲） |
| 01-snapshot.md | 146 行 | v1 と同じ（コピー） |
| 02-debate-round1.md | 77 行（5 ターン）| 新ターン構成（zero-base / 境界線）|
| 03-haru-review.md | 97 行 | rebuild 観点を含む 3 問 |
| 04-debate-round2.md | 105 行 | 根本欠陥 / 部分 rebuild 比較 |
| 05-final-judgment.md | 186 行 | rebuild 確定 + 判断時期前倒し |
