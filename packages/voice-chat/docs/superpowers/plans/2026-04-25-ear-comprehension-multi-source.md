# EmberChat 耳の理解力改善 Plan — マルチソース・コンテキスト戦略

> **Status:** Strategy Plan + Phase 0.5/0.7 ベンチ検証完了（2026-04-25）
> **作成日:** 2026-04-25
> **起点:** YouTube視聴中のSTT幻聴事例（'2人分に着替える音声になりに歯応えしてすっきり生地が出てくる' / '大阪大学 駅' — どちらも実音声と無関係な完全幻聴）
> **ベンチ結果:** `2026-04-25-stt-benchmark-analysis.md`（kotoba-whisper-v2.0 で近接発話 CER 1/3 削減を実測）

## ゴール

EmberChat（別端末で動く常時稼働AIパートナー）が、Akiraさんが「今何をしているか」を理解し、適切なタイミングで役立つ情報提供ができるようにする。

**狭義のゴール**: マイクSTT幻聴に振り回されない耳
**広義のゴール**: マイク・クラウド・ネットワーク発見・対話の4経路から状況を組み立てる「観察＋確認」型コンテキストエンジン

---

## 起点となった問題

### 観測ログ（Listening mode、gemma4:e4b、2026-04-25 19:26）

```
19:26:28 [STT/small] '2人分に着替える音声になりに歯応えしてすっきり生地が出てくる' (spoke@19:26:20, +7.8s)
19:26:28 [ambient] buffered
19:26:36 [batch] 1件 → LLM: ['2人分に着替える音声になりに歯応えしてすっきり生地が出てくる']
19:26:36 [ambient] model=gemma4:e4b method=llm_batch source=不明 intervention=skip
19:26:36 [ambient] → SKIP (unknown)
19:26:39 [stt_correct] skipped for low-confidence ambient text
19:26:39 [STT/small] '大阪大学 駅' (spoke@19:26:28, +10.8s)
```

**実音声**: テレ東BIZ「前澤友作のプライベートゴルフ場」YouTube動画（千葉のゴルフ場、ロールスロイス、ZOZO、カブアンド等）
**実STT結果と動画内容の重なり**: 0文字（完全な幻聴）

### 既存パイプラインの解析

`app.py:4400-4485` の処理フロー：

| 段 | 関門 | 結果 |
|---|---|---|
| 1 | Whisper `small` (int8/CPU, beam=1, VAD on) | 幻聴を出力 |
| 2 | `no_speech_prob > 0.6` 破棄 | 通過（0.3〜0.6帯と推定） |
| 3 | `_is_whisper_hallucination`（文字反復・多様性） | 通過（多様性ある幻聴） |
| 4 | `_looks_like_initial_prompt_echo` | 通過 |
| 5 | キーボードパルス検出 | 通過 |
| 6 | `should_apply_stt_correction` | False（speaker未特定・wake未検出） |
| 7 | `classify_source` | "unknown"（30字＜40字、buf小、call語なし） |
| 8 | `decide_intervention` | "skip"（unknown + reactivity<5） |

**評価**: 最終的に SKIP で止血されているが、構造的な弱点が3点：
1. Whisper small は遠距離マイクの劣化メディア音声で頻繁に幻聴する
2. `classify_source` がテキストのみで判定、音響特徴を使えていない
3. `avg_logprob`（faster-whisper の信頼度信号）を捨てている

---

## 制約と前提

### 動作環境
- **EmberChat は別端末で稼働**（リビング/寝室/キッチン/モバイルを想定）
- 持っている入力: マイクのみ（必要に応じてカメラ）
- 持っている出力: スピーカー（TTS）
- ネット接続: 家のWi-Fi 内 + クラウド到達可

### 視聴ソースの多様性
Akiraさんが観る/聴く端末は複数：

| 視聴端末 | EmberChatから取得可能性 |
|---|---|
| メインMac (Chrome等) | ◎ Bridge経由で取得可 |
| iPad (YouTube/Netflix app) | △ Shortcuts連携 or 不可 |
| iPhone (YouTube app) | △ 同上 |
| Apple TV (YouTube/Netflix) | ○ mDNS / MediaRemote / HomeKit |
| Chromecast / GoogleTV | ◎ mDNS Cast Discovery + DIAL API |
| Spotify Connect端末 | ◎ Spotify Web API（クラウド） |
| Fire TV / 各社スマートTV内蔵アプリ | △〜× ベンダーAPI次第 |
| 古いTV+HDMI接続 | × ハード的に取れない |

→ **「自動で100%確実にソース特定」は構造的に不可能**

### 思想的制約
- 全知ぶった発話は禁止（憶測で恥かかない）
- マイクSTT幻聴をそのまま反応に変換しない
- 介入コスト > 沈黙コストの原則を堅持

---

## 思考のピボット

### Pivot 1: 耳 ≠ マイク

✗ 古い問い: 「マイクで拾った音をどう正確に文字起こしするか」
○ 新しい問い: 「Akiraさんの今の状況を、利用可能な全信号から推定するか」

マイク → 空気 → スピーカー → 圧縮 の経路は**情報を捨て続ける劣化パイプ**。デジタル直取り（NowPlaying API、字幕API、ネットワーク発見）には絶対勝てない。

### Pivot 2: メディア音はマイクで聞かない

EmberChatのマイクSTTは「**Akiraさんの近接発話のみ**」に絞る。メディア音声（TV/YouTube/音楽）は別経路で取得する。マイクが拾うメディア音は **音響シーン分類**（speech/music/TV/silence）にとどめ、文字化しない。

### Pivot 3: 全知ぶらない、分からない時は聞く

複数ソースを試して取れない場合は、**自然な会話で**「今何観てるの？」と聞く。これが人間のパートナーシップに近い振る舞いで、実は最もロバスト。**AIだから全部知ってる必要はない**。

---

## 信号源マップ（5階層 Tiered Resolution）

並列に試して、最も確度の高い結果を採用する。

### Tier 1: パッシブ・ネットワーク発見（自動／設定不要）

| プロトコル | 発見できるもの | 取れる情報 |
|---|---|---|
| mDNS `_googlecast._tcp` | Chromecast / GoogleTV | DIAL API で NowPlaying（appName, title） |
| mDNS `_airplay._tcp` | Apple TV / AirPlay受信機 | デバイス情報＋（要ペアリング）NowPlaying |
| MediaRemote framework | Apple TV (iOS同ネット) | NowPlaying |
| mDNS `_spotify-connect._tcp` | Spotify Connect端末 | 再生中track |
| Roku ECP | Roku TV | アプリ名・チャンネル |

**実装難度**: pychromecast (Python) で Chromecast は数行。Apple TV系は要研究。

### Tier 2: クラウドAPI（自動／OAuth1回）

| サービス | API | 取れるもの |
|---|---|---|
| **Spotify** | `/me/player/currently-playing` | どの端末で再生中でも track info |
| Apple Music | MusicKit (制限多い) | 再生中（Apple ID共有時） |
| YouTube Data API | `/videos`, `/captions` | videoId既知なら字幕・タイトル |
| Last.fm Scrobbling | scrobble feed | 横断的な音楽再生履歴 |
| Slack | Web API（既存） | 未読DM・ステータス・チャンネル投稿 |
| Google Calendar | gcal API（既存） | 次の予定・会議中フラグ |
| Gmail | Gmail API（既存） | 重要メール |

**Spotifyが最強**: 視聴端末を問わずクラウドに集約される。

### Tier 3: ユーザー側に1度仕込む自動化

| 仕込み先 | 内容 |
|---|---|
| iPad/iPhone Shortcuts | YouTube/Netflix起動時にWebhookでEmberChatにURL通知 |
| Mac Chrome拡張 | YouTube視聴URLを定期push |
| メインMac LaunchAgent | nowplaying-cli + frontmost app + Zoom起動検出 |

### Tier 4: 音響指紋（Last Resort）

| 手段 | 識別範囲 |
|---|---|
| ACRCloud / AudD クラウドAPI | 数千万曲＋一部TV番組 |
| Shazam Library (iOS Native) | 楽曲のみ |
| chromaprint (自前) | 自前DB持つなら |

**起動条件**: scene_classifier が "music" or "tv" 検知時のみ（コスト制御）。

### Tier 5: 会話で確立（最重要）

```
ambient state: media_likely 検知
              ↓
        Tier 1-4 全部空振り
              ↓
        Mei が自然に: 「ねえ、今何観てるの？」
              ↓
   Akira: 「前澤さんのYouTube」
              ↓
   YouTube Data API で「前澤友作 ガイア」検索
              ↓
   Top候補1件 を session.media_context にセット
              ↓
   字幕取得 → 5-10分間はその動画前提で動く
              ↓
   音響シーン変化検知（曲調変化・無音等）→ context無効化 → 再質問
```

**ルール**:
- 1セッション内で同じ質問は3回まで（拒否されたら諦める）
- セッションキャッシュ 5-10分
- "外れた"フィードバックがあれば即破棄
- 静寂時間や会話中には聞かない

---

## アーキテクチャ全体

```
┌─ Memory層 (cogmem) ────────────────────────────┐
│   過去の会話・好み・反応履歴                    │
└──────────────────────────────────────────────────┘
            ↑                            ↓
┌─ Reasoning層 (Mei/Eve LLM + Policy) ───────────┐
│   AmbientState を読んで発話/沈黙を決定         │
│   メディア確度別に介入レベル切り替え           │
└──────────────────────────────────────────────────┘
            ↑
┌─ Sensing層 ──────────────────────────────────────┐
│  Tier 5: Conversational Resolution             │
│   "今何観てる？" → ユーザー応答 → 確立        │
│       ↑ fallback                                │
│  Tier 4: Audio Fingerprinting (ACR)            │
│       ↑ fallback                                │
│  Tier 3: User-side Automation (Shortcuts/拡張) │
│       ↑ fallback                                │
│  Tier 2: Cloud APIs (Spotify/Cal/Slack)        │
│       ↑ fallback                                │
│  Tier 1: Network Discovery (mDNS/Cast/AirPlay) │
│       ↑ trigger                                 │
│  Mic Scene Classifier (YAMNet/PANNs)           │
│       ↑                                         │
│  Mic Audio (限定STT: wake or Akira近接のみ)    │
└──────────────────────────────────────────────────┘
```

---

## AmbientState モデル

```python
@dataclass
class AmbientState:
    primary_activity: Literal[
        "watching_video", "listening_music", "coding",
        "in_call", "in_meeting", "writing", "thinking_alone",
        "talking_to_someone", "household", "idle", "unknown"
    ]
    media_context: MediaContext | None
    media_confidence: Literal["high", "medium", "low", "none"]
    user_speech: SpeechContext | None
    social_presence: Literal["alone", "with_akira_only", "with_others"]
    intervention_budget: float  # 0.0-1.0
    location_hint: str | None  # "living"/"bedroom"/"kitchen"

@dataclass
class MediaContext:
    source: Literal["youtube", "spotify", "apple_music", "tv", "unknown"]
    title: str | None
    artist_or_channel: str | None
    position_sec: float | None
    duration_sec: float | None
    transcript_window: str | None  # 現在位置±30秒の字幕
    resolved_via: Literal["mdns", "cloud_api", "shortcut", "acr", "conversation"]
```

---

## 介入ポリシー（メディア確度別）

| confidence | 振る舞い |
|---|---|
| **High（Tier 1-3 で確定）** | co-view モード。具体的な補足発話可（「前澤さんの最近のニュースは...」） |
| **Medium（Tier 4 ACR一致）** | 控えめ補足。曖昧表現で（「これ前澤さんの動画かな？」） |
| **Low（mic scene=media のみ）** | コメント禁止。Akiraさんの独り言にだけ短く相槌、または1回だけ「これ何観てるの？」 |
| **None（不明）** | 完全沈黙 |

### Activity別の反応モード

| Activity（推定源） | 反応モード |
|---|---|
| in_meeting (Bridge: Zoom/FaceTime running) | **完全沈黙** |
| coding (Bridge: VSCode focused, keystroke high) | 沈黙、wake のみ |
| watching_media (媒体特定済み) | reactivity 5 = co-view |
| watching_media (媒体不明) | passive、Tier 5 を試す |
| listening_music (Cloud: Spotify playing) | 曲切れ目に短コメント可 |
| household (mic scene: cooking/water/vacuum) | 手の離せない作業 → 音声タスク歓迎 |
| conversation (mic: multi-speaker, not Akira call) | 完全沈黙 |
| alone_quiet | wake 待機 |
| absent | 不在モード |

state ソース優先順位: **Bridge > Cloud API > Network Discovery > Mic Scene** の順で信頼。

---

## 実装ロードマップ

### Phase 0: 耳の出血止血（半日）

- [ ] **Step 0.1:** `_transcribe_sync` に `avg_logprob < -0.8` 破棄を追加
  - File: `app.py:454` 直後（return text の前）
  - 1行: `if seg_list and sum(s.avg_logprob for s in seg_list)/len(seg_list) < -0.8: return ""`
- [ ] **Step 0.2:** `_is_near_field` 関数追加（マイク近接判定）
  - 高域/低域比 + RMS変動率で判定
  - メディア遠距離音声を弾く
- [ ] **Step 0.3:** `classify_source` の閾値見直し
  - "20字以上 + speaker未特定 + MEI未発話 + call語なし + non-near-field" → media_likely 格上げ
  - 現状の "40字以上" は緩すぎる
- [ ] **Step 0.4:** `no_speech_prob` 閾値を fast モード時 0.5 に締める
- [ ] **Step 0.5:** decoding parameters 追加（ベンチで使用済み・効果確認）
  - `condition_on_previous_text=False`（前セグメント引きずり防止）
  - `compression_ratio_threshold=2.4`（繰り返し系幻聴破棄）
  - `log_prob_threshold=-1.0`（自信ない時に空文字）
  - `temperature=[0.0, 0.2, 0.4]`（fallback で慎重に）
  - File: `app.py:446-451` の `model.transcribe()` 呼び出し

### Phase 0.5: kotoba-whisper-v2.0-faster へ置き換え（1-2日 / **採用決定**）

> **ベンチエビデンス**: 近接発話 CER 0.079 → **0.024**（誤り率 1/3）
> 特に `wake__good_morning_01` で small が "メイ**ン**おはよう" と誤読していたものが kotoba は "メイおはよう" と完全認識。wake_detect 信頼性に直結する致命的改善。

- [ ] **Step 0.5.1:** `_whisper_model_fast` を kotoba-tech/kotoba-whisper-v2.0-faster に置換
  ```python
  # app.py:384
  _whisper_model_fast = WhisperModel(
      "kotoba-tech/kotoba-whisper-v2.0-faster",
      device="cpu", compute_type="int8",
  )
  ```
  - HFキャッシュ済み: `~/.cache/huggingface/hub/models--kotoba-tech--kotoba-whisper-v2.0-faster/`
  - サイズ: 1.5GB（faster-whisper / ctranslate2 形式、`--device metal` 検証は別タスク）
- [ ] **Step 0.5.2:** **2段階デコーディング前提**で動作させる（Phase 0.7 と一体）
  - kotoba 単独は約5倍遅い（0.79s → 4.02s）
  - always-on で毎発火 4秒は重い → wake/Akira近接時のみ kotoba を呼ぶ
- [ ] **Step 0.5.3:** メモリ・load 時間の本番影響実測
  - WhisperModel 常駐保持 vs 都度ロードの判断
- [ ] **Step 0.5.4:** 既存 fixtures の manifest 修正
  - `desk_monologue` / `direct_question` / `tv_outro` は録音内容と transcript が不一致（ベンチで判明）
  - 削除 or 録音し直し or transcript を実音声に合わせる

### Phase 0.7: 2段階デコーディング（2-3日 / **採用決定・条件発火必須**）

> **ベンチエビデンス**: kotoba 単独と同等の精度（CER 0.024）。本番では発火条件設計が ROI を決める。

- [ ] **Step 0.7.1:** Stage 1（small）と Stage 2（kotoba）の振り分け
  - Stage 1: 既存 `_whisper_model_fast` を small のまま維持（高速・wake/scene判定用）
  - Stage 2: kotoba を別インスタンスで保持
- [ ] **Step 0.7.2:** 発火条件の実装
  - `wake_detected == True`（wake_detect.py 後）
  - `speaker_result.is_akira AND near_field_score > threshold`
  - `_always_on_conversation_until > now`（会話モード中）
- [ ] **Step 0.7.3:** 録音バッファ保持・再デコード
  - Stage 2 発火時に同じ audio_data を kotoba で再推論
  - Stage 1 結果は破棄、Stage 2 結果を最終 text として採用
- [ ] **Step 0.7.4:** 本番レイテンシ実測
  - 平常時: small ~0.8s（変わらず）
  - Akira発話時: small + kotoba ~5s（許容範囲か検証）
- [ ] **Step 0.7.5:** Phase 0.5 の置き換えと整合
  - Phase 0.5 を「Stage 2 用に kotoba モデルを追加保持」に読み替え（`_whisper_model_fast` は small のまま）

### Phase 0.9: 二重VAD（webrtcvad + Silero）— **採用見送り**

> **2026-04-26 追加調査**: 当初の CER 悪化（0.76→0.97）は `webrtcvad_voice_ratio` の audio配列破壊バグが原因と判明。修正後は CER 0.735（two_stage と同等）まで回復。**ただし期待した「メディア弾き」効果は原理的に得られず、採用見送り判定は変わらず**。

#### バグ詳細
- `(audio * 32767)` が特定条件で in-place 化され audio が破壊
- CPython 3.14 + NumPy 1.26 + 特定の呼び出し履歴の組み合わせ
- 修正: `np.multiply(audio, 32767.0, dtype=np.float32)` で dtype 明示
- 検証スクリプト: `tests/investigate_dualvad.py`

#### voice_ratio による「メディア弾き」が不可能な理由
- 静寂・ノイズ: voice_ratio 0.00-0.04（skip可能）✅
- 近接発話: voice_ratio **0.44-0.65**
- 遠距離メディア（人声）: voice_ratio **0.63-1.00**
- → 近接発話より遠距離メディアの方が voice_ratio が高い**逆転現象**
- 閾値での切り分け不可能

#### 結論
- ❌ **現実装は採用しない**（メディア弾きはできない）
- ⭕ 副次効果として静寂・空メディアの超低レイテンシ skip はあるが、Phase 0 の avg_logprob 破棄で同等の防衛効果が得られるため、追加価値薄い
- 🔬 **再設計するなら別アプローチ**:
  - webrtcvad で voice 区間のみ抽出して**音声を実際に切り刻む**設計
  - 音響特徴（near-field 判定、SNR、duration）と組み合わせる
  - WebRTC VAD 単体では「人声 vs メディア人声」の区別は原理的に不可能なので、別の信号と組み合わせる前提で再考

### Phase 0.95: 信号レベル AEC（保留）

- ⏸ 別ベンチで検証してから判断
- 自TTS出力との相関を引いて echo_suppress_until を不要にできる可能性
- 実装は speex / WebRTC AEC（複雑、リアルタイム制御ループ要）

### Phase 1: Spotify NowPlaying購読（半日・最大ROI）

- [ ] **Step 1.1:** Spotify Web API OAuth 設定
  - Akiraさんの Spotify アプリで refresh_token 取得
  - `.env` に `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`
- [ ] **Step 1.2:** `spotify_now_playing.py` 新規作成
  - 30秒ごとに `/me/player/currently-playing` をポーリング
  - track_id, title, artist, position, is_playing をstateに反映
- [ ] **Step 1.3:** AmbientListener に `external_audio_context` フィールド追加
- [ ] **Step 1.4:** Mei/Eve プロンプトに `[いまSpotifyで再生中: ...]` を注入
- [ ] **Step 1.5:** テスト: `tests/test_spotify_context.py`

### Phase 2: mDNS ネットワーク発見（2-3日）

- [ ] **Step 2.1:** `pychromecast` 統合 — Chromecast/GoogleTV 発見
- [ ] **Step 2.2:** Cast NowPlaying ポーリング
  - app_id, media_metadata（YouTubeなら videoId 含む場合あり）
- [ ] **Step 2.3:** YouTube Data API でvideoId → title/captions取得
- [ ] **Step 2.4:** Apple TV / AirPlay デバイス発見（要研究）
- [ ] **Step 2.5:** `network_discovery.py` モジュール化

### Phase 3: 会話的確立フロー（Tier 5）（1週）

- [ ] **Step 3.1:** `MediaContextResolver` クラス実装
  - Tier 1-4 並列試行ロジック
  - confidence 計算
- [ ] **Step 3.2:** "今何観てる？" 自然質問のタイミング判定
  - scene=media_likely + Tier 1-4 失敗 + 直近独り言あり + 5分以上聞いてない
- [ ] **Step 3.3:** YouTube Data API で検索 → 候補確定フロー
- [ ] **Step 3.4:** session.media_context 保持・無効化ロジック
  - 5-10分キャッシュ、scene変化で再評価
- [ ] **Step 3.5:** ユーザー拒否（"今は聞かないで"）の検出と記憶
- [ ] **Step 3.6:** テスト: dialog flow ユニットテスト

### Phase 4: メインMac Bridge（並行・1週）

- [ ] **Step 4.1:** `ember-context-agent` 新リポ作成（メインMac側、Python or Node）
- [ ] **Step 4.2:** macOS LaunchAgent として常駐
- [ ] **Step 4.3:** イベント送信:
  - `nowplaying-cli` で再生中メディア
  - `osascript` で frontmost app + window title
  - Zoom/FaceTime プロセス検出
  - キーストローク活動レベル
- [ ] **Step 4.4:** WebSocket クライアント → EmberChat へpush
- [ ] **Step 4.5:** EmberChat 側 WebSocket サーバ + state統合
- [ ] **Step 4.6:** Chrome拡張版（オプション）— YouTube/動画タブの url/title

### Phase 5: 音響シーン分類（1週）

- [ ] **Step 5.1:** YAMNet ONNX モデル組み込み（CPU推論）
- [ ] **Step 5.2:** scene_classifier モジュール
  - 出力: speech/music/tv/cooking/vacuum/silence/multi-speaker
- [ ] **Step 5.3:** classify_source に scene 情報を渡す
- [ ] **Step 5.4:** STT発火条件: `wake OR (speaker=Akira AND near_field)` に絞る
- [ ] **Step 5.5:** 環境音は scene のみで state 更新（Whisper通さない）

### Phase 6: 音響指紋（実験・1週）

- [ ] **Step 6.1:** ACRCloud / AudD API 評価（精度・コスト・レイテンシ）
- [ ] **Step 6.2:** scene=music/tv 検知時のみ起動
- [ ] **Step 6.3:** confidence=medium の co-view 動作テスト

### Phase 7: iPad/iPhone Shortcuts 自動化（数日）

- [ ] **Step 7.1:** Akiraさん用 Shortcut テンプレート作成
  - YouTube/Netflix/Apple TV+ アプリ起動時に URL/title を Webhook
- [ ] **Step 7.2:** EmberChat 側 受信エンドポイント
- [ ] **Step 7.3:** 配布手順 doc 化

### Phase 8: マルチデバイス・関係的記憶（中長期）

- [ ] **Step 8.1:** EmberChat 端末ロケーションタグ（"living"/"bedroom"/"kitchen"）
- [ ] **Step 8.2:** 複数端末の音量差で Akira位置推定
- [ ] **Step 8.3:** 家族メンバーの speaker profile + 関係的記憶
- [ ] **Step 8.4:** 留守番モード（来客検知・宅配音検知 → Akiraさんに通知）

---

## 推奨される最初の手（着手順 / ベンチ結果反映版）

### 🥇 即効・1日コース
1. **Phase 0**（半日）耳止血: avg_logprob破棄 + near-field判定 + scene閾値 + decoding parameters
2. **Phase 1**（半日）Spotify NowPlaying購読: 投資/リターン圧倒的

### 🥈 数日で本格改善
3. **Phase 0.5 + 0.7**（合計 3-5日）kotoba-whisper-v2.0 + 条件発火2段階デコーディング
   - **近接発話 CER を 1/3 に削減**（ベンチ実測）
   - wake_detect 信頼性が決定的に向上（"メイ" の誤読が消える）

### 🥉 戦略的差別化（1週〜）
4. **Phase 3**（1週）会話的確立フロー: AIに「全知の振り」をやめさせる設計の勝利

---

これで現状の「STT幻聴に振り回される耳」が以下の4つの強みを持った耳に化ける：

1. **近接Akira発話を3倍正確に拾う**（kotoba + 2段階）
2. **音楽は確実に分かる**（Spotify購読）
3. **メディア視聴は素直に聞く**（会話的確立）
4. **静かな時はちゃんと黙る**（avg_logprob + decoding parameters）

Phase 0+1 を1日で先に入れて即効性を体感 → Phase 0.5+0.7 で本質改善 → Phase 3 で振る舞いを賢くする、の順がROI最大。

---

## 設計原則

1. **耳はAkiraさんの直接発話だけに使う。メディア音は耳で聞かない**
2. **環境音は文字化せず分類だけ**（speech/music/cooking/silence）
3. **コンテキストは多経路から取る**（Network/Cloud/Bridge/Conversation）
4. **取れない時は素直に聞く**（憶測で発話しない）
5. **発話判断は「沈黙コスト < 介入コスト」を厳守**
6. **session.media_context で確立した内容は5-10分保持、シーン変化で再評価**
7. **ユーザーの拒否は記憶する**（同じこと3回聞かない）

---

## 関連ファイル

### 既存（変更対象）
- `voice_chat/app.py` — STTパイプライン、ambient統合
- `voice_chat/ambient_listener.py` — classify_source / decide_intervention
- `voice_chat/ambient_policy.py` — should_apply_stt_correction
- `voice_chat/ambient_rules.json` — 学習ルール
- `voice_chat/speaker_id.py` — Akira/家族識別

### 新規（このPlanで追加）
- `voice_chat/spotify_now_playing.py`
- `voice_chat/network_discovery.py`
- `voice_chat/scene_classifier.py`
- `voice_chat/media_context_resolver.py`
- `voice_chat/external_context.py`（Bridge/Cloud統合層）
- `voice_chat/audio_features.py`（near-field判定等）
- メインMac側: `ember-context-agent/`（別リポ or サブディレクトリ）

### 検証済み（2026-04-25 ベンチで作成）
- `voice_chat/tests/benchmark_stt_quality.py` — STT 4構成比較ベンチスクリプト
- `voice_chat/tests/fixtures/audio/incoming/media__youtube_far_field__01〜16.{webm,transcript.txt}` — 遠距離メディア音声 16サンプル + sidecar transcript
- `docs/superpowers/plans/2026-04-25-stt-benchmark-results.{json,md}` — 生データ
- `docs/superpowers/plans/2026-04-25-stt-benchmark-analysis.md` — 最終分析レポート

---

## オープンな決定事項

### ✅ 解決済み（ベンチで決着）
- ~~kotoba-whisper-v2.0 採用するか~~ → **採用**（CER 1/3 削減）
- ~~2段階デコーディング採用するか~~ → **採用（条件発火必須）**
- ~~二重VAD 採用するか~~ → **採用見送り**（CER悪化）
- ~~AEC 採用するか~~ → **別フェーズ保留**

### Akiraさん確認待ち
1. Phase 0.5 採用順: 即時（Phase 0 と並行）か、段階的（Phase 0 → 0.5 → 0.7）か？
2. Phase 0.7 の発火条件: `wake_detected OR Akira近接 OR 会話モード` の3条件で十分？
3. Phase 1 の Spotify トークン取得は手動でやる？それとも自動セットアップフロー作る？
4. Phase 3 の「分からない時は聞く」を有効にする最小 reactivity レベル？（4以上？5固定？）
5. メインMac Bridge は Python LaunchAgent or Node.js？（既存スタックとの整合性）
6. Phase 6 ACR は商用API使う前提？コスト許容範囲は？
7. EmberChat 端末は1台想定？将来複数想定（Phase 8 の優先度）？

### 🔬 残課題（要 isolated 検証）
- 二重VAD の悪化原因究明（temperature determinism or 内部キャッシュ）
- kotoba のメモリ使用量・load 時間の本番影響（1.5GB モデル常駐の現実性）
- MPS/Metal で kotoba を動かせるか（現状CPU int8、Metal で 2-3倍高速化の可能性）

---

## 成功基準

このPlanの効果は以下で測る：

1. **STT幻聴反応率**: メディア音声に対する誤った発話/skip率
   - 現状: 計測なし → 目標: <1%
2. **メディアコンテキスト解決率**: media_likely 検知時にcontext確定できた割合
   - 現状: ほぼ0% → 目標: >70%（Tier 1-3で50%, Tier 5で+20%）
3. **役立つ発話率**: ユーザーから positive reaction を得た発話 / 全発話
   - 現状: 計測なし → 目標: ベースライン確立後 +50%
4. **介入過多率**: ユーザーから negative reaction（"うるさい"等）を得た割合
   - 現状: 計測なし → 目標: <2%

ログ拡張: `co_view_*_check.sh` を拡張して上記4指標を集計可能にする。
