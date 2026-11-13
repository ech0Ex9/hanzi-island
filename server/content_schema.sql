-- 汉字小岛 · 内容库 schema（data/content.db）
-- 只存字、课程结构；学习记录/统计在 data/stats.db。
-- v2：书 → 单元 → 课文 → 字位置；characters 存「字的内容」。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
  char              TEXT PRIMARY KEY,
  pinyin            TEXT NOT NULL,
  lesson_id         TEXT NOT NULL,
  lesson            TEXT NOT NULL,
  lesson_order      INTEGER NOT NULL,
  radical           TEXT,
  strokes           INTEGER,
  structure         TEXT,
  origin            TEXT,
  meaning           TEXT,
  words_json        TEXT NOT NULL DEFAULT '[]',
  sentence          TEXT,
  mnemonic          TEXT,
  confusions_json   TEXT NOT NULL DEFAULT '[]',
  quiz_types_json   TEXT NOT NULL DEFAULT '[]',
  audio_key         TEXT
);

-- 拓展识字表：幼儿识字 1300 的顺序和成员。字内容仍在 characters 里；
-- 这个表只决定「幼儿识字 1300」范围的顺序，不影响课内 688 字的课程结构。
CREATE TABLE IF NOT EXISTS literacy_entries (
  char        TEXT PRIMARY KEY,
  sort_order  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_literacy_entries_order
  ON literacy_entries(sort_order);

-- 说明：curriculum_items.char 不设指向 characters 的外键——课程位置允许先于
-- 字内容导入，查询时按需 JOIN characters。
CREATE TABLE IF NOT EXISTS books (
  id          TEXT PRIMARY KEY,   -- 1a / 1b
  title       TEXT NOT NULL,      -- 一年级上册
  edition     TEXT NOT NULL,      -- 2024 统编版
  sort_order  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS units (
  id          TEXT PRIMARY KEY,   -- 1a-u1
  book_id     TEXT NOT NULL,
  unit_no     INTEGER NOT NULL,
  title       TEXT NOT NULL,      -- 第一单元
  kind        TEXT NOT NULL,      -- 识字 / 拼音 / 阅读
  sort_order  INTEGER NOT NULL,
  FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE INDEX IF NOT EXISTS idx_units_book ON units(book_id, sort_order);

CREATE TABLE IF NOT EXISTS lessons (
  id          TEXT PRIMARY KEY,   -- 1a-u1-l1
  unit_id     TEXT NOT NULL,
  lesson_no   TEXT NOT NULL,      -- 1 / 园地一
  title       TEXT NOT NULL,      -- 天地人
  kind        TEXT NOT NULL,      -- 识字课 / 拼音课 / 阅读课 / 语文园地
  sort_order  INTEGER NOT NULL,
  FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE INDEX IF NOT EXISTS idx_lessons_unit ON lessons(unit_id, sort_order);

CREATE TABLE IF NOT EXISTS curriculum_items (
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
  FOREIGN KEY (lesson_id) REFERENCES lessons(id)
);

CREATE INDEX IF NOT EXISTS idx_items_lesson ON curriculum_items(lesson_id, item_order);
CREATE INDEX IF NOT EXISTS idx_items_char ON curriculum_items(char);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (1, datetime('now'));
