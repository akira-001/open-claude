# 人間の会話ロジック再現 — Proactive Agent v3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** proactive agent の話題選択を、人間が「気になる人に配慮しながら話しかける時」の思考プロセスに忠実に再現する

**Architecture:** 6つのスコア軸（タイムリーさ、新鮮さ、会話の流れ、感情フィット、ユーザー親和性、意外性）で候補をスコアリングし、Claude には最終判断のみを委ねる。スコアリングはコード側で決定論的に行い、ダッシュボードで全候補の内訳が可視化される。

**Tech Stack:** TypeScript (proactive agent), Python (interest scanner), React (dashboard)

**Eng Review Decisions (2026-03-27):**
1. **categoryWeights → 読み取り専用**: TS priors に重み学習を一本化。categoryWeights は affinity の入力としてのみ使用（更新停止）
2. **反応検知 → イベント駆動**: pendingReward ポーリングを廃止。既存 handleReaction() に TS 更新をフックイン。neutral は次回 run() で2h+無反応を検知
3. **RawCandidate → 共通フィールド + metadata bag**: source discriminant + Record<string, unknown>
4. **ファイル分離**: thompson-sampling.ts（数学ユーティリティ）+ conversation-scorer.ts（スコアリング）
5. **ループ安全弁**: gammaSample() に 1000回上限 + 期待値フォールバック
6. **Credit assignment**: 粗い更新を許容（データ量が少なく rescale で古い誤りが薄まる）

---

## 人間の会話ロジックとは何か

人間が気になる人に話しかける時、無意識にやっていること:

1. **「今何してるかな？」** — 相手の状態を推し量る
2. **「これ、あの人喜ぶかな？」** — 相手のフィルターを通す
3. **「最近この話したっけ？」** — 同じ話をしないか確認
4. **「昨日のあの件、どうなったかな？」** — 会話の続きを考える
5. **「今これ言って大丈夫？」** — タイミングを判断
6. **「これ意外と面白いかも」** — サプライズ要素

静的な「優先度リスト」では再現できない。**同じ情報でも、文脈によってスコアが変わる**のが人間の会話。

---

## スコアリングモデル: 6軸

各候補に対して0.0〜1.0のスコアを6軸で算出:

| 軸 | 何を測るか | 高い例 | 低い例 |
|----|-----------|--------|--------|
| **timeliness** | 時間的な旬 | 今日の試合結果、さっき出た記事 | 1週間前のニュース |
| **novelty** | 会話での新鮮さ | 今日まだ触れてない話題 | 今日3回目のドジャースの話 |
| **continuity** | 会話の流れ | 昨日のゴルフレッスンの感想聞く | 脈絡なく温泉の話 |
| **emotional_fit** | 今の状態への適合 | 休日にリラックスした話題 | 忙しい日に重い経営の話 |
| **affinity** | ユーザーの好み | 反応が良かったカテゴリ | 無視されがちなカテゴリ |
| **surprise** | 意外な面白さ | AIとゴルフの交差点記事 | いつものドジャーススコア |

### 重み（Thompson Sampling で学習 + 文脈で動的調整）

重みは固定値ではなく、**Beta分布からサンプリング**して毎回決定する。
ユーザーの反応を報酬信号として分布を更新し、どの軸が「良い話題選び」に効くかを学習する。

```
初期 priors（Beta分布の α, β）:
  timeliness:    α=5, β=5   → 期待値 0.50（事前知識: 旬は重要）
  novelty:       α=4, β=6   → 期待値 0.40
  continuity:    α=4, β=6   → 期待値 0.40
  emotional_fit: α=3, β=7   → 期待値 0.30
  affinity:      α=2, β=8   → 期待値 0.20
  surprise:      α=2, β=8   → 期待値 0.20
```

**学習ループ:**
```
1. Beta(α, β) から各軸の重みをサンプリング → 正規化
2. 文脈ボーナスを加算（朝→timeliness、週末→emotional_fit 等）
3. 再正規化してスコアリングに使用
4. ユーザー反応を観測
5. 選んだ候補のスコアが高かった軸の α or β を更新
```

**候補選択の探索（B: バンディット）:**
```
スコア1位を常に選ぶと exploitation に偏る。
Thompson Sampling の重みサンプリング自体が探索を内包するが、
候補選択にも UCB ボーナスを加える:

exploration_bonus = √(2 × ln(total_selections) / axis_selections)
adjusted_score = final_score + exploration_coeff × exploration_bonus
```

**文脈ボーナス（ルールベース）:**
- 朝一番 → timeliness +0.10（今日の情報を優先）
- 前回の話題から2時間以内 → continuity +0.10（フォローアップの機会）
- 直近3回無反応 → surprise +0.15（マンネリ打破）
- 週末 → emotional_fit +0.10（リラックスした話題を重視）

### 最終スコア
```
sampled_weights = normalize(sample(Beta(α_i, β_i)) + context_bonus_i)
final_score = Σ (axis_score × sampled_weight) for each axis
selection_score = final_score + exploration_bonus  # 候補選択時のみ
```

---

## ファイル構成

| ファイル | 役割 | 変更 |
|---------|------|------|
| `src/thompson-sampling.ts` | **NEW** — Beta分布サンプリング、priors 更新、rescale | 作成 |
| `src/conversation-scorer.ts` | **NEW** — 6軸スコアリング、文脈ボーナス、探索ボーナス | 作成 |
| `src/skill-enhanced-proactive-agent.ts` | run() でスコアラーを呼び出し、handleReaction() で TS 更新 | 修正 |
| `src/proactive-state.ts` | LearningState 追加、categoryWeights 更新停止、buildCronPrompt 修正 | 修正 |
| `interest_scanner.py` | timeliness, emotion_type, ワイルドカード枠, カテゴリ交差スキャン | 修正 |
| `dashboard/src/pages/ProactiveConfig.tsx` | スコア内訳 + 学習状態 + 探索ボーナス表示 | 修正 |
| `dashboard/server/api.ts` | stats API にスコア + 学習情報を含める | 修正 |
| `src/__tests__/thompson-sampling.test.ts` | **NEW** — TS 数学関数の単体テスト (~15件) | 作成 |
| `src/__tests__/conversation-scorer.test.ts` | **NEW** — 6軸スコアリングの単体テスト (~35件) | 作成 |
| `src/__tests__/proactive-agent.test.ts` | handleReaction → TS 統合テスト追加 (~5件) | 修正 |

---

## Task 1: thompson-sampling.ts + conversation-scorer.ts — スコアリングエンジン

**Files:**
- Create: `src/thompson-sampling.ts`
- Create: `src/conversation-scorer.ts`
- Create: `src/__tests__/thompson-sampling.test.ts`
- Create: `src/__tests__/conversation-scorer.test.ts`

### スコアリング関数の設計

```typescript
interface ScoredCandidate {
  topic: string;
  source: string;          // 'interest-cache' | 'calendar' | 'cogmem' | 'email' | 'follow-up'
  category: string;        // interest category ID
  scores: {
    timeliness: number;    // 0-1
    novelty: number;       // 0-1
    continuity: number;    // 0-1
    emotional_fit: number; // 0-1
    affinity: number;      // 0-1
    surprise: number;      // 0-1
  };
  finalScore: number;
  reasoning: string;       // なぜこのスコアか（1行）
}

interface ConversationContext {
  currentHour: number;
  dayOfWeek: number;       // 0=日, 6=土
  todayMessages: Array<{ time: string; summary: string; source: string }>;
  recentHistory: Array<{ category: string; interestCategory?: string; sentAt: string; reaction: string | null; reactionDelta: number }>;
  calendarDensity: number; // 0=空, 1=普通, 2=忙しい
  lastSentMinutesAgo: number;
  consecutiveNoReaction: number; // 直近で連続して無反応の数
}

// --- Thompson Sampling 関連 ---

interface WeightPrior {
  alpha: number;           // positive signal の累積
  beta: number;            // negative signal の累積
}

interface LearningState {
  priors: Record<string, WeightPrior>;   // 各軸の Beta 分布パラメータ
  totalSelections: number;               // 候補選択の総数
  categorySelections: Record<string, number>;  // カテゴリ別選択回数（探索ボーナス用）
  lastUpdated: string;                   // ISO8601
  version: number;                       // 学習状態のバージョン（リセット時にインクリメント）
}

type Reaction = 'positive' | 'neutral' | 'negative';
```

- [ ] **Step 1: ファイル作成 — 型定義とスケルトン**

`src/conversation-scorer.ts` を作成。
ScoredCandidate, ConversationContext, WeightPrior, LearningState インターフェースを定義。
`scoreCandidate()`, `scoreCandidates()`, `createInitialLearningState()` のスケルトンを作成。

```typescript
const DEFAULT_PRIORS: Record<string, WeightPrior> = {
  timeliness:    { alpha: 5, beta: 5 },
  novelty:       { alpha: 4, beta: 6 },
  continuity:    { alpha: 4, beta: 6 },
  emotional_fit: { alpha: 3, beta: 7 },
  affinity:      { alpha: 2, beta: 8 },
  surprise:      { alpha: 2, beta: 8 },
};

function createInitialLearningState(): LearningState {
  return {
    priors: structuredClone(DEFAULT_PRIORS),
    totalSelections: 0,
    categorySelections: {},
    lastUpdated: new Date().toISOString(),
    version: 1,
  };
}
```

- [ ] **Step 2: timeliness スコア実装**

```typescript
function scoreTimeliness(candidate: RawCandidate): number {
  // pub_date があれば: 0時間=1.0, 6時間=0.75, 24時間=0.5, 48時間=0.0
  // カレンダーイベント: 今日=0.9, 明日=0.6, 来週=0.3
  // cogmem: 今日のエントリ=0.8, 今週=0.5
  // follow-up: 昨日の話題=0.9（フォローアップは旬が短い）
}
```

- [ ] **Step 3: novelty スコア実装**

```typescript
function scoreNovelty(candidate: RawCandidate, ctx: ConversationContext): number {
  // 今日同じカテゴリで送信済み → 0.0（絶対ブロック）
  // 今日同じソースで送信済み → 0.1
  // 昨日同じカテゴリ → 0.3
  // 3日以上前 → 0.7
  // 7日以上前 → 0.9
  // 一度も触れてない → 0.8

  // 注意: 「長く触れてない」と「一度も触れてない」は違う
  // 長く触れてない → 復活の新鮮さ = 0.9
  // 一度も触れてない → 未知のリスク = 0.8（少し下げる）
}
```

- [ ] **Step 4: continuity スコア実装**

```typescript
function scoreContinuity(candidate: RawCandidate, ctx: ConversationContext): number {
  // 直近の送信メッセージの interestCategory と一致
  //   → 昨日の同カテゴリ + 自然なフォローアップ質問 = 0.9
  //   → 「ゴルフレッスンどうだった？」「ドジャース勝ったね」
  // 直近の MILESTONE に関連 = 0.7
  // 2つの興味の交差点 = 0.6（AI × ゴルフ記事）
  // 脈絡なし = 0.0

  // 特殊: フォローアップ候補を自動生成
  // 昨日 hobby-trigger で送った → 今日は結果/感想を聞く候補を追加
}
```

- [ ] **Step 5: emotional_fit スコア実装**

```typescript
function scoreEmotionalFit(candidate: RawCandidate, ctx: ConversationContext): number {
  // 週末 + 趣味/レジャー → 0.9
  // 週末 + 仕事 → 0.2
  // 忙しい日（calendarDensity=2） + 軽い話題 → 0.7
  // 忙しい日 + 重い話題 → 0.3
  // 夜（20時） + リラックス系 → 0.9
  // 朝（9時） + ビジネス系 → 0.8

  // カテゴリ → 感情タイプ のマッピング
  // light: dodgers, golf, onsen, food, local, weather
  // medium: campingcar, cat_health, llm_local, dev_tools
  // heavy: ai_agent, business_strategy, ma_startup
}
```

- [ ] **Step 6: affinity スコア実装**

```typescript
function scoreAffinity(candidate: RawCandidate, ctx: ConversationContext): number {
  // proactive-state の reaction history から算出
  // カテゴリ別の反応率（positive / total）
  // 反応率 80%+ → 0.9
  // 反応率 50-80% → 0.7
  // 反応率 < 50% → 0.4
  // データなし → 0.5（中立）

  // user-insights の arousal も加味
  // arousal >= 0.8 のインサイトに関連 → +0.1
}
```

- [ ] **Step 7: surprise スコア実装**

```typescript
function scoreSurprise(candidate: RawCandidate, ctx: ConversationContext): number {
  // === 探索候補は自動的に高スコア ===

  // カテゴリ交差（探索D）: interest_scanner が見つけた2カテゴリ交差記事
  if (candidate.category === '_cross') {
    return 0.9;
  }

  // ワイルドカード（探索C）: 既存カテゴリ外の話題
  if (candidate.category === '_wildcard') {
    return 0.8;
  }

  // cogmem 未カテゴリ化（探索B）: 最近よく出るが分類されていないトピック
  if (candidate.category === '_discovery') {
    const occurrences = (candidate.metadata.occurrences as number) || 0;
    return Math.min(0.5 + occurrences * 0.1, 0.85);  // 出現回数に応じて 0.5-0.85
  }

  // === 通常カテゴリの surprise ===

  // 2つの興味カテゴリの交差点（タイトルから検出）
  //   例: "AIを使ったゴルフスイング分析" = ai_agent × golf
  const crossMatch = detectCrossCategoryInTitle(candidate.topic);
  if (crossMatch) return 0.85;

  // 普段触れないカテゴリからの高品質記事
  const categoryN = ctx.recentHistory.filter(h => h.category === candidate.category).length;
  if (categoryN === 0) return 0.7;  // 直近で全く触れていない

  // 「去年の今頃」型の記憶
  if (candidate.source === 'cogmem' && candidate.metadata.isOneYearAgo) return 0.8;

  // 定番カテゴリの定番情報
  return 0.1;
}

// タイトルから複数カテゴリに該当するか検出
function detectCrossCategoryInTitle(title: string): string[] | null {
  const CATEGORY_KEYWORDS: Record<string, string[]> = {
    ai_agent: ['AI', '人工知能', 'エージェント', 'Claude', 'ChatGPT'],
    golf: ['ゴルフ', 'スイング', 'パター'],
    dodgers: ['ドジャース', '大谷', 'MLB'],
    campingcar: ['キャンピングカー', '車中泊'],
    onsen: ['温泉', '露天風呂'],
    cat_health: ['猫', 'ネコ', 'キャット'],
    business_strategy: ['経営', 'DX', 'コンサル'],
    // ...
  };

  const matched: string[] = [];
  for (const [cat, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    if (keywords.some(kw => title.includes(kw))) {
      matched.push(cat);
    }
  }
  return matched.length >= 2 ? matched : null;
}
```

- [ ] **Step 8: Thompson Sampling — Beta分布サンプリングと重み生成**

```typescript
// Beta分布からのサンプリング（Jöhnk's algorithm — 外部ライブラリ不要）
function betaSample(alpha: number, beta: number): number {
  // alpha, beta が共に1以上の場合は Gamma 経由が安定
  const gammaA = gammaSample(alpha);
  const gammaB = gammaSample(beta);
  return gammaA / (gammaA + gammaB);
}

function gammaSample(shape: number): number {
  // Marsaglia and Tsang's method
  if (shape < 1) {
    return gammaSample(shape + 1) * Math.pow(Math.random(), 1 / shape);
  }
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  while (true) {
    let x: number, v: number;
    do {
      x = randn();
      v = 1 + c * x;
    } while (v <= 0);
    v = v * v * v;
    const u = Math.random();
    if (u < 1 - 0.0331 * (x * x) * (x * x)) return d * v;
    if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}

function randn(): number {
  // Box-Muller transform
  const u1 = Math.random();
  const u2 = Math.random();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

// 学習済み priors から重みをサンプリング
function sampleWeights(priors: Record<string, WeightPrior>): Record<string, number> {
  const sampled: Record<string, number> = {};
  for (const [axis, prior] of Object.entries(priors)) {
    sampled[axis] = betaSample(prior.alpha, prior.beta);
  }
  // 正規化して合計 1.0 に
  const sum = Object.values(sampled).reduce((a, b) => a + b, 0);
  for (const k of Object.keys(sampled)) sampled[k] /= sum;
  return sampled;
}
```

- [ ] **Step 9: 文脈ボーナス + 最終スコア算出**

```typescript
function getContextBonus(ctx: ConversationContext): Record<string, number> {
  const bonus: Record<string, number> = {
    timeliness: 0, novelty: 0, continuity: 0,
    emotional_fit: 0, affinity: 0, surprise: 0,
  };

  // 朝一番: タイムリーさ重視
  if (ctx.currentHour >= 8 && ctx.currentHour <= 10) bonus.timeliness += 0.10;

  // フォローアップ機会: 前回から2時間以内
  if (ctx.lastSentMinutesAgo < 120) bonus.continuity += 0.10;

  // マンネリ打破: 3回連続無反応
  if (ctx.consecutiveNoReaction >= 3) bonus.surprise += 0.15;

  // 週末: 感情フィット重視
  if (ctx.dayOfWeek === 0 || ctx.dayOfWeek === 6) bonus.emotional_fit += 0.10;

  return bonus;
}

function getDynamicWeights(
  learningState: LearningState,
  ctx: ConversationContext
): { weights: Record<string, number>; sampledRaw: Record<string, number>; bonus: Record<string, number> } {
  // Step 1: Beta分布からサンプリング
  const sampledRaw = sampleWeights(learningState.priors);

  // Step 2: 文脈ボーナスを加算
  const bonus = getContextBonus(ctx);
  const combined: Record<string, number> = {};
  for (const axis of Object.keys(sampledRaw)) {
    combined[axis] = sampledRaw[axis] + (bonus[axis] || 0);
  }

  // Step 3: 再正規化
  const sum = Object.values(combined).reduce((a, b) => a + b, 0);
  const weights: Record<string, number> = {};
  for (const k of Object.keys(combined)) weights[k] = combined[k] / sum;

  return { weights, sampledRaw, bonus };
}

function scoreCandidates(
  rawCandidates: RawCandidate[],
  ctx: ConversationContext,
  learningState: LearningState
): { candidates: ScoredCandidate[]; weightsUsed: Record<string, number>; sampledRaw: Record<string, number>; bonus: Record<string, number> } {
  const { weights, sampledRaw, bonus } = getDynamicWeights(learningState, ctx);

  const candidates = rawCandidates.map(c => {
    const scores = {
      timeliness: scoreTimeliness(c),
      novelty: scoreNovelty(c, ctx),
      continuity: scoreContinuity(c, ctx),
      emotional_fit: scoreEmotionalFit(c, ctx),
      affinity: scoreAffinity(c, ctx),
      surprise: scoreSurprise(c, ctx),
    };

    const finalScore = Object.entries(scores).reduce(
      (sum, [axis, score]) => sum + score * weights[axis], 0
    );

    return { ...c, scores, finalScore, reasoning: buildReasoning(c, scores) };
  }).sort((a, b) => b.finalScore - a.finalScore);

  return { candidates, weightsUsed: weights, sampledRaw, bonus };
}
```

- [ ] **Step 10: 探索ボーナス — UCB で候補選択に多様性を注入**

```typescript
const EXPLORATION_COEFF = 0.1;  // 探索の強さ（0=exploitation only, 高い=探索強め）

// 探索候補カテゴリには追加の固定ボーナス
const DISCOVERY_BONUS: Record<string, number> = {
  '_wildcard':  0.15,  // ワイルドカード: 強めの探索ボーナス
  '_cross':     0.10,  // カテゴリ交差: surprise スコアが既に高いので控えめ
  '_discovery': 0.12,  // cogmem 未カテゴリ化: 中程度
};

function addExplorationBonus(
  candidates: ScoredCandidate[],
  learningState: LearningState
): ScoredCandidate[] {
  const totalN = Math.max(learningState.totalSelections, 1);

  return candidates.map(c => {
    const categoryN = learningState.categorySelections[c.category] || 0;

    // UCB1 探索項: あまり選ばれてないカテゴリにボーナス
    let explorationBonus = categoryN === 0
      ? EXPLORATION_COEFF * 2  // 未知のカテゴリには大きめのボーナス
      : EXPLORATION_COEFF * Math.sqrt(2 * Math.log(totalN) / categoryN);

    // 探索候補カテゴリには追加の固定ボーナス
    explorationBonus += DISCOVERY_BONUS[c.category] || 0;

    return {
      ...c,
      explorationBonus,
      selectionScore: c.finalScore + explorationBonus,
    };
  }).sort((a, b) => b.selectionScore - a.selectionScore);
}
```

- [ ] **Step 11: 報酬更新 — ユーザー反応で Beta 分布を更新**

```typescript
function updatePriors(
  learningState: LearningState,
  chosen: ScoredCandidate,
  reaction: Reaction
): LearningState {
  const updated = structuredClone(learningState);

  // Credit assignment: スコアが高い軸ほど強く更新
  for (const [axis, score] of Object.entries(chosen.scores)) {
    if (score < 0.3) continue;  // 寄与が小さい軸はスキップ

    if (reaction === 'positive') {
      updated.priors[axis].alpha += score;      // 成功軸を強化
    } else if (reaction === 'negative') {
      updated.priors[axis].beta += score * 0.7; // ペナルティは控えめ
    } else {
      // neutral: ごく弱いペナルティ（無反応は「悪い」ではなく「わからない」）
      updated.priors[axis].beta += score * 0.2;
    }
  }

  // 選択カウント更新
  updated.totalSelections += 1;
  updated.categorySelections[chosen.category] =
    (updated.categorySelections[chosen.category] || 0) + 1;
  updated.lastUpdated = new Date().toISOString();

  return updated;
}

// 安全弁: α+β が大きくなりすぎると新しい反応の影響が薄まる
// 定期的に rescale して「最近の反応」を重視する
function rescalePriors(
  learningState: LearningState,
  maxSum: number = 50  // α+β の上限
): LearningState {
  const updated = structuredClone(learningState);
  for (const [axis, prior] of Object.entries(updated.priors)) {
    const sum = prior.alpha + prior.beta;
    if (sum > maxSum) {
      const scale = maxSum / sum;
      updated.priors[axis].alpha *= scale;
      updated.priors[axis].beta *= scale;
    }
  }
  return updated;
}
```

- [ ] **Step 12: フォローアップ候補の自動生成**

```typescript
function generateFollowUpCandidates(ctx: ConversationContext): RawCandidate[] {
  // 昨日のメッセージから自然なフォローアップを生成
  // 例: 昨日「ゴルフレッスン楽しんで」→ 今日「レッスンどうだった？」
  // 例: 昨日「ドジャース開幕戦」→ 今日「試合楽しめた？」

  const followUps: RawCandidate[] = [];
  const yesterday = // 昨日の todayMessages を取得

  for (const msg of yesterday) {
    followUps.push({
      topic: `${msg.summary} のフォローアップ`,
      source: 'follow-up',
      category: msg.source,
      pub_date: null,
      metadata: { originalMessage: msg.summary },
    });
  }

  return followUps;
}
```

- [ ] **Step 13: コミット**

```bash
git add src/conversation-scorer.ts
git commit -m "feat: add 6-axis conversation scoring engine with Thompson Sampling"
```

---

## Task 2: interest_scanner.py — メタデータ強化 + 探索機能

**Files:**
- Modify: `/Users/akira/workspace/ai-dev/web-search/interest_scanner.py`

### 2A: 基本メタデータ追加

- [ ] **Step 1: 各アイテムに timeliness_score を追加**

score_item() の結果に timeliness を分離して保存:

```python
def score_item(item: dict, priority: float) -> float:
    # ... 既存ロジック
    freshness = max(0, 1.0 - (hours_old / 48))
    item["timeliness"] = round(freshness, 3)  # NEW: 分離して保存
    score += freshness * 0.4
    # ...
```

- [ ] **Step 2: カテゴリに感情タイプを追加**

```python
INTEREST_CATEGORIES = {
    # light: 趣味・リラックス系
    "dodgers":           { ..., "emotion_type": "light" },
    "golf":              { ..., "emotion_type": "light" },
    "onsen":             { ..., "emotion_type": "light" },
    "food_dining":       { ..., "emotion_type": "light" },
    "local_tokorozawa":  { ..., "emotion_type": "light" },
    "weather_seasonal":  { ..., "emotion_type": "light" },
    # medium: 関心度が高いが重くない
    "campingcar":        { ..., "emotion_type": "medium" },
    "cat_health":        { ..., "emotion_type": "medium" },
    "llm_local":         { ..., "emotion_type": "medium" },
    "dev_tools":         { ..., "emotion_type": "medium" },
    # heavy: ビジネス・専門
    "ai_agent":          { ..., "emotion_type": "heavy" },
    "business_strategy": { ..., "emotion_type": "heavy" },
    "ma_startup":        { ..., "emotion_type": "heavy" },
}
```

キャッシュに emotion_type を含めて保存。

### 2B: ワイルドカード枠（C）

毎回1枠、既存カテゴリに属さない「意外な話題」を取得する。

- [ ] **Step 3: ワイルドカード検索の実装**

```python
# 既存カテゴリのキーワードを全て収集（除外フィルタ用）
CATEGORY_KEYWORDS = set()
for cat in INTEREST_CATEGORIES.values():
    for q in cat["queries_ja"] + cat.get("queries_en", []):
        for word in q.split():
            if len(word) >= 2:
                CATEGORY_KEYWORDS.add(word.lower())

def scan_wildcard() -> list[dict]:
    """既存カテゴリに該当しないトップニュースを取得"""
    # Google News トップ（日本語）
    items = fetch_google_news("注目 テクノロジー OR サイエンス OR 話題", "ja", 10)

    # 既存カテゴリのキーワードを含むものを除外
    wildcards = []
    for item in items:
        title_lower = item["title"].lower()
        if not any(kw in title_lower for kw in CATEGORY_KEYWORDS):
            item["score"] = score_item(item, 0.3)  # 低めの priority
            item["timeliness"] = ...  # score_item で設定済み
            wildcards.append(item)

    return wildcards[:2]  # 最大2件
```

- [ ] **Step 4: キャッシュに wildcard カテゴリを保存**

```python
# main() 内、通常スキャン後に追加
wildcard_items = scan_wildcard()
if wildcard_items:
    results["_wildcard"] = {
        "label": "ワイルドカード",
        "items": wildcard_items,
        "count": len(wildcard_items),
        "priority": 0.3,
        "tier": "C",
        "emotion_type": "light",
        "lastChecked": datetime.now(timezone.utc).isoformat(),
    }
```

### 2C: 隣接カテゴリ交差（D）

2つの興味カテゴリの交差点にある記事を発見する。

- [ ] **Step 5: カテゴリ交差ペアの定義**

```python
# 意外性の高い組み合わせを定義
CROSS_CATEGORY_PAIRS = [
    # (cat1, cat2, 検索クエリ)
    ("golf", "ai_agent",          ["AI ゴルフ スイング分析", "golf AI coaching"]),
    ("golf", "cat_health",        ["ペット ゴルフ場", "cat cafe golf"]),
    ("dodgers", "local_tokorozawa", ["ドジャース パブリックビューイング 埼玉"]),
    ("ai_agent", "business_strategy", ["AI 経営コンサル 自動化", "AI CEO advisory"]),
    ("campingcar", "onsen",       ["キャンピングカー 温泉 旅行", "車中泊 温泉巡り"]),
    ("campingcar", "cat_health",  ["猫 キャンピングカー 旅行", "cat camping travel"]),
    ("llm_local", "golf",         ["ローカルAI スポーツ分析"]),
    ("onsen", "local_tokorozawa", ["所沢 近場 日帰り温泉 新規オープン"]),
    ("dev_tools", "business_strategy", ["ノーコード DX 中小企業"]),
]
```

- [ ] **Step 6: 交差スキャンの実装**

```python
def scan_cross_categories(priorities: dict, cache: dict) -> list[dict]:
    """カテゴリ交差点の記事を検索"""
    # 12時間おき（Tier C と同じ頻度）
    cross_cache = cache.get("categories", {}).get("_cross", {})
    last_checked = cross_cache.get("lastChecked")
    if last_checked:
        try:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last_checked)).total_seconds() / 3600
            if elapsed < 12:
                return cross_cache.get("items", [])
        except (ValueError, TypeError):
            pass

    items = []
    seen_titles = set()

    for cat1, cat2, queries in CROSS_CATEGORY_PAIRS:
        # 両カテゴリの優先度の平均が一定以上の場合のみスキャン
        avg_priority = (priorities.get(cat1, 0) + priorities.get(cat2, 0)) / 2
        if avg_priority < 0.3:
            continue

        for query in queries:
            lang = "en" if any(c.isascii() and c.isalpha() for c in query) else "ja"
            for item in fetch_google_news(query, lang, 2):
                if item["title"] not in seen_titles:
                    seen_titles.add(item["title"])
                    item["score"] = score_item(item, avg_priority)
                    item["cross_categories"] = [cat1, cat2]
                    items.append(item)

    items.sort(key=lambda x: x["score"], reverse=True)
    return items[:5]
```

- [ ] **Step 7: キャッシュに _cross カテゴリを保存**

```python
cross_items = scan_cross_categories(priorities, cache)
if cross_items:
    results["_cross"] = {
        "label": "カテゴリ交差",
        "items": cross_items,
        "count": len(cross_items),
        "priority": 0.5,
        "tier": "B",
        "emotion_type": "light",
        "lastChecked": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 8: コミット**

```bash
cd /Users/akira/workspace/ai-dev/web-search
git add interest_scanner.py
git commit -m "feat: add timeliness, emotion_type, wildcard, and cross-category scanning"
```

---

## Task 3: proactive agent — スコアラー統合

**Files:**
- Modify: `src/skill-enhanced-proactive-agent.ts`
- Modify: `src/proactive-state.ts`

- [ ] **Step 1: run() にスコアリングパイプラインを追加**

gatherMemoryContext() の後、buildSkillEnhancedPrompt() の前に:

```typescript
// Build conversation context
const conversationCtx = this.buildConversationContext(state);

// Gather raw candidates from all sources
const rawCandidates = this.buildRawCandidates(collectedData, memoryContext);

// Score candidates with 6-axis model
const scoredCandidates = scoreCandidates(rawCandidates, conversationCtx);

// Store scored candidates in state for dashboard
state.lastScoredCandidates = scoredCandidates.slice(0, 10);
```

- [ ] **Step 2: buildRawCandidates() 実装**

6つのソースから RawCandidate[] を構築:

```typescript
function buildRawCandidates(
  collectedData: CollectedData,
  memoryContext: MemoryContext,
  interestCache: InterestCache,
  ctx: ConversationContext
): RawCandidate[] {
  const candidates: RawCandidate[] = [];

  // 1. interest-cache: 通常カテゴリ
  for (const [catId, catData] of Object.entries(interestCache.categories)) {
    if (catId.startsWith('_')) continue;  // _wildcard, _cross は別処理
    for (const item of catData.items) {
      candidates.push({
        topic: item.title,
        source: 'interest-cache',
        category: catId,
        pub_date: item.pub_date,
        metadata: { url: item.url, mediaSource: item.source, emotion_type: catData.emotion_type },
      });
    }
  }

  // 2. interest-cache: ワイルドカード枠（探索C）
  const wildcardItems = interestCache.categories['_wildcard']?.items || [];
  for (const item of wildcardItems) {
    candidates.push({
      topic: item.title,
      source: 'interest-cache',
      category: '_wildcard',
      pub_date: item.pub_date,
      metadata: { url: item.url, isWildcard: true },
    });
  }

  // 3. interest-cache: カテゴリ交差（探索D）
  const crossItems = interestCache.categories['_cross']?.items || [];
  for (const item of crossItems) {
    candidates.push({
      topic: item.title,
      source: 'interest-cache',
      category: '_cross',
      pub_date: item.pub_date,
      metadata: { url: item.url, crossCategories: item.cross_categories },
    });
  }

  // 4. カレンダー
  for (const event of collectedData.calendar || []) {
    candidates.push({
      topic: event.summary,
      source: 'calendar',
      category: guessCalendarCategory(event),
      pub_date: event.start,
      metadata: { location: event.location },
    });
  }

  // 5. cogmem 未カテゴリ化トピック（探索B）
  //    gatherMemoryContext() で抽出した「最近よく出るがカテゴリ化されていないキーワード」
  for (const topic of memoryContext.uncategorizedTopics || []) {
    candidates.push({
      topic: topic.keyword,
      source: 'cogmem',
      category: '_discovery',
      pub_date: null,
      metadata: { occurrences: topic.count, lastSeen: topic.lastDate, arousal: topic.avgArousal },
    });
  }

  // 6. フォローアップ候補
  const followUps = generateFollowUpCandidates(ctx);
  candidates.push(...followUps);

  return candidates;
}
```

- [ ] **Step 3: buildConversationContext() 実装**

proactive-state から ConversationContext を構築。calendarDensity はカレンダーデータから算出。

- [ ] **Step 3.5: gatherMemoryContext() に未カテゴリ化トピック抽出を追加（探索B）**

```typescript
// gatherMemoryContext() 内に追加
async function extractUncategorizedTopics(): Promise<Array<{keyword: string; count: number; lastDate: string; avgArousal: number}>> {
  // cogmem search で直近7日のログからキーワードを抽出
  // 既存の INTEREST_CATEGORIES のキーワードに該当しないものをフィルタ

  const KNOWN_KEYWORDS = new Set([
    'ドジャース', '大谷', 'ゴルフ', '温泉', 'キャンピングカー', '猫',
    'AI', 'エージェント', 'Claude', 'LLM', 'Ollama', '経営', 'コンサル',
    '所沢', 'Slack', 'M&A', 'スタートアップ', // ... 全カテゴリのキーワード
  ]);

  // cogmem watch --since "7 days ago" --json から workflow_patterns を取得
  // または cogmem search で高頻度キーワードを抽出
  const result = execSync(
    'cd /Users/akira/workspace/open-claude && cogmem search "最近の話題 トレンド 気になる" --json --limit 20',
    { encoding: 'utf-8', timeout: 10000 }
  );

  const entries = JSON.parse(result);

  // エントリからキーワードを抽出し、既知カテゴリに属さないものをフィルタ
  const keywordCounts: Record<string, {count: number; lastDate: string; totalArousal: number}> = {};

  for (const entry of entries) {
    const words = extractKeywords(entry.content);  // 名詞抽出（簡易: 2文字以上のカタカナ/漢字列）
    for (const word of words) {
      if (KNOWN_KEYWORDS.has(word)) continue;
      if (!keywordCounts[word]) {
        keywordCounts[word] = { count: 0, lastDate: entry.date, totalArousal: 0 };
      }
      keywordCounts[word].count++;
      keywordCounts[word].totalArousal += entry.arousal || 0.5;
      if (entry.date > keywordCounts[word].lastDate) {
        keywordCounts[word].lastDate = entry.date;
      }
    }
  }

  // 2回以上出現したものだけ返す
  return Object.entries(keywordCounts)
    .filter(([_, v]) => v.count >= 2)
    .map(([keyword, v]) => ({
      keyword,
      count: v.count,
      lastDate: v.lastDate,
      avgArousal: v.totalArousal / v.count,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 3);  // 最大3件
}
```

- [ ] **Step 4: buildCronPrompt() を修正 — スコア付き候補を含める**

```
## 話題候補（スコア順）
| # | 話題 | ソース | 総合 | 旬 | 新鮮 | 流れ | 状態 | 好み | 意外 |
|---|------|--------|------|----|----|------|------|------|------|
| 1 | ドジャース開幕戦結果 | interest-cache | 0.82 | 0.9 | 0.8 | 0.9 | 0.8 | 0.7 | 0.3 |
| 2 | Claude Code検証記事 | interest-cache | 0.71 | 0.8 | 0.7 | 0.3 | 0.5 | 0.9 | 0.6 |
| 3 | ゴルフレッスンの感想 | follow-up | 0.68 | 0.5 | 0.9 | 1.0 | 0.7 | 0.5 | 0.2 |
...

上記の候補から最適なものを1つ選ぶか、NO_REPLY を判断してください。
スコアは参考値です。あなたの直感で最終判断してください。
```

- [ ] **Step 5: decision log にスコア内訳 + 学習情報を保存**

```typescript
state.lastDecisionLog = {
  ...decisionLog,
  scoredCandidates: scoredCandidates.slice(0, 10).map(c => ({
    topic: c.topic,
    source: c.source,
    category: c.category,
    scores: c.scores,
    finalScore: c.finalScore,
    explorationBonus: c.explorationBonus,
    selectionScore: c.selectionScore,
    reasoning: c.reasoning,
  })),
  weightsUsed,          // 今回使った重み（サンプリング + 文脈ボーナス後）
  sampledRaw,           // Beta分布からの生サンプル値
  contextBonus: bonus,  // 文脈ボーナスの内訳
  priors: learningState.priors,  // 現在の学習状態
};
```

- [ ] **Step 6: handleReaction() に TS priors 更新を統合**

既存のイベント駆動 handleReaction() に TS 学習をフックイン。
pendingReward は使わない — Slack の reaction_added イベントで即座に更新。

```typescript
// skill-enhanced-proactive-agent.ts の handleReaction() を拡張
async handleReaction(emoji: string, messageTs: string, channel: string): Promise<void> {
  const state = loadState(this.statePath);
  const entry = state.history.find((h) => h.slackTs === messageTs);
  if (!entry) return;

  // 既存: categoryWeights は読み取り専用に変更（applyReaction の重み更新を停止）
  // 反応の記録（entry.reaction, entry.reactionDelta, stats）は維持
  applyReaction(state, messageTs, emoji);

  // NEW: Thompson Sampling priors を更新
  const scoredCandidate = state.lastScoredCandidates?.find(
    c => c.category === entry.interestCategory || c.topic === entry.preview
  );
  if (scoredCandidate && state.learningState) {
    const reaction = emojiToReaction(emoji);  // 'positive' | 'neutral' | 'negative'
    state.learningState = updatePriors(state.learningState, scoredCandidate, reaction);
    state.learningState = rescalePriors(state.learningState);
  }

  saveState(state, this.statePath);

  // 既存: Skill learning
  if (this.enableSkillLearning) {
    await this.learnFromReaction(emoji, messageTs);
  }
}
```

- [ ] **Step 7: neutral 検知（次回 run() 冒頭）**

run() の冒頭で、前回送信から2時間以上経過 + 反応なしを neutral として TS 更新。

```typescript
// run() の冒頭に追加
function checkNeutralReaction(state: ProactiveState): void {
  if (!state.lastScoredCandidates?.length) return;
  const lastEntry = state.history[state.history.length - 1];
  if (!lastEntry || lastEntry.reaction !== null) return;  // 既に反応あり

  const minutesSinceSent = (Date.now() - new Date(lastEntry.sentAt).getTime()) / 60000;
  if (minutesSinceSent < 120) return;  // 2時間未満はまだ待つ

  const scoredCandidate = state.lastScoredCandidates.find(
    c => c.category === lastEntry.interestCategory
  );
  if (scoredCandidate && state.learningState) {
    state.learningState = updatePriors(state.learningState, scoredCandidate, 'neutral');
    state.learningState = rescalePriors(state.learningState);
  }
}
```

- [ ] **Step 8: learningState の永続化 + lastScoredCandidates の保存**

`proactive-state.ts` の型と `loadState()` / `saveState()` を拡張:

```typescript
interface ProactiveState {
  // ... 既存フィールド
  learningState?: LearningState;                    // Thompson Sampling の学習状態
  lastScoredCandidates?: ScoredCandidate[];         // 直近のスコア付き候補（ダッシュボード + 反応マッチ用）
}

// loadState() 内:
if (!state.learningState) {
  state.learningState = createInitialLearningState();
}
```

- [ ] **Step 9: categoryWeights の更新停止**

`applyReaction()` 内の `updateWeight()` 呼び出しをコメントアウトまたは条件分岐。
既存の categoryWeights 値は保持（affinity スコアの入力として使用）。

- [ ] **Step 10: コミット**

```bash
git add src/skill-enhanced-proactive-agent.ts src/proactive-state.ts src/conversation-scorer.ts src/thompson-sampling.ts
git commit -m "feat: integrate 6-axis scoring with Thompson Sampling into proactive agent"
```

---

## Task 4: ダッシュボード — スコア内訳の可視化

**Files:**
- Modify: `dashboard/src/pages/ProactiveConfig.tsx`
- Modify: `dashboard/server/api.ts`

- [ ] **Step 1: API に scoredCandidates を含める**

stats API で `lastScoredCandidates` を返す。

- [ ] **Step 2: 判断ログセクションにレーダーチャート風のスコア表示**

各候補のスコア内訳を6軸のバーチャートで表示:

```
#1 ドジャース開幕戦結果 [0.82]
  旬  ████████░░ 0.9
  新鮮 ████████░░ 0.8
  流れ █████████░ 0.9
  状態 ████████░░ 0.8
  好み █████████░ 0.7
  意外 ███░░░░░░░ 0.3

#2 Claude Code検証記事 [0.71]
  旬  ████████░░ 0.8
  ...
```

- [ ] **Step 3: スコア軸のラベルを日本語で表示**

```typescript
const AXIS_LABELS: Record<string, string> = {
  timeliness: '旬',
  novelty: '新鮮さ',
  continuity: '流れ',
  emotional_fit: '状態',
  affinity: '好み',
  surprise: '意外性',
};
```

- [ ] **Step 4: 動的重みの表示（サンプリング + 文脈ボーナスの分解）**

「今回の重み配分」セクションを追加。3層構造で表示:
1. **Beta分布からのサンプル**: 学習済みの生の重み
2. **文脈ボーナス**: なぜこの重みになったか（朝だから、週末だから、等）
3. **最終重み**: 正規化後の実際に使われた重み

- [ ] **Step 5: 学習状態の可視化**

「学習状態（Thompson Sampling）」セクションを追加:

```
各軸の信頼度:
  旬     ████████░░ α=12.3 β=7.1  期待値=0.63  [95%CI: 0.45-0.79]
  新鮮さ  ██████░░░░ α=8.2  β=9.4  期待値=0.47  [95%CI: 0.30-0.64]
  流れ   █████░░░░░ α=6.1  β=8.9  期待値=0.41  [95%CI: 0.23-0.60]
  状態   ████░░░░░░ α=4.5  β=10.2 期待値=0.31  [95%CI: 0.14-0.50]
  好み   ███░░░░░░░ α=3.8  β=11.1 期待値=0.26  [95%CI: 0.11-0.44]
  意外性  ██░░░░░░░░ α=2.9  β=9.7  期待値=0.23  [95%CI: 0.08-0.42]

学習回数: 47回 | 最終更新: 2分前
```

信頼区間（95% CI）は Beta 分布の 2.5% / 97.5% パーセンタイルで算出。
CI が広い = まだ不確実 → 探索が多い。CI が狭い = 確信が高い → 活用に寄る。

- [ ] **Step 6: 探索 vs 活用の透明性**

候補リストの表示に `explorationBonus` を追加:
```
#1 ドジャース開幕戦結果 [0.82 + 0.02 = 0.84]
                       ↑score   ↑exploration
#3 天気（ゴルフ前日）    [0.54 + 0.18 = 0.72]  ← 探索ボーナスで浮上
                                ↑ 選択回数が少ない
```

- [ ] **Step 7: コミット**

```bash
git add dashboard/
git commit -m "feat: add Thompson Sampling learning visualization to proactive dashboard"
```

---

## Task 5: ビルドとテスト

- [ ] **Step 1: ダッシュボードビルド**

```bash
cd /Users/akira/workspace/claude-code-slack-bot/dashboard && npm run build
```

- [ ] **Step 2: pm2 restart + dashboard restart**

```bash
pm2 restart claude-slack-bot
pkill -f "tsx server/api.ts"; cd dashboard && nohup npx tsx server/api.ts &
```

- [ ] **Step 3: 手動実行で動作確認**

```bash
curl -s -X POST http://127.0.0.1:3457/internal/run-proactive
```

ダッシュボードで判断ログのスコア内訳が表示されることを確認。

- [ ] **Step 4: ブラウザで確認（スクリーンショットで内容を検証）**

```bash
$B goto http://localhost:3456/bot/proactive
$B screenshot /tmp/proactive-v3.png
```

スクリーンショットを読んで、スコア内訳が妥当な値か、表示が正しいかを確認。

---

## 設計の核心: なぜこれが「人間らしい」か

1. **同じ情報でも文脈で価値が変わる** — ドジャースの試合結果は試合当日は timeliness=1.0 だが翌々日は 0.2。でも「昨日観た試合」のフォローアップなら continuity=0.9 で救われる

2. **低優先カテゴリでもタイムリーなら浮上する** — 普段 Tier C の「天気」でも、ゴルフレッスンの日に雨予報なら timeliness=1.0 + emotional_fit=0.9 で一気にトップに

3. **飽きを検知して変化をつける** — 3回連続無反応 → surprise の重みが上がり、普段と違うカテゴリの話題が選ばれる

4. **会話の流れを大切にする** — 昨日ゴルフの話をしたら、今日はゴルフの話題よりゴルフのフォローアップ（「どうだった？」）の方がスコアが高い

5. **相手の状態を想像する** — 忙しい日に重い話はしない、週末は楽しい話題を選ぶ

6. **経験から学ぶ（Thompson Sampling）** — 「前にこういう話題で反応良かったから、似た状況ではこの軸を重視しよう」。人間が無意識にやっている「この人にはこの話の振り方が合う」を Beta 分布の更新で再現する

7. **たまに冒険する（UCB 探索）** — いつも安全な話題だけだと関係が硬直する。試したことのないカテゴリに探索ボーナスを付けて、新しい反応パターンを発見する機会を作る

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 5 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**VERDICT:** ENG CLEARED — 5 issues all resolved (dual learning→C案, polling→event-driven, RawCandidate→metadata bag, TS分離, ループ安全弁). 55 test paths identified for TDD.
