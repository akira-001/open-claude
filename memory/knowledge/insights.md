# インサイト

*記憶の定着プロセスで更新されます。最終更新: 2026-03-29（Checkpoint #5）*

---

## INS-001: Claude Code のコンテキストコストは Session Init が支配的
**発生**: 2026-03-29 | **Arousal**: 0.8 | **ドメイン**: context-management
スキル呼び出し時のフルテキスト展開・ログ2件のフル読み込み・cogmem コマンド出力の蓄積により、セッション開始直後でも 15〜20k tokens を消費する。「まだ会話していないのにバッファーが大きい」現象の根本原因。
**対策**: contexts/ に20行ブリーフィングを事前生成し、Session Init でフルログを読まない設計へ移行。

## INS-002: /statusline コマンドは設定済みでも気づきにくい
**発生**: 2026-03-29 | **Arousal**: 0.6 | **ドメイン**: claude-code-tooling
`[ctx: 46%]` 表示を別ターミナルに出す方法を調査したとき、最初「コマンドがない」と誤答した。実際は `/statusline` スキルコマンドとして存在し、既に `~/.claude/statusline-command.sh` と `settings.json` が設定済みだった。
**教訓**: Claude Code の隠れたコマンドは `/context` や `/help` 経由だけでなくスキルとして実装されていることがある。

## INS-003: セッション間の記憶継続に必要な情報は「引き継ぎ」だけ
**発生**: 2026-03-29 | **Arousal**: 0.8 | **ドメイン**: context-architecture
フルログを毎回読む必要はなく、cogmem index があれば必要なときに検索できる。Session Init の目的は「コンテキスト復元」であり、その最小単位は「引き継ぎ（次のアクション・注意事項）」のみ。
**応用**: Wrap で 20行ブリーフィングを生成 → Session Init でそれだけ読む設計が最適。

## INS-004: autocompact バッファーは Session Init の負荷の可視化
**発生**: 2026-03-29 | **Arousal**: 0.5 | **ドメイン**: context-management
autocompact バッファー = 現在のセッション内の古いターン。セッション開始直後でも大きいのは Session Init がその場で大量のコンテンツを展開するから。バッファーサイズは Session Init の設計コストの指標として使える。
