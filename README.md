# 汉字小岛

给一年级小朋友认汉字用的本地小应用。**只做认读，不做描红、笔顺和书写**，学习记录全部留在本机。

> 家长第一次使用，请先看 [家长使用手册](web/manual.html)。应用运行后也可以打开 `http://127.0.0.1:8765/manual.html`，或在今日页点「家长看板 → 打开家长使用手册」。

## 一眼看懂

- **课内 688 字**：2024 统编版一年级上册 279 字 + 2025 统编版一年级下册 413 字（两册共 692 个字次，去重后 688 个不同字），覆盖 702 个课程位置、16 个单元。
- **幼儿识字 1300**：课内 664 字 + 拓展 636 字，作为认字模块的独立范围。
- **完整学习路径**：学新字 → 3 种题型 → 间隔复习 → 艾宾浩斯认字 → 字卡册 → 读一读（30 篇短文 + 10 首古诗）。
- **家长可用**：17 枚成长印章、家长看板、易错字、打印清单、学习记录和字库备份。
- **适合孩子**：全程键盘可操作，也能用鼠标；12 分钟护眼提醒、减少动效、手机/平板触控尺寸。
- **本地离线**：macOS 双击 `start.command` 启动，第一次装好依赖后断网也能用。

## 安装与启动

仓库：<https://github.com/ech0Ex9/hanzi-island>。朋友使用时点 **Code → Download ZIP**，解压到「下载」或桌面。

### macOS（一键）

1. 确认有 Python 3.9 或更新版本：打开「终端」，输入 `python3 --version`。
   - 没有的话，到 <https://www.python.org/downloads/macos/> 下载安装包；
   - 或者在终端运行 `xcode-select --install` 安装命令行工具。
2. 双击 `start.command`。第一次打开如果 macOS 提示「无法验证开发者」，右键 `start.command` → **打开**。
3. 第一次运行会自动创建 `.venv` 并联网安装依赖；看到浏览器打开 `http://127.0.0.1:8765` 就好了。之后断网也能用。

停止时双击 `stop.command`。它只停止本项目记录的那个进程，不会误杀别的 Python 程序。启动脚本会检查是否已经有实例在运行；8765 端口被占用时自动换到 8766–8775，健康检查通过后再打开浏览器。

朋友的进度和你的完全分开：`data/stats.db` 不在仓库里，第一次运行会自动新建一份空的学习记录。

### Windows（手动）

先安装 Python 3.9 或更新版本，然后在项目目录打开 PowerShell：

```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py --port 8765
```

再打开浏览器访问 `http://127.0.0.1:8765`。关闭时在 PowerShell 里按 `Ctrl+C`。

## 现在能做什么

- **今日任务**：先复习到期字，再学新字（数量可在家长页调整）；每次会话总预算 20 题（复习最多 15 个）。没排进本次的到期字会显示「还有 N 个到期」，下次优先。
- **学新字**：大字、拼音、部首/笔画/结构、意思、组词、例句、记忆口诀、形近字。新字卡自动连读：字音（拼音音节 mp3）→ 组词1 → 组词2；词语和句子用系统语音。学习页顶栏显示课程来源（如「一年级上册 · 第一单元 · 天地人」）。
- **3 种题型**：听音选字、句子填空、看拼音选字；干扰项只从形近字、同课字、已学字里抽，不从全库抽。
- **全流程键盘操作**：答题方向键移动选项高亮 + 回车确认；答完回车 = 下一个；学字卡回车 = 开始认字；结算页回车 = 再学一组；弹窗回车 / Esc 关闭。
- **间隔复习**：Leitner 盒子 0–5，按 1 / 3 / 7 / 15 / 60 天安排；答错降一级。
- **认字（艾宾浩斯）**：底部第 4 个 tab。先整体过一遍「幼儿识字 1300」（课内 664 + 拓展 636），也可以只过课内 688 / 上册 279 / 下册 413；孩子自评「认识 / 不认识」；之后按 1 / 2 / 4 / 7 / 15 / 30 / 60 天复习，用答题结果验证自评。自评「认识」但第一次答错会标成「高估」。和今日任务分开排队，每组最多复习 15 个字。
- **过字与改自评**：按 ↑ 回看上一个字重新标记，↓ 往后、End 回到最新；回看时未标记黑色、认识绿色、不认识红色；鼠标左键点字卡或页面空白处 = 认识，右键 = 不认识。自评标错了可以在「改自评」页搜索汉字 / 拼音 / 组词后改回来；自评「不认识」的字可以生成 A4 打印清单，带拼音和组词。
- **读一读**：30 篇短文/儿歌覆盖 16 个单元（上册 17 篇、下册 13 篇）；顶部可按册筛选；点字听读音、点 ▶ 听整句、拼音可开关（灰色字表示还没学过）；多音字按句子语境标注读音（如「站得直」读 de、「数一数」读 shǔ）。
- **诗岛（古诗 10 首）**：读一读里的「古诗」页，收录咏鹅、江南、悯农、静夜思、春晓、池上、小池、画鸡、梅花、村居；点字听读音、点句听整句、拼音开关、一句意思和小知识。诗句默认用系统语音，个别句子可在 `poems.csv` 的 `line_audio` 指定拼音音频（咏鹅第一句「鹅，鹅，鹅」就是三遍 `e2.mp3`）。读完点「读完了」，记录阅读次数，并解锁「第一首诗 / 诗岛小旅行」成就。
- **字卡册与导航**：首页按册（一上 / 一下 / 全部）→ 单元 → 课文展示闯关地图；全部 702 个位置都有内容。字卡册可按册 + 单元筛选，顶部「按部首认字」可以直接选部首看同部首字；点字听读音、看组词（词块可点击发音）和句子；可展开「精选字族」「多音字」面板，支持打印这一页。
- **小岛成就**：17 枚成长印章（15 枚学习 + 2 枚诗歌），奖励完成、坚持、勇气、探索和读诗，不奖励正确率、不扣分、不排名。今日页有成就卡，结算页解锁新印章会弹出提示，家长页可以看完整成就墙并一键关闭孩子端展示。数据从真实学习记录推导，不做积分商城。
- **护眼与无障碍**：连续学习 12 分钟弹出 20 秒远眺提醒；「减少动效」开关 + 系统 `prefers-reduced-motion`；正文对比度 ≥ 4.5:1；手机/平板按钮 ≥ 56px、适配安全区。
- **家长看板**：入口在今日页（不在底部导航，避免孩子误触）；学过多少、掌握多少、今日正确率、连续天数、易错字、艾宾浩斯自评 vs 实测、最近 7 天柱状图与学习建议、部首徽章、小岛成就、每日新字设置、「自动播放读音」开关、导出答题 CSV、备份 SQLite。

## 数据在哪

| 数据 | 位置 | 说明 |
|---|---|---|
| 学习记录 | `data/stats.db` | SQLite，WAL 模式；进度、答题、认字、成就、设置、读诗记录 |
| 字库 | `data/content.db` | 启动时由 CSV 导入，可删除重建 |
| 课内字 | `data/characters.csv` | 688 个不同字的内容 |
| 幼儿识字 | `data/literacy_1300.csv` | 1300 行：课内 664 + 拓展 636 |
| 课程位置 | `data/curriculum/1a.csv`、`1b.csv` | 一上 283 个位置、一下 419 个位置 |
| 短文/儿歌 | `data/readings.csv` | 30 篇；`pronunciations` 列标注句子里的多音字 |
| 古诗 | `data/poems.csv` | 10 首；`speech` 列修正朗读文本，`line_audio` 列指定逐句朗读方式 |
| 字族 | `data/families.csv` | 23 组精选；同部首字族由前端按 688 字自动归类 |
| 多音字补充 | `data/polyphonic.csv` | 30 个常见字 |
| 原始录入存档 | `data/sources/` | 识字表来源 |
| 字体 | `web/assets/fonts/lxgw-wenkai-subset.woff2` | 霞鹜文楷子集，OFL，见同目录 `OFL.txt` |
| 日志 / 运行状态 | `logs/server.log`、`.run/` | 启动脚本使用 |

所有数据只在本机，不上传网络。家长页可以分别下载「学习记录」和「字库」的备份；`data/stats.db` 不进入仓库。

## 已知边界

- 2024 版与旧版字表位置不同：《对韵歌》2024 为 9 字；云 / 花 / 鸟 / 石 分属拼音13 / 拼音5 / 阅读4 / 阅读9；以 `data/curriculum/1a.csv` 为准。
- 1a 有 5 个差异字（旁、旦、元、星、期）待对照课本核实，见 `data/curriculum/README.md`。
- 「幼儿识字 1300」里 636 个拓展字的拼音、部首、笔画、释义和组词是简编数据，多音字只取常用读音；不进入课内今日任务，也不改变课内 688 字的统计，建议家长对照孩子实际用字核对。
- 单字优先播放拼音音节 mp3；词语和句子使用系统 Web Speech API，不同 Mac 的音色可能不同。上游缺 `xiu1` / `xiang2`，修、休、详、翔 4 个字用系统语音兜底。
- 古诗逐句可以指定 mp3；「读整首」仍把整首交给系统语音，不会逐句切换音频。
- 象形字只做了 10 个（日 / 月 / 山 / 水 / 火 / 木 / 田 / 人 / 口 / 目）的字形演变，其余字没有插图。
- 有答题记录和复习进度，但还没有完整操作流水（发音播放、拼音开关、提示、页面停留等）；`events` 表已预留。
- 没有移动端真机测试；目前按响应式 CSS 设计。
- 单机单用户，没有多孩档案；还没有打包成 `.app`，仍通过 `start.command` + 浏览器运行。

## 开发

```bash
cd hanzi-island
python3 app.py --port 8765
```

打开 `http://127.0.0.1:8765`。改前端不用重启；改 Python 需要 `./stop.command && ./start.command`。清空测试数据用家长页「清空进度」或 `POST /api/reset`；看数据库用 `sqlite3 data/stats.db`（学习记录）或 `sqlite3 data/content.db`（字与课程），也可以用 DB Browser for SQLite；日志在 `logs/server.log`。

前端分两层：`web/js/app.js` 管路由、状态和事件；`web/js/components.js` 放不依赖状态的展示组件（字卡头、内容块、小节标题、面板、按钮等），学习页 / 字卡册 / 弹窗 / 家长页共用。

常用工具：

```bash
python3 tools/import_curriculum.py --dry   # 检查课程 CSV
python3 tools/import_curriculum.py         # 手动导入课程位置
python3 tools/validate_content.py          # 校验内容与课程位置
python3 tools/validate_readings.py         # 校验短文用字与篇幅
python3 tools/validate_families.py         # 校验字族用字
python3 tools/validate_polyphonic.py       # 校验多音字补充与音频
python3 tools/validate_recognition.py      # 校验艾宾浩斯认字范围与排程
python3 tools/validate_literacy.py         # 校验幼儿识字 1300 与数据库落库
python3 tools/validate_poems.py            # 校验古诗拼音、朗读文本、朗读方式与音频
```

目录：

```
hanzi-island/
├── app.py                 FastAPI 入口
├── start.command          双击启动
├── stop.command           双击停止
├── requirements.txt
├── server/                路由、数据库、Leitner 复习、艾宾浩斯认字、古诗、成就
├── data/                  字表 / 短文 / 古诗 / 课程 CSV；运行时 SQLite
├── web/                   页面、样式、脚本、家长手册、拼音音频、字体
├── tools/                 内容导入与校验脚本
├── docs/                  内容规划、数据库与 API、专题设计
├── TODO.md
└── logs/
```

## API 速览

```
GET  /api/health
GET  /api/bootstrap        设置 + 统计 + 书目 + 课文 + 短文 + 古诗 + 字族 + 今日队列 + 成就
GET  /api/today            今日队列（含 backlog / 课程来源 / reading_key）
GET  /api/characters       全部字 + 进度
GET  /api/characters/{字}
GET  /api/books            书目（册 → 单元 → 课文摘要）
GET  /api/books/{book_id}  某一册
GET  /api/lessons
GET  /api/lessons/{lesson_id}  某一课的字和进度
GET  /api/poems            诗岛列表 + 阅读进度
GET  /api/poems/{id}       一首古诗
POST /api/poems/{id}/read  记录读完一首诗
POST /api/sessions         开始一次学习
PATCH /api/sessions/{id}   结束（body `{completed}` 标记是否走到结算页）
POST /api/attempts         提交答题（支持批量，可带 reading_key）
GET  /api/progress
GET  /api/stats/summary    家长看板
GET  /api/parent/weekly    最近 7 天周报
GET  /api/achievements     成就墙（含进度、已解锁、未读）
POST /api/achievements/seen  标记成就已展示
GET  /api/polyphonic       多音字（教材标注 + 常见补充）
GET  /api/recognition/summary   艾宾浩斯认字总览
POST /api/recognition/runs      开始/继续整体过一遍
GET  /api/recognition/runs/{id}/items/{index}  按序号取本轮的字（回看用）
POST /api/recognition/runs/{id}/reports  记录「认识 / 不认识」
GET  /api/recognition/items     搜索已自评的字（改自评用）
PATCH /api/recognition/items/{char}  修改单个字的自评
GET  /api/recognition/today     今日认字复习队列
GET  /api/recognition/print     不会的字打印清单
POST /api/recognition/attempts  提交认字复习答题
GET  /api/settings
POST /api/settings
POST /api/reset
GET  /api/export/attempts.csv
GET  /api/backup           下载学习记录备份（同 /api/backup/stats）
GET  /api/backup/content   下载字库备份
```

## 音频来源

单字拼音音节使用开源仓库 [mp3-chinese-pinyin-sound](https://github.com/davinfifield/mp3-chinese-pinyin-sound)，许可证为 **Unlicense（public domain）**。音频在 `web/assets/audio/pinyin/`，文件名对应字表里的 `audio_key`（例如 `ri4.mp3`）。脚本会同时读取 `characters.csv`、`literacy_1300.csv` 和 `poems.csv`，没有 `audio_key` 时按拼音推导，扩字或加诗后运行：

```bash
python3 tools/fetch_pinyin_audio.py
```

上游音频库本身缺 `xiu1`（修 / 休）和 `xiang2`（详 / 翔）两个音节，这 4 个字会自动退回系统语音；其余 1320 个字都有音节 mp3。

词语和句子使用系统 Web Speech API。古诗逐句默认也走系统语音，`poems.csv` 的 `line_audio` 可以按句改成拼音音频。

## 许可证

- 项目代码和原创内容：**MIT**，见根目录 [`LICENSE`](LICENSE)。可以自由使用、修改、分发和商用。
- 字体 `web/assets/fonts/lxgw-wenkai-subset.woff2`：霞鹜文楷，**SIL Open Font License 1.1**，见同目录 `OFL.txt`，不适用 MIT。
- 拼音音频：788 个文件来自 [mp3-chinese-pinyin-sound](https://github.com/davinfifield/mp3-chinese-pinyin-sound)，为 **Unlicense（public domain）**；8 个轻声补录文件（me5、men5、zhe5、a5、ba5、la5、na5、ya5）来自百度汉语 CDN，仅建议个人/家用，不在 MIT 范围内。商业发行请自行替换这 8 个文件。

## 内容依据

- 《义务教育语文课程标准（2022 年版）》：1–2 年级认识 1600 字左右，会写 800 字左右。
- 2024 统编版一年级上册识字表 280 字（按课文列 283 字次 / 279 个不同字）。
- 2025 统编版一年级下册识字表 410 字（419 字次 / 413 个不同字）。
- 「幼儿识字 1300」：课内 664 字 + 拓展 636 字。

具体规划见 `docs/outline.md`、`docs/poetry-design.md` 和 `TODO.md`。
