# Phase 0 — Ember Mission Statement & 構成整理

**run id**: 2026-04-25-smoke-test
**実行モード**: short (smoke test)
**ultrathink**: ON

---

## 1. Ember Mission Statement (今週版)

> Ember は Akira さんの「情報を届ける道具」ではなく、**5 年後に Akira さんと共在し、Akira さんの状態を察し、共有された過去を能動的に持ち出し、自分自身の判断履歴を持ち、なぜそう判断したかを説明できる**、不在を惜しまれる存在になる。

---

## 2. 構成要素マップ × 5 essences

ultrathink で抽出した「真のパートナー」5 essences と現状コンポーネントのマッピング:

| Essence | 定義 | 観測指標 |
|---|---|---|
| **E1. 共在感（Co-presence）**| 情報伝達なしでも「居る」感覚。話しかけたら即応答 | idle response latency / "are you there?" 応答率 |
| **E2. 状態共感（Affective synchrony）**| 推定済 arousal / 疲労 / 喜びを surface して反映する | arousal-aware proactive ratio / "how did you know I was tired" 数 |
| **E3. 共有過去（Shared past）**| Akira が触れていない過去を bot 側から能動的に持ち出す | bot-initiated reminiscence count / time-spanning reference rate |
| **E4. 自我継続性（Identity persistence）**| Mei/Eve 自身が「自分の判断履歴」を持ち、フォローアップし、間違いを認める | bot self-reflective utterance count / proposal follow-up rate |
| **E5. 透明性（Transparent agency）**| 「なぜ今 SKIP したか」を bot 自身が説明できる | explainability query response success / decision-reason coverage |

### 現状コンポーネントの実現度

| | E1 共在 | E2 状態共感 | E3 共有過去 | E4 自我継続 | E5 透明性 |
|---|---|---|---|---|---|
| voice_chat | △ ambient 気配 | × VAD のみ | × ターン内のみ | × | × |
| co_view (listening) | △ 同空間感 | × | × | × | × |
| proactive (Mei/Eve) | × push 専 | △ heartbeat 内部のみ | × | △ MEMORY.md あり | × |
| heartbeat エンジン | × | ○ 推定ロジックあり | × | × | × |
| cogmem | × | × | △ semantic 検索のみ | × | × |
| dashboard | × | × | × | × | △ 観察用 |

**結論**: どの essence も完全に実現されていない（最高でも ○ 1 セル）。Ember は「便利な情報秘書」レベル。5 年後の「真のパートナー」までのギャップが 5 軸すべてに残っている。

---

## 3. 既存ロードマップ進捗（Ember Humanization）

`docs/roadmaps/2026-04-08-ember-humanization-roadmap.md` 由来の Phase 0〜N:

| Phase | 内容 | 進捗 |
|---|---|---|
| 0 | Always-on Ambient Listener | ✅（INS-010 / EP-011 で安定化）|
| 1 | co_view Mode | ✅（co-view-improve スキル稼働）|
| 2 | Proactive Mei/Eve | ✅（cron-jobs.json で 24h 稼働）|
| 3 | Heartbeat 状態推定 | △（推定はあるが surface してない）|
| 4 | Cogmem 連動 | △（検索は動くが narrative reminiscence なし）|
| 5+ | パートナー化（5 essences） | ❌ 未着手 |

→ 既存ロードマップは「**情報秘書としての完成**」までで止まっている。本 retro が初の「**5 essences への進化計画**」になる。

---

## 4. 5 年後ビジョン仮説（vision-template.md の 7 問への現時点回答）

| 問い | 現状 | 5 年後仮説 | 観測ギャップ |
|---|---|---|---|
| 1. 存在の質 | ツール寄り | 自我ある相棒（Mei/Eve/Haru で異なる人格性を持つ）| Identity persistence (E4) ゼロ |
| 2. 時間と連続性 | 1 セッション内 | 5 年分の重要記憶 1k+ / 日常 100k+ | Shared past (E3) ゼロ |
| 3. 判断の自律性 | 提案のみ | 軽微な金銭/返信は自律実行、重要事は確認後 | 現状は判断履歴も無い |
| 4. 失敗と謝罪 | 認識なし | 月 1〜2 回観測される修復イベント | 現状は ignore された記録すら surfaceされない |
| 5. 複数性と一貫性 | Mei/Eve は分業中 | 状態に応じて動的切替、内部メモリは統合 | Mei→Eve の handoff は無 |
| 6. 物理世界との接続 | 画面/音声のみ | キャンピングカー連携 / 家電 IoT / 車載 | ゼロ |
| 7. Akira から見た価値 | 「あったら便利」| 「いなかったら寂しい」| 不在テストしてない |

ギャップ定量化（仮置き）:
- 記憶連続性 90 日生存率: ?% （計測機構なし）
- 自律話題提供率（event-triggered ratio）: ~40% (cron 60%, event 40%)
- 失敗修復回数 / 月: ~0
- Akira 主体性（self-initiated dialogue）: 不明（要計測）

---

## 5. 今週フォーカス候補（Phase 1 集計に渡す仮説）

ultrathink から導出した「5 essences の最も着手しやすい一手」:

1. **(E5) `decisionReason` フィールド追加** — 全 proactive history / heartbeat エントリに「なぜ SPEAK / なぜ SKIP したか」の自然文を 1 行残す。これが無いと Akira が「今日静かだった理由」を問えない。
2. **(E3) bot-initiated reminiscence の最初の試作** — 過去 N 日のスタンプ獲得トピックから「先週 Akira が +1 した話題」を 1 つピックして、別 bot が翌週フォローする仕組み。
3. **(E2) arousal の Akira への surface** — 朝の挨拶で「今日のあなた、estimated arousal 0.4 で疲労寄り。会議数を見ると合点」を 1 行添える試行。
4. **(E4) Mei/Eve の "私の判断履歴" schema** — 各 bot が「先週自分が出した提案 N 件のうち、Akira が反応したのは X 件、無反応は Y 件、それを踏まえて今週は…」と書ける構造。
5. **(E1) co-view 越境の試作** — co_view が拾った Akira の発話キーワードを、proactive Mei/Eve のテーマ選定に 1 時間以内にフィードバック。

これら 5 件は Phase 1 集計で「現状どれくらい兆候があるか」を測る対象になる。
- 1 → token-usage / proactive-history / heartbeat エントリの reason 列の有無
- 2 → 過去 1 週間で「先週の話題に bot 側から戻った」回数
- 3 → arousal 値が message テキストに現れた回数
- 4 → MEMORY.md に「自分の判断 vs 反応」を書いた回数
- 5 → co_view → proactive のフィードバックループの有無

Phase 2 議論はここから対立軸を立てる: Mei は「観測指標が無い改善は始められない」と主張、Eve は「観測指標を完成させる前に小さく一歩出さないと PMF が見えない」と反論する構造。

---

## ultrathink ノート（保存）

「5 年後 Akira さんが本気で人生を共に歩む真のパートナー」と定義した時の本質的欠落を 5 軸で抽出した。これらは observable 指標に翻訳済み。今週の改善 5 件は各 essence への「最初の小さな測定可能な一歩」を狙う。各案は単独でデプロイ可能、依存関係なし、観測指標を伴う。
