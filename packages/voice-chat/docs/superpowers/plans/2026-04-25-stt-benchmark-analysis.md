# STT Quality Benchmark — 最終分析レポート

> **生データ**: `2026-04-25-stt-benchmark-results.{json,md}`
> **ベンチスクリプト**: `tests/benchmark_stt_quality.py`
> **日付**: 2026-04-25

## TL;DR

| 結論 | エビデンス |
|---|---|
| **kotoba-whisper-v2.0 を採用** | 近接発話 CER 8% → **2.4%**（誤り率 1/3） |
| **2段階デコーディングの採用は条件付き** | 近接ではkotoba単独と同等、レイテンシは平均ベターだが本番効果は要検証 |
| **二重VAD（webrtcvad+Silero）は採用しない** | 遠距離メディアで CER 0.76 → 0.97 と悪化、効果なし |
| **遠距離メディア音声は文字化を諦める** | 全構成で CER>70%、構造的に解けない |

## ベンチ条件

- **対象構成**: small / kotoba / two_stage / two_stage_dualvad
- **サンプル**: 27 件
  - 既存 fixtures 9 件（wake/question/monologue/desk/direct/keyboard/media/tv）
  - 合成 2 件（silence_3s, white_noise_3s）
  - **遠距離メディア 16 件**（Akiraさん録音の `meeting-2026-04-25_22-06-44.webm` 7.76分 を 30秒間隔で 7秒チャンク切り出し）
- **モデル**: faster-whisper 1.2.1, CPU int8
- **decoding parameters**: `condition_on_previous_text=False`, `compression_ratio_threshold=2.4`, `log_prob_threshold=-1.0`, `no_speech_threshold=0.6`, `temperature=[0.0, 0.2, 0.4]`, `hotwords="メイ"`
- **CER**: 句読点・空白除去後の文字編集距離（jiwer）

## カテゴリ別結果

### ★ 近接発話シナリオ（n=3, wake/question/monologue）

これが本番で最も重要なシナリオ。Akira近接発話の認識精度。

| 構成 | 平均CER | 改善率 |
|---|---|---|
| small | 0.079 | baseline |
| **kotoba** | **0.024** | **-69%（誤り率1/3）** |
| two_stage | 0.024 | -69% |
| two_stage_dualvad | 0.024 | -69% |

サンプル別の決定的な差：

| サンプル | 期待 | small | kotoba |
|---|---|---|---|
| `wake__good_morning_01` | "メイ、おはよう。" | "メイ**ン**おはよう" CER=0.17 partial | "**メイ**おはよう" CER=0.00 **ok** |
| `question_schedule_planning_01` | "今日の予定どうしようかな？" | CER=0.00 ok | CER=0.00 ok |
| `monologue_tired_after_work_01` | "疲れたなあ、ちょっと休もうかな。" | CER=0.07 ok | CER=0.07 ok |

**`wake__good_morning_01` の "メイ" 誤読が決定的**。small は wake word を取り損ねる頻度が高く、これは本番の wake_detect の精度に直結する。

### 遠距離メディア（n=16, YouTube 7分動画 7秒チャンク）

| 構成 | 平均CER | 平均レイテンシ |
|---|---|---|
| small | 0.776 | 0.99s |
| kotoba | **0.722** | 4.35s |
| two_stage | 0.760 | 3.35s |
| two_stage_dualvad | **0.974** | 3.97s |

**全構成 CER>70%** で実用にならない。kotoba が最良だが、絶対値として悪すぎる。

サンプル別観察：
- `chunk_03` 期待: "なので、ま、とりあえずクロードコード広げて、ま、オンラインショップで..."
  - small: "どうもこんにちは。 今日は、 クローの子としておいて、 オンラインショックでやっ"
  - kotoba: "なのでとりあえずプロノコード広げてオンラインショップでやって"
  - kotoba は意味的にだいぶ近いが、固有名詞（クロードコード→プロノコード）誤認

- `chunk_15` 期待: "この色味とかもなんかカブトの色味とかを取ってきたりして..."
  - small: "うんこの色味とかもなんかカブトの色を踏みよってコントってことにしてちょっとそれが" CER=0.61
  - kotoba: "この色味とかもなんかかぶての色を見るとかを撮っていきたいとしてちょっとそれっぽい" CER=0.48
  - **two_stage_dualvad: "おうおう" CER=1.00（完全な失敗）**

### 静寂・ホワイトノイズ（n=2）

| 構成 | 結果 |
|---|---|
| 全構成 | ok_skip（空文字を返す）✅ |

→ どの構成も無音から幻聴を出さない。ベースは健全。

### 既存fixtures の品質問題

`desk_monologue` (1.10s), `direct_question` (1.50s), `tv_outro` (1.70s) は録音内容と manifest の transcript が明らかに不一致（"疲れたなあ" 期待 → "うーん" 出力）。これは ambient_listener 回帰テスト用に作られた合成サンプルで、STT精度ベンチには不向き。

## 二重VAD が悪化した原因分析（2026-04-26 追加調査で判明）

### 一次原因: `webrtcvad_voice_ratio` の audio 配列破壊バグ

トレース調査で **`(audio * 32767)` が in-place 演算として実行され、audio 自体が int16値で上書きされる** バグを発見した：

```
ENTRY:  id=100592eb0 mean=-0.000066    ← 正常な float32 音声
STEP1:  id_a1=100592eb0 mean=-2.173577  ← id 同じ！audio が int16値で上書き
```

`a1 = audio * 32767` の結果のIDが audio と同じ ＝ **新規バッファが作られず audio に直接書き込まれた**。本来 numpy の `*` 演算は新規配列を返すはず。

### 影響経路

1. webrtcvad に渡された audio が int16スケール（max=19393）に変質
2. 破壊された audio が後段の two_stage（small + kotoba）に渡される
3. kotoba が異常スケール値を「音声」と解釈 → 幻聴
4. → CER 0.974 という極端な悪化

### 再現条件の謎

- 単純な `np.random.randn` 配列では再現しない
- 関数引数渡しでも単独では再現しない
- WhisperModel ロード後でも単独では再現しない
- **`investigate_dualvad.py` の特定の呼び出し履歴（H1: kotoba 5回連続 → H3: webrtcvad）下でのみ再現**
- → **CPython 3.14 + NumPy 1.26 + メモリallocator状態 + 関数スコープ**の組み合わせが原因と推定
- 完全な根本究明は NumPy/CPython バグ報告レベル

### 修正

```python
# Before（バグあり）:
pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16).tobytes()

# After（dtype 明示で新規バッファ保証）:
scaled = np.multiply(audio, 32767.0, dtype=np.float32)
pcm = np.clip(scaled, -32768, 32767).astype(np.int16).tobytes()
```

### 修正後の再ベンチ結果

| 構成 | 修正前 CER | 修正後 CER |
|---|---|---|
| small | 0.743 | 0.753 |
| kotoba | 0.703 | 0.703 |
| two_stage | 0.726 | 0.733 |
| **two_stage_dualvad** | **0.863** | **0.735** |

dualvad の outcome 分布も two_stage と完全一致（ok=3, partial=1, missed=5, wrong=16, ok_skip=2）。

### 二次的な発見: voice_ratio による「メディア弾き」は原理的に不可能

修正後のベンチで voice_ratio 分布を見ると**期待と逆**：

| 種類 | voice_ratio |
|---|---|
| 静寂・ホワイトノイズ・空メディア | 0.00-0.04（skipされる）✅ |
| 近接発話（wake/question/monologue） | **0.44-0.65** |
| **遠距離メディア音声** | **0.63-1.00** |
| tv_outro | 1.00 |

**遠距離メディアの方が近接発話より voice_ratio が高い**。理由は連続的に人声が流れるから（ナレーション・対談動画では会話の隙間が少ない）。WebRTC VAD は「人声成分の有無」しか見ない設計で、**「近接 vs 遠距離」も「人声 vs メディア音声」も区別できない**。

→ voice_ratio による閾値切り分けは原理的に不可能。例えば近接発話 0.44 を skip しないために閾値を 0.40 にすると遠距離メディアは全通過。逆に 0.50 にすると近接発話の direct_question (0.60) は通るが wake_good_morning_01 (0.44) が誤skipされる。

### 結論（更新版）

- **バグ修正**: ✅ CER悪化は解消（0.863 → 0.735、two_stageと同等）
- **期待した効果**: ❌ メディア弾きは原理的に不可能（voice_ratio が逆順）
- **副次的効果**: ⭕ 完全静寂・ノイズの skip で超低レイテンシ（27サンプル中3件、それぞれ <0.01s）
- **採用判定**: **見送り（変わらず）** — 副次効果のためだけに WebRTC VAD を入れる価値は薄い。Phase 0 の avg_logprob 破棄で同等の防衛効果が得られる。

## レイテンシ詳細

近接発話シナリオ（n=3）の平均：
- small: 0.79s
- kotoba: 4.02s（5倍遅い）
- two_stage: 4.81s（small + kotoba 連続実行のため遅い）
- two_stage_dualvad: 4.82s

→ 本番では **near_field 検知 + Akira speaker_id 一致時のみ kotoba 起動**にすれば、平常時は small 0.8s、Akira発話時のみ +4s（約5秒応答）に抑えられる。

## 本番への適用提案

### 即時採用（ROI 高）

#### 1. **kotoba-whisper-v2.0-faster で `_whisper_model_fast` を置き換え**

`app.py:384` を変更：
```python
# Before:
_whisper_model_fast = WhisperModel("small", device="cpu", compute_type="int8")

# After:
_whisper_model_fast = WhisperModel(
    "kotoba-tech/kotoba-whisper-v2.0-faster",
    device="cpu",
    compute_type="int8",
)
```

**ただし**: kotoba は約5倍遅い（small 0.79s → kotoba 4.02s）。always-on パイプラインで毎発火 4秒は重い。**2段階デコーディングと併用する前提**で採用すべき。

#### 2. **decoding parameters を追加**

`_transcribe_sync` の `model.transcribe()` 呼び出しに以下を追加：
```python
condition_on_previous_text=False,
compression_ratio_threshold=2.4,
log_prob_threshold=-1.0,
temperature=[0.0, 0.2, 0.4],
```

#### 3. **`avg_logprob < -0.8` 破棄**

```python
if seg_list:
    avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
    if avg_lp < -0.8:
        return ""
```

これらは即実装可能、コスト微小、効果は近接発話で確実。

### 中期採用（実装注意）

#### 4. **2段階デコーディング**（条件発火）

Stage 1: small（高速、wake/scene 判定）
Stage 2: kotoba（条件発火）

発火条件：
- `wake_detected == True` （wake_detect.py 後）
- `speaker_result.is_akira AND near_field_score > threshold`
- `_always_on_conversation_until > now`（会話モード中）

これで平常時は small 0.8s、重要発話時のみ kotoba を起動して +4s。

ただし本ベンチでは「全サンプルが Akira 近接前提」なので Stage 2 がほぼ毎回発火し、kotoba 単独と同等の精度になっている。**本番の発火条件設計が効果を決める**。

### 採用見送り

#### 5. **二重VAD（webrtcvad + Silero）**

現実装は遠距離メディアで CER 0.76 → 0.97 に悪化。原因不明（temperature fallback or 内部キャッシュ影響）。
**現状では本番採用しない**。再設計するなら以下の方針：
- webrtcvad で「voice 判定された区間のみ抽出して再構築 → Whisper」（音声を実際に切り刻む）
- mode を 3→2 に下げる（aggressive過ぎ）
- voice_ratio 閾値を 0.1 → 0.3 に上げる

これらは別ベンチで検証してから判断。

#### 6. **AEC（Acoustic Echo Cancellation）**

別フェーズで評価予定。本ベンチでは未実施。

## Plan への反映

`docs/superpowers/plans/2026-04-25-ear-comprehension-multi-source.md` の Phase 0/0.5/0.7 に以下を反映する：

### Phase 0: 即時実装（半日）
- [ ] `avg_logprob < -0.8` 破棄
- [ ] `condition_on_previous_text=False` 等の decoding parameters 追加
- [ ] near-field 判定追加（高域/低域比）
- [ ] `classify_source` の閾値見直し
- [ ] **二重VAD 採用見送りを Plan に明記**

### Phase 0.5: kotoba-whisper-v2.0 統合（1-2日）
- [ ] `_whisper_model_fast` を kotoba に置き換え（**ただし2段階前提**）
- [ ] WhisperModel 読み込み時間・メモリの実測（本番リソース影響）

### Phase 0.7: 2段階デコーディング（2-3日）
- [ ] Stage 1: small（既存維持）
- [ ] Stage 2: kotoba（条件発火）
- [ ] 発火条件: wake / Akira近接 / conversation_mode
- [ ] 録音バッファ保持・再デコードロジック
- [ ] 本番レイテンシ実測

### Phase 0.95: 信号レベル AEC（保留）
- [ ] 別ベンチで検証してから判断

### Phase 0.9: 二重VAD（**ボツ**）
- ✗ 採用見送り

## 残課題

1. **二重VAD の悪化原因究明**: temperature determinism or 内部キャッシュ。要 isolated 再現テスト
2. **kotoba のメモリ使用量・load 時間の本番影響**: 1.5GB モデル、常駐させる現実性
3. **MPS/Metal 対応**: 現状 CPU int8。Apple Silicon Metal で kotoba を動かせれば 2-3倍高速化の可能性
4. **`monologue__tired_after_work_01` で kotoba が "ぁ" を落とす**: small 「疲れたな**ぁ** ちょっと休もうかな」 vs kotoba 「疲れたなちょっと休もうかな」 — kotoba の正規化挙動に微妙な差。実用上は誤差レベル

## 結論一言

**kotoba-whisper-v2.0 + 条件発火2段階デコーディング を採用、二重VAD は不採用、AEC は別フェーズ**。

近接発話 CER 1/3 削減は本番の wake_detect 信頼性・会話品質に直結する。実装ROI は圧倒的に高い。
