# P0 · 内容底座设计

日期：2026-11-12
状态：已实施（2026-11-12 完成，验收记录见文末）

> **实施勘误**：4.2 归位表写于拿到 2024 识字表原始数据之前，两处与 2024 教材不符，
> 实施时以 `data/curriculum/1a.csv`（家长提供的 2024 新版识字表）为准：
>
> 1. 识字4《日月山川》2024 为「水日月火山田川禾」（无石、新增川）；「石」在阅读9《乌鸦喝水》。
> 2. 第六单元识字5《对韵歌》2024 为 9 字「对歌雨风虫清绿桃红」；旧 Demo 的
>    「云」在汉语拼音13、「花」在汉语拼音5、「鸟」在阅读4《四季》。
>
> 因此现有 40 字的实际归位：第一单元 32 字 + 《对韵歌》4 字 + 石/云/花/鸟 散落各课。
> 课程位置先行导入（283 + 419 行），无内容的字显示「筹备中」，内容在 P1/P2 补齐。
> `curriculum_items.char` 未设指向 characters 的外键（规格原文有）——因为要求课程位置
> 先于字内容导入且不崩溃，改为查询时 JOIN。

## 一、目标

在不丢失现有学习进度的前提下，把「40 字 Demo」升级成能承载一上 280、一下 410 的内容底座。

P0 只做扩内容前必须补的基础设施，不补新字内容，不做练习/家长新功能。

## 二、为什么现在做

当前 40 字的内容本身可用，但课程结构是扁平的：

- `characters` 表一个字只有一条 `lesson_id`、`lesson`、`lesson_order`。
- 首页把 40 字都算成「第一单元」。
- 2024 版第一单元实际只有 4 课 + 语文园地一，共 33 字。
- 《对韵歌》7 字属于第六单元识字5。

如果不先补「书 → 单元 → 课文 → 字」的模型，扩到 280 时单元会继续混，后面还要返工。

## 三、非目标

- 不补 280/410 的新字内容（P1/P2）。
- 不做错字本、自由练习、家长周报、打印（P3）。
- 不做操作流水、故事/儿歌、插图、视觉打磨、打包（P4）。
- 不改 Leitner 盒子的 1/3/7/15/30 天间隔（P2 扩到 690 前再评估）。

## 四、数据模型

### 4.1 新表

```sql
CREATE TABLE books (
  id          TEXT PRIMARY KEY,   -- 1a / 1b
  title       TEXT NOT NULL,      -- 一年级上册
  edition     TEXT NOT NULL,      -- 2024 统编版
  sort_order  INTEGER NOT NULL
);

CREATE TABLE units (
  id          TEXT PRIMARY KEY,   -- 1a-u1
  book_id     TEXT NOT NULL,
  unit_no     INTEGER NOT NULL,
  title       TEXT NOT NULL,      -- 第一单元 识字
  kind        TEXT NOT NULL,      -- 识字 / 汉语拼音 / 阅读
  sort_order  INTEGER NOT NULL,
  FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE lessons (
  id          TEXT PRIMARY KEY,   -- 1a-u1-l1
  unit_id     TEXT NOT NULL,
  lesson_no   TEXT NOT NULL,      -- 1 / 园地一
  title       TEXT NOT NULL,      -- 天地人
  kind        TEXT NOT NULL,      -- 识字 / 拼音 / 阅读 / 语文园地
  sort_order  INTEGER NOT NULL,
  FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE TABLE curriculum_items (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  lesson_id           TEXT NOT NULL,
  char                TEXT NOT NULL,
  item_order          INTEGER NOT NULL,
  pinyin_override     TEXT,
  audio_key_override  TEXT,
  meaning_override    TEXT,
  words_override      TEXT,
  sentence_override   TEXT,
  mnemonic_override   TEXT,
  UNIQUE (lesson_id, char),
  FOREIGN KEY (lesson_id) REFERENCES lessons(id),
  FOREIGN KEY (char) REFERENCES characters(char)
);
```

说明：

- `characters` 继续存「字的内容」，一个字只有一条，作为默认内容。
- `curriculum_items` 存「字在教材里的位置」，同一个字可以在不同课出现。
- 多音字先用一组 `*_override` 字段做课内覆盖；覆盖为空时用 `characters` 的默认内容。以后需要完整多读音模型时再加 `char_readings` 表。
- `char_progress` 仍按 `char` 记进度。同一个字在不同课出现时共享进度，这是刻意的简化。

### 4.2 现有 40 字的归位

| 2024 位置 | 字 | 数量 |
|---|---|---:|
| 第一单元 识字1 天地人 | 天 地 人 你 我 他 | 6 |
| 第一单元 识字2 金木水火土 | 一 二 三 四 五 上 下 | 7 |
| 第一单元 识字3 口耳目手足 | 口 耳 目 手 足 站 坐 | 7 |
| 第一单元 识字4 日月山川 | 日 月 水 火 山 石 田 禾 | 8 |
| 第一单元 语文园地一 | 六 七 八 九 十 | 5 |
| 第六单元 识字5 对韵歌 | 对 云 雨 风 花 鸟 虫 | 7 |

第一单元合计 33 字，第六单元 7 字。

顺带修正课文名：`识字3 口耳目` → `识字3 口耳目手足`。

## 五、数据文件

拆成「内容」和「课程位置」两个来源，避免同一份 lesson 信息写两遍。

### 5.1 `data/characters.csv`

只存字的内容：

```
char,pinyin,radical,strokes,structure,origin,meaning,words,sentence,mnemonic,confusions,quiz_types,audio_key
```

现有 40 行做一次拆分迁移，旧文件备份为 `data/characters.legacy.csv`。

### 5.2 `data/curriculum/1a.csv`

一上课程位置：

```
book_id,unit_no,unit_title,unit_kind,lesson_no,lesson_title,lesson_kind,lesson_order,item_order,char,pinyin_override,audio_key_override,meaning_override,words_override,sentence_override,mnemonic_override
```

P0 先放现有 40 行；P1 补到 280 行。

`override` 列留空时用 `characters.csv` 的默认内容；多音字或课文语境不同时才填。

`1b.csv` 同理，P2 再建。

### 5.3 工具

- `tools/import_curriculum.py`：把 `data/curriculum/*.csv` 导入 `books/units/lessons/curriculum_items`。
- `tools/validate_content.py`：升级为 v2，检查内容和课程位置。
- `tools/fetch_pinyin_audio.py`：已有，扩字后继续用。

校验至少覆盖：

- 每个课程位置的字在 `characters.csv` 里存在。
- 同一课不重复字；课程顺序不重复。
- 拼音有声调；`audio_key` 能和拼音对应，或对应 mp3 存在。
- 组词包含目标字；例句包含目标字且只出现一次（可出填空）。
- 形近字是单字；题型在允许集合里。
- 课程总字数与预期一致（1a = 280）。

## 六、API

保持现有 API 兼容，新增课程层级字段：

- `GET /api/bootstrap`：返回 `books`（含 units / lessons 摘要）、`stats`、`queue`、`settings`。
- `GET /api/books`：书目。
- `GET /api/books/{book_id}`：某册的单元 / 课文摘要。
- `GET /api/lessons/{lesson_id}`：某课的字和进度。
- `GET /api/today`：队列项增加 `book_id`、`book_title`、`unit_id`、`unit_no`、`unit_title`、`lesson_id`、`lesson_title`、`reading_key`、`audio_key`。
- `POST /api/attempts`：可选带 `reading_key`，答题仍写 `attempts`。

同一个字有多个课程位置时，队列取「书 → 单元 → 课文 → 字」顺序最靠前的一条；复习和新字都按这个规则显示来源。

为控制 P0 复杂度，`bootstrap` 暂时继续返回带字的 lessons；280 字的 JSON 在本机可接受。690 字时再拆成分册接口。

## 七、前端

- 首页：册切换（一上/一下）→ 单元 → 课文卡片。
- 第一单元显示 33 字，第六单元显示 7 字。
- 字卡册：册 + 单元筛选，只渲染当前单元，不再一次铺 280/690 张卡。
- 学习页顶栏显示「一上 · 第一单元 · 天地人」。
- 出题干扰项不再从全库抽：
  - 单字题：形近字 + 同课字 + 已学字。
  - 组词题：同课词 + 已学字的词。
  - 避免 280 字后大量抽到没学过的字。

## 八、复习预算

当前 `MAX_REVIEWS_PER_SESSION = 8`，280 字学习高峰约 25 个到期/天，会积压。

P0 改为：

- 每次会话总预算 20 题（复习 + 新字）。
- 复习最多 15 个，新字最多 `new_per_day` 个，且不超过剩余预算。
- 到期字优先；没排进本次的继续留在队列，下次优先。
- 队列返回 `backlog` 数量，首页显示「还有 N 个到期」。
- 保留「再复习一组」入口，让家长/孩子有余力时清积压。

## 九、迁移与兼容

1. 新建表，不动 `char_progress` / `attempts` / `sessions`。
2. 从 `data/curriculum/1a.csv` 导入课程位置。
3. 现有 40 字按上表归位；`char_progress` 不动，学习进度不丢。
4. 旧 `characters.lesson_id/lesson/lesson_order` 先保留但不再作为数据源；新建字时用第一条课程位置回填，兼容现有的 `NOT NULL` 约束，后续再删。
5. 服务启动时幂等导入；CSV 改了重启即可更新。

## 十、验收

- [x] 现有 40 字进度不丢（迁移逻辑保留进度；测试流程走完已 `POST /api/reset` 恢复干净库）。
- [x] 首页第一单元显示 33 个位置（32 个有内容），第六单元《对韵歌》9 个位置（4 个有内容）。
- [x] 字卡册按册/单元筛选，单元分组正确（含内容字的花/云/地/鸟/石 所在单元自动启用）。
- [x] 学习会话显示课程来源，答题记录带 `reading_key`（可空，已出现在 attempts 和 CSV 导出）。
- [x] 今日队列总预算 20（复习最多 15），复习优先，返回 backlog（实测 30 个到期 → 15+5+15）。
- [x] 出题干扰项只来自形近字、同课字、已学字。
- [x] `tools/validate_content.py` 对 40 字 0 错误；对课程位置能报告缺内容，不崩溃。
- [x] 现有 4 种题型、音频、弹窗、家长页无回归（浏览器实测完整学习流程）。
- [x] 283 + 419 行课程位置可导入，首页能显示两册 8+8 个单元的骨架（内容可后补）。

## 十一、实施顺序

1. **P0.1**：schema + 数据文件拆分 + 迁移脚本；用 40 字跑通。
2. **P0.2**：API 课程层级 + 队列 metadata；测试。
3. **P0.3**：首页/字卡册/学习页导航；测试 33 + 7。
4. **P0.4**：校验 v2 + 280 课程位置导入（内容 P1 补）。
5. **P0.5**：复习预算 + 干扰项约束。
6. **P0.6**：回归测试 + README/TODO 更新。

## 十二、风险

- **2024 字表来源**：目前按公开 2024 目录核对，完整 280 字表仍需从教材 PDF/权威资料整理，并由家长核对。
- **多音字**：P0 只做课内覆盖，不做完整多读音模型；遇到一字多音时先保证当前课文读音正确。
- **进度归属**：同一个字跨课出现时共享进度；如果以后要按读音分开统计，再加 `char_readings` 和 `reading_key` 进度。
- **API 体积**：280 字 bootstrap 仍可接受；690 字前再拆接口，不在 P0 过度设计。
