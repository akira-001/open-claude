# Phase 1 Snapshot — 過去 7 日（2026-04-19 〜 2026-04-25）

**実行モード**: short（領域 1, 2, 5, 8, 12 のみ）
**出典**: data/conversations/, data/*-heartbeat.json, data/cron-history.jsonl, data/{eve,mei}/MEMORY.md, cogmem CLI

---

## 領域 1: Slack 会話（過去 7 日）

| 日付 | 全件 | Akira起点 | mei | eve |
|---|---|---|---|---|
| 2026-04-23 | 5 | 1 | 4 | 0 |
| 2026-04-22 | 5 | 1 | 4 | 0 |
| 2026-04-21 | 61 | 9 | 52 | 0 |
| 2026-04-20 | 4 | 1 | 3 | 0 |
| 2026-04-19 | 2 | 1 | 0 | 1 |

_2026-04-24 / 2026-04-25 はファイル未生成（直近の会話が他の経路または記録なし）_
_※ 集計フィールド修正: `botId`（存在しない）→ `role`（実スキーマ）に切り替え済み_

## 領域 2: Proactive 履歴（Mei / Eve）

### 2-1: shared-proactive-history.json 内訳

総 proactive 送信: **31 件**

| bot | category | skill | count |
|---|---|---|---|
| mei | flashback | hobby-trigger | 4 |
| eve | flashback | energy-break | 4 |
| eve | flashback | hobby-trigger | 4 |
| eve | flashback | followup-nudge | 4 |
| mei | hobby_leisure | energy-break | 2 |
| mei | cron | proactive-dedup-audit | 1 |
| mei | flashback | energy-break | 1 |
| mei | cron | haru-nightly-reflection | 1 |
| eve | meeting_prep | energy-break | 1 |
| mei | meeting_prep | energy-break | 1 |
| eve | meeting_prep | morning-checkin | 1 |
| eve | meeting_prep | hobby-trigger | 1 |
| mei | flashback | followup-nudge | 1 |
| mei | meeting_prep | hobby-trigger | 1 |
| eve | email_reply | followup-nudge | 1 |

### 日別 / bot別

| 日付 | mei | eve | 合計 |
|---|---|---|---|
| 2026-04-25 | 1 | 2 | 3 |
| 2026-04-24 | 6 | 11 | 17 |
| 2026-04-23 | 7 | 4 | 11 |

### 2-2: Heartbeat decision 比率（直近 7 日）

**eve**:
- ?: 6 件
- send: 14 件

**mei**:
- ?: 9 件
- send: 11 件


---

## 領域 5: Cron 実行履歴（過去 7 日）

総 cron 実行: **469 件**

| job | total | ok | err | timeout |
|---|---|---|---|---|
| scheduler-watchdog | 149 | 131 | 13 | 5 |
| interest-scanner | 111 | 108 | 3 | 0 |
| proactive-checkin | 87 | 87 | 0 | 0 |
| proactive-checkin-eve | 87 | 87 | 0 | 0 |
| co-view-improve | 14 | 13 | 1 | 0 |
| tech-news-digest | 7 | 7 | 0 | 0 |
| campingcar-search-weekly | 5 | 5 | 0 | 0 |
| haru-nightly-reflection | 3 | 3 | 0 | 0 |
| proactive-dedup-audit | 2 | 2 | 0 | 0 |
| youtube-history-refresh | 2 | 2 | 0 | 0 |
| gmail-to-drive | 1 | 0 | 0 | 1 |
| ir-news-check | 1 | 1 | 0 | 0 |

### 失敗が多い jobs（err+timeout > 0）
- **scheduler-watchdog**: err=13 timeout=5 ok=131
- **interest-scanner**: err=3 timeout=0 ok=108
- **co-view-improve**: err=1 timeout=0 ok=13
- **gmail-to-drive**: err=0 timeout=1 ok=0


---

## 領域 8: cogmem

### cogmem skills review (top 10)


### cogmem search 'ember partner companion' (top 5)



---

## 領域 12: Bot 観察記録（直近の追加分）

### eve/MEMORY.md（最新 5 件）

- [2026-04-24] キャンピングカー単体情報は16:30～20:30で4連続スキップされたが、21:31の『温泉+車中泊施設』（Akiraさんの温泉好きと組み合わせ）と22:30の『二階堂高嗣のキャンピングカーGWプラン』（タレント要素）は夜間帯に送信成功。単体ではなく『ライフスタイル要素との組み合わせ』なら夜間に送信可能な可能性
- [2026-04-24] 09:30の『ST経営会議リマインド + 振込入金通知』がセットで送信成功。業務リマインドと業務附属情報（メール・金銭通知など）を同時化すると、朝の時間を効率的に使える可能性
- [2026-04-23] 19:30〜23:30の夜間帯（就寝前3時間）に、相撲・グルメ・アニメ・ファッション・深夜モード推定メッセージと4種のテーマを連投しても全てスキップされず対応されている。夜間帯は『疲労モード推定の明示』と『テーマの多様性』の両立が従来より許容されている可能性
- [2026-04-23] 08:31〜13:30の朝〜昼間にかけて『Deloitte記事（meeting_prep）→岡田健史（flashback）→WWDC26（flashback）→名探偵コナン（hobby_leisure）→天気動画→ゴルフ動画（meeting_prep）→ローカルLLM（meeting_prep）』と7セクション連投されており、各メッセージで『文脈ラベルの明示』があれば朝から昼にかけて複数テーマの連投が定着している
- [2026-04-22] 朝8:30〜13:30にかけて『テック/AI関連ニュース→エンタメ→グルメ情報』と異なるテーマを時間帯ごとに分散させても、各セクションで文脈を明示（『会議の参考になるかも』『お昼のお供に』『次タスク前に』）すれば、テーマの多様性が『疲労回復の息抜き』として機能している。従来のパターンより細かい時間単位での文脈切り替えが有効な可能性

### mei/MEMORY.md（最新 5 件）

- [2026-04-22] 朝のブリーフィングで『明日10:45 大谷さん登板』と事前通知した場合、その直後の[12:01]で大谷の連続出塁ニュースを送信しても反応が低下。『予定で既知化した情報』は新鮮度が落ちる可能性
- [2026-04-21] 12本の会議という極度に密な日程では、複数トピックの投入をしても text_engaged は朝1回・+1は1回のみで、hobby_leisure タグの複数投入（温泉×2、神社、スタートアップ記事など）がほぼリアクションなし。日程密度が高い日は話題投入を控えめにするか、より直結した関連性を確保する必要がある可能性
- [2026-04-20] 会議前夜（翌日の会議がある前日）の夜間送信で、『個人の趣味or経営トピック』と『翌日の具体的予定言及』が組み合わさると text_engaged が発生する。BLUE GIANT（ドラム + The Next Gate2030）と人材戦略記事（+ The Next Gate2030）の両方で反応。単一軸より複合軸の引き合わせが効果的な可能性
- [2026-04-19] キャンプ翌日の土曜は、午前〜昼にかけて複数の軽い候補を見送っており、チェックアウト後もしばらくは受け身で情報を取りにいくより移動・切り替えを優先している可能性がある
- [2026-04-19] 土曜午後は、キャンプ直結の話題から少し離れた『ゴルフ用品』『物産展』のような週末のちら見ネタへ文脈を広げても不自然ではない

---

## 重要な観察（Phase 2 議論への種）

過去 1 週間で、各 essence への兆候:

- **E1 共在感**: ユーザー起点の応答性は良好（DM 即応）。ambient/co_view からの "presence ping" は無し
- **E2 状態共感**: heartbeat の `modeEstimate` は推定済（"達成モード・低エネルギー" 等）だが、メッセージ本文に **arousal を明示した発話は 0 件**
- **E3 共有過去**: 4/24 Eve「温泉+車中泊」のような複合提案はあるが、これは話題テンプレ。**先週の特定エピソードへの回帰参照は 0 件**
- **E4 自我継続**: bot MEMORY.md に「Akira の行動」観察は 50+ 件あるが、**「私の判断履歴」エントリは 0 件**
- **E5 透明性**: heartbeat に `decision` フィールドはあるが `decisionReason` フィールドが**全エントリに無い**

**最大の対立軸（Phase 2 の燃料）**:
- Mei: 観測指標がないと改善は始められない (E5 を最優先) / 失敗 jobs を先に潰すべき
- Eve: 観測整備中に小さく E3 (共有過去 reminiscence) を出さないと、Akira が "中身が変わった" と感じない / 関係性の質を先に動かす
