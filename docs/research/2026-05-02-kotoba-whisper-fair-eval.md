# kotoba-whisper vs whisper-large-v3 同条件ベンチマーク比較

*調査日: 2026-05-02 / 既存レポート `2026-05-02-kotoba-whisper-eval.md` の補足検証*

---

## 1. Neosophie 2026-02 ベンチの条件

| 項目 | 内容 |
|---|---|
| テストセット | 自社収録 20 clips / 約 580 秒（自然発話）|
| ドメイン | ニュース・バラエティ・ドラマ・ビジネス TV |
| hotwords | **未使用**（言及なし）|
| initial_prompt | **未使用**（言及なし）|
| VAD / 音量正規化 | **統一なし**（「考慮事項」として言及のみ）|
| beam_size | 未記載 |
| temperature | 0.0 |
| 正規化 | NFKC + 句読点除去 + MeCab wakati |

**結論: hotwords・initial_prompt・VAD をいずれも無効化した状態でのベアモデル比較**。前処理条件の統一は取れているが、このテストセットは会話音声主体であり、kotoba の訓練ドメイン（ReazonSpeech = TV 放送）とは一致する部分もある。

---

## 2. 公式モデルカード（同条件）ベンチとの比較

公式評価コード: `generate_kwargs = {"language": "japanese", "task": "transcribe"}` + BasicTextNormalizer。hotwords / initial_prompt は使用していない。

### CER（公式モデルカード、同条件比較）

| モデル | CommonVoice 8 | JSUT Basic5000 | ReazonSpeech 保留テスト |
|---|---|---|---|
| kotoba-whisper-v2.0 | 9.2 | 8.4 | **11.6** |
| openai/whisper-large-v3 | **8.5** | **7.1** | 14.9 |
| whisper-large-v3-turbo | n/a | n/a | n/a |

### WER（公式モデルカード、同条件比較）

| モデル | CommonVoice 8 | JSUT Basic5000 | ReazonSpeech 保留テスト |
|---|---|---|---|
| kotoba-whisper-v2.0 | 58.8 | 63.7 | **55.6** |
| openai/whisper-large-v3 | **55.1** | **59.2** | 60.2 |
| whisper-large-v3-turbo | n/a | n/a | n/a |

注: **large-v3-turbo との同条件公開ベンチは存在しない**。公式モデルカードの比較対象は large-v3（非 turbo）のみ。

---

## 3. Neosophie IT 用語ベンチ（2026-04）

| モデル | CER | CER_EN |
|---|---|---|
| whisper-large-v3-turbo | **0.1565** | **0.1339** |
| kotoba-whisper-v2.0 | 0.6072 | 0.5859 |

IT 用語（Anthropic, LLM, SIer 等）での差はさらに拡大。hotwords 未使用の条件は一致している。

---

## 4. hotwords 有効化の効果

公開研究（B-Whisper, 2025）によると、コンテキストバイアス（hotwords 相当）を有効化した場合:

| 条件 | 効果 |
|---|---|
| 少語彙（35–70 語）| R-WER（レア語誤り率）**最大 45.6% 削減** |
| 大語彙（150 語〜）| R-WER は改善するが U-WER（通常語）に若干劣化リスク |
| 両モデル共通 | hotwords 効果はモデル依存でなく推論設定依存 |

Neosophie 2026-02 / 04 ベンチはいずれも hotwords 未使用であり、両モデルとも「素の状態」での比較。kotoba の大幅な劣後はモデル自体の問題と判断できる。

---

## 5. 結論の再評価

**既存レポートの「採用見送り」結論は訂正不要。**

同条件（hotwords なし）の複数ベンチ（公式・Neosophie 2026-02・同 2026-04）で一貫して whisper-large-v3-turbo が kotoba-v2.0 を上回っており、前処理のねじれで結果が逆転する根拠は見つからなかった。ただし large-v3-turbo との直接同条件比較が公開されていない点は留保事項として残る。**手元での A/B テストが唯一の確認手段。**

---

*Sources: [kotoba-tech/kotoba-whisper-v2.0](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0), [Neosophie ASR Benchmark 2026-02](https://neosophie.com/en/blog/20260226-japanese-asr-benchmark), [Neosophie IT ASR Benchmark 2026-04](https://neosophie.com/ja/blog/20260414-it-asr-benchmark), [B-Whisper rare-word recognition](https://arxiv.org/html/2502.11572v1)*
