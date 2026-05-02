# kotoba-whisper 採用評価レポート

*調査日: 2026-05-02 / 対象: ember voice-chat STT 精度改善*

---

## 1. モデル一覧とサイズ

| モデル | パラメータ | 蒸留元 | 備考 |
|---|---|---|---|
| kotoba-whisper-v1.0 | 756M | large-v3 | 初版。ReazonSpeech 訓練 |
| kotoba-whisper-v2.0 | 756M | large-v3 | v1.0 の訓練データ拡充版 |
| kotoba-whisper-v2.1 | 756M | v2.0 + postproc | 句読点付与パイプライン追加 |
| kotoba-whisper-v2.2 | 756M | v2.0 + postproc | 話者分離・句読点付与 |
| kotoba-whisper-v2.0-faster | 756M (CT2) | v2.0 | CTranslate2 変換済み、faster-whisper 直接利用可 |

デコーダ層を 2 層に削減（large-v3 の 32 層から大幅削減）しつつ、エンコーダは full large-v3 を維持。

---

## 2. WER / CER / 速度ベンチマーク

### 公式ベンチ（v2.0 モデルカード）

| モデル | CER ReazonSpeech | CER CommonVoice8 | CER JSUT | 相対レイテンシ |
|---|---|---|---|---|
| kotoba-whisper-v2.0 | **11.6** | 9.2 | 8.4 | **6.3x** |
| whisper-large-v3 | 14.9 | 8.5 | 7.1 | 1.0x (基準) |

ReazonSpeech（TVテレビ音声由来）では kotoba が明確に優位。汎用ドメイン（CommonVoice / JSUT）では large-v3 が若干優位。

### 第三者ベンチ（Neosophie, 2026-02）

| モデル | WER | CER | RTF |
|---|---|---|---|
| whisper-large-v3-turbo | **0.218** | **0.184** | 0.013 |
| reazonspeech-espnet-v2 | 0.234 | - | 0.589 |
| **kotoba-whisper-v2.0** | 0.534 | 0.495 | **0.008** |
| reazonspeech-nemo-v2 | 0.348 | 0.329 | 0.020 |

注: このベンチはテストセット不明。RTF は kotoba が最速だが、WER は large-v3-turbo が大きく上回る。ReazonSpeech 訓練特化ゆえ、ドメイン外（会話音声）で精度が落ちる可能性がある。

---

## 3. Apple Silicon 動作経路

| 経路 | ライブラリ | kotoba 対応 | 現行 ember との互換 |
|---|---|---|---|
| faster-whisper (CT2) | CTranslate2 | `kotoba-tech/kotoba-whisper-v2.0-faster` 公式配布 | **完全互換**（`WhisperModel` API 同一） |
| mlx-whisper | Apple MLX | `kaiinui/kotoba-whisper-v2.0-mlx` コミュニティ変換版 | API 変更必要（`mlx_whisper.transcribe`） |
| whisper.cpp | GGML | 変換ツールなし（非公式のみ） | 非推奨 |

**推奨経路: faster-whisper (CT2)**。ember が既に `from faster_whisper import WhisperModel` を使用しており、モデル名変更のみで差し替え可能。

---

## 4. ハイブリッド運用の妥当性

現行の使い分けは合理的で、kotoba 採用後もそのまま維持できる。

| パス | 現行モデル | kotoba 採用後 | 理由 |
|---|---|---|---|
| 短発話 VAD トリガー | whisper small (CPU, int8) | **変更なし** | 速度優先。kotoba-v2.0 は small より 6x 大きく待機不可 |
| 周期チャンク（180s） | large-v3-turbo (CPU, int8_float32) | **kotoba-v2.0-faster** に変更候補 | 精度重視、ReazonSpeech 系会話に強い |

---

## 5. VOICE-COMMAND vs CONVERSATION-DICTATION

kotoba は ReazonSpeech（TV 放送）で訓練されているため、**自然発話の書き起こし（CONVERSATION-DICTATION）に強い**。短コマンド（「ねぇメイ」等の VOICE-COMMAND）ではエンコーダ処理コストが割高になる一方、精度差は小さい。固有名詞については、ReazonSpeech には IT 専門語が少ないため「スマートAIグラス」「キュウちゃんモデル」等の認識は、hotwords 注入なしでは改善しない可能性がある。

---

## 6. 代替案比較

| モデル | WER | サイズ | Apple Silicon | 特記 |
|---|---|---|---|---|
| whisper-large-v3-turbo（現行） | 0.218 | 809M | CPU int8 | 第三者ベンチで最高精度 |
| kotoba-whisper-v2.0 | 0.534* | 756M | faster-whisper OK | ReazonSpeech 特化。*テストセット依存 |
| reazonspeech-espnet-v2 | 0.234 | 不明 | 非サポート | RTF=0.589 で低速すぎ |
| reazonspeech-nemo-v2 | 0.348 | 不明 | 非サポート | NeMo 環境構築コスト大 |
| Wav2Vec2-Japanese | 0.370 | 159M | 未検証 | WER が大幅に劣後 |
| AssemblyAI Japanese | 非公開 | クラウド | N/A | オフライン不可 |

---

## 7. 移行コスト見積もり

- **コード変更**: `get_whisper()` 内のモデル名を `"large-v3-turbo"` から `"kotoba-tech/kotoba-whisper-v2.0-faster"` に変更（1 行）
- **モデルダウンロード**: 初回起動時に約 1.5GB（HuggingFace Hub 自動取得）
- **推論時間**: M2 Pro 実測で 5.6 分音声 → 73 秒（RTF ≈ 0.22）。large-v3-turbo より高速と推定
- **API 互換性**: 完全互換。`language="ja"`, `hotwords`, `vad_filter` 等の引数はそのまま使用可
- **リスク**: ドメイン外テキスト（IT 固有名詞）では精度が劣化する可能性。A/B テスト必須

---

## 採用判断

**現時点では見送りを推奨する。**

第三者ベンチ（2026-02）で whisper-large-v3-turbo（WER 0.218）が kotoba-v2.0（WER 0.534）を大幅に上回っている。ember のコメント（`# CER は 2026 ベンチで最良（0.178）`）が示す通り、既に最良モデルを運用中の可能性が高い。

固有名詞誤認識の根本原因は訓練データではなく **hotwords 不足**にある。「スマートAIグラス」「キュウちゃんモデル」を `_WHISPER_FILE_HOTWORDS` に追記する方が、モデル差し替えより即効性が高い。

**採用するとすれば、次の一歩:**

1. `_WHISPER_FILE_HOTWORDS` に対象固有名詞を追加して 1 週間実運用（コスト 0）
2. 改善が不十分な場合、`get_whisper()` のモデル名を `"kotoba-tech/kotoba-whisper-v2.0-faster"` に変更して A/B テスト
3. chunk_transcribe の CER をログで計測し、large-v3-turbo と比較して判断

---

*Sources: HuggingFace kotoba-tech model cards, Neosophie Japanese ASR Benchmark 2026, kaiinui/kotoba-whisper-v2.0-mlx*
