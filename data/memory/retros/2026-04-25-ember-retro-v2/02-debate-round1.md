# Round 1 — Mei × Eve 議論（v2 run, 5 ターン圧縮）

**run id**: 2026-04-25-smoke-test-v2
**圧縮の前提**: フル 20 ターン版から **新構造で重要な Turn (1, 2, 13, 14, 19) を抽出**して 5 ターンに再構成
**観点タグ集計**: Mei {kpi: 1, governance: 2} / Eve {ux: 1, 🌍 zero-base: 1}

---

### Turn 1 — Mei

**観点**: kpi
**強制テーマ**: 過去 1 週間の最大の成功（数値根拠）
**主張**: cron 469 件中 interest-scanner 111/111 ok=108 (97.3%)。4/24 socket timeout 修正 (INS-009) で安定化。proactive-checkin/eve も 174/174 = 100%。
**根拠**: snapshot §5。先週まで 10 分タイムアウトで断続停止していた経路が安定。
**次の問い**: Eve、これは「守りの成功」だよ。攻めの 5 essences 進展はゼロ。incremental ペースで 5 年到達できると思う？

---

### Turn 2 — Eve

**観点**: ux
**強制テーマ**: 過去 1 週間の最大の失敗 / 摩擦
**主張**: 4/24 の proactive 17 件偏在。snapshot §2-1 を見て。Mei + Eve 独立 cron が同日に 6+11 件発火した。Akira は「過剰提供」を感じてる可能性大、reminiscence で件数減らしても、**判定が独立な構造は変わらない**から再発する。
**根拠**: snapshot §2-1「日別 / bot別」で 4/24=17 件、4/25=3 件、SD ±5。eve heartbeat の `?` 30%、mei 45%。
**次の問い**: Mei、incremental の decisionReason 追加だけで「両 bot が独立に重複発火する」根本問題は消えると思う？

---

### Turn 3 — Eve

**観点**: 🌍 zero-base
**強制テーマ**: zero-base 再設計 ideation（既存制約完全無視、サンクコスト忘却）
**主張**: もし Ember が 1 行も書かれてない状態なら、私はこう作る:
- **残す**: cogmem core / TTS pipeline / dashboard 基盤
- **統合**: proactive-agent + heartbeat-engine + Mei/Eve cron → **単一 `decision-engine`**（毎分 1 回ループ、状態 → SPEAK判定 → bot-selector → reason 同時生成）
- **全廃**: per-bot 独立 cron（4 つ）、独立 SKIP/SPEAK 判定の重複
- **新規**: `presence-loop`（無音検知で「いるよ」 ping）、`narrative-memory`（cogmem を時系列エピソード単位に再構築）
- 5 年ビジョン Q1〜Q7 への到達: Q2/Q3/Q4/Q5/Q7 に直接効く

**根拠**: vision-template の Q5「複数性と一貫性」に対し、**現状の 4 つの独立 cron は構造的にゴール（動的切替）と矛盾**。incremental では辿り着けない。
**次の問い**: Mei、サンクコスト忘れて評価して。incremental で v3 (cognitive-loop unified) に到達するパスはある？

---

### Turn 4 — Mei

**観点**: governance
**強制テーマ**: rebuild vs incremental 境界線（3 軸評価）
**主張**: Eve の zero-base 案、サンクコスト除外で評価する。境界線 3 軸:

| 軸 | incremental | rebuild |
|---|---|---|
| ① KPI 到達確率（unknown 5%以下、3 ヶ月）| 50%（decisionReason だけでは構造的に消えない偏在が残る）| **80%（決定が一気通貫で生成、偏在は構造的に消える）** |
| ② アーキ複雑度（12 ヶ月後）| 増加（decisionReason × heartbeat × 4 cron が並走）| **減少（4 cron → 1 loop）** |
| ③ 移行コスト合計 | dev 5 人日 (1, 2, 3) + 永続的に複雑度税 | dev 10〜15 人日 (decision-engine + 段階移行) で完了 |

→ **3 軸ともに rebuild 優位。ただし「いま全部やる」のは無理なので、incremental v1.5 で観測整備しつつ v2 (decision-engine) を pilot する**。incremental だけでは 5 年到達不可と判断。

**根拠**: snapshot §2-1 偏在 SD ±5、§2-2 unknown 30〜45%。両者の「同時に」「構造的に」改善する案は incremental になし。
**次の問い**: Eve、これ Phase 5 で「フォーカス 5 件 + rebuild 候補 1 件」として申し送るよね？ 別 issue の Sonnet 移行は rebuild と矛盾するから降格でいい？

---

### Turn 5 — Mei

**観点**: governance
**強制テーマ**: 来週フォーカス 5 + rebuild 申し送り（合意候補）
**主張**: Eve 同意、Phase 5 申し送り内容を確定:

**今週フォーカス 5 件（v1.5 = incremental）**:
1. 🛠 decisionReason 追加（観測基盤、rebuild の判定材料にもなる）
2. 🌱 reminiscence trigger v0（E3、push 過剰の対症療法だが essence 進展あり）
3. 🌱 ThoughtTracePage MVP（観測 UI、rebuild 判定にも使える）
4. 🌱 morning mood mirror v0（E2、独立に進展可能）
5. 🛠 prototype: decision-engine 種まき（**rebuild 候補の prototype 段階を 1 つ含める**）← 5 件目を Sonnet 移行から差し替え

**rebuild 候補（Phase 5 別枠）**:
- proactive-agent + heartbeat-engine + Mei/Eve cron → 単一 `decision-engine`
- 段階: 5 件目 prototype (1-2 人日) → 2026-07 pilot → 2026-08 scale
- decide-to-rebuild: 2026-07-25 時点で unknown < 5% かつ 偏在 SD < 3 なら incremental 続行、未到達なら rebuild 確定

**Sonnet 移行は降格**: rebuild 確定で flashback skill 自体が消える可能性、rebuild 着手後に再評価。

**根拠**: Round 1 全議論。Turn 4 の 3 軸評価で incremental 単独不可と判定済み。
**次の問い**: なし（最終ターン）。

---

### Round 1 サマリ

**合意点**:
1. **incremental だけでは 5 essences 5 年到達不可**（Turn 4 の 3 軸評価）
2. proactive 偏在は判定独立構造に起因 → 構造的問題、decisionReason だけでは消えない
3. 5 件フォーカスのうち 1 件を **rebuild prototype 種まき** に充てる

**不合意点**:
1. Sonnet 移行を完全降格 vs 並行で続ける（Mei 降格、Eve は段階的継続を主張）
2. rebuild prototype を 5 件目に入れる vs 別枠に切り出す（Mei 入れる、Eve 別枠で集中投資）

**未解決の問い**（Phase 3 で Haru へ）:
1. 外部の AI agent では「単一 decision-engine」アーキテクチャの実例はあるか
2. decision-engine の段階移行で観測指標が壊れない（移行中も continuity を保つ）方法
3. v1.5 → v2 の境界線 3 軸（KPI 到達確率、複雑度、移行コスト）の数値感は妥当か
