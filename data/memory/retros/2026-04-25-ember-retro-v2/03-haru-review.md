# Haru レビュー — Round 1（v2 run）

**phase**: 3
**Web 調査**: スキップ（`--skip-haru-web`）
**v2 の特徴**: Round 1 で **incremental 限界を明示的に判定**し、rebuild 候補が Round 1 サマリに既に出ている。Haru の役割は rebuild 候補を**外側から検証**+ Round 2 への問いを返す。

---

## 1. 外部環境スキャン

スキップ。本来であれば以下を調査:
- LangGraph / OpenAI Assistants で「単一 decision-engine」アーキテクチャの採用状況
- Replika / Pi.ai が独立 cron 並列構造を捨てたか
- Anthropic agent SDK の design pattern

---

## 2. Round 1 への所見

| Turn | 評価 | 補正・追加観点 |
|---|---|---|
| 1 | ⭕ 守りの成功は valid。攻め空白も自覚あり | — |
| 2 | ⭕⭕ 判定独立構造の指摘が鋭い。snapshot §2-1 の SD は強い証拠 | 「諦めた」仮説（v1 で議論）も同根。bot 数を減らす根本対処 |
| 3 | ⭕⭕ zero-base ideation として品質高い。Q1〜Q7 マッピングも適切 | ただし「全廃 4 cron」のリスク見積もりが浅い。移行中の dual-run 期間が必要 |
| 4 | ⭕⭕ 3 軸評価フレーム優秀。ただし② アーキ複雑度の数値根拠が弱い | LOC / file count で測れる。pilot 前にベースライン取得を |
| 5 | ⭕ Sonnet 降格は妥当。5 件目に prototype 種まきも合理的 | ただし**今週 5 件目を rebuild 種まきにする**選択は重い。Akira 介入チェックポイント必須 |

---

## 3. 費用対効果マトリクス（rebuild 候補を含む）

| 案 | コスト | 効果 | 撤退条件 | ROI |
|---|---|---|---|---|
| 1. decisionReason | dev 0.5 人日 + LLM tok | unknown 30〜45% → 5% | rebuild で消えるならスキップ | ◎（観測整備） |
| 2. reminiscence v0 | dev 1 人日 | E3 自発参照 0 → 週 1 件 | 効果なしなら凍結 | ◎ |
| 3. ThoughtTracePage | dev 1 人日 | E5 体感化 | rebuild で schema 変わるなら作り直し | ○ |
| 4. morning mood mirror | dev 2 人日 | E2 surface 第一打 | 反応 0 なら凍結 | ◎ |
| 5. **🌍 decision-engine prototype** | dev 1-2 人日（並列稼働、観察モード）| pilot 判断材料 | prototype で「結局 incremental で十分」と判明したら凍結 | **◎ 戦略最重要** |

**Sonnet 移行**: rebuild と矛盾するため Round 2 で正式に降格判定推奨。

---

## 4. 5 年ビジョン整合性

vision-template Q1〜Q7 と今週フォーカスのマッピング（rebuild prototype 込み）:

| 問い | フォーカス効く案 |
|---|---|
| Q1 存在の質 | 1, 5（rebuild 後のアーキで自我設計可能になる）|
| Q2 連続性 | 2 |
| Q3 自律性 | 1, 4 |
| Q4 失敗修復 | 5（decision-engine なら decision history が自然に蓄積）|
| **Q5 複数性と一貫性** | **5（最直接、現状の独立 cron は Q5 と構造的に矛盾）** |
| Q6 物理世界 | 2（reminiscence 初回テーマで布石）|
| Q7 不在を惜しまれる | 2 |

→ **rebuild prototype (案 5) は Q1/Q4/Q5 に効く戦略案件**。incremental 4 件は Q2/Q3/Q6/Q7 をカバー。**5 件揃って初めて 7 軸全カバー**。

---

## 5. Round 2 への問い 3 件

### Q1（Eve Turn 3 への問い直し）

**zero-base 案の "全廃 4 cron" のリスクは過小評価では？**

prototype 段階で「並列稼働、観察モード」とあるが、Mei/Eve の独立性を一部失う移行中の体験は Akira 視点で連続性を破る可能性。Round 2 で**段階移行中の Akira 体験保証**を 1 つ提案せよ。

### Q2（Mei Turn 4 への問い直し）

**3 軸評価の数値根拠を強化**

② アーキ複雑度の評価が定性的。Round 2 で **LOC / file count / 結合度メトリクス** で incremental 12 ヶ月後 vs rebuild 12 ヶ月後の数値ベースライン取得を planning に組み込め。

### Q3（戦略軸からの問い）

**rebuild 確定タイミングを前倒すべきか？**

Round 1 では「2026-07-25 判断」だが、incremental 限界が Turn 4 で既に判明している。**判断時期を 2026-06-15 に前倒しできないか**？早期判断はリスク（観測データ不足）と利得（dev リソース効率）のトレードオフ。Round 2 で評価せよ。

---

**Haru は Phase 3 では結論を出さない**。Phase 5 ultrathink で全議論統合 + rebuild 候補を最終確定する。
