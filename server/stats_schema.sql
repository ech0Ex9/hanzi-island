-- 汉字小岛 · 统计库 schema（data/stats.db）
-- 只存学习记录、进度、设置；字与课程在 data/content.db。
-- 注意：char_progress / attempts 不再对 characters 建外键（跨库外键不可用），
-- 字是否存在由内容库保证。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT PRIMARY KEY,
  started_at  TEXT NOT NULL,
  ended_at    TEXT,
  completed   INTEGER NOT NULL DEFAULT 0,
  app_version TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id     TEXT,
  ts             TEXT NOT NULL,
  local_date     TEXT NOT NULL,
  char           TEXT NOT NULL,
  question_type  TEXT NOT NULL,
  selected       TEXT,
  correct_answer TEXT,
  is_correct     INTEGER NOT NULL,
  response_ms    INTEGER,
  reading_key    TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_char_ts
  ON attempts(char, ts);
CREATE INDEX IF NOT EXISTS idx_attempts_local_date
  ON attempts(local_date);
CREATE INDEX IF NOT EXISTS idx_attempts_session
  ON attempts(session_id, ts);

CREATE TABLE IF NOT EXISTS char_progress (
  char          TEXT PRIMARY KEY,
  box           INTEGER NOT NULL DEFAULT 0,
  due_at        TEXT,
  exposures     INTEGER NOT NULL DEFAULT 0,
  attempts      INTEGER NOT NULL DEFAULT 0,
  correct       INTEGER NOT NULL DEFAULT 0,
  wrong         INTEGER NOT NULL DEFAULT 0,
  streak        INTEGER NOT NULL DEFAULT 0,
  mastery       TEXT NOT NULL DEFAULT 'new',
  first_seen_at TEXT,
  last_seen_at  TEXT,
  updated_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_progress_due
  ON char_progress(due_at);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- 完整操作流水（发音播放、拼音开关、提示、页面停留等），当前预留。
CREATE TABLE IF NOT EXISTS events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  client_event_id TEXT UNIQUE,
  session_id      TEXT,
  ts              TEXT NOT NULL,
  local_date      TEXT NOT NULL,
  type            TEXT NOT NULL,
  char            TEXT,
  payload_json    TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_events_session_ts
  ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts
  ON events(type, ts);

-- 艾宾浩斯认字：整体过一遍 + 每日复习。和 char_progress 的 Leitner 盒子相互独立。
CREATE TABLE IF NOT EXISTS recognition_runs (
  id         TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at   TEXT,
  scope      TEXT NOT NULL DEFAULT 'all', -- all / 1a / 1b / unit:xxx
  total      INTEGER NOT NULL DEFAULT 0,
  known      INTEGER NOT NULL DEFAULT 0,
  unknown    INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'active' -- active / finished
);

CREATE INDEX IF NOT EXISTS idx_recognition_runs_status
  ON recognition_runs(status, started_at);

CREATE TABLE IF NOT EXISTS recognition_items (
  char               TEXT PRIMARY KEY,
  run_id             TEXT,
  self_report        TEXT NOT NULL,          -- known / unknown
  reported_at        TEXT NOT NULL,
  stage              INTEGER NOT NULL DEFAULT 0, -- R0..R7
  due_at             TEXT NOT NULL,
  attempts           INTEGER NOT NULL DEFAULT 0,
  correct            INTEGER NOT NULL DEFAULT 0,
  wrong              INTEGER NOT NULL DEFAULT 0,
  streak             INTEGER NOT NULL DEFAULT 0,
  first_quiz_at      TEXT,
  first_quiz_correct INTEGER,
  last_result        INTEGER,
  last_seen_at       TEXT,
  updated_at         TEXT,
  FOREIGN KEY (run_id) REFERENCES recognition_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_recognition_items_due
  ON recognition_items(due_at);
CREATE INDEX IF NOT EXISTS idx_recognition_items_run
  ON recognition_items(run_id);

CREATE TABLE IF NOT EXISTS recognition_attempts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  char         TEXT NOT NULL,
  ts           TEXT NOT NULL,
  local_date   TEXT NOT NULL,
  result       INTEGER NOT NULL,             -- 1 对 / 0 错
  stage_before INTEGER,
  stage_after  INTEGER,
  response_ms  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_recognition_attempts_char_ts
  ON recognition_attempts(char, ts);
CREATE INDEX IF NOT EXISTS idx_recognition_attempts_date
  ON recognition_attempts(local_date);

-- 小岛成就：只记录第一次解锁，进度实时从学习记录推导。
CREATE TABLE IF NOT EXISTS badge_unlocks (
  badge_id    TEXT PRIMARY KEY,
  unlocked_at TEXT NOT NULL,
  local_date  TEXT NOT NULL,
  seen        INTEGER NOT NULL DEFAULT 0,
  meta_json   TEXT NOT NULL DEFAULT '{}'
);

-- 诗岛：读完一首诗记一条流水；同一首可以重复读。
CREATE TABLE IF NOT EXISTS poem_reads (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  poem_id    TEXT NOT NULL,
  ts         TEXT NOT NULL,
  local_date TEXT NOT NULL,
  mode       TEXT NOT NULL DEFAULT 'read',
  completed  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_poem_reads_poem
  ON poem_reads(poem_id, ts);
CREATE INDEX IF NOT EXISTS idx_poem_reads_date
  ON poem_reads(local_date);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (3, datetime('now'));

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (4, datetime('now'));

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (5, datetime('now'));

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (6, datetime('now'));
