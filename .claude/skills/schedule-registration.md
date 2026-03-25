# スケジュール写真からのカレンダー登録スキル

## トリガー
- Akiraが業務スケジュールの写真を送ってきた時
- カレンダー登録を依頼された時
- 「予定登録して」「カレンダーに入れて」等の発言

## 手順

### Step 1: 画像からイベント情報を抽出
1. 画像を読み取り、以下を特定する:
   - イベント名（【】内のプロジェクト名含む）
   - 日時（開始・終了）
   - 場所（会議室名、Microsoft Teams等）
2. 読み取った予定を一覧表で確認提示する

### Step 2: gcalcliで登録
各イベントを以下のコマンドで登録:
```bash
gcalcli --calendar "Akira_public" add \
  --title "イベント名" \
  --when "YYYY-MM-DD HH:MM" \
  --duration 分数 \
  --where "場所" \
  --reminder "2 popup" \
  --noprompt
```

**コマンドのポイント**:
- `--noprompt` を必ず付ける（インタラクティブ入力を回避）
- `--reminder "2 popup"` でデフォルト2分前通知を設定
- `--where` は場所がある場合のみ付与
- 場所が複数ある場合（例: "Microsoft Teams, Shinagawa_MR_Z"）はそのまま入れる

### Step 3: 登録結果を報告
- 登録した件数と一覧を報告
- エラーがあれば個別に報告

## ルール
- **昼食・夕食の予定も登録する**（2026-03-25以降の変更）
- カレンダー名は `Akira_public`
- タイムゾーンは Asia/Tokyo
- リマインダーはデフォルト2分前ポップアップ（Akiraが別途指定した場合はそれに従う）
- 場所の略称はそのまま使う（Shinagawa_MR_F等）
- イベント名は画像の表記をそのまま使う（【KC：社内】等のプレフィックス含む）

## リマインダーの後から設定
gcalcliの`edit`はインタラクティブで使えない。既存イベントへのリマインダー追加はGoogle Calendar APIをPythonで直接叩く:
```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

creds_path = "/Users/akira/.gcalcli/oauth"  # gcalcliの認証情報を流用
with open(creds_path) as f:
    token_data = json.load(f)

creds = Credentials(
    token=token_data["token"],
    refresh_token=token_data["refresh_token"],
    token_uri=token_data["token_uri"],
    client_id=token_data["client_id"],
    client_secret=token_data["client_secret"],
)
service = build("calendar", "v3", credentials=creds)

# イベント更新
event = service.events().get(calendarId="primary", eventId=EVENT_ID).execute()
event["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 2}]}
service.events().update(calendarId="primary", eventId=EVENT_ID, body=event).execute()
```

## 学習メモ
- gcalcliには`update`コマンドがない（edit はインタラクティブ）
- 登録時に`--reminder`を付けておけば後からAPI叩く必要なし
- 以前は昼食・夕食を除外していたが、2026-03-25にAkiraから「次から昼食と夕食も登録して」と指示があり変更
