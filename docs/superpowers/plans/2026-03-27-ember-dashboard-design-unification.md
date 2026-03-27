# Ember Dashboard Design Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ember ダッシュボードのビジュアルを cogmem のアーストーンに統一し、CSS Custom Properties + Tailwind ハイブリッドで実装する。

**Architecture:** CSS Custom Properties を `src/index.css` に定義し、全コンポーネントの Tailwind カラークラスを `bg-[var(--surface)]` 形式に置換。レイアウトユーティリティ（flex, grid, gap, p-*, m-*）は維持。

**Tech Stack:** React 19, Tailwind CSS 3.4, CSS Custom Properties, Recharts

**Spec:** `docs/superpowers/specs/2026-03-27-ember-dashboard-design-unification.md`

**Working Directory:** `/Users/akira/workspace/claude-code-slack-bot/dashboard`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/index.css` | Modify | CSS Custom Properties 定義 + scrollbar 更新 |
| `src/types.ts` | Modify | CATEGORY_COLORS + CHART_COLORS 定義 |
| `src/components/Layout.tsx` | Modify | メイン背景色 |
| `src/components/Sidebar.tsx` | Modify | サイドバー全体の色 + アクティブ状態 |
| `src/components/BotSelector.tsx` | Modify | cyan → accent 置換 |
| `src/pages/Overview.tsx` | Modify | カード・テーブル・チャート・バッジ |
| `src/pages/ActivityLog.tsx` | Modify | チャート・テーブル |
| `src/pages/CategoryWeights.tsx` | Modify | チャート・ボタン |
| `src/pages/PersonalityConfig.tsx` | Modify | フォーム・選択UI |
| `src/pages/ModelsLimits.tsx` | Modify | フォーム |
| `src/pages/ProactiveConfig.tsx` | Modify | フォーム・トグル・タグ |
| `src/pages/ConversationHistory.tsx` | Modify | テーブル |
| `src/pages/UserInsights.tsx` | Modify | arousal カラー関数 |
| `src/pages/Constants.tsx` | Modify | カード |
| `src/pages/BotManagement.tsx` | Modify | カード・ボタン |
| `src/pages/CronJobsPage.tsx` | Modify | リンク・テキスト |
| `src/pages/McpServersPage.tsx` | Modify | 選択UI |
| `src/pages/BotWizard.tsx` | Modify | ウィザード全体（最大ファイル） |
| `src/pages/StampCompetition.tsx` | Modify | BOT_COLORS・テーブル |
| `src/pages/GlobalConfig.tsx` | Modify | テキスト色 |

---

### Task 1: CSS Custom Properties + Color Constants

**Files:**
- Modify: `src/index.css`
- Modify: `src/types.ts`

- [ ] **Step 1: index.css に CSS Custom Properties を追加**

`@tailwind` ディレクティブの後、既存のスタイルの前に追加:

```css
/* Ember Glow Design Tokens */
:root {
  /* Main Content Area */
  --bg: #f5ede4;
  --surface: #ede4d8;
  --surface-hover: #e4d8ca;
  --border: #d4c8b8;
  --text: #3a2e28;
  --text-dim: #705848;
  --scrollbar-thumb: #9a8878;
  --scrollbar-thumb-hover: #b8a898;

  /* Accent (from Ember logo) */
  --accent: #C06830;
  --accent-hover: #A85828;
  --accent-dim: #904820;
  --accent-light: #E8854A;

  /* Status + hover variants */
  --success-hover: #3a7a3a;

  /* Sidebar */
  --sidebar-bg: #31241e;
  --sidebar-surface: #3e3028;
  --sidebar-border: #4a3e34;
  --sidebar-text: #a89888;
  --sidebar-text-active: #f0e8e0;
  --sidebar-active-bg: rgba(192, 104, 48, 0.12);
  --sidebar-active-border: #C06830;

  /* Status */
  --success: #4a8a4a;
  --warning: #8a6a20;
  --error: #b85040;
  --info: #5070a0;
}
```

- [ ] **Step 2: scrollbar のハードコードカラーを CSS 変数に置換**

```css
/* Before */
::-webkit-scrollbar-thumb { background: #4b5563; }
::-webkit-scrollbar-thumb:hover { background: #6b7280; }

/* After */
::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); }
::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-thumb-hover); }
```

- [ ] **Step 3: types.ts の CATEGORY_COLORS を更新**

```typescript
export const CATEGORY_COLORS: Record<SuggestionCategory, string> = {
  email_reply: '#5070a0',
  meeting_prep: '#6a5a9a',
  deadline_risk: '#984030',
  slack_followup: '#C06830',
  energy_break: '#4a8a4a',
  personal_event: '#8a6a20',
  hobby_leisure: '#8a4a6a',
  flashback: '#6a5a9a',
};
```

- [ ] **Step 4: types.ts に CHART_COLORS を追加**

```typescript
export const CHART_COLORS = {
  primary: '#C06830',
  secondary: '#8a6a20',
  tertiary: '#5070a0',
  grid: '#d4c8b8',
  axis: '#705848',
  tooltip: {
    bg: '#ede4d8',
    border: '#d4c8b8',
    text: '#3a2e28',
  },
};
```

- [ ] **Step 5: dev サーバーで CSS 変数が読み込まれることを確認**

Run: `cd /Users/akira/workspace/claude-code-slack-bot/dashboard && npm run dev`
→ ブラウザで DevTools → `:root` の CSS 変数が定義されていることを確認

- [ ] **Step 6: Commit**

```bash
git add src/index.css src/types.ts
git commit -m "style: add Ember Glow CSS custom properties and update color constants"
```

---

### Task 2: Layout + Sidebar

**Files:**
- Modify: `src/components/Layout.tsx`
- Modify: `src/components/Sidebar.tsx`
- Modify: `src/components/BotSelector.tsx`

- [ ] **Step 1: Layout.tsx — メイン背景を CSS 変数に**

```
bg-gray-900 → bg-[var(--bg)]
```

- [ ] **Step 2: Sidebar.tsx — 全カラークラスを CSS 変数に置換**

置換マッピング:
```
bg-gray-950           → bg-[var(--sidebar-bg)]
border-gray-800       → border-[var(--sidebar-border)]
text-gray-200         → text-[var(--sidebar-text-active)]
text-gray-400         → text-[var(--sidebar-text)]
text-gray-500         → text-[var(--text-dim)]
text-gray-600         → text-[var(--text-dim)]
hover:text-gray-200   → hover:text-[var(--sidebar-text-active)]
hover:bg-gray-800/30  → hover:bg-[var(--sidebar-surface)]
bg-gray-800/60        → bg-[var(--sidebar-active-bg)]
text-white            → text-[var(--sidebar-text-active)]
border-cyan-500       → border-[var(--sidebar-active-border)]
border-gray-700       → border-[var(--sidebar-border)]
hover:border-gray-500 → hover:border-[var(--sidebar-text)]
text-orange-400       → text-[var(--accent-light)]
```

- [ ] **Step 3: BotSelector.tsx — cyan を accent に置換**

```
text-cyan-400         → text-[var(--accent)]
focus:border-cyan-500 → focus:border-[var(--accent)]
bg-gray-900           → bg-[var(--surface)]
border-gray-700       → border-[var(--border)]
text-gray-100         → text-[var(--text)]
border-gray-800       → border-[var(--border)]
text-gray-500         → text-[var(--text-dim)]
```

- [ ] **Step 4: BotSelector.tsx — インライン SVG のカラーも置換**

ドロップダウン矢印の SVG URL に `%236b7280` (= #6b7280) がハードコードされている。
`%23705848` (= var(--text-dim) の値) に置換。

- [ ] **Step 5: /browse で確認**

サイドバーがダークチョコレート、メインがサンドストーン、アクティブ状態が左ボーダーオレンジになっていることを確認。

- [ ] **Step 6: Commit**

```bash
git add src/components/Layout.tsx src/components/Sidebar.tsx src/components/BotSelector.tsx
git commit -m "style: migrate Layout, Sidebar, BotSelector to Ember Glow tokens"
```

---

### Task 3: Overview ページ

**Files:**
- Modify: `src/pages/Overview.tsx`

- [ ] **Step 1: カード背景・ボーダーを置換**

```
bg-gray-800     → bg-[var(--surface)]
border-gray-700 → border-[var(--border)]
```

- [ ] **Step 2: テキスト色を置換**

```
text-gray-100  → text-[var(--text)]
text-gray-300  → text-[var(--text)]
text-gray-400  → text-[var(--text-dim)]
text-gray-500  → text-[var(--text-dim)]
```

- [ ] **Step 3: セマンティックカラーを置換**

```
text-blue-400   → text-[var(--accent)]
text-green-400  → text-[var(--success)]
text-red-400    → text-[var(--error)]
text-amber-400  → text-[var(--warning)]
text-purple-400 → text-[var(--info)]
```

- [ ] **Step 4: テーブルのホバーを置換**

```
hover:bg-gray-700/30  → hover:bg-[var(--surface-hover)]
border-gray-700/50    → border-[var(--border)]
```

- [ ] **Step 5: Recharts のインラインカラーを CHART_COLORS に置換**

```typescript
import { CHART_COLORS } from '../types';

// Area chart
stroke={CHART_COLORS.primary}  // was "#3b82f6"
stopColor={CHART_COLORS.primary}

// Axis
stroke={CHART_COLORS.axis}  // was "#6b7280"

// Tooltip
contentStyle={{
  backgroundColor: CHART_COLORS.tooltip.bg,
  border: `1px solid ${CHART_COLORS.tooltip.border}`,
  borderRadius: '8px',
}}
labelStyle={{ color: CHART_COLORS.axis }}
```

- [ ] **Step 6: /browse で確認**

Overview ページのカード、テーブル、チャートが Ember Glow カラーになっていることを確認。

- [ ] **Step 7: Commit**

```bash
git add src/pages/Overview.tsx
git commit -m "style: migrate Overview page to Ember Glow tokens"
```

---

### Task 4: ActivityLog + CategoryWeights

**Files:**
- Modify: `src/pages/ActivityLog.tsx`
- Modify: `src/pages/CategoryWeights.tsx`

- [ ] **Step 1: ActivityLog.tsx — カード・テーブル・チャートを置換**

同じパターン:
```
bg-gray-800     → bg-[var(--surface)]
border-gray-700 → border-[var(--border)]
text-gray-400   → text-[var(--text-dim)]
text-gray-300   → text-[var(--text)]
text-gray-500   → text-[var(--text-dim)]
text-blue-400   → text-[var(--accent)]
text-green-400  → text-[var(--success)]
text-red-400    → text-[var(--error)]
hover:bg-gray-700/30 → hover:bg-[var(--surface-hover)]
border-gray-700/50   → border-[var(--border)]
```

Recharts:
```typescript
import { CHART_COLORS } from '../types';

// Axis
stroke={CHART_COLORS.axis}       // was "#6b7280"

// Tooltip (same pattern as Overview)
contentStyle={{
  backgroundColor: CHART_COLORS.tooltip.bg,
  border: `1px solid ${CHART_COLORS.tooltip.border}`,
  borderRadius: '8px',
}}

// Lines — 3本それぞれ distinct な色:
stroke={CHART_COLORS.primary}    // "sent" — #C06830 (was "#3b82f6")
stroke="#4a8a4a"                  // "positive" — success green (was "#22c55e")
stroke="#b85040"                  // "negative" — error red (was "#ef4444")
```

- [ ] **Step 2: CategoryWeights.tsx — チャート・ボタンを置換**

```
bg-gray-800     → bg-[var(--surface)]
border-gray-700 → border-[var(--border)]
text-gray-300   → text-[var(--text)]
text-cyan-400   → text-[var(--accent)]
accent-blue-500 → accent-[var(--accent)]  (range input)
bg-blue-600     → bg-[var(--accent)]
hover:bg-blue-700 → hover:bg-[var(--accent-hover)]
bg-green-600    → bg-[var(--success)]
hover:bg-green-700 → hover:bg-[var(--success-hover)]
bg-gray-700     → bg-[var(--border)]
hover:bg-gray-600 → hover:bg-[var(--text-dim)]
text-red-400    → text-[var(--error)]
text-green-400  → text-[var(--success)]
```

- [ ] **Step 3: /browse で確認**

- [ ] **Step 4: Commit**

```bash
git add src/pages/ActivityLog.tsx src/pages/CategoryWeights.tsx
git commit -m "style: migrate ActivityLog and CategoryWeights to Ember Glow"
```

---

### Task 5: フォーム系ページ（PersonalityConfig, ModelsLimits, ProactiveConfig）

**Files:**
- Modify: `src/pages/PersonalityConfig.tsx`
- Modify: `src/pages/ModelsLimits.tsx`
- Modify: `src/pages/ProactiveConfig.tsx`

- [ ] **Step 1: 共通パターンを3ファイルに適用**

全ファイル共通の置換:
```
bg-gray-800         → bg-[var(--surface)]
border-gray-700     → border-[var(--border)]
bg-gray-900         → bg-[var(--bg)]
bg-gray-900/50      → bg-[var(--bg)]
text-gray-100       → text-[var(--text)]
text-gray-400       → text-[var(--text-dim)]
text-gray-300       → text-[var(--text)]
focus:border-blue-500 → focus:border-[var(--accent)]
bg-blue-600         → bg-[var(--accent)]
hover:bg-blue-700   → hover:bg-[var(--accent-hover)]
bg-green-600        → bg-[var(--success)]
hover:bg-green-700  → hover:bg-[var(--success-hover)]
bg-purple-600       → bg-[var(--info)]
hover:bg-purple-700 → hover:bg-[#405a8a]
text-red-400        → text-[var(--error)]
text-green-400      → text-[var(--success)]
text-cyan-400       → text-[var(--accent)]
```

- [ ] **Step 2: PersonalityConfig の選択 UI を置換**

```
border-cyan-500     → border-[var(--accent)]
bg-cyan-500/10      → bg-[var(--accent)]/10
hover:border-gray-600 → hover:border-[var(--text-dim)]
```

- [ ] **Step 3: ProactiveConfig のトグルスイッチを置換**

```
bg-cyan-600 (on)    → bg-[var(--accent)]
bg-gray-600 (off)   → bg-[var(--border)]
```

タグ:
```
bg-gray-900/50      → bg-[var(--bg)]
border-gray-700     → border-[var(--border)]
text-gray-300       → text-[var(--text)]
text-gray-500       → text-[var(--text-dim)]
hover:text-red-400  → hover:text-[var(--error)]
bg-gray-700         → bg-[var(--border)]
hover:bg-gray-600   → hover:bg-[var(--text-dim)]
```

- [ ] **Step 4: /browse で確認**

- [ ] **Step 5: Commit**

```bash
git add src/pages/PersonalityConfig.tsx src/pages/ModelsLimits.tsx src/pages/ProactiveConfig.tsx
git commit -m "style: migrate form pages to Ember Glow tokens"
```

---

### Task 6: テーブル系ページ（ConversationHistory, UserInsights, StampCompetition）

**Files:**
- Modify: `src/pages/ConversationHistory.tsx`
- Modify: `src/pages/UserInsights.tsx`
- Modify: `src/pages/StampCompetition.tsx`

- [ ] **Step 1: ConversationHistory.tsx — テーブル・セレクトを置換**

共通パターン適用 + 条件分岐色:
```
text-gray-500 (null)     → text-[var(--text-dim)]
text-green-400 (positive) → text-[var(--success)]
text-red-400 (negative)   → text-[var(--error)]
text-gray-400 (neutral)   → text-[var(--text-dim)]
```

- [ ] **Step 2: UserInsights.tsx — arousalColor 関数を更新**

```typescript
// Before
const arousalColor = (a: number) =>
  a < 0.3 ? 'text-red-400' : a < 0.6 ? 'text-yellow-400' : 'text-green-400';

// After
const arousalColor = (a: number) =>
  a < 0.3 ? 'text-[var(--error)]' : a < 0.6 ? 'text-[var(--warning)]' : 'text-[var(--success)]';
```

- [ ] **Step 3: UserInsights.tsx — ボタン・range input も置換**

```
bg-blue-600       → bg-[var(--accent)]
hover:bg-blue-700 → hover:bg-[var(--accent-hover)]
accent-blue-500   → accent-[var(--accent)]
```

- [ ] **Step 4: StampCompetition.tsx — BOT_COLORS + テーブルを置換**

BOT_COLORS を Ember Glow に:
```typescript
const BOT_COLORS: Record<string, string> = {
  mei: '#8a4a6a',    // was '#ec4899' (pink)
  eve: '#6a5a9a',    // was '#8b5cf6' (purple)
};
const DEFAULT_BOT_COLOR = '#5070a0';  // was '#3b82f6'
```

Winner バッジ:
```
bg-yellow-500/20    → bg-[var(--warning)]/20
text-yellow-400     → text-[var(--warning)]
border-yellow-500/30 → border-[var(--warning)]/30
```

- [ ] **Step 5: /browse で確認**

- [ ] **Step 6: Commit**

```bash
git add src/pages/ConversationHistory.tsx src/pages/UserInsights.tsx src/pages/StampCompetition.tsx
git commit -m "style: migrate table/insight pages to Ember Glow tokens"
```

---

### Task 7: 残りのページ（Constants, BotManagement, CronJobs, McpServers, GlobalConfig）

**Files:**
- Modify: `src/pages/Constants.tsx`
- Modify: `src/pages/BotManagement.tsx`
- Modify: `src/pages/CronJobsPage.tsx`
- Modify: `src/pages/McpServersPage.tsx`
- Modify: `src/pages/GlobalConfig.tsx`

- [ ] **Step 1: 全5ファイルに共通パターンを適用**

```
bg-gray-800       → bg-[var(--surface)]
border-gray-700   → border-[var(--border)]
border-gray-600   → border-[var(--border)]
text-gray-400     → text-[var(--text-dim)]
text-gray-100     → text-[var(--text)]
text-gray-200     → text-[var(--text)]
text-cyan-400     → text-[var(--accent)]
text-blue-400     → text-[var(--accent)]
bg-blue-600       → bg-[var(--accent)]
hover:bg-blue-700 → hover:bg-[var(--accent-hover)]
bg-red-900/30     → bg-[var(--error)]/10
border-red-700    → border-[var(--error)]
text-red-400      → text-[var(--error)]
text-yellow-400   → text-[var(--warning)]
```

- [ ] **Step 2: CronJobsPage 固有の色を置換**

purple ボタン:
```
bg-purple-600       → bg-[var(--info)]
hover:bg-purple-700 → hover:bg-[#405a8a]
```

選択 UI:
```
border-cyan-500     → border-[var(--accent)]
bg-cyan-500/10      → bg-[var(--accent)]/10
```

ステータスバッジ:
```
bg-green-500/20 text-green-400   → bg-[var(--success)]/20 text-[var(--success)]
bg-red-500/20 text-red-400       → bg-[var(--error)]/20 text-[var(--error)]
bg-yellow-500/20 text-yellow-400 → bg-[var(--warning)]/20 text-[var(--warning)]
```

- [ ] **Step 3: GlobalConfig 固有の色を置換**

Danger ボタン:
```
bg-red-600       → bg-[var(--error)]
hover:bg-red-700 → hover:bg-[#983838]
```

成功アラート:
```
bg-green-900/30 border-green-700 text-green-400
→ bg-[var(--success)]/10 border-[var(--success)] text-[var(--success)]
```

- [ ] **Step 4: McpServersPage の選択 UI を置換**

```
border-cyan-500       → border-[var(--accent)]
bg-cyan-500/10        → bg-[var(--accent)]/10
hover:border-gray-600 → hover:border-[var(--text-dim)]
```

- [ ] **Step 5: /browse で確認**

- [ ] **Step 6: Commit**

```bash
git add src/pages/Constants.tsx src/pages/BotManagement.tsx src/pages/CronJobsPage.tsx src/pages/McpServersPage.tsx src/pages/GlobalConfig.tsx
git commit -m "style: migrate remaining pages to Ember Glow tokens"
```

---

### Task 8: BotWizard（最大ファイル、単独タスク）

**Files:**
- Modify: `src/pages/BotWizard.tsx`

- [ ] **Step 1: カード・コンテナ・テキストの共通パターンを適用**

```
bg-gray-800      → bg-[var(--surface)]
border-gray-700  → border-[var(--border)]
bg-gray-900      → bg-[var(--bg)]
text-gray-100    → text-[var(--text)]
text-gray-200    → text-[var(--text)]
text-gray-300    → text-[var(--text)]
text-gray-400    → text-[var(--text-dim)]
text-gray-500    → text-[var(--text-dim)]
```

- [ ] **Step 2: ウィザードステップインジケーターを置換**

```
bg-blue-600 (active circle)  → bg-[var(--accent)]
bg-gray-700 (inactive)       → bg-[var(--border)]
text-gray-400 (inactive)     → text-[var(--text-dim)]
text-gray-200 (active label) → text-[var(--text)]
text-gray-500 (inactive label) → text-[var(--text-dim)]
bg-blue-600 (progress line)  → bg-[var(--accent)]
bg-gray-700 (progress line)  → bg-[var(--border)]
```

- [ ] **Step 3: 選択 UI（personality, motif）を置換**

```
border-cyan-500    → border-[var(--accent)]
bg-cyan-900/20     → bg-[var(--accent)]/10
text-cyan-300      → text-[var(--accent)]
hover:border-gray-600 → hover:border-[var(--text-dim)]
text-cyan-400      → text-[var(--accent)]
```

- [ ] **Step 4: ボタンを置換**

```
bg-blue-600        → bg-[var(--accent)]
hover:bg-blue-500  → hover:bg-[var(--accent-hover)]  (※ 実際は hover:bg-blue-700 の場合もあり — ファイル内の実際のクラスに合わせる)
disabled:bg-gray-700 → disabled:bg-[var(--border)]
disabled:text-gray-500 → disabled:text-[var(--text-dim)]
bg-green-600       → bg-[var(--success)]
hover:bg-green-500 → hover:bg-[var(--success-hover)]
bg-gray-700        → bg-[var(--border)]
hover:bg-gray-600  → hover:bg-[var(--text-dim)]
```

- [ ] **Step 5: トグルスイッチのハードコードカラーを置換**

```typescript
// Before (inline style)
backgroundColor: enabled ? '#2563eb' : '#4b5563'

// After
backgroundColor: enabled ? 'var(--accent)' : 'var(--border)'
```

- [ ] **Step 6: エラー表示を置換**

```
bg-red-900/30  → bg-[var(--error)]/10
border-red-700 → border-[var(--error)]
text-red-400   → text-[var(--error)]
text-blue-400  → text-[var(--accent)]
hover:text-blue-300 → hover:text-[var(--accent-light)]
text-blue-400 (generating) → text-[var(--accent)]
```

- [ ] **Step 7: /browse で確認**

ウィザードの全4ステップ（Overview → Config → Personality → Confirm）を確認。

- [ ] **Step 8: Commit**

```bash
git add src/pages/BotWizard.tsx
git commit -m "style: migrate BotWizard to Ember Glow tokens"
```

---

### Task 9: タイポグラフィ統一

**Files:**
- Modify: `src/index.css`
- Modify: 全コンポーネント（タイポグラフィ関連のみ）

- [ ] **Step 1: index.css にベースタイポグラフィを追加**

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: var(--text);
  background: var(--bg);
}
```

- [ ] **Step 2: 全ページのカードラベルにタイポグラフィクラスを追加**

`text-xs text-gray-400` のカードラベルを以下に統一:
```
text-xs → text-[0.75rem]
+ uppercase tracking-[0.05em] font-medium
```

これは各ページの stat カードラベル（「Messages Today」等）に適用。
対象ファイル: Overview.tsx, CategoryWeights.tsx, ModelsLimits.tsx, ProactiveConfig.tsx, PersonalityConfig.tsx

- [ ] **Step 3: テーブルヘッダーにタイポグラフィを統一**

`text-gray-400 text-xs` のテーブルヘッダーを:
```
+ uppercase tracking-[0.05em] font-medium
```

対象: Overview.tsx, ActivityLog.tsx, ConversationHistory.tsx, StampCompetition.tsx

- [ ] **Step 4: stat 値に tabular-nums を追加**

数値表示（`text-2xl font-bold`）に `tabular-nums` を追加:
```
className="text-[1.75rem] font-bold tabular-nums"
```

※ Tailwind は `tabular-nums` をユーティリティとしてサポート。

- [ ] **Step 5: /browse で確認**

- [ ] **Step 6: Commit**

```bash
git add src/index.css src/pages/*.tsx
git commit -m "style: unify typography with cogmem patterns"
```

---

### Task 10: バッジスタイルの pill 化

**Files:**
- Modify: `src/pages/Overview.tsx`
- Modify: 他のバッジ使用箇所

- [ ] **Step 1: Overview.tsx のカテゴリバッジを pill 化**

```
rounded → rounded-full  (= border-radius: 9999px)
```

badge の `+ '20'` パターンはそのまま活用（CATEGORY_COLORS が更新済みなので色は自動で変わる）。

- [ ] **Step 2: ステータスバッジ（enabled/disabled）を pill + 新色に**

Overview 等にあるステータスバッジ:
```
bg-green-900/40 text-green-400 → background: rgba(74,138,74,0.12), color: #3a7a3a
bg-gray-700 text-gray-400      → background: rgba(138,112,96,0.15), color: var(--text-dim)
+ rounded-full
```

- [ ] **Step 3: /browse で確認**

- [ ] **Step 4: Commit**

```bash
git add src/pages/Overview.tsx
git commit -m "style: update badges to pill shape with Ember Glow colors"
```

---

### Task 11: 最終 QA + クリーンアップ

- [ ] **Step 1: 全ページを /browse で巡回確認**

以下の全ページを確認:
1. Overview — カード、チャート、テーブル
2. Activity Log — チャート、テーブル
3. Category Weights — チャート、スライダー、ボタン
4. Personality Config — 選択UI、テキストエリア
5. Models & Limits — フォーム
6. Proactive Config — トグル、タグ
7. Conversation History — テーブル
8. User Insights — arousal 色
9. Constants — カード
10. Bot Management — カード、ボタン
11. Cron Jobs — テキスト
12. MCP Servers — 選択UI
13. Bot Wizard — 全4ステップ
14. Stamp Competition — テーブル、バッジ
15. Global Config — テキスト

- [ ] **Step 2: Tailwind の旧カラークラスが残っていないか grep 確認**

```bash
grep -rn 'gray-[0-9]' src/ --include='*.tsx' | grep -v node_modules
grep -rn 'cyan-' src/ --include='*.tsx'
grep -rn 'blue-[0-9]' src/ --include='*.tsx'
```

残っていれば修正。

- [ ] **Step 3: ビルドが通ることを確認**

```bash
npm run build
```

- [ ] **Step 4: 最終 Commit**

```bash
git add -A
git commit -m "style: final cleanup — Ember Glow design unification complete"
```
