Step 1: リポジトリのクローンと依存関係インストール

 cd ~/workspace
 git clone https://github.com/mpociot/claude-code-slack-bot.git
 cd claude-code-slack-bot
 npm install

 Step 2: Slack Appの作成

 1. https://api.slack.com/apps にアクセス
 2. 「Create New App」→「From a manifest」を選択
 3. リポジトリに含まれる slack-manifest.json の内容をペースト（あれば）
 4. なければ手動で以下を設定:

 Bot Token Scopes:
 - chat:write, chat:write.public, im:write
 - app_mentions:read, channels:history, im:history
 - users:read, reactions:read, reactions:write

 Event Subscriptions（Socket Mode経由）:
 - app_mention, message.im, member_joined_channel

 App-Level Token:
 - 「Basic Information」→「App-Level Tokens」→ connections:write スコープで生成

 Step 3: トークン取得

 ┌────────────────┬────────────────────────────────────────────┬────────────────┐
 │    トークン    │                  取得場所                  │  フォーマット  │
 ├────────────────┼────────────────────────────────────────────┼────────────────┤
 │ Bot Token      │ OAuth & Permissions → Install to Workspace │ xoxb-*         │
 ├────────────────┼────────────────────────────────────────────┼────────────────┤
 │ App Token      │ Basic Information → App-Level Tokens       │ xapp-*         │
 ├────────────────┼────────────────────────────────────────────┼────────────────┤
 │ Signing Secret │ Basic Information → App Credentials        │ ランダム文字列 │
 └────────────────┴────────────────────────────────────────────┴────────────────┘

 Step 4: Anthropic APIキー取得

 - https://console.anthropic.com/settings/keys でAPIキーを作成
 - フォーマット: sk-ant-*

 Step 5: 環境変数の設定

 cp .env.example .env

 .env に以下を記入:
 SLACK_BOT_TOKEN=xoxb-***
 SLACK_APP_TOKEN=xapp-***
 SLACK_SIGNING_SECRET=***
 ANTHROPIC_API_KEY=sk-ant-***
 BASE_DIRECTORY=/Users/akira/workspace/open-claude
 DEBUG=true

 Step 6: 起動と動作確認

 npm run dev

 Slackで:
 1. ボットをチャンネルに招待（/invite @botname）
 2. @botname こんにちは とメンション
 3. 応答が返ればOK

 Step 7: デバッグモードをオフにして本番運用

 .env で DEBUG=false に変更し npm run prod で起動。

 既知の注意点

 - Node.js v25非対応: Node.js v18〜v22を使うこと
 - メンテナンス停滞: 最終コミットは2025年6月。API互換性問題が発生したらフォークして修正が必要
 - セッション管理: メモリ上のため、再起動でセッションがリセットされる
 - 常時起動: tmux や pm2 でバックグラウンド実行が必要

 動作確認チェックリスト

 - npm run dev でエラーなく起動する
 - Slackでボットをメンションして応答が返る
 - DMでボットに直接メッセージを送って応答が返る
 - BASE_DIRECTORY 内のファイルについて質問して正しく答える
 - スレッド内でコンテキストが維持される

 cwd open-claude

   常時稼働させたい場合の選択肢:

  1. スリープさせない - システム設定 → ディスプレイをオフにするだけにする（電気代かかる）
  2. クラウドにデプロイ - VPSやRailway/Render等にデプロイする（月数ドル〜）
  3. 使う時だけ起動 - pm2 start claude-slack-bot / pm2 stop claude-slack-bot で手動切り替え

  pm2 startup
  pm2 save

    完了:                                                                                                                                               
  - 26ジョブすべてがスケジュール登録済み 
  - テストジョブでSlack DM送信を確認済み                                                                                                              
  - pm2で常時起動＋Mac再起動時の自動起動設定済み                                     
                                                                                                                                                      
  今後注意が必要な点:                                                                                                                                 
  - 一部ジョブが外部スクリプト（anthropic_daily_cost.py、gmail_to_drive.py等）を参照している → 実際の実行時にパスが見つからないエラーが出る可能性あり 
  - MCP サーバー設定（mcp-servers.json）がまだ未設定 → RSS取得やWeb検索を使うジョブ（tech-news-digest、IR系）で必要                                   
  - これらは明朝5:00の tech-news-digest 実行時に実際のエラーを見て調整するのが効率的                                                                  
                                                                                           

                                                                                             VSCodeを一度完全に終了して再起動してから、ターミナルで以下を実行
  してみて:

  1. VSCodeを完全に閉じる（Cmd+Q）
  2. Finderで /Applications/Visual Studio Code.app を右クリック →
  「情報を見る」
  3. 「Rosettaを使用して開く」にチェックが入っていたら外す
  4. VSCodeを再起動
  5. ターミナルで uname -m を実行 → arm64 になるはず
  6. arm64 を確認したら curl -fsSL https://claude.ai/install.sh |
  sh を実行

  もしVSCodeのRosetta設定が外れていたら、別の何かが原因（anyenv/nod
  envの初期化スクリプト等）。その場合は教えてね。

  自動設定（今やったこと）                                                      
  - .env に DEFAULT_WORKING_DIRECTORY=open-claude を追加                        
  - cwd を設定しなくても自動的に /Users/akira/workspace/open-claude が使われる  
                                                                                
  変更方法（Slack 上で）                                                        
  - cwd プロジェクト名 — BASE_DIRECTORY からの相対パスで変更（例: cwd           
  claude-code-slack-bot）                                                       
  - cwd /absolute/path — 絶対パスで変更                                         
  - cwd — 現在の設定を確認                                                      
                                                                                
  デフォルト自体を変えたい場合                                                  
  - /Users/akira/workspace/claude-code-slack-bot/.env の                        
  DEFAULT_WORKING_DIRECTORY を編集して pm2 restart claude-slack-bot   

❯ OK、今日は完了。最後にSlackにテスト送信をして、その後ラップして。                 

学習状況や会話ログ、記憶の定着などのダッシュボード実装

Mei: 元大手企業のCFOで、いろいろな業種の中期経営計画の立案・実行を経験している。

Eve: 元ベンチャー企業のSEOで、現場で様々な事業立ち上げの成功・失敗経験あり

「アバントグループの成長戦略について、MeiとEveで20ターン意見交換して」
「AI活用戦略についてMeiとEveで議論して」     

Superpowers vs gstack 比較
基本情報
Superpowers (obra/Jesse Vincent)gstack (garrytan/Garry Tan)作者Jesse Vincent（Prime Radiant）Garry Tan（Y Combinator CEO）⭐ GitHub Stars108k— (3月17日公開、急速に拡大中)ライセンスMITMIT対応プラットフォームClaude Code, Cursor, Codex, OpenCode, Gemini CLIClaude Code専用インストール/plugin install (プラグインシステム)git clone → .claude/skills/ にコピー
思想の違い
Superpowersgstackコンセプトプロセスフレームワーク — 開発方法論そのものを教えるロールベースチーム — 専門家ペルソナを切り替えるメタファー「エージェントに開発方法論を叩き込む」「1人のアシスタントを仮想チームに変える」重視するものTDD、計画性、システマティックなデバッグプロダクト思考、CEO視点のレビュー、ビジュアルQAターゲット方法論を重視するエンジニア高速にプロダクトをシッピングしたいファウンダー/シニアエンジニア
スキル構成の比較
Superpowers（約15スキル） — 開発プロセスの各フェーズをカバー：

brainstorming → writing-plans → subagent-driven-development → TDD → code review → finishing branch
デバッグ専用スキル（systematic-debugging、root-cause-tracing）
メタスキル（スキルの書き方を教えるスキル）

gstack（25+コマンド） — ロール別に専門家を召喚：

/office-hours — プロダクト壁打ち（6つの根本的質問）
/plan-ceo-review — ファウンダーモード（ユーザー価値・市場フィット重視）
/plan-eng-review — テックリードモード（アーキテクチャ・障害モード分析）
/plan-design-review /design-consultation — デザインレビュー
/review — 本番リスク重視のコードレビュー
/ship /land-and-deploy /canary — デプロイ系
/browse — 永続的Chromiumブラウザセッション（最大の差別化ポイント）
/qa /qa-only — diffからルート特定→ブラウザで自動検証
/retro — エンジニアリング振り返り
/freeze /unfreeze /guard /careful — 安全管理系
/cso /investigate /benchmark /document-release /codex — その他