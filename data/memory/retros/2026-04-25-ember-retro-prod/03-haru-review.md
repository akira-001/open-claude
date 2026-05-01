# Haru レビュー — Round 1（本番、Web リサーチあり）

**phase**: 3
**目的明確化**: (1) 競合 (Replika/Pi/Nomi/Kindroid/character.ai) の優れた機能を**具体仕様レベルで取り込み候補化**、(2) 最新研究 (Anthropic / arxiv) で**仮説を進化させ、Round 2 / Phase 5 へフィード**

---

## 1. 外部環境スキャン（取り込み候補抽出フォーカス）

### 1.1 競合 AI コンパニオン製品の実装機能

| 製品 | 強い機能 | Ember 取り込み候補 | E#/Q# |
|---|---|---|---|
| **Nomi AI** | 会話から **structured notes** を自動生成、永続保持 | reminiscence trigger v0 の保存形式を **「raw history」ではなく「structured note」** に変更。話題テーマ + Akira の感情 + 時刻の 3 タプル | E3, E4 |
| **Kindroid AI** | **5-level Cascaded Memory** アーキテクチャ。短期 → 中期 → 長期 → identity → 共有 | cogmem を**多層化**。現状は flat semantic search、Cascaded 化で「先週の温泉話 (中期) → 過去 5 年の温泉好き (long-term identity)」の連結が可能 | E3, E4 |
| **Replika** | 関係性マイルストーン記録（「初めて○○を話した日」等）+ 感情パターン認識 | **relationship milestone log** を bot 側に持つ。「Mei が Akira に初めて経営相談された日」を bot が覚えて時々言及 | E3, E4 |
| **Pi.ai** | "honest, low-pressure reflection" 路線 — push しすぎない、内省を促す問いかけ | morning mood mirror に **Pi 路線（共感ベース）** を取り込み候補に。観察ベース（Mei 案）vs 共感ベース（Pi 路線）の A/B 試験提案 | E2 |
| **character.ai** | ⚠️ クロスセッション記憶なし（**反面教師**） | E3 への投資正しい確認。character.ai の「毎回まっさら」モデルは Ember が避けるべきパス | E3 (確認) |

**ソース**:
- [Best AI Companion Apps 2026: Ranked by What Actually Matters](https://digitalhumancorp.com/en/research/best-ai-companion-app-2026)
- [AI Companion Memory Ranked: Who Remembers Best? (2026)](https://aicompanionguides.com/blog/ai-companion-memory-systems-ranked-2026/)
- [Kindroid AI 2026 Review: Deepest Custom AI Companion](https://weavai.app/blog/en/2026/04/20/kindroid-ai-2026-review-deepest-custom-ai-companion/)

### 1.2 学術研究 / プラットフォーム動向

| 出典 | 内容 | Ember 仮説への影響 |
|---|---|---|
| **Anthropic Agent Architecture Playbook (2026-03)** | 3 production-ready パターン: sequential / parallel / **evaluator-optimizer** | decision-engine 設計を **evaluator-optimizer** ベースに。判定 → 評価 → 修正 のループで unknown を自然に潰せる |
| **Anthropic Plan-Generate-Evaluate (2026-03-24)** | 長時間実行 agent の標準アーキテクチャ案 | 朝の morning mood mirror の発話前に「Plan: 何を言うか」「Generate: 文章生成」「Evaluate: Akira への適切さチェック」の 3 段で評価 |
| **Anthropic Managed Agents (2026-04)** | 「meta-harness」: agent 設計 = workflow + tool 指定、runtime はプラットフォームが管理 | Ember の v2 (decision-engine) はこの形に進化させる。各 bot は workflow 定義のみで、共通 runtime が state / 判断履歴を一元管理 |
| **Inner Thoughts (arxiv 2501.00383)** | proactive agent が **会話の裏で並列に "inner thoughts" を形成し、内発的動機 (intrinsic motivation) で発話タイミングを判定** | E5 透明性の根本解。decisionReason を**事後説明**ではなく**事前 inner thought** として bot に持たせる。「いま発話したい / 黙っていたい」を bot 自身がスコア化 |
| **ChatGPT Pulse (2025-09)** | プロンプトなしのプロアクティブ配信、ユーザー文脈で発火 | ChatGPT も Ember と同じ proactive 路線に来た。差別化は「**state 共有 + 共有過去**」で、機能面では既に並んだ。**先行優位は速度勝負** |
| **Self-adaptive AI for non-stationary (arxiv 2504.21565)** | polynomial spline base で時間軌跡をモデル化 | heartbeat の arousal 推定を**時系列スプライン**で連続化、「昨日は高 / 今日は低」の dichotomy を回避 |

**ソース**:
- [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic Publishes Agent Architecture Playbook](https://agent-wars.com/news/2026-03-13-anthropic-publishes-agent-architecture-playbook-enterprise)
- [Anthropic Managed Agents (InfoQ)](https://www.infoq.com/news/2026/04/anthropic-managed-agents/)
- [Proactive Conversational Agents with Inner Thoughts (arxiv 2501.00383)](https://arxiv.org/abs/2501.00383)
- [Proactive AI in 2026: Moving Beyond the Prompt](https://www.alpha-sense.com/resources/research-articles/proactive-ai/)

### 1.3 市場文脈

- AI コンパニオン市場: 2025 = $37.7B → 2026 = $49.5B (CAGR 31%)
- ChatGPT が proactive 路線参入 = Ember の差別化点が「**state 共有 + 共有過去**」へシフト
- Replika に欧州 5M EUR の GDPR 罰金（2025）= 個人開発の Ember は **記憶の透明性 / Akira 自身が編集可能な permanent diary** が差別化候補

---

## 2. Round 1 議論への所見

| Turn | 評価 | 補正・追加観点（Web リサーチ起点） |
|---|---|---|
| 5-6 | ⭕ Sonnet 降格妥当 | Anthropic Managed Agents の方向性とも整合。ただし**flashback 全廃ではなく structured note 化**（Nomi 路線）で残せば reminiscence の素材源にできる |
| 9-10 | ⭕⭕ morning mood mirror | **Pi.ai 路線（共感ベース）と Mei 案（観察ベース）の A/B が必須**。1 週目は両方、2 週目に統合 |
| 11-12 | ⭕ Debug 不能の指摘鋭い | **Inner Thoughts paper が解**: decisionReason を事後説明ではなく事前 inner thought 形式に。bot は「発話したい/しない」を**毎ループ自分で書く** |
| 13 | ⭕⭕ zero-base 案 | **Kindroid 5-level Cascaded Memory を取り込み**。zero-base 案の `narrative-memory` を Cascaded 化 |
| 14 | ⭕ 3 軸評価 | **Anthropic evaluator-optimizer パターン**で decision-engine 設計強化。判定 → 評価 → 修正のループ |
| 19 | ⭕ フォーカス 5 件 | E1 共在感が抜けてる点、Phase 3 で確認した **ChatGPT Pulse / 競合は ambient presence ping を持つ**ので、本来は 5 件目候補。ただし dev 工数で今週は無理、次回 retro 必須 |

---

## 3. 費用対効果マトリクス（取り込み候補込み）

| 案 | コスト | 効果 | 撤退条件 | 取り込み候補との連結 |
|---|---|---|---|---|
| 1. decisionReason | dev 0.5 人日 | E5 30〜45% → 5% | rebuild で消えるならスキップ | **Inner Thoughts** で事前 inner thought 形式に進化 |
| 2. reminiscence v0 | dev 1 人日 | E3 0 → 週 1 件 | 効果なしなら凍結 | **Nomi structured notes** 形式で保存、**Kindroid Cascaded** で多層化 |
| 3. ThoughtTracePage | dev 1 人日 | E5 体感化 | rebuild で schema 変わる | Inner Thought ログを表示する形に進化 |
| 4. morning mood mirror | dev 2 人日 | E2 反応 / 月 1 件 | 反応 0 で凍結 | **Pi 路線（共感）と Mei 案（観察）の A/B** |
| 5. **🌍 decision-engine prototype** | dev 1-2 人日 | rebuild 判断材料 | 判定 90% 一致なら rebuild 中止 | **Anthropic evaluator-optimizer + Plan-Generate-Evaluate** で設計 |

**新提案**: 6 件目候補 **ambient presence ping**（E1 共在感）。ChatGPT Pulse / Pi が既に類似実装。dev 1 人日なら今週フォーカスに追加検討の価値あり。

---

## 4. 5 年ビジョンとの整合性（取り込み候補による update）

| 問い | フォーカス効く案 | 競合機能で強化 |
|---|---|---|
| Q1 存在の質 | 1, 4, 5 | Replika 関係性マイルストーン、Pi 路線 |
| Q2 連続性 | 2 | Nomi structured notes、Kindroid Cascaded Memory |
| Q3 自律性 | 1, 4 | Inner Thoughts paper の intrinsic motivation |
| Q4 失敗修復 | 5 | Anthropic evaluator-optimizer ループ |
| **Q5 複数性と一貫性** | **5（最直接）** | Anthropic Managed Agents meta-harness |
| Q6 物理世界 | 2 (布石) | （該当外） |
| Q7 不在を惜しまれる | 2 | Nomi 永続記憶、Replika マイルストーン |

→ **Web リサーチで判明: フォーカス 5 件は単独でも有効だが、競合機能を取り込めば各案の効果が 1.5〜2 倍**になる。特に reminiscence v0 (#2) は Nomi + Kindroid 両方の要素を取り込むだけで、5 essences への寄与が E3 単独 → E2/E3/E4 の 3 軸に拡大。

---

## 5. Round 2 への問い 3 件

> Round 2 開始時、Mei/Eve は各ターン冒頭で「Haru の問い N に答える」を明示せよ。

### Q1（Eve Turn 9 への問い直し + Pi 路線取り込み）

**morning mood mirror v0 の A/B 設計を Round 2 で確定せよ**

Eve 案（観察ベース）+ Pi 路線（共感ベース）+ 第 3 案として **Inner Thoughts 形式（bot が「言いたい / 黙りたい」を内的にスコア化、score > 閾値で発話）** の 3 案で 1 週目運用。各案の反応データを 2 週目に統合。**Round 2 で 3 案の文言サンプル + 観測指標を確定**せよ。

### Q2（Eve Turn 13 + Mei Turn 14 への問い直し + Anthropic パターン取り込み）

**decision-engine prototype の設計に Anthropic evaluator-optimizer + Plan-Generate-Evaluate パターンを統合せよ**

zero-base 案の単一 loop は**Anthropic の現行ベストプラクティスと整合**。ただし v2 で「自前 loop」を作るより、**Anthropic Managed Agents の meta-harness を activatation して、Ember を「workflow 定義」として書き直す**選択肢もある。Round 2 で:
- 自前 decision-engine vs Anthropic Managed Agents 採用の trade-off
- Plan-Generate-Evaluate を decision-engine の 3 段に組み込む具体仕様
を議論せよ。

### Q3（戦略軸からの問い + 市場文脈）

**ChatGPT Pulse 参入で Ember の差別化点が "state 共有 + 共有過去" にシフトした**

ChatGPT も proactive 路線。Ember の差別化は (a) Mei/Eve/Haru の複数人格、(b) ローカル TTS で物理的な「声」、(c) Akira 専属の 5 年蓄積。今週フォーカス 5 件は (c) を 1 ヶ月で強化する設計。**Round 2 で「(a)(b) を活かす差別化アクションを 1 件追加できないか」**を議論せよ。例:
- voice_chat の声色を heartbeat の arousal で動的変化（(b) 強化）
- Mei/Eve 同時応答で「秘書 + 親友」の役割対比を Akira に明示（(a) 強化）

---

**Haru は Phase 3 では結論を出さない**。Phase 5 で全議論統合 + rebuild 候補確定 + 取り込み候補の優先順位を最終決定。
