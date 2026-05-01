# インサイト

*記憶の定着プロセスで更新されます。最終更新: 2026-05-01（Checkpoint #8）*

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

## INS-009: 外部ライブラリ・モデルでハマったらコード診断より先に Web Issue を確認
**発生**: 2026-05-01 | **Arousal**: 0.85 | **ドメイン**: debugging-process
外部ライブラリ・SDK・蒸留モデルなど「動くはずの構成が動かない」状態は、ライブラリ側の既知挙動（必須パラメータ、訓練データ起因の制約等）が原因のことが多い。これを自前のログ追加・統計収集で発見しようとすると数十分〜数時間溶かす。**Web 1 検索で 5 分で解決**できるケースが珍しくない。
**確認順序**: (1) 公式モデルカード / README の Quick Start コード例を実装と差分比較 → (2) GitHub Issues で「empty / 0 / not working」系キーワード検索 → (3) HuggingFace Discussions（モデル特有の質問が集中）。当てはまる Issue を見つけたら、コード診断は中断して Issue の解決策を先に試す。
**実例**: kotoba-whisper-v2 切替で 30 分以上、フィルタ緩和や PCM 統計ログを次々追加していたが、HF モデルカードに「`chunk_length=15` `condition_on_previous_text=False` 必須」と明記されていた（後で確認したら結局これでも 0 segments で別の構造的問題だったが、まず確認すべきだった）。
**応用**: 新規ライブラリ・モデル採用時の最初の 5 分を「公式 Quick Start のコピペ実行」「Issues を 'empty/empty output/not working' で検索」に必ず使う。

## INS-010: STT 系で peak/rms 比が連続発話の signature
**発生**: 2026-05-01 | **Arousal**: 0.6 | **ドメイン**: audio-processing
PCM 入力の peak と rms の比（peak/rms）が **5〜10x** なら通常の連続発話、**>50x** なら短い大音量パルス（キーボード・マウス・机振動等の transient noise）が静かな背景に乗っている状態。後者を Whisper に渡すと訓練データに無い波形でハルシネーション（英単語混在、繰り返し etc）。
**実例**: PC 向きを変えて「音量が上がった」つもりで peak 0.47 / rms 0.0069（比 68x）になり、whisper の出力が「ERERERERER... boatswast Cypésulteemn」のような完全 garbage に。peak だけ見ると音量改善だが rms が伴わないと SNR は悪化している。
**応用**: STT 入力前に peak/rms 統計をログし、比 >30x なら **transient-dominant** とフラグ立てて transcribe を skip する or 警告する。ゲイン正規化は peak だけでなく peak/rms 比のチェックとセットで行う。

## INS-011: 共有ブラウザはスクラッチ不要、Browserbase + Playwright で実現できる
**発生**: 2026-05-01 | **Arousal**: 0.5 | **ドメイン**: browser-automation, ai-agent-architecture
GitHub openagents-org/openagents の共有ブラウザ機能（複数エージェント + 人間が同じ画面を観察しながら操作する）はゼロから書かれていない。**Browserbase（クラウド SaaS、$0.10/min 程度）** で起動した Chromium インスタンスの `liveUrl` を iframe 表示し、Playwright が CDP 経由で操作、persistent context で認証永続化する。ローカル fallback は Playwright Chromium headless + スクショ画像で代替（ライブ感は弱い）。
**応用**: Slack で同等機能を作る場合「Browserbase iframe を Canvas/メッセージに貼る」or「ローカル Playwright + スクショ投稿」の 2 択。ライブ性が必要なら課金、なくて良いなら無料で構築可能。Akiraさんの Mei + Eve + cogmem は意味記憶で OpenAgents を上回るが、ライブ操作機能は Browserbase 相当が必要。

## INS-012: 認証必須 Web 調査は「人間ログイン → AI 抽出復帰」往復モデルが効く
**発生**: 2026-05-01 | **Arousal**: 0.7 | **ドメイン**: human-ai-collaboration, browser-automation
認証必須サイト（YouTube 履歴、Google Calendar、SaaS 管理画面、銀行サイト）への AI アクセスは、**human-only 領域（パスワード/2FA）と AI-only 領域（DOM 抽出）を明確に分離する**設計が成立する。具体: headed Chromium を CDP モードで起動 → AI が遷移しログアウト検知 → 人間に「ログインして」と依頼（パスワード手動入力、AI は介入しない）→ 完了通知を受けて AI が抽出再開。プロファイル `--user-data-dir=~/.cache/livebrowse-profiles/<name>` で認証情報は永続化、初回だけログインすれば次回以降は自動。
**実例**: YouTube 視聴履歴 34 件 / Google Calendar 今日の予定 5 件を、Akiraさんが 1 回ログインしただけで以降ログイン不要で抽出。閉じる時の graceful shutdown を守れば Cookie は永続化される。
**応用**: 機密性の高いデータ（クライアント企業の管理画面など）でも、Akiraさんが認証だけ手動で済ませれば AI が後続の収集・分析を担える分業が可能。`livebrowse` スキル（`~/.claude/skills/livebrowse/`）として運用化済。Slack ではこの往復が難しいので、ローカル CLI / 同じマシン上での運用に向く。

## INS-013: Akiraさんは明示訂正マーカーをほぼ使わない（短い再指示が事実上の訂正）
**発生**: 2026-05-01 | **Arousal**: 0.8 | **ドメイン**: user-modeling, conversation-design
Humanness v1 計測中、5 週間の Slack 会話ログ全件を走査して訂正マーカー（「違う」「そうじゃない」「じゃなくて」等）の出現を調査した結果、**実質 0 件**だった。Akiraさんは短い再指示（30 字未満で 60 秒以内、ack 系でない）で軌道修正するスタイル（例: 「重複登録で。」「Slackの画面になってるよ」「co-viewのSlack送信先調べて」「もう一度送って」）。
**含意**: 訂正検出ヒューリスティクスを「明示マーカー」だけに頼ると Akiraさんに対しては検出ゼロになる。**explicit_count（高精度・低再現）と redirect_count（低精度・高再現）の二系統** で測るのが正解。秘書・パートナー型 AI のチューニングでは Akiraさんが言わなかったことから推測する設計が必要。
**応用**: ユーザー識別子としても価値ある特徴。proactive 提案が滑った時の検出、ペルソナ修正のフィードバック収集、co_view の介入タイミングなど、Akiraさんが「ダメ」と明示しないシグナルを拾う仕組みを別途用意する必要がある。

## INS-014: 「人間に近い問答」は単一指標で測れない（三層モデル）
**発生**: 2026-05-01 | **Arousal**: 0.7 | **ドメイン**: ai-evaluation, ember-design
汎用ベンチマーク（Chatbot Arena / MultiChallenge / EQ-Bench / HLE）は **「Akiraさん個人にとっての自然さ」** を測れない。Ember は「常時稼働パートナー」であって「ベンチマーク提出 LLM」ではないため、運用ログから取れる Akiraさん固有の signal を最優先にする三層モデルが必要:
1. **表層（friction_rate）**: 「Mei/Eve は意図を 1 発で読み取れているか」
2. **反応層（proactive engagement）**: 「打った球は Akiraさんに刺さっているか」
3. **深層（persona consistency）**: 「キャラが状況に応じて壊れていないか」
**応用**: humanness v1 は三指標を `memory/metrics/humanness/YYYY-MM-DD.json` に記録。v2 候補 = 記憶想起精度、感情トーン整合、会話継続ターン数、co_view 介入頻度。Ember の「人間らしさ進化」を数字で追跡できる初の枠組み。
