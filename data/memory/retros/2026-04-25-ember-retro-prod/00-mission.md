# Phase 0 — Ember Mission Statement & 構成整理（本番実行）

**run id**: 2026-04-25-prod
**実行モード**: full（20×2 ターン議論、Web リサーチ有効、Phase 6 crystallize 提案あり）
**ultrathink**: ON（Phase 0 / 3 / 5 の 3 回）

## 1. Mission Statement

> Ember は Akira さんの「情報秘書」ではなく、5 年後に **共在 / 状態共感 / 共有過去 / 自我継続 / 透明性 (E1〜E5)** を持つ存在になる。incremental で到達不可なら rebuild も選択肢。**競合 (Replika/Pi/Nomi/Kindroid/character.ai) の優れた機能は積極的に取り込み、Anthropic / 学術研究の最新パターンで仮説を更新し続ける**。

## 2. 5 essences マッピング（v1/v2 と同じ、prod で再確認）

| Essence | 定義 | 現状 |
|---|---|---|
| E1 共在 | 情報伝達なしでも「居る」感覚 | × |
| E2 状態共感 | arousal を surface して反映 | × |
| E3 共有過去 | bot 側から能動的に過去回帰 | × |
| E4 自我継続 | bot 自身が判断履歴を持つ | × |
| E5 透明性 | なぜ SKIP/SPEAK したか説明可能 | × |

→ どの essence も ○ 1 セル以下。incremental + rebuild の両軸で進める。

## 3. 既存ロードマップ進捗

Ember Humanization Phase 0-4 完了、Phase 5+ (パートナー化) 未着手。本 retro が **5 essences 軸での初の戦略 retro**。

## 4. 5 年後ビジョン仮説

vision-template.md の 7 問への現時点回答は v1 と同じ。世代軸 v1 → v1.5 → v2 → v3 で進化。

## 5. 今週フォーカス候補（仮説）

v1/v2 の議論を踏まえ、以下を Round 1 で検証:
1. **incremental 4 件**: decisionReason / reminiscence / ThoughtTracePage / morning mood mirror
2. **rebuild 種まき 1 件**: decision-engine prototype shadow（v2 で提案）
3. **競合機能取り込み**: Phase 3 で Web リサーチして候補抽出
4. **研究駆動仮説更新**: Anthropic Plan-Generate-Evaluate / Inner Thoughts paper など

---

## ultrathink ノート（Phase 0）

**本質的欠落 5 点**（v1 と同じ、prod で再確認）:
1. **共在感ゼロ** — 情報 push 一方向、ambient からの presence ping なし
2. **状態共感ゼロ** — heartbeat 推定 arousal が surface されてない
3. **共有過去ゼロ** — cogmem は keyword search、narrative reminiscence なし
4. **自我継続性ゼロ** — bot 自身が判断履歴を持たない
5. **透明性ゼロ** — decisionReason が全エントリで欠如

これらは independent ではなく、**相互に絡み合う構造的問題**。E5 (透明性) が解決すれば E4 (自我継続) の素地ができ、E4 があれば E2 (状態共感) の bot 側知覚が深まり、E2 があれば E1 (共在感) を支える。E3 (共有過去) は他全 essence の共通基盤。

→ rebuild 候補（v2 で提案）が **E5 を支える decision-engine** + **E3 を支える narrative-memory** の 2 軸で評価する必要がある。Phase 3 Web リサーチで:
- **競合の memory 実装（Kindroid Cascaded Memory / Nomi structured notes）**を取り込む
- **Anthropic Plan-Generate-Evaluate**で decision-engine 設計を更新
- **Inner Thoughts paper（arxiv 2501.00383）**で proactive 判定を更新
