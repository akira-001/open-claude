# STT Quality Benchmark Results — 2026-04-25

> 4構成（small / kotoba / 2段階 / +二重VAD）の比較ベンチ。

## メタデータ

- **date**: 2026-04-25
- **device**: cpu
- **compute_type**: int8
- **samples_count**: 27
- **small_model**: small
- **kotoba_model**: kotoba-tech/kotoba-whisper-v2.0-faster

## サマリ

| 構成 | 平均CER (transcript付きのみ) | 平均レイテンシ | ok | partial | wrong | missed | hallucinated | ok_skip |
|---|---|---|---|---|---|---|---|---|
| small | 0.753 | 0.88s | 2 | 1 | 17 | 5 | 0 | 2 |
| kotoba | 0.703 | 3.41s | 3 | 1 | 18 | 3 | 0 | 2 |
| two_stage | 0.733 | 2.71s | 3 | 1 | 16 | 5 | 0 | 2 |
| two_stage_dualvad | 0.735 | 2.60s | 3 | 1 | 16 | 5 | 0 | 2 |

## サンプル別の出力

**Outcome 凡例**: `ok`(CER<0.15) / `partial`(<0.40) / `wrong`(≥0.40) / `missed`(空・期待あり) / `hallucinated`(出力・期待空) / `ok_skip`(空・期待空)

### `keyboard_clicks` (keyboard)

- 期待: `カタ`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | missed | `` | 1.000 | 0.02s | 0.00 |  |
| kotoba | missed | `` | 1.000 | 0.00s | 0.00 |  |
| two_stage | missed | `` | 1.000 | 0.00s | 0.00 | stage=1 |
| two_stage_dualvad | missed | `` | 1.000 | 0.00s | 0.00 | vr=0.56 stage=1 |

### `desk_monologue` (desk)

- 期待: `疲れたなあ`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `んー` | 1.000 | 1.22s | -1.03 |  |
| kotoba | wrong | `ん` | 1.000 | 3.91s | -0.51 |  |
| two_stage | wrong | `んー` | 1.000 | 4.14s | -1.03 | stage=1 |
| two_stage_dualvad | wrong | `んー` | 1.000 | 2.63s | -1.03 | vr=0.11 stage=1 |

### `direct_question` (direct)

- 期待: `今日の予定どうしようかな？`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `うーん` | 0.917 | 0.75s | -0.84 |  |
| kotoba | wrong | `ん` | 1.000 | 3.98s | -0.52 |  |
| two_stage | wrong | `うーん` | 0.917 | 0.75s | -0.84 | stage=1 |
| two_stage_dualvad | wrong | `うーん` | 0.917 | 0.75s | -0.84 | vr=0.60 stage=1 |

### `tv_outro` (tv)

- 期待: `この動画をご視聴いただきありがとうございました`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `ん` | 1.000 | 0.75s | -0.90 |  |
| kotoba | wrong | `ごめん` | 0.957 | 4.00s | -0.80 |  |
| two_stage | wrong | `ん` | 1.000 | 0.74s | -0.90 | stage=1 |
| two_stage_dualvad | wrong | `ん` | 1.000 | 0.74s | -0.90 | vr=1.00 stage=1 |

### `keyboard_mechanical_short_01` (keyboard)

- 期待: `無言のまま、キーボードを3回打って、1秒置いて、マウスを1回クリックしてください。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | missed | `` | 1.000 | 0.01s | 0.00 |  |
| kotoba | missed | `` | 1.000 | 0.01s | 0.00 |  |
| two_stage | missed | `` | 1.000 | 0.01s | 0.00 | stage=1 |
| two_stage_dualvad | missed | `` | 1.000 | 0.02s | 0.00 | vr=0.33 stage=1 |

### `media_youtube_outro_01` (media)

- 期待: `この動画をご視聴いただきありがとうございました。また次回の動画でお会いしましょう。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | missed | `` | 1.000 | 0.01s | 0.00 |  |
| kotoba | missed | `` | 1.000 | 0.01s | 0.00 |  |
| two_stage | missed | `` | 1.000 | 0.01s | 0.00 | stage=1 |
| two_stage_dualvad | missed | `` | 1.000 | 0.00s | 0.00 | vad_skip(vr=0.04) |

### `monologue_tired_after_work_01` (monologue)

- 期待: `疲れたなあ、ちょっと休もうかな。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | ok | `疲れたなぁ ちょっと休もうかな` | 0.071 | 0.81s | -0.33 |  |
| kotoba | ok | `疲れたなちょっと休もうかな` | 0.071 | 4.04s | -0.22 |  |
| two_stage | ok | `疲れたなちょっと休もうかな` | 0.071 | 4.86s | -0.22 | stage=2 |
| two_stage_dualvad | ok | `疲れたなちょっと休もうかな` | 0.071 | 4.85s | -0.22 | vr=0.65 stage=2 |

### `question_schedule_planning_01` (question)

- 期待: `今日の予定どうしようかな？`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | ok | `今日の予定どうしようかな` | 0.000 | 0.80s | -0.32 |  |
| kotoba | ok | `今日の予定どうしようかな` | 0.000 | 4.06s | -0.10 |  |
| two_stage | ok | `今日の予定どうしようかな` | 0.000 | 4.86s | -0.10 | stage=2 |
| two_stage_dualvad | ok | `今日の予定どうしようかな` | 0.000 | 4.85s | -0.10 | vr=0.56 stage=2 |

### `wake_good_morning_01` (wake)

- 期待: `メイ、おはよう。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | partial | `メインおはよう` | 0.167 | 0.78s | -0.67 |  |
| kotoba | ok | `メイおはよう` | 0.000 | 4.01s | -0.34 |  |
| two_stage | ok | `メイおはよう` | 0.000 | 4.76s | -0.34 | stage=2 |
| two_stage_dualvad | ok | `メイおはよう` | 0.000 | 4.73s | -0.34 | vr=0.44 stage=2 |

### `synthetic_silence` (silence)

- 期待: `(空が正解)`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | ok_skip | `` | 0.000 | 0.01s | 0.00 |  |
| kotoba | ok_skip | `` | 0.000 | 0.00s | 0.00 |  |
| two_stage | ok_skip | `` | 0.000 | 0.01s | 0.00 | stage=1 |
| two_stage_dualvad | ok_skip | `` | 0.000 | 0.00s | 0.00 | vad_skip(vr=0.00) |

### `synthetic_white_noise` (noise)

- 期待: `(空が正解)`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | ok_skip | `` | 0.000 | 0.00s | 0.00 |  |
| kotoba | ok_skip | `` | 0.000 | 0.00s | 0.00 |  |
| two_stage | ok_skip | `` | 0.000 | 0.00s | 0.00 | stage=1 |
| two_stage_dualvad | ok_skip | `` | 0.000 | 0.00s | 0.00 | vad_skip(vr=0.03) |

### `media__youtube_far_field__01` (media_far_field)

- 期待: `ボイスアップラボのギリギリ開発会議。はい、どうもボイスアップラボのトールです。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `はい、どうも、ボイスアップのポールです` | 0.556 | 0.84s | -0.83 |  |
| kotoba | wrong | `はいどうもごちそうプラムのトールです` | 0.639 | 4.00s | -0.50 |  |
| two_stage | wrong | `はい、どうも、ボイスアップのポールです` | 0.556 | 0.82s | -0.83 | stage=1 |
| two_stage_dualvad | wrong | `はい、どうも、ボイスアップのポールです` | 0.556 | 0.82s | -0.83 | vr=0.63 stage=1 |

### `media__youtube_far_field__02` (media_far_field)

- 期待: `はい。ちょっと今回はあの先週池田さんがショピファイのAIツールキットの話をしてくれたので`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `今回は専州 ケドさんが処理入った処理を聞いてお話をしてくれた` | 0.698 | 0.93s | -0.83 |  |
| kotoba | wrong | `今回は先週けどさんが書きと話をしてくれた` | 0.651 | 4.00s | -0.37 |  |
| two_stage | wrong | `今回は専州 ケドさんが処理入った処理を聞いてお話をしてくれた` | 0.698 | 0.91s | -0.83 | stage=1 |
| two_stage_dualvad | wrong | `今回は専州 ケドさんが処理入った処理を聞いてお話をしてくれた` | 0.698 | 0.92s | -0.83 | vr=0.77 stage=1 |

### `media__youtube_far_field__03` (media_far_field)

- 期待: `なので、ま、とりあえずクロードコード広げて、ま、オンラインショップで、え、ものをちょっと売りたいんだ。だけど、ま、集客はちょっと`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `どうもこんにちは、こんにちは。 今日は、 クローブコードを紹介します。今日は、オンラインスをプレイしています。` | 0.945 | 4.66s | -1.32 |  |
| kotoba | wrong | `なのでとりあえずプロノコード広げてオンラインショップでやって` | 0.527 | 4.08s | -0.34 |  |
| two_stage | wrong | `どうやって作ってますか?うん、作ってますとりあえずプロのことをしておいてま、オンラインで作って` | 0.891 | 3.48s | -0.91 | stage=1 |
| two_stage_dualvad | wrong | `どうやってやってるんですかねうんとりあえずプロの方で仕上げてオンラインしておくぜって` | 0.945 | 2.26s | -0.80 | vr=0.79 stage=1 |

### `media__youtube_far_field__04` (media_far_field)

- 期待: `欲望を入れてみただけですね。欲望を入れた状態です。初心者ECオーナーがとりあえずやりたいこと書いた。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `欲望を入れてみただけですね欲望を入れた時お世話です先社インシーオーナーがとりあえずやりたいことを書いてああそうです` | 0.383 | 1.12s | -0.63 |  |
| kotoba | wrong | `欲望を入れてみた状態ですね写真者ECOーナーがとりあえずやりたいこと書いたありがとうございました` | 0.553 | 8.06s | -0.40 |  |
| two_stage | wrong | `欲望を入れてみた状態ですね写真者ECOーナーがとりあえずやりたいこと書いたありがとうございました` | 0.553 | 9.04s | -0.40 | stage=2 |
| two_stage_dualvad | wrong | `欲望を入れてみた状態ですね写真者ECOーナーがとりあえずやりたいこと書いたありがとうございました` | 0.553 | 9.02s | -0.40 | vr=0.96 stage=2 |

### `media__youtube_far_field__05` (media_far_field)

- 期待: `サービスがいいよねというところで、ま、一応AI連携機能が豊富なサービスはどれですかっていう風に聞いてみました。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `いいよねというところで、一応AIで受け取るのが僕のサービスはどれですかっていうふうに聞いてみました` | 0.327 | 0.97s | -0.52 |  |
| kotoba | partial | `いいよねというところで一応AI連携機能が僕のサービスはどれですかって聞いてみました` | 0.250 | 4.05s | -0.22 |  |
| two_stage | partial | `いいよねというところで一応AI連携機能が僕のサービスはどれですかって聞いてみました` | 0.250 | 4.98s | -0.22 | stage=2 |
| two_stage_dualvad | partial | `いいよねというところで一応AI連携機能が僕のサービスはどれですかって聞いてみました` | 0.250 | 4.97s | -0.22 | vr=0.90 stage=2 |

### `media__youtube_far_field__06` (media_far_field)

- 期待: `ベースとかストアーズとかあるけど、ま、ちょっと商品説明を生成してくれる機能ぐらいあるかなぐらいのところで今は回ってるのかな。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `です とかすとはずとあるけどまあちょっと商品説明を 制施してくれますのぐらい` | 0.610 | 0.94s | -0.88 |  |
| kotoba | wrong | `ベースとかストアズとかあるけどちょっと商品説明を生成してくれる機能ぐらい` | 0.390 | 4.03s | -0.23 |  |
| two_stage | wrong | `です とかすとはずとあるけどまあちょっと商品説明を 制施してくれますのぐらい` | 0.610 | 0.92s | -0.88 | stage=1 |
| two_stage_dualvad | wrong | `です とかすとはずとあるけどまあちょっと商品説明を 制施してくれますのぐらい` | 0.610 | 0.91s | -0.88 | vr=0.88 stage=1 |

### `media__youtube_far_field__07` (media_far_field)

- 期待: `それはまだできないっぽいですね。え、でもAIツールキット繋がってないんでしょ、まだ。AIツールキット繋がってないです。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `ペンの電話のツールキットはつながってないの?はい、ツールキットを` | 0.722 | 0.92s | -0.85 |  |
| kotoba | wrong | `でも電話ツールキッドつながってないの?開発用トゥルキットを` | 0.722 | 4.03s | -0.56 |  |
| two_stage | wrong | `ペンの電話のツールキットはつながってないの?はい、ツールキットを` | 0.722 | 0.90s | -0.85 | stage=1 |
| two_stage_dualvad | wrong | `ペンの電話のツールキットはつながってないの?はい、ツールキットを` | 0.722 | 0.90s | -0.85 | vr=0.85 stage=1 |

### `media__youtube_far_field__08` (media_far_field)

- 期待: `ストアの作成はさすがに今はポチポチやってねというところがあったので、ま、それはやりました。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `そういう体験が行われていると ストアの作成はさっそくなりにごちごちやってね` | 0.952 | 0.96s | -0.79 |  |
| kotoba | wrong | `ストアの作成はスポチとしてやって` | 0.738 | 4.00s | -0.49 |  |
| two_stage | wrong | `ストアの作成はスポチとしてやって` | 0.738 | 4.93s | -0.49 | stage=2 |
| two_stage_dualvad | wrong | `ストアの作成はスポチとしてやって` | 0.738 | 4.97s | -0.49 | vr=0.95 stage=2 |

### `media__youtube_far_field__09` (media_far_field)

- 期待: `ドメインを教えたらもうここの時点であのAIツールキットとかを紹介してくれて、で、ここでこの時点で`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `ご迷いを教えたらこの時点で AIツールキットとかを紹介してくれて` | 0.391 | 0.89s | -0.43 |  |
| kotoba | wrong | `この時点でAIツールキットとかを紹介してくれて` | 0.500 | 3.99s | -0.30 |  |
| two_stage | wrong | `この時点でAIツールキットとかを紹介してくれて` | 0.500 | 4.88s | -0.30 | stage=2 |
| two_stage_dualvad | wrong | `この時点でAIツールキットとかを紹介してくれて` | 0.500 | 4.85s | -0.30 | vr=0.85 stage=2 |

### `media__youtube_far_field__10` (media_far_field)

- 期待: `そしたらこの最初に初期設定で入れた情報がもう全部取れる状態で、これでもうクロードコードからも情報を、え、登録し放題みたいな`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `それでは、このURLにアップスしてください。どうしたらこういう画面。` | 0.897 | 0.88s | -0.78 |  |
| kotoba | wrong | `このURLにアクセスしてください出てきてきて` | 0.948 | 3.99s | -0.33 |  |
| two_stage | wrong | `このURLにアクセスしてください出てきてきて` | 0.948 | 4.81s | -0.33 | stage=2 |
| two_stage_dualvad | wrong | `このURLにアクセスしてください出てきてきて` | 0.948 | 4.81s | -0.33 | vr=0.79 stage=2 |

### `media__youtube_far_field__11` (media_far_field)

- 期待: `状態になって。で、ここからこの画像だけ与えて`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | missed | `` | 1.000 | 0.82s | 0.00 |  |
| kotoba | wrong | `情報を登録しようないという状態があって` | 0.950 | 3.93s | -0.29 |  |
| two_stage | missed | `` | 1.000 | 0.80s | 0.00 | stage=1 |
| two_stage_dualvad | missed | `` | 1.000 | 0.80s | 0.00 | vr=0.83 stage=1 |

### `media__youtube_far_field__12` (media_far_field)

- 期待: `カブトの画像を入れて、これを`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `すみません、どうかの事項で入れてくれてさっきのクロードコードに` | 1.923 | 0.90s | -0.75 |  |
| kotoba | wrong | `説明文とかも自動で入れてくれてさっきのクロードコードに` | 1.769 | 4.02s | -0.21 |  |
| two_stage | wrong | `説明文とかも自動で入れてくれてさっきのクロードコードに` | 1.769 | 4.89s | -0.21 | stage=2 |
| two_stage_dualvad | wrong | `説明文とかも自動で入れてくれてさっきのクロードコードに` | 1.769 | 4.87s | -0.21 | vr=0.86 stage=2 |

### `media__youtube_far_field__13` (media_far_field)

- 期待: `で、これ、ま、実際に手でやろうとするとちょっとややこしいですね。ショピファイの実際の画面はこんな感じで。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | missed | `` | 1.000 | 0.77s | 0.00 |  |
| kotoba | wrong | `なるほど` | 0.979 | 3.83s | -0.61 |  |
| two_stage | missed | `` | 1.000 | 0.75s | 0.00 | stage=1 |
| two_stage_dualvad | missed | `` | 1.000 | 0.75s | 0.00 | vr=0.92 stage=1 |

### `media__youtube_far_field__14` (media_far_field)

- 期待: `まあ、でもそこら辺を知らずに何も知らないショピファイ初めて使ったんですけど`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `まあそこら辺をしようぜになりますよ大衆議会の所持人のおかしです` | 0.750 | 0.92s | -0.89 |  |
| kotoba | wrong | `そこら辺を知らずに何も知らない守備会も所持ちいい` | 0.583 | 4.02s | -0.34 |  |
| two_stage | wrong | `まあそこら辺をしようぜになりますよ大衆議会の所持人のおかしです` | 0.750 | 0.91s | -0.89 | stage=1 |
| two_stage_dualvad | wrong | `まあそこら辺をしようぜになりますよ大衆議会の所持人のおかしです` | 0.750 | 0.90s | -0.89 | vr=0.94 stage=1 |

### `media__youtube_far_field__15` (media_far_field)

- 期待: `この色味とかもなんかカブトの色味とかを取ってきたりして、ちょっとそれっぽい感じ。ええ、画像に合わせてくれたわけです。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `うんこの色味とかもなんかカブトの色を踏みよってコントってことにしてちょっとそれが濃いからえぇ` | 0.611 | 1.01s | -0.67 |  |
| kotoba | wrong | `この色味とかもなんかかぶての色を見るとかを撮っていきたいとしてちょっとそれっぽい感じ` | 0.481 | 4.02s | -0.38 |  |
| two_stage | wrong | `この色味とかもなんかかぶての色を見るとかを撮っていきたいとしてちょっとそれっぽい感じ` | 0.481 | 5.01s | -0.38 | stage=2 |
| two_stage_dualvad | wrong | `この色味とかもなんかかぶての色を見るとかを撮っていきたいとしてちょっとそれっぽい感じ` | 0.481 | 5.00s | -0.38 | vr=0.78 stage=2 |

### `media__youtube_far_field__16` (media_far_field)

- 期待: `そうですね。だからそこら辺もなんか何ができるかっていうところのリストも当然持ってるので、そういうアドバイスまでやってくれたんです。`

| 構成 | outcome | text | CER | latency | logprob | extra |
|---|---|---|---|---|---|---|
| small | wrong | `プロドコードが分かれ言ってくれてそういうアウトレイをポイポイっとプロドコードを足すからます` | 0.903 | 0.98s | -0.73 |  |
| kotoba | wrong | `コードコードから言ってくれてそのURAをポイポイッとコロドコロで渡したら` | 0.871 | 4.03s | -0.50 |  |
| two_stage | wrong | `コードコードから言ってくれてそのURAをポイポイッとコロドコロで渡したら` | 0.871 | 4.98s | -0.50 | stage=2 |
| two_stage_dualvad | wrong | `コードコードから言ってくれてそのURAをポイポイッとコロドコロで渡したら` | 0.871 | 4.98s | -0.50 | vr=0.86 stage=2 |

## 結果サマリと推奨

- 平均CER最良: **kotoba** (0.703)
- 平均レイテンシ最速: **small** (0.88s)
- 幻聴最少: **small** (0件)

## 次のアクション候補

1. 推奨構成を Plan の Phase 0/0.5/0.7 に反映
2. 本番 `app.py` への段階統合
3. AEC（信号レベル自TTSキャンセル）を別フェーズで評価
