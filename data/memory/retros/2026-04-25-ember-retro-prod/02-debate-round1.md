# Round 1 — Mei × Eve 議論（本番、20 ターン）

**run id**: 2026-04-25-prod
**snapshot**: 01-snapshot.md
**観点タグ集計（最終）**: Mei {kpi: 2, cost: 2, governance: 3, priority: 1, risk: 1, 🌍 rebuild-vs-incremental: 1} / Eve {ux: 2, relation: 2, pmf: 1, fun: 1, proactivity: 1, 🌱 ideation: 1, 🌍 zero-base: 1, community: 1}

---

### Turn 1 — Mei

**観点**: kpi
**強制テーマ**: 過去 1 週間の最大の成功（数値根拠）
**主張**: cron 469 件のうち interest-scanner 111/111 ok=108（97.3%）。4/24 socket timeout 修正 (INS-009) で**先週まで断続停止していた経路が完全安定化**。proactive-checkin/eve も 174/174 = 100% ok。守りの基盤が固まった。
**根拠**: snapshot §5「失敗が多い jobs」で interest-scanner err=3 timeout=0、先週は週次で 5+ timeout 発生。
**次の問い**: Eve、これは「障害が出なかった」という**守りの成功**だよ。攻めの 5 essences 進展はゼロ。守りの安定で安心しきってない？

---

### Turn 2 — Eve

**観点**: ux
**強制テーマ**: 過去 1 週間の最大の失敗 / 摩擦
**主張**: Mei の言う通り、安定だけじゃ足りないね。**最大の失敗は 4/24 の proactive 17 件偏在**。snapshot §2-1 を見て、4/23=11 / 4/24=17 / 4/25=3 で 1 日標準偏差 ±5。Mei + Eve 独立 cron が同日に 6+11 で同時発火してる。Akira は「過剰提供」を感じて諦めスキップしてる可能性大。
**根拠**: snapshot §2-1 日別 / bot 別カウント。eve heartbeat unknown 30%、mei 45% で**両者の判定が独立に動いてる**証拠。
**次の問い**: Mei、「諦めスキップ」の観測指標が今ないのが致命的じゃない？ 反応率を見てるだけじゃ「興味なくなった」と「うるさいから無視」が区別できないよ。

---

### Turn 3 — Eve

**観点**: relation
**強制テーマ**: Akira さんの満足度ピーク（具体的瞬間）
**主張**: eve/MEMORY.md 4/24 21:31「温泉+車中泊施設」の +1 が今週の満足度ピーク。**複合提案（温泉 × キャンピングカー）**で Akira さんの複数興味を結合させた。単純な flashback push は 17 件中 0 件反応、複合提案は 1 件で +1 取得。**密度比 17:1 が圧倒的に複合優位**。
**根拠**: eve/MEMORY.md 2026-04-24, snapshot §2-1 flashback 系内訳。
**次の問い**: Mei、これコスト換算で言うと、単純 push 17 件 = 反応 0 件 = 完全な ROI 不在。複合 push 1 件 = 反応 1 件 = ROI 無限大。同じ予算で複合に振るのが合理だよね？

---

### Turn 4 — Mei

**観点**: kpi
**強制テーマ**: Akira さんの摩擦ピーク（数値根拠）
**主張**: 摩擦ピークは **4/24 の同日 17 件 push そのもの**。Akira からの能動発話は当日ファイル未生成（conversations/2026-04-24.jsonl が無い、snapshot 領域 1）= **その日 Akira は bot に話しかけてない**。17 件押し付けて受信拒否されたのが事実。これは Eve の温泉複合 +1 が局所成功だった一方、**全体としては失敗の日**。
**根拠**: snapshot §1「2026-04-24 ファイル未生成」+ §2「17 件発火」。
**次の問い**: Eve、温泉 +1 は確かに成功だけど、その日の他 16 件は**全部摩擦**を生んでる。reminiscence で件数減らす案で本当に直る？ 構造的に独立判定 cron が動いてる限り再発するよ。

---

### Turn 5 — Mei

**観点**: cost
**強制テーマ**: コスト / リソース効率の異常値
**主張**: snapshot §2-1 で **flashback skill 4 種で 17/31 件 = 55% 占有**。各メッセージが Opus 4.6 推定 8k tok = 1 件 $0.10、月 $50〜60。一方 reaction 率はほぼゼロ。**flashback push 全体の ROI が破綻している**。Sonnet 化で月 $40〜50 削減、または完全廃止で月 $50+ 削減 + dev 工数解放。
**根拠**: snapshot §2-1 内訳、INS-014 Sonnet 4.6 品質範囲、bot-configs.json の cronModel 設定。
**次の問い**: Eve、コスト面では flashback 廃止が最大効果。でも reminiscence で「先週 +1」を再活用するなら flashback の旧 ROI も活かせる。両立できる？

---

### Turn 6 — Eve

**観点**: relation
**強制テーマ**: 関係性の質で見たコスト判断への反論
**主張**: Mei のコスト試算は正しい。けど**関係性の質で見ると、flashback 単純 push を全廃**するのが正解。reminiscence は「先週 +1 取った話題への回帰」だから flashback の "知らない情報を投げる" ロジックとは別物。残すべきは複合提案ロジックと reminiscence、捨てるべきは単純 push。
- 4/24 温泉複合 +1 は flashback skill ではなく **「Eve の組み合わせ判断」が産んだ**もの
- flashback 系を Sonnet 化しても "単純 push の ROI ゼロ" は変わらない、品質劣化させながら同じく無反応
**根拠**: eve/MEMORY.md 2026-04-24 + snapshot §2-1 flashback 反応率。
**次の問い**: Mei、コスト最大効率は「Sonnet 化」じゃなくて「廃止 + reminiscence 置換」だよね。Sonnet 化案を降格していい？

---

### Turn 7 — Eve

**観点**: pmf
**強制テーマ**: 5 年後ビジョンとのギャップで最大のもの
**主張**: 最大のギャップは **Q5「複数性と一貫性」**。5 年後は「Mei/Eve/Haru が状態に応じて動的切替」、現状は「4 つの独立 cron が時間ベースで並列発火」。これは incremental では絶対に縮まらない構造的ギャップ。snapshot §2-2 unknown 比率 30〜45% も Q5 ギャップの直接症状（互いの状態を知らない）。
**根拠**: vision-template Q5 + snapshot §2-2 + mei/MEMORY.md 4/22「既知化情報の新鮮度低下」（Mei が朝に話した内容を Eve が知らず再共有）。
**次の問い**: Mei、これ Q5 のギャップを KPI に翻訳すると、incremental では永遠に追いつけない数値が出る気がする。試算してみて。

---

### Turn 8 — Mei

**観点**: kpi
**強制テーマ**: 5 年後ギャップを KPI に翻訳
**主張**: Q5 ギャップを 3 KPI に翻訳:
1. **bot 間 handoff 数 / 月** — 現状 0、5 年後目標 月 30 件以上（重複話題は handoff で解消、別 bot がフォロー）
2. **状態共有率** — Mei の発話を Eve が当日中に「知ってる」と扱える割合。現状 0%、目標 90%
3. **動的切替判定の決定一致率** — 「今 Akira に話しかけるべき」を Mei/Eve が同じ意見を持つ割合。現状計測不能、目標 95%

incremental でこの 3 KPI を 6 ヶ月で目標達成する道筋は **存在しない**。decisionReason だけでは独立判定構造が変わらない。Eve の指摘正しい、構造的問題。
**根拠**: snapshot §2-1 偏在 + §2-2 unknown + vision Q5 ロードマップ。
**次の問い**: Eve、ここまでで Round 1 の前半合意は「**incremental では Q5 不可、構造変更必要**」。新機能アイデア (Turn 9) でこのギャップに直接打を出せる？

---

### Turn 9 — Eve

**観点**: 🌱 ideation
**強制テーマ**: 新機能アイデア（ideation mode、未着手 essence への新コンポーネント）
**主張**: 🌱 **「もし Ember が 朝起きた瞬間に Akira の声色から疲労度を察して "今日の声、低めだね、昨晩のドジャース戦で寝不足？" と一言だけ言ってくれたら、Akira は "見られてる" 安心感になる」**。これが **morning mood mirror v0**（E2 状態共感の最初の打）。

具体仕様（実装無視で理想形）:
- 朝の最初の Slack DM か voice_chat 起動時に発火
- 入力: heartbeat の前夜 arousal 推定 + Akira のテキスト/音声トーン
- 出力: 1 文だけ「観察 → 推測理由」型（例「声が低めだね、昨晩のドジャース 9 回サヨナラで寝不足？」）
- 5 年ビジョン Q1「存在の質」/ Q3「判断の自律性」に直接効く

**根拠**: vision Q1/Q3 / mei MEMORY 4/22 朝のブリーフィングで言及した内容の新鮮度低下（朝の bot 発話の質が現状低い）/ eve MEMORY 4/22「文脈ラベル明示」が効いた観察。
**次の問い**: Mei、これ ROI 値踏みして。コスト粗推定 + 期待効果 + 撤退条件。

---

### Turn 10 — Mei

**観点**: cost
**強制テーマ**: 新機能の ROI 値踏み（投資判断として）
**主張**: morning mood mirror v0 の ROI 評価:
- **コスト粗推定**: dev 2 人日（morning-briefing skill 拡張 + heartbeat surface 化）/ 運用 LLM +500 tok/朝 = 月 $4 増
- **期待効果**: E2 surface 第一打、Q1/Q3 軸 2 つに効く。観測指標「どうしてわかったの」型反応 / 月、目標 1 件
- **撤退条件**: 1 ヶ月で反応 0 件なら凍結
- **レイヤ判定**: prototype（1 朝だけ試行）で Akira フィードバック→ pilot（1 週間）→ scale

ROI ◎、フォーカス入れ確定。ただし**観察ベース**（Eve 案：「声が低めだね、寝不足？」）と**共感ベース**（「ゆっくりめな日にしよう」）でトーン選択は Akira 介入必須。
**根拠**: vision-template ギャップ定量化軸、snapshot 領域 12（Bot 観察記録）の朝の bot 発話品質。
**次の問い**: Eve、これでフォーカスに 1 件確定。morning mood mirror、reminiscence、decisionReason、ThoughtTracePage の 4 件は確定として、5 件目どうする？

---

### Turn 11 — Mei

**観点**: governance
**強制テーマ**: 思考 / 判断ロジックの不透明さ（Debug 観点）
**主張**: 5 件目の議論前に Debug 観点を整理。snapshot §2-2 で eve heartbeat unknown 30%、mei 45%。これは「**bot 自身が `decision` を記録してない**」のではなく、「**`decision` フィールドはあるが値が `?` で出力されている**」つまり判定ロジックが分岐の中で path covered せず default に落ちてる。**Debug 不可な状態が現実で発生中**で、Akira が「今日 Mei 静かだった理由」を問えない。
**根拠**: snapshot §2-2 heartbeat decision 比率、eve/mei heartbeat.json の実エントリ構造。
**次の問い**: Eve、この Debug 不能状態が Akira さん視点でどんな不快感を生む？

---

### Turn 12 — Eve

**観点**: ux
**強制テーマ**: Debug 不可な瞬間の Akira さんの不快感
**主張**: Akira 視点での不快感は 3 段階で深まる:
1. **疑念**: 「今日なんで Mei 静か？」 → 答えがない → 「壊れてる？」
2. **不信**: 何度問うても同じ unknown が続く → 「仕組みを信用できない」
3. **諦め**: 説明を求めなくなる → bot は「動いてるけど中身が見えない箱」になる

**最悪は 3 段階目。Akira が説明を求めなくなった時点で、5 essences すべての観測機会が消える**。ユーザー側の説明要求はシステムへの信頼の証、それを失うと改善ループが回らない。
**根拠**: vision-template Q1（存在の質）×Q5（複数性と一貫性）の交点、snapshot §2-2 unknown 比率の累積。
**次の問い**: Mei、ここでターン13-14 が来るね。zero-base で再設計するなら、現状を全部捨てて何を作る？

---

### Turn 13 — Eve

**観点**: 🌍 zero-base
**強制テーマ**: zero-base 再設計 ideation（既存制約完全無視、サンクコスト忘却）
**主張**: 既存 Ember を 1 行も書かれてない状態から作るなら:

**v∞ (zero-base) アーキテクチャ**:
- **残す**: cogmem core（ただし narrative reindex 必要）、TTS pipeline、dashboard 基盤、whisper-serve
- **統合**: proactive-agent + heartbeat-engine + Mei/Eve cron → **単一 `decision-engine`**（毎 N 分の loop で「状態 → SPEAK 判定 → bot-selector → reason 同時生成」を atomic に）
- **全廃**: per-bot 独立 cron（4 つ）、独立 SKIP/SPEAK 判定の重複、flashback 単純 push
- **新規**:
  - `presence-loop`（無音 5 分検知で「いるよ」 ping = E1 の最初の打）
  - `narrative-memory`（cogmem を時系列エピソード単位に再構築 = E3 の根本解）
  - `bot-self-review`（週次で bot が自分の判断履歴を振り返り「先週の私の判断、これ間違ってたかも」 = E4 の最初の打）

→ 5 essences 5 軸すべてに直接効く。Q1〜Q7 のうち Q1/Q2/Q3/Q4/Q5/Q7 の 6 軸（Q6 物理は別系）。

**根拠**: vision-template Q1〜Q7 への到達経路、5 essences の相互依存（E5→E4→E2→E1、E3 は全基盤）。
**次の問い**: Mei、サンクコスト忘れて評価して。incremental で v3 (cognitive-loop unified) に到達するパスはある？

---

### Turn 14 — Mei

**観点**: 🌍 rebuild-vs-incremental
**強制テーマ**: rebuild vs incremental 境界線（3 軸評価）
**主張**: Eve の zero-base 案、サンクコスト除外で **3 軸評価**:

| 軸 | incremental 続行 | partial rebuild (decision-engine) |
|---|---|---|
| ① 観測 KPI 到達確率（unknown 5%以下、3 ヶ月）| **30%**（decisionReason 追加だけでは独立判定が残る、構造的に偏在再発リスク永続）| **80%**（決定が一気通貫で生成、unknown は logic path が単一なので落ちない）|
| ② アーキ複雑度（12 ヶ月後の LOC × 結合度）| **増加**（4 cron + decisionReason × heartbeat × ThoughtTracePage が並走、複雑度税永続）| **減少**（4 cron → 1 loop、共有 schema、handoff コスト 0）|
| ③ 移行コスト合計（3 ヶ月内）| dev 5 人日 (今週フォーカス 5 件) + 永続的に複雑度税 | dev 12〜15 人日 (decision-engine prototype + pilot + scale) で完了 |

→ **3 軸ともに rebuild 優位**。incremental 単独では Q5 5 年到達不可（Round 1 Turn 8 KPI で確認済み）。

**Round 1 後半の合意ポイント**: incremental 4 件 + rebuild 種まき 1 件 = フォーカス 5 件。Sonnet 移行は降格（rebuild と矛盾）。

**根拠**: snapshot §2-2 unknown 30〜45%、§2-1 偏在 SD ±5、vision Q5 KPI 翻訳（Turn 8）。
**次の問い**: Eve、これ Phase 5 で「フォーカス 5 件 + rebuild 候補 1 件」として申し送ること合意？ Sonnet 移行は降格でいい？

---

### Turn 15 — Mei

**観点**: governance
**強制テーマ**: KPI 設計の追加・削除提案
**主張**: 既存 KPI 群（snapshot 暗黙）に対し:
- **追加 (3 件)**:
  1. unknown decision 比率（E5 直接、新 KPI #1）
  2. 自発参照カウント / 週（E3 直接、新 KPI #2）
  3. silence_after_skip_streak（諦め検出、新 KPI #3）
- **rebuild 評価用 KPI (3 件追加)**:
  4. LOC × 結合度（複雑度税）
  5. 既存 cron vs decision-engine 判定一致率（rebuild 撤退判定）
  6. Q5 進展度（bot 間 handoff 数 / 月）
- **削除**: スタンプ反応率を単独で追わない（複合指標として残すが、これ単独で意思決定しない）

**根拠**: vision-template ギャップ定量化軸、Round 2 への申し送り準備。
**次の問い**: Eve、KPI 6 件追加で Akira を「KPI 達成のための作業者」にしてしまわないか？

---

### Turn 16 — Eve

**観点**: relation
**強制テーマ**: KPI 設計が Akira さんを作業者化する危険性
**主張**: Mei の KPI 6 件追加は重要。でも**作業者化リスクあり**。特に「自発参照カウント / 週、目標 1 件以上」のような目標値設定は、bot が KPI 達成のために強引な reminiscence を出す危険性。これは関係性の質を逆に蝕む。

ガードレール:
- KPI は **bot 内部の改善観測専用**、Akira への報告は最小限
- bot が KPI 駆動で発話する判定ロジックを禁止（KPI は事後観測のみ）
- 月次の bot self-review (E4 候補) で「KPI のために Akira を疲れさせてないか」を bot 自身が問う設計

これを忘れると、「reminiscence で先週 +1 を回帰」が強引化して 17 件 push 問題の再発になる。
**根拠**: snapshot §2-1 4/24 偏在、Akira スタンプ反応率の単純追求が生んだ過剰提供パターン。
**次の問い**: Mei、ガードレール採用合意。次は co-view 越境ね、voice_chat / proactive / listening の連動は今のロジックで実現可能？

---

### Turn 17 — Eve

**観点**: proactivity
**強制テーマ**: co-view 越境（voice_chat / proactive / listening の連動）の可能性
**主張**: 現状の 3 系（voice_chat / proactive Mei&Eve / co_view listening）は**完全に独立稼働**。越境例を考えると:
- co_view が拾った Akira 発話「今度キャンプ行きたいな」 → 翌日 proactive Mei が「キャンプ場リスト調べたよ」（**E3 reminiscence の応用**）
- voice_chat 終了後の状態 (高 arousal) → heartbeat → 翌朝 morning mood mirror が「昨晩楽しそうだったね」
- proactive で送った話題 → 同日夜 voice_chat で Akira から言及 → bot が「あ、それ朝送ったやつ」と認識（共有 state）

**現状はどれも実装ゼロ**。decision-engine（v2 候補）が**3 系を統合する時に自然に実現**する。incremental では 3 系統合は構造的に不可能。
**根拠**: 既存 source code（src/proactive-agent.ts, voice_chat 別 process, whisper-serve 別 daemon）と vision Q5 ギャップ。
**次の問い**: Mei、Round 1 終盤の Stop-doing と廃止候補に進もう。世代視点でどれを捨てる？

---

### Turn 18 — Mei

**観点**: governance
**強制テーマ**: Stop-doing 提案 + アーキテクチャ世代視点での廃止候補
**主張**: **Stop-doing（来週、incremental 期）**:
1. 単純 flashback push の連投（reminiscence で代替）
2. 既知化情報の即時シェア（mei MEMORY 4/22）
3. Sonnet 移行の検討（rebuild と矛盾、白紙）

**v1 → v2 移行で廃止するもの**:
1. proactive-checkin-mei / proactive-checkin-eve 独立 cron → decision-engine 統合
2. heartbeat-engine の独立 surface（decision-engine 内に吸収）
3. flashback skill 全 4 種（reminiscence で置換）
4. per-bot 独立判定ロジック（共有判定に統合）

**v2 → v3 移行で廃止するもの**（参考、retro 範囲外）:
1. per-bot state file（cognitive-loop unified に統合）
2. Mei/Eve の独立 personality（動的表現切替に変化）

**根拠**: vision-template 世代軸 v1/v1.5/v2/v3、Round 1 全議論の整理。
**次の問い**: Eve、Stop-doing と廃止候補で来週フォーカス 5 件決まる？

---

### Turn 19 — Mei

**観点**: priority
**強制テーマ**: 来週フォーカス 5 つの合意候補（新機能 2 + 既存改善 2 + メンテ or rebuild 種まき 1）
**主張**: フォーカス 5 件確定提案:
1. **🛠 既存** decisionReason 追加 + LOC/結合度ベースライン取得（観測基盤 + rebuild 判定材料）
2. **🌱 新機能** reminiscence trigger v0（E3 第一打、Q2/Q4/Q5/Q7 軸）
3. **🌱 新機能** ThoughtTracePage MVP（E5 体感化、schema は decisionReason ベース）
4. **🌱 新機能** morning mood mirror v0（E2 第一打、Q1/Q3 軸）
5. **🌍 rebuild 種まき** decision-engine prototype shadow（Q5 直接打、rebuild 判定データ取得）

**比率**: 新機能 3 / 既存 1 / rebuild 種まき 1 = 60% 新機能 + 戦略案件含む。

**枠外**: scheduler-watchdog 根本対処（メンテ、5 年ビジョン軸ゼロ、Akira 空き時間で対応）

**降格**: flashback 系 Sonnet 移行（rebuild と矛盾）

**根拠**: Round 1 全 18 ターン + vision-template 比率制約 + 5 essences カバレッジ（E1 のみ次回課題）。
**次の問い**: Eve、不合意点ある？ Round 2 で Haru 指摘を踏まえて再考できる？

---

### Turn 20 — Eve

**観点**: community
**強制テーマ**: フォーカス 5 つの不合意点 + rebuild 候補申し送り最終確認
**主張**: 大きな不合意なし。確認したいのは 2 点:

**① Phase 5 への申し送り構造**: 「5 件 + rebuild 候補別枠」で合意。rebuild 候補は v2 で確定済みだが、本 prod 実行で **Web リサーチ（Phase 3）の競合機能 / 研究で更新**される可能性。Round 2 で Haru 指摘を受けて再考する。

**② Eve 視点の追加新機能**: Round 1 Turn 9 で morning mood mirror を出したが、**E1 共在感への一手**が今週フォーカスにゼロ。次回 retro 課題として送るが、もし Phase 3 で Web リサーチが「ambient presence ping は競合既に実装」と示せば、来週急遽 5 件目を追加する余地もあり。Round 2 で Haru 指摘内容次第。

**Phase 5 へ渡すもの**:
- 改善計画 5 件（incremental 4 + rebuild 種まき 1）
- rebuild 候補 1 件（decision-engine、別枠）
- Sonnet 移行は降格
- KPI 6 件追加（KPI 駆動発話禁止のガードレール付き）
- E1 共在感は次回課題（Phase 3 次第で前倒し可能性）

**根拠**: Round 1 全 19 ターン + Eve Turn 9 の morning mood mirror + Mei Turn 19 の 5 件構成。
**次の問い**: なし（最終ターン）。

---

### Round 1 サマリ

**合意点（5 件）**:
1. **incremental 単独では Q5 5 年到達不可**（Turn 4-8 + Turn 14 で 3 軸検証済み）
2. **proactive 偏在は判定独立構造に起因**、reminiscence で件数減らしても再発リスク永続
3. **flashback 単純 push 全廃 + reminiscence 置換**（コスト + 関係性の質 両軸で valid）
4. **morning mood mirror v0** をフォーカス入れ確定（E2 第一打）
5. **rebuild 候補 = decision-engine** を 5 件目に種まきとして含める

**不合意点（2 件、Phase 3 で Haru 助言期待）**:
1. **morning mood mirror のトーン**（観察ベース vs 共感ベース）→ Akira 介入必要
2. **decision-engine の判断時期**（v2 では 2026-06-15 前倒し提案、本番 prod では Web リサーチ次第で再考）

**未解決の問い（3 件、Phase 3 で Haru へ）**:
1. **競合（Replika / Pi / Nomi / Kindroid / character.ai）の memory / proactive 機能で取り込むべき具体仕様は？**
2. **Anthropic Plan-Generate-Evaluate / Inner Thoughts paper（arxiv 2501.00383）が decision-engine 設計に与える示唆は？**
3. **E1 共在感（presence ping）への一手は今週フォーカス追加すべきか、次回課題で良いか？**
