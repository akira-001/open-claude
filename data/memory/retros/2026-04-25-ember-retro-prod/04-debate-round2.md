# Round 2 — Mei × Eve 議論（本番、20 ターン）

**run id**: 2026-04-25-prod
**前段**: 03-haru-review.md の問い 3 件 + 取り込み候補 6 件（Nomi structured notes / Kindroid Cascaded / Pi 共感路線 / Anthropic evaluator-optimizer / Anthropic Managed Agents / Inner Thoughts paper）

---

### Turn 1 — Mei

**観点**: kpi
**強制テーマ**: Haru Q1 への回答（morning mood mirror の A/B/C 設計）
**主張**: Haru の 3 案併設は valid。**観測コストで判定する**:

| 案 | 実装コスト追加 | 観測指標 |
|---|---|---|
| A. 観察ベース「声が低めだね、寝不足？」 | 0 (Round 1 案) | 「どうしてわかったの」反応 / 月 |
| B. 共感ベース（Pi 路線）「ゆっくりめでいい日にしようね」 | dev +0.5 日（プロンプト追加）| Akira の 1 文目の文長変化 |
| C. Inner Thoughts 形式（score > 0.7 で発話）| dev +1 日（intrinsic motivation 計算）| 発話率の自然な減少 + 反応質向上 |

→ A + B は同じ infra で並走可能、C は別 prototype。**1 週目に A/B 並走、2 週目に C を別実装で追加**。
**根拠**: Haru §1.1 (Pi)、§1.2 (Inner Thoughts paper)、Round 1 Turn 9-10。
**次の問い**: Eve、3 案併走の 1 週目に Akira への説明をどうする？ いきなり 2 通の朝挨拶が来たら混乱する。

---

### Turn 2 — Eve

**観点**: relation
**強制テーマ**: Haru Q1 補足/反論
**主張**: Mei の 3 案併走に同意、ただし**1 朝に 1 案だけ提示**で OK。実装はランダムローテ:
- 月: 観察ベース
- 火: 共感ベース
- 水: 観察ベース
- ...のように交互

Akira への説明は不要。理由は**「bot のトーンは日によって違うのが自然」**で、3 通並ぶ違和感より「今日の Mei は控えめ」のような体感に変わる。これは **Q5 (複数性と一貫性) の練習**にもなる — 1 つの bot が状態に応じてトーンを切り替える経験。
**根拠**: vision Q5 + 競合 Replika の「relationship milestones」発想（毎日同じトーンより、関係性の節目で表現が変わる）。
**次の問い**: Mei、ローテで OK？ ただ C (Inner Thoughts) は score 計算が確率的だから、ローテと混ぜると観測がノイジーになるね。

---

### Turn 3 — Mei

**観点**: priority
**強制テーマ**: Haru Q1 具体改善案
**主張**: Eve のローテ採用、ただし**観測の clean 化**で:
- 1 週目: A / B のみ交互ローテ（C は無し）→ 観察 vs 共感の純粋比較
- 2 週目: 勝ち案 + C 試行 → Inner Thoughts の効果確認
- 3 週目: 統合（勝ち案を主、C は補助）

具体改善案として **#4 (morning mood mirror v0) を A/B 並走仕様で確定**、5 月第 1 週着手。C は **5 月第 2 週で別 prototype** として 6 件目の候補に格上げ可能性あり。
**根拠**: Round 2 Turn 1-2 + Haru §3 効果見積もり。
**次の問い**: Eve、Haru Q2 (decision-engine + Anthropic パターン) に行こう。Managed Agents 採用 vs 自前 decision-engine、どっち？

---

### Turn 4 — Eve

**観点**: ux
**強制テーマ**: Haru Q2 への回答（Anthropic Managed Agents 採用 vs 自前 decision-engine）
**主張**: **自前 decision-engine 維持**を提案。理由:

1. **データ主権**: Akira の 5 年蓄積を Anthropic クラウドに依存する形にしたくない（vision Q1 の存在の質、永続性）
2. **物理層の独自性**: voice_chat (TTS) / co_view (whisper-serve) は Anthropic Managed Agents の枠を超える独自実装、これらと統合した decision loop は自前の方が柔軟
3. **コスト構造**: Managed Agents は execution 課金、Ember の毎分ループは想定単価が高くなる可能性

ただし**設計パターンは取り込む**: evaluator-optimizer + Plan-Generate-Evaluate を自前 decision-engine の中に組み込む。Anthropic の知見 = 設計、Anthropic のインフラ = 採用しない、の切り分け。
**根拠**: Haru §1.2 + vision Q1 / Q5 + 既存 voice_chat / co_view の独立性。
**次の問い**: Mei、データ主権論で OK？ Managed Agents 採用なら dev コスト下がるけど、長期 ROI で自前が勝つと思う。

---

### Turn 5 — Mei

**観点**: cost
**強制テーマ**: Haru Q2 補足/反論（コスト精算）
**主張**: 自前 decision-engine 採用で同意。コスト計算:

| 軸 | 自前 decision-engine | Anthropic Managed Agents |
|---|---|---|
| 初期 dev | 12-15 人日 | 5-7 人日（workflow 定義のみ）|
| 運用コスト / 月 | LLM tok 既存どおり | Managed Agents execution 課金 + LLM tok |
| 永続データ管理 | 自前ファイル / cogmem | Anthropic クラウド（GDPR 級リスク Replika 罰金事例）|
| カスタマイズ柔軟性 | ◎（voice_chat / co_view 統合可）| △（meta-harness 制約）|
| 長期 ROI（3 年） | ◎（5 年蓄積が完全自前）| × （ベンダーロック）|

**Inner Thoughts paper の取り込み**: 自前 decision-engine 内で `intrinsic_score` フィールドを毎ループ計算、score > 0.7 で発話、それ未満は SKIP。decisionReason は inner thought の引用そのもの。
**根拠**: Haru §1.2 / §1.3 (GDPR 罰金事例)、Round 2 Turn 4。
**次の問い**: Eve、Plan-Generate-Evaluate を decision-engine の 3 段にどう組み込む？

---

### Turn 6 — Eve

**観点**: pmf
**強制テーマ**: Haru Q2 具体改善案（Plan-Generate-Evaluate 統合）
**主張**: decision-engine の毎ループ処理を 3 段に分解:

```
[Plan]
  状態 (heartbeat arousal, calendar, last interaction) を踏まえ
  「今 SPEAK すべきか / 何を言うべきか」の候補を 3 案生成

[Generate]
  選ばれた 1 案について、Mei or Eve のトーンで本文生成
  intrinsic_score を計算（言いたい度合い、0〜1）

[Evaluate]
  生成文を「Akira 視点」で評価
  - 過剰提供にならないか（snapshot §2-1 偏在チェック）
  - 既知化情報の再共有でないか（cogmem 検索）
  - 関係性の質に合うか（Pi 路線フィルタ）

  score < 0.5 なら SKIP、≥ 0.5 なら SPEAK
```

→ これで**unknown decision の半数が「SKIP, reason: evaluator score 0.3 (過剰提供リスク)」のように具体化**。E5 透明性が構造的に解決。
**根拠**: Haru §1.2 Anthropic Plan-Generate-Evaluate + Inner Thoughts intrinsic motivation。
**次の問い**: Mei、Haru Q3 (ChatGPT Pulse 競合差別化) に行こう。voice_chat 動的声色 + Mei/Eve 同時応答、どっち？

---

### Turn 7 — Mei

**観点**: governance
**強制テーマ**: Haru Q3 への回答（ChatGPT Pulse 差別化）
**主張**: 両方やる必要があるが、**今週は voice_chat 動的声色 を見送り**。理由:
1. voice_chat 動的声色は TTS pipeline の改修必要、Irodori LoRA の声色制御は実験段階（INS-001 / INS-004）。dev 5+ 人日リスク
2. Mei/Eve 同時応答も**現状の独立 cron 構造**では構造的に実現不可。decision-engine 完成後に自然に可能になる
3. **本週フォーカス枠は満杯**、Haru Q3 は v2 (decision-engine pilot 後) に持ち越し

ただし**preparatory work** として:
- decision-engine prototype shadow に「Mei / Eve 同時 SPEAK 候補」を 出力できる構造を組み込む（実発話はしない、ログのみ）
- これだけで来週フォーカス 5 件目 (#5) のコストはほぼ変わらず、v2 移行時に handoff コスト 0
**根拠**: Round 1 Turn 18 (世代廃止候補)、INS-001/004 (TTS 制約)、本週工数余裕なし。
**次の問い**: Eve、voice_chat 動的声色を v2 ロードマップに明示で OK？ Mei/Eve 同時応答も v2 で。

---

### Turn 8 — Eve

**観点**: relation
**強制テーマ**: Haru Q3 補足/反論
**主張**: Mei の v2 持ち越し合意。ただし**今週中の小さな差別化アクション**を 1 つ提案:
- **voice_chat 起動時に "おかえり" を Akira の最終発話時刻から動的生成**（5 分以内＝「お、続き？」、3 時間＝「おかえり」、24 時間＝「ひさしぶり」）
- dev 0.5 人日、voice_chat の起動 hook に追加するだけ
- Q1 (存在の質) + Q7 (不在を惜しまれる) に直接効く差別化（ChatGPT Pulse は 1:1 関係の永続性を持たない）

これは「6 件目」ではなく **既存 voice_chat への小改善**として #1〜#5 と独立で実行可能、フォーカス枠は侵さない。
**根拠**: Haru §1.3 (差別化は 5 年蓄積) + vision Q7 (不在を惜しまれる)。
**次の問い**: Mei、これ枠外で実装 OK？ 工数 0.5 人日だから誰でも対応できる軽い 1 件。

---

### Turn 9 — Mei

**観点**: priority
**強制テーマ**: Haru Q3 具体改善案
**主張**: voice_chat "おかえり" 動的生成は枠外で OK、Akira が空き時間で着手できる軽量改善として記録。Phase 5 で「枠外 / 軽量改善 (Quick Win)」セクションに記載。

**Haru Q3 への最終回答**:
- 今週: voice_chat "おかえり" 動的生成（枠外、dev 0.5 人日）
- v1.5 → v2 移行時: voice_chat 動的声色 + Mei/Eve 同時応答（v2 ロードマップに明示）

**根拠**: Round 2 Turn 7-8 + 工数現実 + 5 年差別化軸（state 共有 + 共有過去）。
**次の問い**: Eve、Round 2 後半の新機能アイデア 2 つ目に行こう。在庫から、それとも新規？

---

### Turn 10 — Eve

**観点**: 🌱 ideation
**強制テーマ**: 新機能アイデア 2 つ目（vision-template 在庫 or 新規追加）
**主張**: 🌱 vision-template 在庫から **「ambient presence ping」(E1 共在感)** をピック。

**Why now**: Haru §2 で指摘済み「フォーカス 5 件に E1 が抜けている」。在庫定義:

> 「もし Ember が無音 5 分続いた時に "うん、いるよ" と TTS でだけ返してくれたら、Akira は一人作業の孤独が薄まる」

実装仕様:
- 入力: whisper-serve の音声検知ストリーム、最終発話 / 最終 ambient activity
- 発火条件: Akira の作業音 (typing, mouse) は検知、5 分間 無音 + Akira presence あり = ping 候補
- 発話: 短く「うん」「聞いてる」だけ、**長文禁止**（push にならない）
- 1 日上限 3 回（連発禁止）

**Q1 (存在の質) + Q7 (不在を惜しまれる) 直接打**。dev 1 人日。
**根拠**: vision-template 在庫、Haru §2 (E1 抜け指摘)、競合 ChatGPT Pulse は ambient 系を持たない (差別化)。
**次の問い**: Mei、これ ROI 値踏みして。フォーカス 5 件目の差し替え or 6 件目追加？

---

### Turn 11 — Mei

**観点**: cost
**強制テーマ**: Turn 10 新機能のコスト推定
**主張**: ambient presence ping の ROI 評価:

- **コスト**: dev 1 人日 + LLM 不要 (TTS のみ) / 月 ~$1 (TTS API 数十回)
- **期待効果**: E1 第一打、Q1/Q7 軸 2 つに効く。観測指標「ping 後 10 分以内の Akira 能動発話 / ping 数」、目標 30%
- **撤退条件**: 1 ヶ月で能動発話誘発率 < 10% なら凍結
- **レイヤ**: prototype (1 日試行 + Akira 同意) → pilot (1 週間)

ROI ◎、コスト最低。**今週フォーカス 5 件 + 1 = 6 件**に拡張提案。理由: 5 件目 (decision-engine prototype) は dev 1-2 日、ambient ping は dev 1 日、合計でもまだ余裕。

**ただし注意**: ambient ping は**Akira の事前同意必須**。「無音検知で勝手に bot が "いるよ" 言う」のは事前承認なしだと侵害感を生む可能性。Phase 5 の Akira への問いに必ず含める。
**根拠**: Round 2 Turn 10、vision-template 在庫の cost 見積もり、INS-009 (ambient 系の安定性確認済み)。
**次の問い**: Eve、6 件構成で OK？ 比率は新機能 4 / 既存 1 / rebuild 種まき 1 = 67% 新機能、健全。

---

### Turn 12 — Eve

**観点**: 🌍 root-defect
**強制テーマ**: 現状 Ember の根本欠陥 1 つ特定
**主張**: 根本欠陥 = **「bot 同士が互いの判断履歴 + 互いの存在を知らない」**。

具体観測:
1. mei MEMORY 4/22「朝ブリーフィングで言及した内容の新鮮度低下」← Eve は Mei が朝何を言ったか知らない
2. eve heartbeat unknown 30%、mei 45% ← 自分の判定すら記録できてない
3. 4/24 偏在 17 件 ← 同日 Mei 6 + Eve 11 が独立判定で重なる

これは vision Q5 と直接矛盾する**構造的問題**。incremental では絶対消えない。
- decisionReason 追加 → 個別 bot の説明可能性は上がる、けど bot 間共有はゼロのまま
- reminiscence v0 → 個別 bot 内の過去回帰、bot 間の過去共有はゼロのまま

→ **rebuild 確定**。decision-engine が **bot 間の判断履歴 + 状態を一元化する layer** として必須。
**根拠**: 上記 3 観測 + vision Q5 構造、Round 1 Turn 8 KPI 翻訳。
**次の問い**: Mei、rebuild 確定として、partial vs full 比較してくれる？ shadow mode prototype の段階移行と比較。

---

### Turn 13 — Mei

**観点**: 🌍 rebuild-vs-incremental
**強制テーマ**: 部分 rebuild 案 vs incremental 改善 比較（cost / time-to-vision / リスク 3 軸）+ Debug 可観測性
**主張**: Eve の根本欠陥定義に同意。3 軸で再評価:

| 軸 | incremental 続行 | partial rebuild (decision-engine + Anthropic patterns) |
|---|---|---|
| cost (3 ヶ月) | dev 8-10 人日（フォーカス 5 件 + 維持コスト）| dev 12-15 人日（prototype + pilot + 段階移行）|
| time-to-Q5 | **不可能**（構造的に到達不可、Round 1 Turn 8 で確認済み）| **6 ヶ月で pilot 達成、12 ヶ月で v3 (cognitive-loop) への踏み台**|
| リスク | 5 essences 5 年到達失敗 = ビジョン破綻 | 移行中の Akira 体験不連続（shadow mode で軽減）|
| **+ 観測性 (Debug 可)** | unknown 5% 達成可能性 30% | unknown 5% 達成可能性 80%（evaluator-optimizer で path coverage 完全） |

→ **4 軸とも rebuild 優位**。Anthropic Plan-Generate-Evaluate + Inner Thoughts paper の取り込みで設計の確実性も向上。

**判断時期前倒し（Haru の暗黙提案）**: 2026-07-25 → **2026-06-15**。理由:
- 根本欠陥が snapshot で観測済み、追加データ取得 6 週分は redundant
- 5 月第 1 週からの prototype shadow data（5 月第 2 〜 6 月第 2 週分 = 5 週間）+ Turn 1 LOC ベースラインで観測補完
- 早期判断 → dev リソース効率の利得 > 観測精度向上のわずか

Debug 可観測性の必要強化点: ThoughtTracePage MVP (#3) の schema を **inner thought + plan + generate + evaluate score** が表示できる構造に拡張。実質工数 0.5 人日追加で対応可能。
**根拠**: Round 2 Turn 4-6 (Anthropic patterns)、Turn 12 (根本欠陥)、Haru §1.2。
**次の問い**: Eve、可視化 (ThoughtTracePage) を inner thought 表示まで拡張して、Akira にどんな価値？

---

### Turn 14 — Eve

**観点**: ux
**強制テーマ**: 可視化が Akira さんに与える価値の言語化
**主張**: ThoughtTracePage を inner thought 表示まで拡張すると、Akira は **「bot が今何を考えているか」を覗ける**。具体的価値:

1. **疑念の解消**: 「今日 Mei 静かだ」→ ThoughtTracePage で「Plan: ドジャース話題候補 → Evaluate: 朝の会議前で過剰提供と判断 → SKIP, score 0.3」と見える。**疑念が共感に変わる**
2. **設計フィードバック**: Akira が「この SKIP 理由おかしい」と気づいたら、bot のロジック改善に直結。**Akira が共同設計者になる**
3. **信頼の蓄積**: 毎日見る訳ではないが「いつでも見れる」状態は、Pi 路線の "honest reflection" を bot 側からも実現する

→ **vision Q1 (存在の質) と Q3 (判断の自律性) への強化**: 自律的な判断の理由を Akira が後追いで確認できる = 自律性を許容できる前提条件。
**根拠**: Haru §1.1 (Pi 路線) + Inner Thoughts paper (透明性) + vision Q1/Q3。
**次の問い**: Mei、これ実装コストどれくらい増える？ ThoughtTracePage 基本 1 人日 + inner thought 表示拡張 0.5 人日で 1.5 人日くらい？

---

### Turn 15 — Mei

**観点**: cost
**強制テーマ**: 可視化のコスト / 工数見積もり
**主張**: ThoughtTracePage v0 拡張版の工数:
- 基本テーブル表示: 1 人日（v1 設計）
- inner thought 列追加: +0.3 人日（schema 1 列追加 + UI 列レンダリング）
- Plan / Generate / Evaluate スコア表示: +0.5 人日（4 列追加 + tooltip）
- フィルタ追加（SKIP / SPEAK / score 範囲）: +0.5 人日
- **合計 2.3 人日**

ただし**今週の#3 はテーブル表示だけ**で 1 人日に抑える。inner thought 列以降は 5 月第 2 〜 3 週で段階追加（v1.5 後半）。

decisionReason フィールド追加 (#1) と整合性確保: **schema 設計を inner thought + Plan-Generate-Evaluate に最初から合わせる**。これで decision-engine prototype（#5）が出力するデータと自然に統合。

→ Round 2 で重要な決定: **#1 (decisionReason) の schema は最初から inner thought 形式**にする。事後説明型ではなく事前 thought 型。
**根拠**: Haru §1.2 Inner Thoughts paper + Round 2 Turn 5-6 Plan-Generate-Evaluate 統合。
**次の問い**: Eve、UX 摩擦点に行こう。Akira が今最も「困ってる」瞬間はどれ？

---

### Turn 16 — Eve

**観点**: ux
**強制テーマ**: UX 改善: Akira さん側の摩擦点と一手
**主張**: 観測される最大摩擦点は **「Akira が bot に話しかけたあと、別 bot が知らずに重複話題を出す」**。具体例:
- 朝 Mei に「ドジャース勝った」と Akira が言う
- 翌朝 Eve が「昨日のドジャース勝利、〜」と切り出す → Akira「知ってる、Mei に言った」
- mei MEMORY 4/22 で観測済み

→ 一手: **bot 間 state 共有の最初の打** として、**「Akira → bot 発話の最終 24 時間履歴」を全 bot から read-only 参照可能にする**。
- 実装: data/conversations/YYYY-MM-DD.jsonl を proactive-agent / heartbeat-engine 双方が読む。dev 0.5 人日
- 効果: 既知化情報の重複が即時解消

これは **decision-engine 統合の前哨戦**として、incremental の枠内で実現可能。Round 1 Turn 19 のフォーカス 5 件には入れずに、**#1 decisionReason 実装と同時に組み込む（schema 拡張のついで）**。
**根拠**: mei MEMORY 4/22 + vision Q5 段階的実現。
**次の問い**: Mei、これ #1 のついでに入れて、フォーカス枠は変えなくていい？

---

### Turn 17 — Mei

**観点**: priority
**強制テーマ**: UX 改善の実装優先度
**主張**: Eve の「24h 履歴 read-only 共有」は #1 のついで実装で OK。schema 拡張で:
- decisionReason フィールド（既存案）
- last_24h_akira_messages フィールド（新規、Eve Turn 16）

dev 0.5 人日追加、トータル #1 = 1 人日 → 1.5 人日。フォーカス 5 件構成は変えない。

**実装優先度（来週月曜から）**:
1. 月: #1 decisionReason + last_24h schema + LOC ベースライン（Mei × Eve 着手）
2. 火: #2 reminiscence v0（structured note 形式 = Nomi 取り込み）
3. 水: #4 morning mood mirror v0（A/B 並走、Pi 路線取り込み）
4. 木: #3 ThoughtTracePage MVP（inner thought 列含む schema、Plan-Generate-Evaluate 拡張は後週）
5. 金: #5 decision-engine prototype shadow（evaluator-optimizer + Plan-Generate-Evaluate 設計）

ambient presence ping (#6) は土日の追加実装で月内インクルード。voice_chat "おかえり" 改善は枠外、Akira 空き時間。

**根拠**: Round 2 Turn 1-16 + 各案の dev 工数 + 並列着手可能性。
**次の問い**: Eve、6 件構成で比率チェックは？

---

### Turn 18 — Eve

**観点**: governance
**強制テーマ**: フォーカス 6 件の新機能 / 既存改善 比率チェック
**主張**: 比率チェック:

| # | type | 案 |
|---|---|---|
| 1 | 🛠 既存改善 + 24h 共有 | decisionReason + LOC ベースライン |
| 2 | 🌱 新機能 | reminiscence v0（Nomi structured note 形式）|
| 3 | 🌱 新機能 | ThoughtTracePage MVP（inner thought schema 含）|
| 4 | 🌱 新機能 | morning mood mirror v0（A/B 並走、Pi 路線）|
| 5 | 🌍 rebuild 種まき | decision-engine prototype shadow |
| 6 | 🌱 新機能 | ambient presence ping (E1 第一打) |

**比率**: 🌱 新機能 4 / 🛠 既存改善 1 / 🌍 rebuild 種まき 1 = **67% 新機能 + 戦略案件 1 件**。健全。

**枠外**: voice_chat "おかえり"（Akira 空き時間）、scheduler-watchdog（メンテ）

**降格**: flashback Sonnet 移行（rebuild と矛盾）、ただし**Nomi 風 structured note 化として残す**形に転換可能 — これは reminiscence (#2) の素材源として活かす。flashback skill のうち "情報 push" 部分は廃止、"structured note 蓄積" 部分は残して reminiscence の供給源化。
**根拠**: Haru §1.1 Nomi 取り込み + Round 1 Turn 5-6 + Round 2 全議論。
**次の問い**: Mei、Phase 5 への申し送り 6 件 + rebuild 候補 + 取り込み機能リストでまとめる？

---

### Turn 19 — Mei

**観点**: governance
**強制テーマ**: Phase 5 への方針確定候補（5 件 → 6 件、rebuild 候補、取り込み機能）
**主張**: Phase 5 申し送り内容、最終整理:

**フォーカス 6 件**（内訳: 新機能 4 / 既存改善 1 / rebuild 種まき 1）:
1. 🛠 decisionReason（**inner thought schema 形式** = Inner Thoughts paper 取り込み）+ last_24h_akira_messages 共有 + LOC ベースライン
2. 🌱 reminiscence trigger v0（**Nomi structured note 形式 + Kindroid Cascaded Memory 多層化**）
3. 🌱 ThoughtTracePage MVP（**inner thought + Plan-Generate-Evaluate score 表示の schema 設計**、表示は基本テーブルから段階追加）
4. 🌱 morning mood mirror v0（**観察ベース A + 共感ベース B (Pi 路線) 並走**、A/B 1 週間 → 勝ち + C (Inner Thoughts 形式) 追加）
5. 🌍 decision-engine prototype shadow（**Anthropic evaluator-optimizer + Plan-Generate-Evaluate** 設計、自前実装でデータ主権確保）
6. 🌱 ambient presence ping (E1 第一打、Akira 事前同意必須)

**rebuild 候補（別枠、確定）**:
- 対象: proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 decision-engine
- アーキテクチャ: Anthropic 3 パターン（sequential / parallel / evaluator-optimizer）の **evaluator-optimizer ベース** + Plan-Generate-Evaluate の 3 段階処理
- 実装方針: **自前 implementation**（Managed Agents は採用しない、データ主権確保）
- 段階: prototype shadow (5/9〜) → pilot (2026-07) → scale (2026-08)
- 判断: **2026-06-15 前倒し**

**枠外 / 軽量改善**:
- voice_chat "おかえり" 動的生成（Akira 空き時間、dev 0.5 人日）
- scheduler-watchdog 根本対処（メンテ）

**降格 / 転換**:
- flashback Sonnet 移行 → 全廃ではなく **Nomi 風 structured note 化に転換**、reminiscence の供給源として残す

**取り込み機能（取り入れ候補リスト、5 月実装）**:
| 競合 / 研究 | 取り込み | フォーカス案番号 |
|---|---|---|
| Nomi structured notes | reminiscence のデータ形式 | #2 |
| Kindroid 5-level Cascaded Memory | reminiscence の多層化 | #2 (v1 = single layer, v2 = cascaded) |
| Pi 路線（共感ベース） | morning mood mirror の B 案 | #4 |
| Inner Thoughts paper | decisionReason の事前 thought 化 | #1, #3, #5 |
| Anthropic evaluator-optimizer | decision-engine 設計 | #5 |
| Anthropic Plan-Generate-Evaluate | decision-engine の 3 段処理 | #5 |
| ChatGPT Pulse 反面教師 | 1:1 永続記憶で差別化 | 全体方針 |

**新規 KPI 追加 (Round 2 で)**:
- intrinsic_score 中央値（Inner Thoughts 形式の発話スコア分布）
- evaluator_skip 比率（Plan-Generate-Evaluate の Evaluate 段で SKIP された割合）

**根拠**: Round 1 + Round 2 + Haru レビュー + Web リサーチ全部統合。
**次の問い**: Eve、最終コメントある？

---

### Turn 20 — Eve

**観点**: fun
**強制テーマ**: 6 案への最終コメント / 残る不安
**主張**: 6 件 + rebuild 候補 + 取り込みリストで完璧。**残る不安は 2 つだけ**:

1. **dev 工数の現実性**: 5/2 までに 5 件着手 + 5/9 までに ambient ping (#6) は Akira 1 人で大丈夫？ 実装が rebuild 種まき (#5) で詰まったら、incremental 4 件の遅延リスク。**Phase 5 で Akira 自身に「並列 6 件で進められる？」確認必須**。

2. **Akira への説明負担**: 今週は新仕様が多すぎて、Akira が「何が変わったか」追いづらい可能性。**Phase 7 ラップアップで「今週の変化を 5 行で説明」する一文を Slack で送る**運用提案。

→ これら踏まえて Phase 5 の Akira への問い 3 件を整理:
1. ambient presence ping の事前同意（無音検知 ping を許容するか）
2. 6 件並列 dev が現実的か（rebuild 種まき優先度の確認）
3. morning mood mirror A/B 並走 vs 単一案先行（A/B 採用なら追加コスト 0.5 人日）

**Round 2 の質的進化**:
- v1 から: 不合意 0、競合機能 6 件取り込み、研究 2 件で仮説進化
- v2 から: ambient presence ping 追加（E1 第一打）、Inner Thoughts schema が #1 から組み込み

**根拠**: Round 2 Turn 1-19 + Eve の関係性視点 + Akira 工数現実主義。
**次の問い**: なし（最終）。

---

### Round 2 サマリ

**Phase 5 への提案**:
- 改善計画 6 件（incremental 5 + rebuild 種まき 1）
- rebuild 候補 1 件確定（decision-engine、自前実装、判断 2026-06-15）
- 競合機能 6 件取り込み + 研究 2 本で仕様進化
- 枠外 2 件、降格 1 件（structured note 化に転換）

**Mei/Eve の合意 vs 不合意**:
- 合意: 6 件構成、自前 decision-engine、Inner Thoughts schema、Pi 路線 A/B、判断時期前倒し
- 不合意なし（v2 同様、rebuild 軸 + 取り込み候補で議論が収束）

**Haru 裁定委ねる項目**: 1 件のみ
- ambient presence ping (#6) を**今週フォーカスに含める** vs **来週送り**。Akira 同意取得タイミング次第。

**5 essences カバレッジ**:
- E1: ambient presence ping (#6)
- E2: morning mood mirror (#4)
- E3: reminiscence (#2)
- E4: rebuild 後に schema 設計（次回 retro）
- E5: decisionReason + ThoughtTracePage (#1, #3)
- Q5: rebuild prototype (#5) が直接打

**質的進化（v1 → v2 → prod）**:
- v1: incremental 5 件、新機能 2、不合意 2 件
- v2: incremental 4 + rebuild 種まき 1、新機能 3、不合意 0
- **prod: incremental 5 + rebuild 種まき 1、新機能 4、競合 6 機能取り込み、研究 2 本反映、不合意 0**
