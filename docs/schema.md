# 数据库与 API

## 一、SQLite 文件

拆成两个库：

- **内容库** `data/content.db`：`characters` / `books` / `units` / `lessons` / `curriculum_items` / `literacy_entries`
  - 来源：`data/characters.csv` + `data/curriculum/*.csv` + `data/literacy_1300.csv`，启动时幂等导入
  - 备份：家长页「备份字库」，或直接复制 `data/content.db`
- **统计库** `data/stats.db`：`char_progress` / `sessions` / `attempts` / `settings` / `events` / `recognition_runs` / `recognition_items` / `recognition_attempts` / `badge_unlocks`
  - 备份：家长页「备份学习记录」，或直接复制 `data/stats.db`
- 旧单库 `data/hanzi.legacy.db`：拆分前版本，首次创建 stats.db 时会复制统计表；之后保留作备份，不再使用
- 模式：WAL、外键开启
- 迁移：`schema_migrations` 表，每次结构变更加一条版本；当前统计库为 v6（成就 `badge_unlocks`、`sessions.completed`、诗岛 `poem_reads`）

统计库连接时会 `ATTACH` 内容库，并建立只读 `TEMP VIEW` 映射内容表，因此查询里仍可直接写 `characters`、`curriculum_items`。写内容表必须用 `connect_content()`。

## 二、表

- `content.db`：`characters`、`books`、`units`、`lessons`、`curriculum_items`、`literacy_entries`
- `stats.db`：`sessions`、`attempts`、`char_progress`、`settings`、`events`、`recognition_runs`、`recognition_items`、`recognition_attempts`、`badge_unlocks`、`poem_reads`

### characters

字表内容：课内 688 字来自 `data/characters.csv`，拓展 636 字来自 `data/literacy_1300.csv`。启动时 upsert，不覆盖学习进度；课内字内容优先，不会被拓展表覆盖。

关键字段：

```
char, pinyin, lesson_id, lesson, lesson_order,
radical, strokes, structure, origin, meaning,
words_json, sentence, mnemonic, confusions_json,
quiz_types_json, audio_key
```

### sessions

每次学习：

```
id, started_at, ended_at, completed, app_version
```

`completed = 1` 表示这一组学习走到了结算页；关闭中途退出时为 0。

### attempts

答题记录（M1 已启用）：

```
id, session_id, ts, local_date, char, question_type,
selected, correct_answer, is_correct, response_ms, reading_key
```

服务端根据 `selected` 和 `correct_answer` 计算 `is_correct`，不直接信任前端。

### char_progress

SRS 状态：

```
char, box, due_at, exposures, attempts, correct, wrong,
streak, mastery, first_seen_at, last_seen_at, updated_at
```

`mastery`：`new` / `learning` / `familiar` / `mastered`。
`box` 0–5，间隔 1/3/7/15/60 天。

### literacy_entries

「幼儿识字 1300」的成员和顺序：

```
char, sort_order
```

- 1300 个字都在这张表里；其中 664 个是课内字，636 个是拓展字。
- 课内字仍以 `curriculum_items` 的课程位置为准；`literacy_entries` 只服务认字模块的范围和排序。
- 拓展字在 `characters` 里用 `lesson_id = 'literacy'` 标记，不写入 `curriculum_items`，因此不会进入课内今日任务。

### recognition_runs / recognition_items / recognition_attempts

艾宾浩斯认字模块，和 `char_progress` 的 Leitner 盒子独立：

```
recognition_runs:
  id, started_at, ended_at, scope, total, known, unknown, status

recognition_items:
  char, run_id, self_report, reported_at, stage, due_at,
  attempts, correct, wrong, streak,
  first_quiz_at, first_quiz_correct, last_result, last_seen_at, updated_at

recognition_attempts:
  id, char, ts, local_date, result, stage_before, stage_after, response_ms
```

- `stage` 0–7，间隔 0/1/2/4/7/15/30/60 天；R0 当天可复习，R1 次日验证。
- `self_report`：`known` / `unknown`；自评不写入 `char_progress`，不增加「学过」。
- `first_quiz_correct` 用来识别高估（自评认识但第一次答错）和低估（自评不认识但第一次答对）。
- 清空进度时三张表一起清空，备份 `stats.db` 时自动包含。

### badge_unlocks

小岛成就的解锁流水：

```
badge_id, unlocked_at, local_date, seen, meta_json
```

- 只记录第一次解锁；进度从 `attempts` / `char_progress` / `recognition_items` / `recognition_attempts` 实时推导。
- `seen` 用来避免重复弹窗；成就不删除、不扣回。
- 旧库第一次启用成就时，已经达成的印章静默补录，避免一次弹出很多旧成就。
- 清空进度时 `badge_unlocks` 一起清空。

### poem_reads

诗岛阅读流水：

```
id, poem_id, ts, local_date, mode, completed
```

- 同一首诗可以重复读，每读一次写一条；`completed = 1` 表示读完。
- 诗的内容在 `data/poems.csv`（10 首试点），不建内容表；`poem_reads` 只存学习记录。CSV 的 `speech` 列是给系统语音的朗读文本，用同音字修正多音字（如「为」→「位」），显示和拼音仍用 `lines`。`line_audio` 列按句指定朗读方式：`tts`（默认，系统语音）或 `mp3:e2 e2 e2`（按顺序播放拼音音节音频）。
- 读完第一首 / 10 首会解锁「第一首诗 / 诗岛小旅行」。
- 清空进度时 `poem_reads` 一起清空。

### settings

```
key, value_json, updated_at
```

当前：`new_per_day`、`sound`、`auto_play_audio`、`reduce_motion`、`theme`、`pinyin_mode`、`achievements_enabled`。

### events（预留，M1 不写入）

完整操作流水：

```
id, client_event_id, session_id, ts, local_date,
type, char, payload_json
```

后续记录：

- `app_open` / `session_start` / `session_end`
- `screen_view`
- `char_view`
- `audio_play`
- `pinyin_toggle`
- `hint_use`
- `answer`（答题仍以 `attempts` 为准）
- `story_read`
- `settings_change`
- `error`

不记录鼠标移动、滚动等无分析价值的动作。

### schema_migrations

```
version, applied_at
```

## 三、SRS 规则

- 答对：`box = min(5, box + 1)`
- 答错：`box = max(0, box - 1)`
- `due_at = today + BOX_DAYS[box]`
- 新字：`first_seen_at IS NULL`
- 复习：`first_seen_at IS NOT NULL AND due_at <= today`
- 每日新字上限：`new_per_day - 今天已经见过的字数`
- 每次最多 15 个复习 + 当日剩余新字，总预算 20 题
- 艾宾浩斯认字单独排队，每组最多 15 个；间隔 1/2/4/7/15/30/60 天

## 四、API

```
GET  /api/health
GET  /api/bootstrap
GET  /api/today
GET  /api/characters
GET  /api/characters/{char}
GET  /api/lessons
GET  /api/poems
GET  /api/poems/{id}
POST /api/poems/{id}/read
POST /api/sessions
PATCH /api/sessions/{id}
POST /api/attempts
GET  /api/progress
GET  /api/stats/summary
GET  /api/parent/weekly
GET  /api/achievements
POST /api/achievements/seen
GET  /api/polyphonic
GET  /api/recognition/summary
POST /api/recognition/runs
GET  /api/recognition/runs/{id}
GET  /api/recognition/runs/{id}/items/{index}
POST /api/recognition/runs/{id}/reports
GET  /api/recognition/items
PATCH /api/recognition/items/{char}
GET  /api/recognition/today
GET  /api/recognition/print
POST /api/recognition/attempts
GET  /api/settings
POST /api/settings
POST /api/reset
GET  /api/export/attempts.csv
GET  /api/backup           学习记录备份（同 /api/backup/stats）
GET  /api/backup/stats     学习记录备份（stats.db）
GET  /api/backup/content   字库备份（content.db）
```

### POST /api/attempts

请求：

```json
{
  "session_id": "abc123",
  "attempts": [
    {
      "char": "日",
      "question_type": "audio",
      "selected": "日",
      "correct_answer": "日",
      "response_ms": 2100
    }
  ]
}
```

返回每个字的 `is_correct` 和更新后的 `progress`，以及最新 `stats`。

## 五、后续加操作流水的步骤

1. 前端加 `track(type, char, payload)`，批量缓存，2–3 秒提交一次，`pagehide` 时 `sendBeacon`。
2. 后端加 `POST /api/events`，用 `client_event_id` 做幂等。
3. 家长页加学习时长、发音次数、提示率、页面停留等统计。
4. 不改 `attempts` / `char_progress` / SRS 逻辑。

## 六、隐私

- 服务只绑定 `127.0.0.1`。
- 不联网、不上传、无账号。
- 数据可一键备份/导出。
