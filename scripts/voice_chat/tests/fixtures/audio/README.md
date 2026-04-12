# Audio Fixtures

Ambient companion の回帰テスト用 fixtures。

各サンプルは次の 2 要素で管理する。

1. 音声ファイル本体
   `tests/fixtures/audio/samples/*.wav`
2. 評価用 manifest
   `tests/fixtures/audio/manifest.json`

## Manifest format

```json
{
  "id": "keyboard_clicks",
  "file": "samples/keyboard_clicks.wav",
  "transcript": "カタ",
  "expected_source": "fragmentary",
  "expected_intervention": "skip",
  "notes": "キーボードや机の打鍵音っぽい短い断片"
}
```

## Purpose

- 実際の利用シーンに近い音声サンプルを蓄積する
- Whisper の結果を `transcript` に固定し、ambient 判定回帰を壊さない
- 将来的には STT golden との比較にも拡張できるようにする

## Current state

現時点では軽量な WAV fixtures を同梱している。
あとから実録音サンプルに差し替える場合も、manifest の `id` と期待値を維持すればテストはそのまま使える。

## Recording Protocol

実録音を追加する時は、次の原則を守る。

1. 1 サンプルは 0.5〜8 秒程度に収める
2. 1 ファイルには 1 シーンだけ入れる
3. 収録直後に「何の音か」「どの状況か」を必ずメモする
4. 個人情報、固有名詞、Slack 通知内容などが入る場合は匿名化する
5. 実運用で比較したいカテゴリごとに最低 3 本は集める

推奨カテゴリ:

- `keyboard`
  キーボード、机の打鍵、マウス操作、生活雑音
- `monologue`
  PC 作業中の短い独り言
- `question`
  名前なしの相談や質問
- `media`
  TV、YouTube、配信、ニュース音声
- `multi_party`
  他人との会話
- `wake`
  明示的な「メイ」呼びかけ

## File Naming

ファイル名は次の形式を推奨する。

```text
<category>__<scene>__<variant>.wav
```

例:

- `keyboard__mechanical_short__01.wav`
- `monologue__tired_after_work__01.wav`
- `question__schedule_planning__01.wav`
- `media__youtube_outro__01.wav`

`manifest.json` の `id` は、上のファイル名から拡張子と連番を除いた短い識別子にする。

例:

- file: `question__schedule_planning__01.wav`
- id: `question_schedule_planning`

## Manifest Authoring Rules

`transcript`:

- Whisper の実際の出力をそのまま書く
- 「こう聞こえてほしい」ではなく、「実際にどう誤認識したか」を残す

`expected_source`:

- `user_identified`
- `user_initiative`
- `user_response`
- `user_likely`
- `user_in_conversation`
- `media_likely`
- `fragmentary`
- `unknown`

`expected_intervention`:

- `skip`
- `backchannel`
- `reply`

`notes`:

- 収録状況を 1 文で書く
- どこが難しいケースかも書く

例:

```json
{
  "id": "question_schedule_planning",
  "file": "samples/question__schedule_planning__01.wav",
  "transcript": "今日の予定どうしようかな？",
  "expected_source": "user_likely",
  "expected_intervention": "reply",
  "notes": "名前なしの相談。人間なら返して自然"
}
```

## Collection Checklist

実録音を追加したら、次を確認する。

1. `samples/` に WAV を置く
2. `manifest.json` に 1 件追加する
3. `python3 tests/fixtures/audio/audit_fixtures.py` を実行する
4. `pytest tests/test_audio_fixtures.py -q` を実行する
5. transcript が適切か再確認する
6. 必要なら `expected_source` / `expected_intervention` を調整する

`audit_fixtures.py` は次をチェックする。

- manifest の重複 ID
- manifest の重複 file
- manifest にあるのに存在しない WAV
- `samples/` にあるのに manifest 未登録の WAV
- `incoming/` に残ったままの WAV

CI や手元確認では次のように使える。

```bash
python3 tests/fixtures/audio/audit_fixtures.py
pytest tests/test_audio_fixtures.py -q
```

## Helper Script

実録音を fixture に登録する時は、次の helper が使える。

```bash
python3 tests/fixtures/audio/register_fixture.py /path/to/sample.wav \
  --category question \
  --scene schedule_planning \
  --variant 01 \
  --id question_schedule_planning_01 \
  --transcript "今日の予定どうしようかな？" \
  --expected-source user_likely \
  --expected-intervention reply \
  --notes "名前なしの相談。人間なら返して自然"
```

このスクリプトは以下をまとめて行う。

1. `samples/` 配下へ命名規約どおりに WAV をコピー
2. `manifest.json` にエントリを追加
3. 追加内容をその場で表示

まず確認だけしたい場合は `--dry-run` を使う。
同じ scene で複数 variant を積みたい時は `--id` で明示的に固有 ID を指定すると安全。

実録音の一時置き場として `incoming/` を使ってよい。
manifest の雛形は `manifest.entry.template.json` を参照。

## Bulk Import From incoming/

複数本まとめて登録したい時は、`incoming/` に `wav + json` のペアを置いて一括取り込みできる。

例:

- `incoming/question__schedule_planning__01.wav`
- `incoming/question__schedule_planning__01.json`

sidecar JSON の雛形は `incoming/sample.sidecar.template.json` を参照。

```bash
python3 tests/fixtures/audio/import_incoming.py --dry-run
python3 tests/fixtures/audio/import_incoming.py
```

本実行では、取り込みに成功した `wav/json` は `incoming/` から自動で削除される。
`--dry-run` の時だけは削除されないので、確認用に何度でも回せる。

sidecar には次の項目を書く。

- `category`
- `scene`
- `variant`
- `id` 任意
- `transcript`
- `expected_source`
- `expected_intervention`
- `notes`

運用フローのおすすめはこれね。

1. 収録した `wav` を `incoming/` に置く
2. 同名の `json` を雛形から作る
3. `import_incoming.py --dry-run` で確認する
4. 問題なければ本実行する
5. `audit_fixtures.py` と `pytest` を回す
