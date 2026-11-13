# 艾宾浩斯认字强化模块 · 设计 TODO

> 状态：**已实现（2026-11-13）**。入口 `#/recognition`，实现见 `server/recognition.py` 与 `web/js/app.js`。  
> 目标：先让孩子自己过一遍识字表，标出「认识 / 不认识」，再根据自评和实际答题结果安排艾宾浩斯复习。

## 实现说明（2026-11-13）

- 默认按建议值实现：先过「幼儿识字 1300」（课内 664 + 拓展 636），也可选全部课内 688 / 一年级上册 / 下册；「认识」次日验证，「不认识」当天可复习。
- 2026-11-13 增补：底部新增「认字」tab；自评「不认识」的字可生成 A4 打印清单（可选是否含高估字、是否显示拼音）。
- 独立入口，不替换现有今日任务；今日页新增一张认字卡，两个模块并存。
- 间隔使用 1 / 2 / 4 / 7 / 15 / 30 / 60 天；认字阶段独立于 `char_progress` 的 Leitner 盒子。
- 每组最多复习 15 个字；和普通今日任务分开计时、分开排队。
- 自评不增加「学过 / 688」；家长页单独显示「已自评、已验证、高估、低估、待复习」。
- 初始过字只显示大字，不显示拼音、不自动读音；点「不认识」后，复习时先看字卡再答题。
- 数据表 `recognition_runs` / `recognition_items` / `recognition_attempts` 存在 `data/stats.db`，清空进度时一起清空。
- 校验：`python3 tools/validate_recognition.py`。

## 一、要解决的问题

现在的「今日任务」默认所有字都从零开始，按课文顺序学。但一年级孩子的识字量差异很大：

- 有些字孩子已经认识，仍要跟着新字卡走一遍，浪费时间；
- 有些字孩子以为认识，实际读错；
- 家长不知道哪些字是「真会」、哪些是「自评会但一考就错」。

这个模块把「自评」和「实测」分开记录，用自评决定先复习谁，用答题结果决定下一次什么时候复习。

## 二、用户流程

### 2.1 第一次：整体过一遍

入口放在「今日」页，作为一张独立卡片：

```
认字大冒险
先整体过一遍，认识的点「认识」，不认识的点「不认识」。
[开始过一遍 · 688 字]   或   [先过一年级上册]
```

规则：

- 一次显示一个字，**不显示拼音、意思、组词**，避免提示。
- 两个大按钮：「认识」「不认识」；键盘 `←` / `→` 或 `1` / `2`。
- 顶部显示进度：`第 128 / 688 字`，可随时点 `×` 退出，进度保存。
- 不要求一次过完；下次从上次停下的字继续。
- 过完显示汇总：认识 X 个、不认识 Y 个；建议先从「不认识」的字开始。
- 这一步只写自评，不直接把字算成「已掌握」。

### 2.2 每天：艾宾浩斯复习

「今日」页增加一行：

```
艾宾浩斯复习 12 个字 · 预计 4 分钟
```

队列优先级：

1. 到期且自评「不认识」的字：先看学字卡，再答题；
2. 到期且自评「认识」的字：直接答题验证；
3. 到期的新字 / 普通 SRS 复习：沿用现有队列；
4. 没排进本次的到期字，显示「还有 N 个，下次优先」。

每个字一次只做 1 题，答完立即结算：

- 答对：升级，下次间隔变长；
- 答错：降级，显示正确答案、读音、意思，并安排更近的复习；
- 自评「认识」但第一次验证答错：标记为「高估」，家长页单独列出；
- 自评「不认识」但第一次验证答对：可以直接跳一级，避免过度重复。

## 三、排程算法

### 3.1 阶段

新增一套独立的认字阶段（不要直接改动现有 Leitner 盒子，避免影响今日任务）：

| 阶段 | 含义 | 下次间隔 |
|---|---|---:|
| R0 | 刚自评「不认识」/ 刚学完 | 当天或次日 |
| R1 | 初步认识 | 1 天 |
| R2 | 两次正确 | 2 天 |
| R3 | 稳定认识 | 4 天 |
| R4 | 熟悉 | 7 天 |
| R5 | 很熟悉 | 15 天 |
| R6 | 接近掌握 | 30 天 |
| R7 | 掌握 | 60 天 |

### 3.2 自评到初始阶段

- 自评「认识」→ `R1`，次日验证；
- 自评「不认识」→ `R0`，当天/次日先学后测；
- 不直接给 `R3` 以上，避免「自评会」但实际不会。

### 3.3 答题后的变化

- 答对：`stage = min(7, stage + 1)`；
- 答错：`stage = max(0, stage - 1)`；
- 连续答对 2 次以上才允许进入 `R4+`；
- `R7` 之后仍按 60 天滚动复习，不彻底移出队列；
- 同一天同一个字只出现一次。

### 3.4 每日预算

第一版把两个模块分开排队，避免改动现有今日任务：

- 认字复习每组最多 15 个；
- 普通今日任务仍按原来的 20 题预算；
- 超出认字预算的字留到下次，显示 backlog；
- 连续学习 12 分钟仍然弹护眼提醒；
- 今日页让家长自己决定先做认字复习还是普通任务。

## 四、数据模型（stats.db）

```sql
CREATE TABLE IF NOT EXISTS recognition_runs (
  id          TEXT PRIMARY KEY,
  started_at  TEXT NOT NULL,
  ended_at    TEXT,
  scope       TEXT NOT NULL DEFAULT 'all', -- all / 1a / 1b / unit:xxx
  total       INTEGER NOT NULL DEFAULT 0,
  known       INTEGER NOT NULL DEFAULT 0,
  unknown     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recognition_items (
  char              TEXT PRIMARY KEY,
  run_id            TEXT,
  self_report       TEXT NOT NULL,          -- known / unknown
  reported_at       TEXT NOT NULL,
  stage             INTEGER NOT NULL DEFAULT 1, -- R0..R7
  due_at            TEXT NOT NULL,
  attempts          INTEGER NOT NULL DEFAULT 0,
  correct           INTEGER NOT NULL DEFAULT 0,
  wrong             INTEGER NOT NULL DEFAULT 0,
  streak            INTEGER NOT NULL DEFAULT 0,
  first_quiz_at     TEXT,
  first_quiz_correct INTEGER,               -- 1 / 0
  last_result       INTEGER,                -- 1 / 0
  last_seen_at      TEXT,
  updated_at        TEXT,
  FOREIGN KEY (run_id) REFERENCES recognition_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_recognition_due
  ON recognition_items(due_at);

CREATE TABLE IF NOT EXISTS recognition_attempts (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  char          TEXT NOT NULL,
  ts            TEXT NOT NULL,
  local_date    TEXT NOT NULL,
  result        INTEGER NOT NULL,           -- 1 对 / 0 错
  stage_before  INTEGER,
  stage_after   INTEGER,
  response_ms   INTEGER
);
```

说明：

- `char` 作为主键：每个字只保留当前状态；重新整体过一遍时更新，不重复。
- `recognition_attempts` 保留历史，方便家长看「第几次才记住」。
- 清空进度时，这三张表一起清空。
- 备份 `stats.db` 时自动包含，不需要额外操作。

## 五、API 草案

```text
GET  /api/recognition/summary      # 也挂在 /api/recognition/overview
  → { total, reported, self_known, self_unknown, verified,
      overconfident, underestimated, due, mastered,
      active_run, latest_run, scopes, by_stage, ... }

POST /api/recognition/runs
  body: { scope: "all" | "1a" | "1b" | "unit:1a-u1", restart: bool }
  → { run: { id, total, reported, known, unknown, status, ... },
      next: { char, index, total } | null, summary }

GET  /api/recognition/runs/{run_id}
  → { run, next, summary }

POST /api/recognition/runs/{run_id}/reports
  body: { char, report: "known" | "unknown" }
  → { run, next, summary }

GET  /api/recognition/today
  → { items: [...], due, backlog, limit, summary }

POST /api/recognition/attempts
  body: { char, correct: bool, response_ms: int }
  → { stage, due_at, due_in_days, overconfident, underestimated }
```

也可以把 `recognition` 字段合并进 `/api/today`，但建议先独立接口，避免把现有今日队列改复杂。

## 六、界面复用

- 学字卡、字卡弹窗继续复用 `web/js/components.js` 的 `charIdentityHtml()` / `charInfoBlocksHtml()`。
- 答题卡复用现有三种题型；把 `makeQuestion()` 从 `app.js` 抽成可复用函数（`web/js/quiz.js`），认字模块和今日任务共用。
- 初始过字页只需要大字 + 两个按钮，单独做一个轻量组件 `recognitionCardHtml()`。
- 家长页增加「自评 vs 实测」面板：
  - 自评认识、实测答错：高估字；
  - 自评不认识、实测答对：低估字；
  - 已验证 / 待验证 / 已掌握数量。

## 七、实施顺序

- [x] **P0 数据层**：加三张表、迁移版本 +1、`reset_progress` 清空、备份验证。
- [x] **P0 API**：`runs / reports / today / attempts / summary`，curl 跑通。
- [x] **P1 整体过一遍**：入口卡片、单字大字屏、认识/不认识、暂停续做、汇总页。
- [x] **P1 校验**：688 字不重不漏；中途退出再进入不重复；自评不增加「学过」统计。
- [x] **P2 每日复习**：到期队列、先学后测、答对升级、答错降级、每组最多 15 个。
- [x] **P2 首页整合**：今日页显示「艾宾浩斯复习 N 个字」，和普通任务不冲突。
- [x] **P3 家长页**：自评 vs 实测、高估字、低估字、掌握分布。
- [x] **P3 体验**：键盘操作、触控尺寸、护眼提醒、减少动效、空状态。
- [x] **P4 测试**：`tools/validate_recognition.py`（间隔、升降级、范围、边界）。
- [x] **P4 回归**：现有今日任务、字卡册、读一读、家长页、Lighthouse 100。

## 八、验收标准

- 幼儿识字 1300 个不同字都能过一遍；同一字不重复出现。
- 课内 688 字的今日任务、统计和字卡册不受拓展字影响。
- 中途退出、刷新、重启后能继续，不丢已报的字。
- 自评「认识」不会直接把字算成「已掌握」；必须经过答题验证。
- 答对/答错后 `due_at` 和 `stage` 正确变化。
- 认字复习每组不超过 15 个；普通今日任务仍按 20 题预算。
- 家长页能看出「自评会但答错」的字。
- 清空进度后三张表一起清空；备份恢复后数据一致。
- 现有功能不回归：`validate_content` / `validate_readings` / `validate_families` / `validate_polyphonic` / `validate_recognition` 全 0 错误，Lighthouse a11y/best-practices/SEO 100。

## 九、待确认

1. 第一次整体过一遍，默认过全部 688 字，还是先过一年级上册？
2. 「认识」的自评是次日验证，还是当天立即抽查一题？
3. 艾宾浩斯模块是独立入口，还是直接替换现在的「今日任务」？
4. 间隔用本文的 1/2/4/7/15/30/60，还是沿用现有 1/3/7/15/60？
5. 初始过字时是否允许点「听读音」？（建议不允许，避免提示答案。）

## 十、建议默认值

如果先做第一版，建议这样定，减少决策成本：

1. **默认过全部 688 字**，但入口同时给「先过一年级上册」；上册过完可以先开始每日复习，下册继续过。
2. **次日验证**，不当天抽查。自评只是分桶，不是最终结论。
3. **独立入口，和现有今日任务并存**。先验证模块有效，再考虑合并；不要一上来改坏现有学习流程。
4. **用 1/2/4/7/15/30/60**。这是更接近艾宾浩斯的阶梯；现有 Leitner 的 1/3/7/15/60 继续服务普通今日任务。
5. **初始过字不自动读音、不显示拼音**，避免提示；孩子点「不认识」后，下一页再显示拼音和读音。
6. **每天先做艾宾浩斯复习，再做普通今日任务**；如果时间不够，优先保证艾宾浩斯复习。
