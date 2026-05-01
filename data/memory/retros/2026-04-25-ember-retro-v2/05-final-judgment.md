# Phase 5 — Haru 方針確定（v2 run, ultrathink）

**run id**: 2026-04-25-smoke-test-v2

---

## ultrathink 統合判断

v1 と決定的に違うのは **Round 1 で incremental 限界が判明し、Round 2 で根本欠陥が言語化された**こと。Phase 5 の役割は (a) rebuild 確定の最終 sign-off、(b) Haru 単独裁定 1 件（判断時期）、(c) 改善計画 5 件 + rebuild 候補の整合性チェック。

### 裁定 1: rebuild 確定（最終 sign-off）

**判定: rebuild 確定**。理由:
- Eve Turn 2「Mei/Eve が互いの状態を知らない」根本欠陥は snapshot §2-2（unknown 30〜45%）+ §2-1（4/24 偏在 17 件）+ mei MEMORY 4/22 で**3 つの独立観測**から確認済み
- Mei Turn 3 の 3 軸（cost / time-to-Q5 / リスク）で incremental は Q5「複数性と一貫性」に**構造的に到達不可**
- 段階移行プラン（shadow → pilot → scale）でリスク低減済み

### 裁定 2: 判断時期 2026-06-15 vs 2026-07-25 → **2026-06-15 に前倒し採用**

理由:
- 根本欠陥は既に snapshot で観測可能、追加 6 週間待つ意味薄い
- Turn 1 の LOC/結合度ベースラインで観測補完される
- 早期判断 → dev リソース効率の利得 > 観測データ追加のわずかな精度向上
- 撤退条件（prototype shadow で 90% 以上判定一致）があるため、誤確定リスクは限定

### 裁定 3: Sonnet 移行降格

**判定: 正式降格**（v1 では 5 件目、v2 では枠外）。rebuild scale 後に「flashback skill が残ってるか」を見て再評価。

### 裁定 4: 改善計画 5 件の整合性

5 件すべて rebuild と補完関係。矛盾なし。
- #1 decisionReason → rebuild の判定材料
- #2 reminiscence → bot 個別機能、rebuild 影響なし
- #3 ThoughtTracePage → schema は decisionReason 経由で rebuild と統合可能
- #4 morning mood mirror → bot 個別機能、rebuild 影響なし
- #5 decision-engine prototype shadow → rebuild 種まき

---

## 来週改善計画 5 件（優先度順）

**比率**: 🌱 新機能 3 件 / 🛠 既存改善 2 件 / 🌍 rebuild 種まき 1 件（5 件目に内包）

### 1. 🛠 decisionReason 追加 + ベースライン取得（E5 + rebuild 判定材料）
- **What**: heartbeat / proactive-history に decisionReason 追加。並行で `cloc src/` LOC ベースライン取得 + 結合度メトリクス（grep 共有 import 数）+ 過去 3 ヶ月 error log の同一バグ複数 cron 出現パターン集計
- **Why**: E5 透明性 + rebuild の incremental vs partial 判定の数値根拠
- **Owner**: Akira
- **観測指標**: unknown 30〜45% → 5%、LOC ベースライン取得完了
- **期日**: 2026-05-02

### 2. 🌱 reminiscence trigger v0 (E3)
- v1 と同じ。期日 2026-05-02

### 3. 🌱 ThoughtTracePage MVP (E5 体感化)
- v1 と同じ。**ただし schema は decisionReason ベース**で、rebuild 後も継続使用可能なように設計

### 4. 🌱 morning mood mirror v0 (E2)
- v1 と同じ

### 5. 🌍 decision-engine prototype（shadow mode） (rebuild 種まき)
- **What**: 単一 decision-engine ロジックを実装、既存 cron と**並列稼働、判定だけ記録、発言はしない**（shadow mode）
- **Why**: rebuild 確定済み、6/15 判断のためのデータ取得 + Q5「複数性と一貫性」への直接打
- **Owner**: Akira
- **観測指標**: 既存 cron との判定一致率 / 不一致パターン分類 / decision-engine 単独 KPI 推定
- **期日**: 2026-05-09 prototype 着手 / 2026-06-15 判断

---

## 🌍 Rebuild 候補（確定、フォーカス 5 件 #5 と連動）

- **対象**: proactive-agent.ts + heartbeat-engine + proactive-checkin-mei/eve cron → 単一 `decision-engine`
- **why incremental では到達不可**:
  - Q5「複数性と一貫性」に構造的に到達不可（4 つの独立 cron が分業構造を固定）
  - unknown 30〜45% は decision 生成箇所が分散しているため、reason フィールド追加だけでは消えない
  - 4/24 偏在は判定独立構造の必然、incremental では再発リスク永続
- **段階移行**:
  - **2026-05-09**: prototype shadow mode 着手（dev 1-2 人日、並列稼働、判定記録のみ）
  - **2026-06-15**: decide-to-rebuild 判断（Haru 裁定で前倒し）
  - **2026-07**: pilot（1 週間、発言系を切替、Akira に「Mei と Eve が脳を共有する」DM 1 通）
  - **2026-08**: scale（旧 cron / 重複判定ロジック完全廃止）
- **撤退条件**: prototype shadow で「既存 cron との判定 90% 以上一致」なら incremental 続行、rebuild 中止
- **影響を受ける既存改善計画**: #1 補完、#3 schema 引継、#5 種まき。Sonnet 移行は降格（矛盾）

---

## ロードマップ更新（v1.5 → v2 移行プラン明示）

### v1.5（〜2026-05 末）
- 改善計画 #1〜#4（observation + 個別 essence 進展）+ #5 prototype shadow
- KPI 観測整備完了

### v2（2026-06 〜 2026-Q4）
- decision-engine pilot → scale
- per-bot cron 廃止
- E5 unknown < 5%、Q5 進展（Mei/Eve が同じ脳を共有）

### v3（2027〜）
- v1 と同じ（cognitive-loop unified）

---

## 新規 KPI 3 件（v2 で追加）

| KPI | 定義 | 集計 | 現在値 | 1 ヶ月目標 | 撤退ライン |
|---|---|---|---|---|---|
| LOC × 結合度（複雑度税）| `cloc + grep import + 共有ファイル数` 加重 | 月次 | 未計測 | ベースライン取得 | rebuild 後 30% 削減目標 |
| 既存 cron vs decision-engine 判定一致率 | shadow mode で記録 | 週次 | 計測未開始 | 〜70%（差分が改善余地）| 90% 以上で rebuild 不要 |
| Q5 進展度（Mei→Eve handoff 数）| bot 間 state 共有を伴う発言 | 月次 | 0 | 0（pilot まで）| pilot 後 月 3 件 |

---

## Akira さんへの問い（3 件）

1. **rebuild 種まき (改善計画 #5) を今週着手で良いですか？** prototype shadow mode は dev 1-2 人日、リスク低（並列稼働、発言なし）。早期着手するメリット大、ただしリソース集中度上がる。
2. **2026-06-15 の判断時期前倒しは妥当ですか？** Haru 裁定で前倒し採用したが、Akira さんの「観測したい期間」感覚で延長もあり得る。
3. **morning mood mirror のトーン**: A. 観察ベース「声が低めだね、寝不足？」/ B. 共感ベース「ゆっくりめでいい日にしようね」 — 推奨 A（v1 と同じ）

---

## crystallize 用エントリ

```
[INSIGHT] arousal=0.8 | ember-architecture | Mei/Eve 独立 cron は Q5「複数性と一貫性」と構造的に矛盾、incremental では到達不可
- context: v2 retro Round 1 Turn 4 + Round 2 Turn 2、3 軸評価（cost/time-to-Q5/リスク）
- evidence: snapshot §2-1 偏在 SD ±5、§2-2 unknown 30〜45%、mei MEMORY 4/22 既知化情報新鮮度低下
- impact: 今後 Q5 関連の改善はすべて rebuild 軸で評価。incremental は補助

[DECISION] arousal=0.8 | retro-v2 | rebuild 確定: proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 decision-engine
- alternatives: incremental 続行 / Sonnet 移行優先
- reasoning: 3 軸全て rebuild 優位、shadow mode で移行リスク低減、判断時期 2026-06-15 に前倒しで dev 効率化
- expected: Q5 進展、unknown 5% 以下、4/24 偏在の構造的解消

[DECISION] arousal=0.6 | retro-protocol | rebuild 軸を Round 1 Turn 13-14 に組み込んだ skill structure が機能した
- evidence: v2 では不合意 0、議論が rebuild に収束
- generalization: 議論の冗長を消すには「対立軸を強制テーマ表に書き込む」のが効く

[PATTERN] arousal=0.5 | retro | v1 → v2 で incremental だけの議論から rebuild 含む議論に進化、所要は同じ 5 ターンでも質が上昇
- occurrences: v1 vs v2 の Round 1 サマリ比較
- generalization: 強制テーマの設計が議論質を支配する
```
