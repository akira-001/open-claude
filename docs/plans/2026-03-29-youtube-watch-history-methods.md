# YouTube Watch History 取得方法 — 比較調査

調査日: 2026-03-29

---

## エグゼクティブサマリー

YouTube の視聴履歴をプログラムから定期取得する方法は大きく4種類存在するが、
**公式かつ自動化可能な方法は「Google Data Portability API」のみ**。
それ以外はすべてToCに違反するか、Googleの変更により随時壊れるリスクがある。

---

## 方法1: YouTube Data API v3

### 現在の状況

**事実上使用不可。**

- `activities.list` エンドポイントは存在するが、2016年9月12日以降 watch history を返さなくなった。
- `channels.list` が返す `contentDetails.relatedPlaylists.watchHistory` は常に固定値 `"HL"` を返す（実際のプレイリストIDではない）。
- `playlistItems.list` で `"HL"` を指定しても常に空リストが返る。
- Google Issue Tracker #35172816 にて長期間オープンのまま放置されている。

### 認証

OAuth 2.0 必須

### データ形式

返らないため不明

### 自動化可否

不可

### 補足

2016年以前はこの API で取得できていた。現在は完全に機能停止。
「workaround」として activities.list の mine=true + contentDetails を試みる記事があるが、
watch history の取得には繋がらない。

---

## 方法2: Google Data Portability API

### 現在の状況

**2024年正式公開。現時点で最も信頼性が高い公式手段。**

### 仕組み

1. OAuth 2.0 でユーザー認証（scope: `dataportability.myactivity.youtube`）
2. `POST /v1/portabilityArchive:initiate` で job 開始（リソース: `myactivity.youtube`）
3. `GET /v1/portabilityArchive/{job_id}:getState` でステータスポーリング
4. 完了後、署名済み URL からアーカイブ ZIP をダウンロード
5. ZIP 内の JSON を解析

### 取得できるデータフィールド

`myactivity.youtube` リソースの Activity Record:

| フィールド | 内容 |
|---|---|
| `header` | "YouTube" 固定 |
| `title` | "Watched [動画タイトル]" 形式 |
| `titleUrl` | 動画の YouTube URL |
| `subtitles` | チャンネル名 + チャンネル URL |
| `time` | ISO 8601 タイムスタンプ (UTC) |
| `products` | "YouTube" |
| `activityControls` | "YouTube watch history" など |

**注意**: 視聴時間（何秒見たか）は取得不可。

### 認証

OAuth 2.0 必須。`https://www.googleapis.com/auth/dataportability.myactivity.youtube` スコープ。

### レート制限・クォータ

- エクスポート間隔は最低 24 時間推奨（前回の `export_time` を次回の `start_time` に使う）
- time filter 対応: `start_time` / `end_time` を指定して差分取得が可能
- 1ジョブの最大完了待ち: 7日間

### 自動化可否

**可能。** cron 日次実行に対応。
Python SDK: `google-auth-oauthlib` + `google-api-python-client`
公式クイックスタート: https://developers.google.com/data-portability/user-guide/python-quickstart

### 制約

- OAuth consent が "one-time" の場合、次回エクスポートに再認可が必要
- "time-based access" を選ぶと period 内は繰り返しエクスポート可能
- Google Cloud Console でのアプリ登録・OAuth 設定が必要
- 個人アカウントの場合、アプリを "test" モードにすると承認なしで使える

---

## 方法3: Google Takeout (手動)

### 現在の状況

**機能するが、自動化が難しい。**

### 仕組み

https://takeout.google.com → YouTube → 「形式」で JSON を選択 → ZIP ダウンロード

### データ形式

`watch-history.json` (または `watch-history.html`)

JSON の各エントリ例:
```json
{
  "header": "YouTube",
  "title": "Watched My Video Title",
  "titleUrl": "https://www.youtube.com/watch?v=XXXXXXXXX",
  "subtitles": [{"name": "Channel Name", "url": "https://www.youtube.com/channel/..."}],
  "time": "2024-01-15T10:23:45.000Z",
  "products": ["YouTube"],
  "activityControls": ["YouTube watch history"]
}
```

### 認証

Google アカウントへのブラウザログイン（手動）

### レート制限

月6回まで自動定期エクスポートを設定可能

### 自動化可否

**部分的に可能だが非推奨。**
- Selenium でブラウザ操作を自動化するスクリプトが GitHub に存在するが、ログイン認証・reCAPTCHA で頻繁に壊れる
- Data Portability API が同等機能を公式に提供するようになったため、Takeout 自動化の優先度は低い

### 注意点

- エクスポートのたびに返されるエントリ数が変動する（過去数年分のみ、不定）
- 視聴時間は含まれない

### パーサライブラリ

`google-takeout-parser` (PyPI): 最終更新 2025年6月。HTML/JSON 両対応。

---

## 方法4: ブラウザスクレイピング (youtube.com/feed/history)

### 現在の状況

**技術的には可能だが、ToS 違反 + 高メンテナンスコスト。**

### 仕組み

1. 認証済みブラウザ Cookie を取得
2. `https://www.youtube.com/feed/history` に Cookie 付きリクエスト
3. レスポンス HTML から `ytInitialData` JSON を抽出
4. continuation token を使ってページネーション

### 使えるライブラリ

| ライブラリ | 状態 | 備考 |
|---|---|---|
| `youtube-unofficial` (tatsh) | 2025年12月 v0.3.1 更新あり。現役 | Cookie 依存。`print-history --json` で JSON Lines 出力 |
| `zvodd/Youtube-Watch-History-Scraper` | アーカイブ済み・メンテナンス停止 | YouTube フロントエンド変更で動作不可 |

### 認証

ブラウザ Cookie 必須（`youtube-unofficial` は yt-dlp 対応ブラウザの Cookie ストレージを使用）

### Cookie 抽出の注意

- Chrome: 2024年7月以降 App-Bound Encryption により外部からの Cookie 抽出が困難
- Firefox: 現状では外部抽出可能（yt-dlp も Firefox 推奨）
- `yt-cookies` (PyPI) でブラウザから Cookie をエクスポート可能

### データ形式

`youtube-unofficial` の `print-history -j` は JSON Lines で出力。
フィールドは内部 YouTube API の `browseEndpoint` 構造に依存（非公式のため変動する）。

### 自動化可否

**条件付きで可能。** Cookie の有効期限（通常2年）内は機能するが、
YouTube フロントエンド変更で突然壊れるリスクがある。cron 本番運用は非推奨。

### レート制限

非公式。スロットリングや BAN のリスクがある。

---

## 方法5: Google My Activity (myactivity.google.com) スクレイピング

### 現在の状況

**非公式 API は存在しない。スクレイピングは極めて困難。**

- `myactivity.google.com` は JavaScript レンダリング必須
- 内部 API エンドポイントは非公開・署名必須
- Google の利用規約で明示的に禁止

### 代替

Data Portability API の `myactivity.youtube` リソースが公式な代替手段。
同じデータソースに OAuth で正規アクセスできる。

---

## 方法比較表

| 方法 | 認証 | 自動化 | 信頼性 | データ量 | 備考 |
|---|---|---|---|---|---|
| YouTube Data API v3 | OAuth | 不可 | 死亡 | — | 2016年に機能停止 |
| **Data Portability API** | OAuth | 可 (推奨) | 高 | タイトル/URL/チャンネル/時刻 | **唯一の公式自動化手段** |
| Google Takeout (手動) | ブラウザ | 部分的 | 中 | タイトル/URL/チャンネル/時刻 | 月6回上限 |
| youtube-unofficial | Cookie | 条件付き | 中〜低 | 内部構造依存 | ToS違反リスク・壊れやすい |
| myactivity.google.com | — | 不可 | なし | — | 非公式 API 存在しない |

---

## 推奨構成（日次 cron 運用）

### ベストプラクティス

```
Data Portability API + time-based access OAuth
```

1. `google-auth-oauthlib` で OAuth token を取得・保存
2. `time-based access` を選択し、定期的なエクスポートを認可
3. 毎日 cron で `InitiatePortabilityArchive(resources=["myactivity.youtube"], start_time=前回export_time)` を実行
4. ポーリングで完了を待つ（通常数分〜数十分）
5. ZIP をダウンロードして `watch-history.json` をパース
6. `google-takeout-parser` (PyPI) でパースするか自前で処理

### 注意点

- 初回 OAuth 認証は手動が必要（以降はトークンリフレッシュで自動化可能）
- エクスポートが完了するまでのレイテンシ（数分〜数時間）を考慮すること
- 「今日見た動画をリアルタイムに知りたい」用途には向かない
  - リアルタイム性が必要な場合は youtube-unofficial の Cookie 方式のほうが即座だが、安定性を犠牲にする

### 不要なもの

- Selenium / ブラウザ自動化
- 非公式 API / スクレイピング
- YouTube Data API v3（watch history 用途では完全に無効）

---

## 参考リンク

- [Data Portability API Overview](https://developers.google.com/data-portability/user-guide/overview)
- [Data Portability API Python Quickstart](https://developers.google.com/data-portability/user-guide/python-quickstart)
- [myactivity.youtube Schema Reference](https://developers.google.com/data-portability/schema-reference/my_activity)
- [Data Portability API Time Filter](https://developers.google.com/data-portability/user-guide/time-filter)
- [google-takeout-parser (PyPI)](https://pypi.org/project/google-takeout-parser/)
- [youtube-unofficial (GitHub)](https://github.com/Tatsh/youtube-unofficial)
- [YouTube API Issue Tracker #35172816](https://issuetracker.google.com/issues/35172816)
