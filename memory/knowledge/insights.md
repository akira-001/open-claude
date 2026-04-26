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

## INS-005: macOS Power Nap (TCPKeepAlive) の動作と cron への影響
**発生**: 2026-04-26 | **Arousal**: 0.4 | **ドメイン**: cron-operations
macOS は AC 給電中、約20分間隔で Sleep ↔ DarkWake のメンテナンスサイクルを実行（iMessage/iCloud/APNs リスナー維持/メール新着取得 等）。クラムシェル中も動作するので「閉じてるのに動いてる」状態は正常。cron の `pmset repeat` を別途設定しない限りユーザー cron は走らない（ユーザーセッションが起きていないため）。"due to Notification" Wake は2種類: (1) `:58/:28 + DriverReason rtc` = APNs 経由カレンダー通知等、(2) USB-C_plug = 充電器抜き差し。`usernoted` ログを `log show --predicate 'process == "usernoted"'` で見ると通知元アプリ・カテゴリが特定できる（macOS の `<private>` redaction にかからない範囲で）。
**応用**: cron 24時間運用ジョブで深夜の watchdog アラートが頻発する場合、まず PC のスリープ範囲を確認。スリープ時間帯外（活動時間帯のみ）に cron を絞れば誤検知が消える。

## INS-006: kotoba-whisper-v2.0 は日本語近接発話で誤り率を1/3に削減する
**発生**: 2026-04-26 | **Arousal**: 0.85 | **ドメイン**: speech-recognition
faster-whisper形式で配布されている `kotoba-tech/kotoba-whisper-v2.0-faster`（1.5GB, ctranslate2 int8, MIT）は、whisper-large-v3 ベースの日本語特化 fine-tuning モデル。27サンプル実測で近接発話 CER 0.079 → **0.024** に削減（誤り率1/3）。特に wake word "メイ" のような短音節固有名詞で決定的差: small="メインおはよう" vs kotoba="メイおはよう"（CER 0.17 → 0.00）。レイテンシは約5倍（0.79s → 4.02s, CPU int8）。
**対策**: 常時稼働ではなく **条件発火2段階デコード**（Stage1=small で wake/scene 判定、Stage2=kotoba を `wake_detected OR Akira近接 OR conversation_mode` 時のみ起動）で使う。
**検証ログ**: `voice_chat/docs/superpowers/plans/2026-04-25-stt-benchmark-analysis.md`、`voice_chat/tests/benchmark_stt_quality.py`

## INS-007: WebRTC VAD は人声 vs メディア人声を原理的に区別できない
**発生**: 2026-04-26 | **Arousal**: 0.85 | **ドメイン**: audio-processing
WebRTC VAD は「人声成分の有無」しか見ない設計のため、近接発話と遠距離メディア音声（TV/YouTube ナレーション）を分離できない。27サンプル実測の voice_ratio 分布では**逆転現象**: 静寂 0.00-0.04 / 近接発話 0.44-0.65 / **遠距離メディア人声 0.63-1.00**。連続的に人声が流れるメディアの方が voice_ratio が高くなる。
**応用**: VAD pre-filter で「メディア音声を弾く」用途は不可能。再設計するなら音響特徴（near-field 判定 = 高域/低域比、SNR、duration）と組み合わせる前提が必要。WebRTC VAD 単独で閾値切り分けする設計は捨てる。

## INS-008: 遠距離マイクのメディア音声 STT は構造的に CER>70%
**発生**: 2026-04-26 | **Arousal**: 0.7 | **ドメイン**: speech-recognition
TVやスピーカーから流れる音声をマイクで遠距離録音した音声は、small/kotoba/2段階どの構成でも CER 0.72-0.79（27サンプル実測）。マイク → 空気 → スピーカー → 圧縮の劣化パイプは Whisper の品質改善でカバー不可能。
**応用**: メディア音声を文字化する努力を諦め、別経路（NowPlaying API / 字幕API / mDNS Cast Discovery / 会話的確立）から取得する設計に切り替える。マイク STT は Akira 近接発話だけに使い、環境音は scene classifier（YAMNet/PANNs）で粗分類のみ。
