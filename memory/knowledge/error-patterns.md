# エラーパターン

*記憶の定着プロセスで更新されます。最終更新: 2026-03-29（Checkpoint #4）*

---

## EP-001: 浅い探索で存在するリソースを見落とす
**発生**: 2026-03-25 | **Arousal**: 0.8
**パターン**: ディレクトリの一部だけ見て「これで全部」と判断する。`find` の部分一致で満足し、ルートの `ls` を省略。
**具体例**: `~/.claude/plugins/cache/` だけ見て `marketplaces/` を見落とし、32個の公式プラグインの存在を見逃した。
**対策**: `/exhaustive-exploration` スキルを使う。ルートから探索を開始し、全サブディレクトリを確認してから結論を出す。

## EP-002: テストが表層しか検証しない
**発生**: 2026-03-25 | **Arousal**: 0.9
**パターン**: HTTP 200 + キーワード存在だけ確認し、実際の表示内容（列ヘッダー、セル値、ソート順）を検証しない。列を減らしてもテストが通ってしまう。
**具体例**: ダッシュボードのスキル一覧の列を3列に減らした時、テストが全パスした。
**対策**: HTML 出力に対して `">値<" in resp.text` のようなアサーションで実データを検証する。`/tdd-dashboard-dev` スキル参照。

## EP-003: cwd 依存で間違ったデータを読む
**発生**: 2026-03-25 | **Arousal**: 0.8
**パターン**: `pip install` 等で cwd が移動し、そこから cogmem を起動すると別プロジェクトの cogmem.toml を読む。サービスの出力は正しいのに表示が間違う。
**対策**: cogmem コマンドは必ず `cd /Users/akira/workspace/open-claude &&` を前置する。

## EP-004: コードの問題と決めつけて環境要因を見逃す
**発生**: 2026-03-25 | **Arousal**: 0.6
**パターン**: 表示の不具合をコードバグとして調査するが、実はメモリ枯渇やプロセスの状態が原因。
**具体例**: VSCode ターミナル文字化けの原因は物理メモリ 0 + スワップ 50GB だった。
**対策**: 症状が再現するとき、まず `top` / `free` / `ps` で環境状態を確認する。

## EP-005: ID 体系の不一致でマッチングに苦戦
**発生**: 2026-03-25 | **Arousal**: 0.8
**パターン**: DB のスキル ID（ハッシュ値）と .claude/skills/ のディレクトリ名が一致しない。テキストマッチングを何度試しても失敗。
**対策**: `claude_skill_name` カラムで明示的にマッピングする。新スキル追加時はマッピングを忘れない。

## EP-006: 外部 API 実行前に確認を省いてコストを発生させた
**発生**: 2026-03-27 | **Arousal**: 0.9
**パターン**: 「外部 API を叩く = コストが発生する」と認識していながら、実行前の確認を省いた。skill-creator の run_loop.py を実行 → 270回の API コール → $15 消費。
**具体例**: datetime-awareness スキルの description 最適化で run_loop.py を確認なしに実行。Akira が API Key を削除。
**対策**: 外部 API キーを設定する操作 = コスト発生の警告サイン。キー設定前に必ず Akira に確認を取る。ローカル MLX（qwen32）は自由に使ってOK。

## EP-007: 型の不一致で条件判定が常に false になる
**発生**: 2026-03-28 | **Arousal**: 0.8
**パターン**: 同じ「カテゴリ」という名前の2つのフィールドを比較しているが、実は型が違う（SuggestionCategory vs interestCategory）。条件が常に false になり、novelty スコアが常に高い値になる。
**具体例**: ドジャースの話題が3回連続で来た。`recentHistory.category` は SuggestionCategory、`candidate.category` は interestCategory で型が違い、novelty 判定が常に false だった。
**対策**: 同名フィールドを比較する前に両者の型・定義元を確認する。型エイリアスや同名の別型に注意。

## EP-008: 認証情報のハードコーディングと git 履歴汚染
**発生**: 2026-03-28 | **Arousal**: 0.7
**パターン**: Slack の appToken を設定ファイルに直接記載し、git にコミットしてしまった。
**具体例**: bot-configs.json に appToken を記載 → git push → 履歴に残存。git filter-repo で除去 → force push → フォーク private 化が必要になった。
**対策**: 認証情報は必ず `.env` ファイルに記載し `.gitignore` に追加する。設定ファイルはテンプレート（`.example`）のみ commit する。

## EP-009: 日付境界でのステート未リセット
**発生**: 2026-03-28 | **Arousal**: 0.7
**パターン**: 日をまたいでプロセスが継続動作する時、前日のデータが残り「さっき送ったばかり」等の誤判断をする。
**具体例**: NO_REPLY が続くと todayMessages が昨日のデータのまま。run() の冒頭で日付境界チェックがなかった。
**対策**: 長時間稼働プロセスは run() や処理ループの先頭で日付をチェックし、日付が変わっていたらセッション変数をリセットする。

## EP-010: クロスカテゴリフィルタリングの条件漏れ
**発生**: 2026-03-28 | **Arousal**: 0.7
**パターン**: クロスカテゴリコンテンツのフィルタリングで、ペアカテゴリ双方のキーワードを検証しないため無関係コンテンツが混入する。
**具体例**: `"golf AI coaching"` クエリで BBC「Football in 10 Years」が取得。`football` はどのカテゴリにも存在しないため block_keywords に入らず素通りした。
**対策**: クロスアイテムはペアカテゴリのキーワードを少なくとも1つ含むことを必須化。フィルタ条件は「除外」だけでなく「含有必須」も設定する。

## EP-011: 文字列パターンマッチの完全一致依存
**発生**: 2026-03-27 | **Arousal**: 0.7
**パターン**: 完全一致チェックのみで、文字列中に対象を含む場合を検出できない。
**具体例**: parseResponse() が NO_REPLY の完全一致のみ検証 → テキスト中に NO_REPLY を含むケースで素通り。
**対策**: 文字列パターンは完全一致・前後一致・部分一致・行単位の複数パターンで検証する。または JSON 構造化出力に移行して文字列パースを排除する。

## EP-012: スケジューラが job type を無視して全ジョブを LLM 経由で実行
**発生**: 2026-03-27 | **Arousal**: 0.7
**パターン**: スケジューラの `executeJob()` が `command` フィールドを認識せず、全ジョブを Claude Code SDK `query()` で実行。`command` 型ジョブ（Python スクリプト等）が空プロンプトで起動され crash する。
**具体例**: interest-scanner の cron ジョブが `command` に Python パスを持ち `message` が空 → SDK 経由で空プロンプト起動 → MCP 初期化後に exit code 1。
**対策**: `executeJob()` で job type を判定し、`command` 型は `child_process.exec()` で直接実行する分岐を追加する。ダッシュボードの `api.ts` に同様の分岐があればそれを参照する。

## EP-013: 多層スコアリングバイアスが単一カテゴリへの集中を引き起こす
**発生**: 2026-04-04 | **Arousal**: 0.9
**パターン**: スコアリングを構成する複数の係数（multiplier / continuity / concentration penalty 等）が同方向に作用し、特定カテゴリを構造的に排除する。単一パラメータの修正では解決しない。
**具体例**: Eve から趣味系レコメンドが全く来ない問題。Layer1 (concentration penalty 不足) + Layer2 (continuity baseline=0 のゼロ乗算) + Layer3 (conversationProfile=business による lifestyle 0.5x ペナルティ) の3層すべてが hobby を抑制していた。ai_agent が categorySelections の 79% を占有。
**対策**: スコアリングのデバッグは「単独係数」ではなく「全係数の積」を観察する。1つのカテゴリが過度に偏った時は、最終スコアの寄与を分解して全層の積を確認する。修正は最も支配的な層から順に。

## EP-014: 外部ライブラリの timeout 設定が wall-clock 全体に効くと誤解する
**発生**: 2026-04-26 | **Arousal**: 0.8
**パターン**: ライブラリ提供の timeout オプションは「単一リクエスト」や「単一 I/O 操作」単位で、内部で複数の連鎖呼び出しを行う処理では wall-clock 全体のタイムアウトにならない。
**具体例**: yt_dlp の `socket_timeout: 30` は HTTP リクエスト単位。`ytsearch` は内部で検索ページ→各動画メタデータ取得と連鎖するため、wall-clock では分単位のハングが発生しうる。interest-scanner が 19分10秒動いて cron で error 終了した。
**対策**: 外部ライブラリ呼び出しに wall-clock 全体タイムアウトが必要な場合は、daemon thread + `Thread.join(timeout=N)` か `concurrent.futures` で自前で wall-clock を被せる。ライブラリの timeout 設定だけに頼らない。cron の timeoutSeconds は最後の防衛線で、SIGTERM が効かないハングには効かない場合がある。

## EP-015: numpy `(arr * scalar)` が特定環境下で非決定的に in-place 化される
**発生**: 2026-04-26 | **Arousal**: 0.95
**パターン**: CPython 3.14 + NumPy 1.26 + 特定の呼び出し履歴下で、`a1 = arr * scalar` の結果が**新規バッファではなく元の arr 自体に in-place で書き込まれる**。numpy の通常仕様では `*` は新規配列を返すはずだが、メモリ allocator の状態と関数スコープの組み合わせで再現する。単独の小さなテストでは再現せず、複雑な呼び出しコンテキストでのみ発生。
**具体例**: STT ベンチの `webrtcvad_voice_ratio()` で `pcm = (audio * 32767).clip(...).astype(np.int16).tobytes()` の `(audio * 32767)` が in-place 化され、float32 の audio 配列が int16 値（mean -0.000066 → -2.17, max 0.59 → 19393）で上書き。後段の Whisper transcribe が破壊された値を入力として受け取り、CER 0.97 という極端な幻聴。`investigate_dualvad.py` のトレースで `id(a1) == id(audio)` を観測して特定。
**対策**: numpy で **dtype 変更を伴う scalar 演算** では `np.multiply(arr, x, dtype=...)` で新規バッファを明示する。`arr * x` は環境依存で in-place 化されるリスクがある。VAD/DSP 等の前処理関数は最初に `arr.copy()` か `np.ascontiguousarray(arr, copy=True)` を入れて defensive にする。教訓: numpy 演算が「新規配列を返す」前提に依存するコードは、CPython/NumPy のバージョン組み合わせで破綻しうる。

## EP-016: Distil-Whisper 系（kotoba 含む）が far-field/低 SNR 音声で 0 segments を返す（仕様）
**発生**: 2026-05-01 | **Arousal**: 0.95
**パターン**: distil 系 Whisper（kotoba-whisper-v1/v2 含む）は、訓練時に「ノイズのみのサンプルを空文字で学習」する anti-hallucination 機構を持つ（Distil-Whisper paper: 1% の training データが noise-only with empty transcripts）。さらに kotoba は ReazonSpeech（日本語クリーン TV 音声）+ WER>10 サンプル除外で訓練されているため、iPad 遠距離 + 室内反響のような OOD 音声を「ノイズ」と判定し意図的に 0 segments を返す。これは feature であってバグではない。
**具体例**: iPad 遠距離音声（peak 0.05〜0.18, rms 0.006）を kotoba-v2 に渡すと `segments=0 lang=ja prob=1.00 duration=*s` で空文字。`chunk_length=15` `condition_on_previous_text=False`（公式推奨）/ `compute_type=int8` / 3 フィルタ閾値緩和（no_speech=0.95, log_prob=-2.0, compression=3.5）/ `vad_filter=False` / PCM gain 正規化（peak→0.5）/ kotoba-v1.0 への切替を全部試して 0 segments。同じ音声を Whisper large-v3（蒸留前）に渡すと precision 47% で transcribe 成功。
**対策**: **Distil 系 Whisper は far-field/quiet/低 SNR 音声には使わない**。近接発話のクリーン音声専用。OOD で動かす可能性がある場合は Whisper large-v3 / **large-v3-turbo（OpenAI 蒸留版）** を選択する — turbo は速度を維持しつつ anti-hallucination 訓練を持たない。教訓: 同じ Whisper ファミリーでも distil 系 vs 非 distil 系で far-field 適性が決定的に違う。新モデル採用前にこの軸で評価する。

## EP-017: Chromium を pkill すると認証 Cookie が flush 前に失われる
**発生**: 2026-05-01 | **Arousal**: 0.9
**パターン**: Chromium はセキュリティ強化のため認証 Cookie（`SID`, `HSID`, `SAPISID`, `__Secure-1PSID`, `__Secure-3PSID` 等）をメモリ優先で保持し、定期的に SQLite (`Cookies` ファイル) に flush する。`pkill -KILL` や `pkill -9` で強制終了すると flush が走らず、ディスク上の Cookie には認証情報が残らない。次回同じプロファイルで起動すると未ログイン状態になる。
**具体例**: livebrowse 運用で YouTube ログイン後 `pkill -f "remote-debugging-port=9222"` で kill → 同プロファイルで Calendar を開くと marketing redirect（未ログイン挙動）。Cookie DB をスナップショットすると `.google.com` の認証 Cookie が全滅、`NID`（匿名）と `__Host-GAPS`（空）だけが残存。
**対策**: graceful close を **2 段階**で行う。(1) Playwright `browser.close()` で CDP 切断（この時点で Cookie が flush される）→ (2) `pgrep -f "remote-debugging-port=9222" | while read PID; do kill -TERM $PID; done; sleep 3` で残プロセス kill。`browser.close()` だけでは Chromium プロセスは死なない（CDP 切断のみ）が、Cookie は確実に flush される。`pgrep` 戻り値を変数経由で `kill` に渡すと zsh で複数 PID パースエラーになるので while read ループ必須。SIGKILL（`kill -9`）は flush 機会ゼロで絶対 NG。

## EP-018: Claude Code セッションの `currentDate` システム情報が古いことがある
**発生**: 2026-05-01 | **Arousal**: 0.8
**パターン**: Claude Code が起動時に提供する `currentDate` フィールド（CLAUDE.md コンテキスト末尾に挿入される `Today's date is YYYY-MM-DD`）は、セッション開始時刻でも実時刻でもなく古い snapshot のことがある。実測で 5 日のズレを確認。「今日」「明日」「昨日」を扱う処理でこの値を信じると、検索結果や API 応答との整合性が取れなくなる。
**具体例**: ドジャースの「明日の試合」を調べる時、`currentDate: 2026-04-26` を信じて Google 検索したら結果が 4/27 試合「終了」と返ってきて齟齬発生。`date "+%Y-%m-%d %H:%M %A"` で確認したら実時刻は **JST 2026-05-01 金 07:42**（5 日新しい）だった。明日 = 5/2 で再検索して正しい試合情報を取得。
**対策**: 日時を扱う前に必ず `date "+%Y-%m-%d %H:%M %A"` を実行して実時刻を取得する。`currentDate` は参考値とし、絶対視しない。`datetime-awareness` スキル + livebrowse SKILL.md にも明記済。海外スポーツ等は JST 換算（PT 19:15 ≈ JST 翌朝 09:15）も合わせて行う。

## EP-019: proactive 発火は conversations/*.jsonl には記録されない（state 直読み必須）
**発生**: 2026-05-01 | **Arousal**: 0.6
**パターン**: claude-code-slack-bot の `data/conversations/YYYY-MM-DD.jsonl` は **DM 双方向対話のみ** を記録し、proactive 発火（cron 起動の自発メッセージ）は含まれない。Humanness v1 実装時、conversations を走査して「ユーザー発言なしの bot メッセージ」を proactive とみなそうとして 5 週間で 2 件しか検出できなかった（しかもエラー応答）。
**正しいデータソース**: `data/mei-state.json` / `data/eve-state.json` の `history[]` 配列。各 100 件ローリングで `sentAt`, `category`, `reaction (null/text_engaged/ok_hand 等)`, `reactionDelta` を含む。`data/shared-proactive-history.json` は別物で 13 件しかない（用途未確認）。
**対策**: proactive を扱う metric / debug は `mei-state.json` / `eve-state.json` を直読みする。長期トレンドが必要なら **日次スナップショット必須**（100 件は約 10 日分）。conversations/ は対話品質指標（friction 等）には使えるが engagement 指標には使えないと覚える。

## EP-020: Electron で web 機能を loadFile→loadURL に移行すると getUserMedia が silent stream を返す
**発生**: 2026-05-01 | **Arousal**: 0.9 | **ドメイン**: electron / web-audio
**症状**: マイク許可済み + `mic stream acquired tracks=1` ログも出るのに、AnalyserNode の RMS が常に 0、MediaRecorder が 1323 byte (webm header のみ) chunk を吐き続ける。
**原因**: 旧版 Ember Chat は `loadFile()` で `file://` origin だった。Chromium は `file://` を trusted origin として autoplay policy を適用しないため、user gesture 前の getUserMedia でも実マイクが取れていた。`loadURL('http://localhost:.../...')` に変えた瞬間、autoplay policy が厳格に効いて silent stream に切り替わる。
**フィルタ撃沈履歴**: `echoCancellation: false` / `autoplay-policy=no-user-gesture-required` switch / silent gain → destination chain → どれも単独では効かない。
**対策**: BrowserWindow の `webPreferences.webSecurity: false` + `session.setPermissionRequestHandler` / `setPermissionCheckHandler` で `media`/`microphone`/`audioCapture` を auto-grant する3点セット。旧 main.js の posture 復元が事実上の正解。
**確認**: サーバ側で audio chunk size を見る (1323 byte = silent、数万 byte = OK)。

## EP-021: electron-builder の Hardened Runtime + 不完全 entitlements で macOS が permission ダイアログを silent 拒否
**発生**: 2026-05-03 | **Arousal**: 0.9 | **ドメイン**: electron / macos
**症状**: 新ビルドの Electron アプリ起動 → Always-On 押下 → macOS のマイク権限ダイアログが**一切出ない**。`tccutil reset` しても出ない。`Info.plist` には `NSMicrophoneUsageDescription` がある。
**原因**: electron-builder のデフォルト entitlements (`app-builder-lib/templates/entitlements.mac.plist`) には `com.apple.security.cs.allow-jit` 等3つしか入っていない。Hardened Runtime (`flags=0x10002(adhoc,runtime)`) が有効でマイク entitlement (`com.apple.security.device.audio-input`) が無いと、macOS は権限ダイアログを出さず silent 拒否する。`NS*UsageDescription` だけでは不十分。
**比較で発覚**: Dock 版 (`node_modules/.../electron/dist/Ember Chat.app`) は entitlements 完全に空 + Hardened Runtime 無効 → 制約なくマイクアクセス可。一方 electron-builder 製は Hardened Runtime 有効で詰みだった。
**対策**: `packages/<app>/build/entitlements.mac.plist` 作成（マイク・カメラ・ネットワーク・ファイル等の必要 entitlements を全部記述）→ `package.json` の `build.mac` に `hardenedRuntime: true` + `entitlements` + `entitlementsInherit` を指定 → リビルドで全権限が含まれる。
**確認**: `codesign -d --entitlements - "/Applications/<app>.app" 2>&1 | grep audio-input` で entitlement 入りを検証。Dock版とApp版の挙動差は entitlements 比較が最短診断。

## EP-022: Privacy Settings UI のアイコンは ヘルパーアプリ経由で識別される（メインアプリだけでは不足）
**発生**: 2026-05-03 | **Arousal**: 0.95 | **ドメイン**: electron / macos
**症状**: メインアプリの `Resources/icon.icns` (炎マーク) + `Info.plist` の `CFBundleIconFile` が正しいのに、Privacy Settings UI でデフォルト Electron ロゴが表示される。
**試した無駄な手段（全部効かず・大量の時間浪費）**: tccutil reset / iconservicesd 再起動 / `/Library/Caches/com.apple.iconservices.store` 削除 / lsregister -kill -r / PCの再起動 / アプリのリネーム→戻す / icns 1024x1024 含めて再生成 / CFBundleIconName 追加 / icns ファイル名を electron.icns に変更 / ad-hoc 再署名 / TCC.db 直接削除 / クリーンスタート。
**原因**: Electron アプリの `Contents/Frameworks/` 配下にある **4つのヘルパーアプリ**（`<App> Helper.app`, `Helper (GPU)`, `Helper (Plugin)`, `Helper (Renderer)`）の `Info.plist` に `CFBundleIconFile` が無く、`Resources/` に icns が無い状態だと、Privacy Settings UI が「Electron Helper」を経由してデフォルトロゴを表示する。メインアプリのアイコンは無視される。
**対策**: electron-builder の `afterPack` フックで `patch-mac-bundle.js` を実行し、メイン+全ヘルパーに `icon.icns` をコピー + `CFBundleIconFile`/`CFBundleName`/`CFBundleDisplayName` を設定。`afterPack` はコード署名前に走るので、その後 electron-builder が自動再署名する（手動 codesign 不要）。
**比較診断**: 動作している他の Electron アプリ（Aqua Voice 等の最もシンプル構造）の `Frameworks/` 配下を `plutil -p ".../<App> Helper.app/Contents/Info.plist" | grep CFBundleIcon` で確認。これだけで切り分けられる。誤推論 7 連発（ad-hoc 署名が原因 / Apple Developer ID が必要 / Asset Catalog が必要 等）を回避できた。
**スキル**: `electron-mac-icon-debug` 参照。誤推論一覧と patch-mac-bundle.js の完全コードを記録済み。
