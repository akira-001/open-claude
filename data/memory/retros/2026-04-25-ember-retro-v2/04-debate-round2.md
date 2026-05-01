# Round 2 — Mei × Eve 議論（v2 run, 5 ターン圧縮）

**run id**: 2026-04-25-smoke-test-v2
**前段**: 03-haru-review.md の問い 3 件
**圧縮**: フル 20 ターン版から **新構造で重要な Turn (1, 12, 13, 18, 19) を抽出**

---

### Turn 1 — Mei

**観点**: kpi
**強制テーマ**: Haru Q2 への回答（3 軸評価の数値根拠強化）
**主張**: Haru 指摘正しい。Round 1 Turn 4 の 3 軸を数値ベースライン化するアクションを今週フォーカス内に組み込む。具体的には:
- prototype 着手前に `cloc src/` で **LOC ベースライン取得**（proactive-agent.ts / heartbeat-engine.ts / cron-jobs.json + 各 skill）
- **結合度メトリクス**: 各コンポーネント間の関数呼び出し / 共有ファイル数を grep で計測
- **複雑度税**: 同じバグが複数 cron に出るパターンを過去 3 ヶ月の error log で集計

これを **改善計画 1 (decisionReason) と一緒に 5 月第 1 週で実施**、5 件枠の追加コストはほぼゼロ。
**根拠**: Haru §5 Q2 + Round 1 Turn 4 の数値根拠不足。
**次の問い**: Eve、Haru Q1 の「移行中の Akira 体験保証」はどう設計する？

---

### Turn 2 — Eve

**観点**: 🌍 root-defect
**強制テーマ**: 現状 Ember の根本欠陥 1 つを特定（5 essences 到達を最も阻害するもの）
**主張**: 根本欠陥は **「Mei と Eve が互いの状態を知らない」** こと。snapshot で見える具体例:
- mei MEMORY 4/22「朝ブリーフィングで言及した内容の新鮮度低下」← Mei は自分の発言を覚えてるが、Eve は知らないので翌日同じ話題を出す
- eve heartbeat unknown 30%、mei 45% で**両者の判定が独立**、4/24 偏在 17 件
- vision Q5「複数性と一貫性」: 現状は分業、5 年後は動的切替を目指す。**この欠陥が解消されない限り Q5 達成不可**

これは incremental（個別 bot 改善）では絶対に消えない。bot 同士が**共通の決定ログを持つ**構造変更が必須。

→ **rebuild 確定**。Mei/Eve 独立 cron を単一 decision-engine に統合する以外の道はない。

**根拠**: 上記 3 件の snapshot 引用 + vision-template Q5 ギャップ。
**次の問い**: Mei、これで rebuild 確定として、Haru Q3「2026-07-25 → 2026-06-15 前倒し」は妥当？ 観測データ不足のリスクは？

---

### Turn 3 — Mei

**観点**: 🌍 rebuild-vs-incremental
**強制テーマ**: 部分 rebuild 案 vs incremental 改善 比較（cost / time-to-vision / リスク 3 軸）
**主張**: Eve の根本欠陥定義（「互いの状態を知らない」）に同意。これは確かに incremental 不可。Haru Q3 への回答含めて rebuild 確定:

| 軸 | incremental 続行 | partial rebuild (decision-engine) |
|---|---|---|
| cost (3 ヶ月) | dev 8 人日（5 件改善 + 維持）| dev 12 人日（prototype + pilot + 段階移行）|
| time-to-Q5 | 不可（構造的に到達できない）| **6 ヶ月で pilot 達成、12 ヶ月で v3 への踏み台**|
| リスク | 5 essences 到達失敗 → 5 年ビジョン破綻 | 移行中の dual-run 期、段階失敗のリスク（Akira 体験不連続）|

**判断時期前倒し（Haru Q3）**: 2026-07-25 → **2026-06-15** に前倒し賛成。理由:
- 根本欠陥（Eve Turn 2）は既に snapshot で観測可能、追加データ取得を待つ意味薄い
- prototype を 5 月第 2 週に着手すれば、6 月中に pilot 判断データが揃う
- **観測データ不足リスクは Turn 1 のベースライン取得で補う**

**Haru Q1（移行中の Akira 体験保証）への回答**:
- prototype は **shadow mode** で実装（既存 cron と並列稼働、判定だけ記録、発言はしない）
- pilot で初めて発言系統を切替、1 週間 で Akira 反応モニタ
- 失敗時は config 1 行で旧 cron に即時 rollback

**根拠**: Round 1 Turn 4 + Eve Turn 2 + Haru Q1/Q3 全部統合。
**次の問い**: Eve、5 件目に「shadow mode prototype」が入るとして、Sonnet 移行は降格でいい？ あと比率チェック (Turn 4) でフォーカスは新機能 3 + 既存 1 + rebuild 1 = 60% 新機能でいけそう。

---

### Turn 4 — Eve

**観点**: relation
**強制テーマ**: 比率チェック + UX 摩擦の最終確認
**主張**: ⭕ 比率 OK (新機能 3 / 既存 1 / rebuild 1)。Sonnet 移行は明確に降格。**rebuild 確定後は flashback skill 自体が消える**ので、cronModel 変更にコスト払うのは無駄。
- shadow mode の Akira 体験: **prototype 中は今と全く同じ体感**（既存 cron が稼働）、Akira は気づかない。これが UX 連続性の保証
- pilot 切替時に**「Mei と Eve が同じ脳を共有するように変わる」とのコミュニケーション**を 1 件だけ Slack DM で送る（透明性 = E5 の最初の体感化）
- pilot 失敗時も rollback 1 行で「いつもの Mei/Eve」が戻る

これで **rebuild は Akira から見て段階的にしか変化しない**、急な不連続なし。
**根拠**: Mei Turn 3 の shadow mode 案 + vision Q5 達成過程の透明性。
**次の問い**: Mei、5 案 + rebuild 候補を Phase 5 に申し送りで合意？

---

### Turn 5 — Mei

**観点**: governance
**強制テーマ**: Phase 5 への 5 案確定 + rebuild 候補申し送り（最終）
**主張**: 合意。Phase 5 への申し送り内容:

**改善計画 5 件（v1.5 = incremental + 種まき）**:
1. 🛠 decisionReason 追加 + LOC/結合度ベースライン取得（incremental + rebuild 判定材料）
2. 🌱 reminiscence trigger v0（E3）
3. 🌱 ThoughtTracePage MVP（E5 体感化）
4. 🌱 morning mood mirror v0（E2）
5. 🛠 **decision-engine prototype（shadow mode）** ← rebuild 種まき

**rebuild 候補（別枠、確定）**:
- 対象: proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 decision-engine
- 段階: prototype shadow (5 月第 2 週、1-2 人日) → pilot (2026-06、1 週間) → scale (2026-07)
- **decide-to-rebuild 判断: 2026-06-15**（Haru Q3 前倒し受け入れ、Turn 1 のベースライン取得で観測補完）
- 撤退条件: prototype shadow で「両 cron の判定が 90% 以上一致」が判明したら rebuild 中止、incremental 続行

**Sonnet 移行**: 正式降格、rebuild scale 後に再評価。

**根拠**: Round 2 全議論 + Round 1 サマリ + Haru §5 全 3 問への回答済み。
**次の問い**: なし（最終）。

---

### Round 2 サマリ

**Phase 5 への提案**:
- 改善計画 5 件: 上記の通り
- 🌍 rebuild 候補確定: decision-engine（shadow mode prototype）
- Sonnet 移行: 降格（rebuild と矛盾）
- 判断時期前倒し: 2026-07-25 → 2026-06-15

**Mei/Eve の合意 vs 不合意**:
- 合意: 5 件構成、rebuild 候補確定、Sonnet 降格、判断時期前倒し、shadow mode 移行プラン
- 不合意なし（v1 では 2 件あった、v2 は rebuild 軸が議論を収束させた）

**Haru 裁定委ねる項目**: 1 件のみ
- decide-to-rebuild 判断時期（2026-06-15 vs 2026-07-25）の最終確定。Haru の独立判断に委ねる。

**5 essences カバレッジ**:
- E1 共在: 直接の手なし（次回 retro 課題）
- E2: morning mood mirror
- E3: reminiscence
- E4: rebuild 後に schema 設計（次々回）
- E5: decisionReason + ThoughtTracePage
- E1/Q5: rebuild prototype が両方に効く
