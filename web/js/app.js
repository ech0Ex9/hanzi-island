import { api } from "./api.js?v=4";
import * as audio from "./audio.js?v=3";
import {
  esc,
  highlightChar,
  masteryLabel,
  infoBlock,
  charChip,
  polyReadingButton,
  sectionHead,
  panel,
  linkButton,
  charIdentityHtml,
  charInfoBlocksHtml,
} from "./components.js?v=2";

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");

const state = {
  boot: null,
  loading: true,
  error: null,
  route: "home",
  session: null,
  quiz: null,
  modal: null,
  parent: null,
  parentLoading: false,
  bootDirty: false,
  starting: false,
  rest: null,
  readingId: null,
  recognitionRun: null,
  recognitionSubmitting: false,
  recognitionPrint: null,
  recognitionPrintLoading: false,
  recognitionPrintError: null,
  recognitionEdit: null,
  recognitionEditLoading: false,
  recognitionEditError: null,
  recognitionEditQuery: "",
  printIncludeOver: true,
  printShowPinyin: true,
  printShowWords: true,
  polyphonic: null,
  polyLoading: false,
  ui: {
    homeBookId: "1a",
    cardBookId: "1a",
    cardUnitId: null,
    readBookId: "all",
    readPinyin: true,
    familyRadical: null,
  },
};

const UI_KEY = "hanzi-ui";
let recognitionEditToken = 0;
let recognitionEditSearchTimer = null;

function loadUi() {
  try {
    return JSON.parse(localStorage.getItem(UI_KEY)) || {};
  } catch (_) {
    return {};
  }
}

function saveUi() {
  try {
    localStorage.setItem(
      UI_KEY,
      JSON.stringify({
        homeBookId: state.ui.homeBookId,
        cardBookId: state.ui.cardBookId,
        cardUnitId: state.ui.cardUnitId,
        readBookId: state.ui.readBookId,
        readPinyin: state.ui.readPinyin,
        familyRadical: state.ui.familyRadical,
      }),
    );
  } catch (_) {
    /* 隐私模式等存不了就算了 */
  }
}

/* ---------------- 工具 ---------------- */

function shuffle(items) {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

function toast(message) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.remove("show"), 2200);
}

let charsCache = { boot: null, list: [] };
let charIndexCache = { boot: null, map: new Map() };

/* boot.lessons 里有 702 个课程位置；缓存一份，避免字卡册每渲染一个 chip 都重新 flatMap。 */
function allChars() {
  if (charsCache.boot !== state.boot) {
    charsCache = {
      boot: state.boot,
      list: (state.boot?.lessons || []).flatMap((lesson) => lesson.chars || []),
    };
  }
  return charsCache.list;
}

/* 家长页「减少动效」：手动开启时给 html 加类，CSS 里统一关掉动画。 */
function applyReduceMotion() {
  document.documentElement.classList.toggle(
    "reduce-motion",
    state.boot?.settings?.reduce_motion === true,
  );
}

/* ---------------- 课程结构辅助 ---------------- */

function books() {
  return state.boot?.books || [];
}

function bookById(id) {
  return books().find((book) => book.id === id) || null;
}

function currentBook(forCards = false) {
  const wanted = forCards ? state.ui.cardBookId : state.ui.homeBookId;
  const all = books();
  return bookById(wanted) || all[0] || null;
}

function unitHasContent(unit) {
  return (unit.lessons || []).some(
    (lesson) => (lesson.content_chars ?? (lesson.chars || []).length) > 0,
  );
}

/* 一册里出现过的不同汉字（按字去重，同一字可能占多个课文位置）。 */
function bookChars(book) {
  const seen = new Set();
  for (const lesson of state.boot?.lessons || []) {
    if (book && lesson.book_id !== book.id) continue;
    for (const item of lesson.chars || []) seen.add(item.char);
  }
  return seen;
}

function learnedCount(chars) {
  return [...chars].filter((char) => findChar(char)?.progress?.first_seen_at).length;
}

/* boot.lessons 里有每个字的详情；books 结构里的课文只有计数，按 id 找详情。 */
function lessonDetail(lessonId) {
  return (state.boot?.lessons || []).find((lesson) => lesson.id === lessonId) || null;
}

function sameLessonChars(item) {
  return allChars().filter((c) => c.lesson_id && c.lesson_id === item.lesson_id);
}

function learnedChars() {
  return allChars().filter((c) => c.progress?.first_seen_at);
}

function findChar(char) {
  if (charIndexCache.boot !== state.boot) {
    charIndexCache = { boot: state.boot, map: new Map() };
    for (const item of allChars()) {
      if (!charIndexCache.map.has(item.char)) charIndexCache.map.set(item.char, item);
    }
  }
  return charIndexCache.map.get(char) || null;
}

function currentItem() {
  return state.session?.items?.[state.session.index] || null;
}

/* 字族：和当前字同一部件/声旁的字，点一下可以接着看。 */
function charFamilyHtml(char) {
  const family = (state.boot?.families || []).find((entry) => (entry.members || []).includes(char));
  if (!family) return "";
  const others = family.members.filter((item) => item !== char && findChar(item));
  if (!others.length) return "";
  return infoBlock(
    "字族",
    `<div class="word-chips">
        <span class="family-key inline">${esc(family.family)}</span>
        ${others.map((item) => charChip(item)).join("")}
      </div>`,
  );
}

/* 同部首：从全库字里自动归类，每个字都能看到自己的一组。 */
function charRadicalFamilyHtml(char) {
  const item = findChar(char);
  const radical = (item?.radical || "").trim();
  if (!radical) return "";
  const group = radicalGroups().find((entry) => entry.radical === radical);
  if (!group || group.count < 2) return "";
  const others = group.members.filter((member) => member !== char);
  if (!others.length) return "";
  const shown = others.slice(0, 8);
  return infoBlock(
    `同部首 · ${radical}`,
    `<div class="word-chips">
        ${shown.map((member) => charChip(member)).join("")}
        ${others.length > shown.length ? `<span class="more-hint">还有 ${others.length - shown.length} 个</span>` : ""}
      </div>`,
  );
}

/* 多音字：显示这个字在课文里的不同读法。 */
function charPolyHtml(char) {
  const item = (state.polyphonic || []).find((entry) => entry.char === char);
  if (!item) return "";
  return infoBlock(
    "多音字",
    `<div class="poly-readings">${(item.readings || [])
      .map((reading) => polyReadingButton(char, reading))
      .join("")}</div>`,
  );
}

function routeFromHash() {
  const raw = location.hash.replace(/^#\/?/, "").split("?")[0];
  return raw || "home";
}

function navigate(route) {
  if (route === "parent") state.parent = null;
  if (route === "recognition-print") {
    state.recognitionPrint = null;
    state.recognitionPrintError = null;
  }
  if (route === "recognition-edit") {
    state.recognitionEdit = null;
    state.recognitionEditError = null;
    state.recognitionEditQuery = "";
  }
  if (route !== "read") state.readingId = null;
  stopLineSpeech();
  audio.stop();
  const hash = `#/${route}`;
  if (location.hash === hash) {
    state.route = route;
    render();
  } else {
    location.hash = hash;
  }
}

/* ---------------- 骨架 ---------------- */

function topbar() {
  const soundOn = state.boot?.settings?.sound !== false;
  return `
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark"></div>
        <div class="brand-text">
          <b>汉字小岛</b>
          <span>每天认几个字</span>
        </div>
      </div>
      <div class="top-actions">
        <button class="icon-btn" data-action="toggle-sound" title="${soundOn ? "关闭声音" : "打开声音"}" aria-label="${soundOn ? "关闭声音" : "打开声音"}">
          ${soundOn ? "声" : "静"}
        </button>
      </div>
    </header>
  `;
}

function bottomNav(active = "home") {
  // 家长看板不放在底部，避免孩子误触；入口放在今日页的安静链接里。
  const items = [
    ["home", "今", "今日"],
    ["cards", "册", "字卡册"],
    ["read", "读", "读一读"],
    ["recognition", "认", "认字"],
  ];
  return `
    <nav class="bottom-nav" aria-label="主导航">
      ${items
        .map(
          ([route, icon, label]) => `
        <button class="nav-btn ${active === route ? "active" : ""}" data-nav="${route}">
          <span class="nav-icon">${icon}</span>
          <span>${label}</span>
        </button>
      `,
        )
        .join("")}
    </nav>
  `;
}

function shell(content, active = "home", showNav = true) {
  return `${topbar()}<main>${content}</main>${showNav ? bottomNav(active) : ""}`;
}

function loadingScreen(message = "正在打开小岛…") {
  return `<div class="loading"><div class="dot"></div><div>${esc(message)}</div></div>`;
}

function errorScreen(message) {
  return `
    <div class="empty">
      <div class="big">🌧</div>
      <h3>小岛暂时打不开</h3>
      <p>${esc(message)}</p>
      <p style="margin-top:16px"><button class="primary-btn small" data-action="retry">再试一次</button></p>
    </div>
  `;
}

/* ---------------- 首页 ---------------- */

function recognitionCardHtml() {
  const rec = state.boot?.recognition;
  if (!rec) return "";
  const active = rec.active_run;
  const due = Number(rec.due || 0);
  const reported = Number(rec.reported || 0);

  if (active) {
    return `
      <section class="recognition-card active-run">
        <div class="recognition-card-head">
          <div>
            <span class="eyebrow">艾宾浩斯认字</span>
            <h2>正在整体过一遍</h2>
            <p>已经过 ${active.reported} / ${active.total} 个字：认识 ${active.known}，不认识 ${active.unknown}。可以分几次完成，进度会自动保存。</p>
          </div>
          <span class="recognition-ring"><b>${active.percent}%</b><i>已过</i></span>
        </div>
        <div class="queue-pills">
          <span class="queue-pill">认识 <b>${active.known}</b></span>
          <span class="queue-pill">不认识 <b>${active.unknown}</b></span>
          ${due ? `<span class="queue-pill warn">今天到期 <b>${due}</b></span>` : ""}
          ${rec.today_attempts ? `<span class="queue-pill">今天已复习 <b>${rec.today_attempts}</b> · 正确率 <b>${rec.today_accuracy}%</b></span>` : ""}
        </div>
        <div class="recognition-actions">
          <button class="primary-btn small" data-action="continue-recognition">继续过一遍</button>
          ${due ? `<button class="ghost-btn small" data-action="start-recognition-review">先复习 ${recognitionGroupSize(due)} 个字</button>` : ""}
          ${
            Number(rec.self_unknown || 0) + Number(rec.overconfident || 0) > 0
              ? `<button class="ghost-btn small" data-action="open-recognition-print">打印不会的字</button>`
              : ""
          }
        </div>
      </section>
    `;
  }

  if (!reported) {
    return `
      <section class="recognition-card">
        <div class="recognition-card-head">
          <div>
            <span class="eyebrow">艾宾浩斯认字</span>
            <h2>先过一遍，看看认识多少</h2>
            <p>${rec.total} 个字逐个出现，认识的点「认识」，不认识的点「不认识」。不显示拼音，不用一次做完。</p>
          </div>
        </div>
        <div class="recognition-actions">
          <button class="primary-btn small" data-action="open-recognition">开始过一遍</button>
        </div>
      </section>
    `;
  }

  return `
    <section class="recognition-card">
      <div class="recognition-card-head">
        <div>
          <span class="eyebrow">艾宾浩斯认字</span>
          <h2>${due ? `今天有 ${due} 个字要复习` : "今天没有到期复习"}</h2>
          <p>${
            due
              ? "按记忆曲线复习：自评不认识的字先看一眼字卡，再答题验证。"
              : `已经自评 ${reported} 个字，认识 ${rec.self_known}，不认识 ${rec.self_unknown}。`
          }</p>
        </div>
        <span class="recognition-ring"><b>${rec.mastered || 0}</b><i>掌握</i></span>
      </div>
      <div class="queue-pills">
        <span class="queue-pill">已自评 <b>${reported}</b></span>
        <span class="queue-pill">自评认识 <b>${rec.self_known}</b></span>
        <span class="queue-pill">待复习 <b>${due}</b></span>
        ${rec.today_attempts ? `<span class="queue-pill">今天已复习 <b>${rec.today_attempts}</b> · 正确率 <b>${rec.today_accuracy}%</b></span>` : ""}
        ${due > recognitionGroupSize(due) ? `<span class="queue-pill warn">本组最多 ${recognitionGroupSize(due)} 个，还有 ${due - recognitionGroupSize(due)} 个下次</span>` : ""}
      </div>
      <div class="recognition-actions">
        ${
          due
            ? `<button class="primary-btn small" data-action="start-recognition-review">开始复习 ${recognitionGroupSize(due)} 个字</button>`
            : `<button class="ghost-btn small" data-action="open-recognition">看认字报告</button>`
        }
        ${
          Number(rec.self_unknown || 0) + Number(rec.overconfident || 0) > 0
            ? `<button class="ghost-btn small" data-action="open-recognition-print">打印不会的字</button>`
            : ""
        }
      </div>
    </section>
  `;
}

function renderHome() {
  const boot = state.boot;
  const stats = boot.stats;
  const queue = boot.queue;
  const totalQueue = queue.reviews.length + queue.new.length;
  const canStart = totalQueue > 0;
  const startedToday = (stats.today_attempts || 0) > 0;
  const startLabel = startedToday ? "再学一组" : "开始学习";

  return `
    <section class="hero">
      <div class="hero-mascot"><span class="smile"></span></div>
      <div>
        <h1>今天，认识几个新朋友？</h1>
        <p>每天 10 分钟，认 5 个新字，玩几道认字题。</p>
      </div>
    </section>

    <section class="stats-grid">
      <div class="stat-card gold"><b>${stats.learned}</b><span>学过 / ${stats.total}</span></div>
      <div class="stat-card red"><b>${stats.due}</b><span>待复习</span></div>
      <div class="stat-card green"><b>${stats.streak}</b><span>连续天数</span></div>
    </section>

    <div class="home-parent-link">
      <button class="text-link" data-nav="parent">家长看板 · 设置与学习记录</button>
    </div>

    <section class="today-card">
      <h2>${canStart ? (startedToday ? "再学一组" : "今天的任务") : "今天学完啦"}</h2>
      <p>${canStart ? (startedToday ? "复习一下，再认几个新字。" : "先复习，再学新字，最后玩几道认字题。") : "去字卡册翻一翻，或者让眼睛休息一下。"}</p>
      <div class="queue-pills">
        <span class="queue-pill">复习 <b>${queue.reviews.length}</b></span>
        <span class="queue-pill">新字 <b>${queue.new.length}</b></span>
        <span class="queue-pill">今日已答 <b>${stats.today_attempts}</b></span>
        ${stats.today_attempts ? `<span class="queue-pill">正确率 <b>${stats.accuracy}%</b></span>` : ""}
        ${queue.backlog > 0 ? `<span class="queue-pill warn">还有 <b>${queue.backlog}</b> 个到期，下次优先</span>` : ""}
      </div>
      ${
        canStart
          ? `<button class="primary-btn" data-action="start-session">${startLabel} · ${totalQueue} 个字</button>`
          : `<button class="ghost-btn" style="width:100%" data-nav="cards">去字卡册看看</button>`
      }
    </section>

    ${recognitionCardHtml()}

    ${renderMap()}
  `;
}

function bookTabs(activeId, action) {
  const all = books();
  if (all.length <= 1) return "";

  const countBook = (book) => {
    const chars = bookChars(book);
    return { learned: learnedCount(chars), total: chars.size };
  };
  const entries = all.map((book) => ({ id: book.id, title: book.title, ...countBook(book) }));
  const allSet = new Set(allChars().map((item) => item.char));
  entries.unshift({ id: "all", title: "全部", learned: learnedCount(allSet), total: allSet.size });

  return `
    <div class="book-tabs" role="tablist">
      ${entries
        .map((entry) => {
          const active = entry.id === activeId;
          const label = entry.total ? `学过 ${entry.learned} / 共 ${entry.total}` : "筹备中";
          return `
            <button class="book-tab ${active ? "active" : ""}" role="tab" aria-selected="${active}" data-action="${action}" data-book="${esc(entry.id)}">
              <b>${esc(entry.title)}</b>
              <span>${label}</span>
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderMap() {
  const allMode = state.ui.homeBookId === "all";
  const list = allMode ? books() : [currentBook(false)].filter(Boolean);
  if (!list.length) {
    return `
      ${sectionHead("闯关地图")}
      <div class="empty"><p>课程还没有导入，试试重启应用。</p></div>
    `;
  }
  return `
    ${sectionHead(
      "闯关地图",
      allMode ? "全部册" : `${list[0].title} · ${list[0].edition || ""}`,
    )}
    ${bookTabs(state.ui.homeBookId, "select-home-book")}
    ${list
      .map(
        (book) => `
      ${
        allMode
          ? `<div class="map-book-head"><b>${esc(book.title)}</b><span>${esc(book.edition || "")}</span></div>`
          : ""
      }
      ${(book.units || [])
        .map((unit) => {
          const unitLessons = unit.lessons || [];
          const total = unitLessons.reduce((n, lesson) => n + lesson.total, 0);
          const learned = unitLessons.reduce((n, lesson) => n + lesson.learned, 0);
          return `
            <div class="unit-head">
              <h3>${esc(unit.title)}<i>${esc(unit.kind)}</i></h3>
              <span>${learned}/${total}</span>
            </div>
            <section class="lesson-path">
              ${unitLessons.map((lesson, index) => lessonCard(lesson, index)).join("")}
            </section>
          `;
        })
        .join("")}
    `,
      )
      .join("")}
  `;
}

function lessonCard(lesson, index) {
  // books 结构里只有计数；字的列表从 boot.lessons 取详情。
  const detail = lessonDetail(lesson.id);
  const chars = (detail?.chars || lesson.chars || []);
  const hasContent = chars.length > 0;
  const learned = detail?.learned ?? lesson.learned;
  const percent = lesson.total ? Math.round((learned / lesson.total) * 100) : 0;
  const done = hasContent && learned === lesson.total && learned > 0;

  if (!hasContent) {
    // 内容还没写（P1/P2 补齐），先显示骨架。
    return `
      <div class="lesson-card locked" aria-disabled="true">
        <span class="lesson-index">${index + 1}</span>
        <span class="lesson-main">
          <span class="lesson-title"><b>${esc(lesson.title)}</b><em>筹备中</em></span>
          <span class="lesson-preview">这课的字还在准备，先学别的吧</span>
        </span>
      </div>
    `;
  }

  const preview = chars.slice(0, 7).map((item) => item.char).join(" ");
  return `
    <button class="lesson-card ${done ? "done" : ""}" data-action="open-lesson" data-lesson="${esc(lesson.id)}">
      <span class="lesson-index">${done ? "✓" : index + 1}</span>
      <span class="lesson-main">
        <span class="lesson-title"><b>${esc(lesson.title)}</b><em>${learned}/${lesson.total}</em></span>
        <span class="lesson-preview">${esc(preview)}${chars.length > 7 ? " …" : ""}</span>
        <span class="progress-track"><span class="progress-fill" style="width:${percent}%"></span></span>
      </span>
    </button>
  `;
}

/* ---------------- 读音播放 ---------------- */

function autoPlayOn() {
  return state.boot?.settings?.auto_play_audio !== false;
}

let chainToken = 0;

/* 取消还在排队的连读定时器（比如已经点「开始认字」了）。 */
function stopAudioChain() {
  chainToken += 1;
}

/* 新字卡自动连读：字音（mp3）→ 组词1 → 组词2，每段间隔约 1 秒。 */
function playLearnChain(item) {
  stopAudioChain();
  const token = chainToken;
  const words = (item.words || []).slice(0, 2);
  audio.speakChar(item.char, item.audio_key);
  let delay = 1000;
  for (const word of words) {
    setTimeout(() => {
      if (token === chainToken) audio.speak(word);
    }, delay);
    delay += 1000;
  }
}

/* ---------------- 眼睛休息 ---------------- */

const REST_AFTER_MS = 12 * 60 * 1000;
const REST_SECONDS = 20;
let restTimer = null;
let restTick = null;

function clearRestTimer() {
  clearTimeout(restTimer);
  restTimer = null;
}

function stopRestTicker() {
  clearInterval(restTick);
  restTick = null;
}

/* 每次进入学习会话（或休息结束）重新计时。 */
function startRestTimer() {
  clearRestTimer();
  stopRestTicker();
  if (!state.session || state.session.finished) return;
  restTimer = setTimeout(showRest, REST_AFTER_MS);
}

function showRest() {
  clearRestTimer();
  stopAudioChain();
  audio.stop();
  state.rest = { left: REST_SECONDS };
  render();
  stopRestTicker();
  restTick = setInterval(() => {
    if (!state.rest) {
      stopRestTicker();
      return;
    }
    state.rest.left -= 1;
    if (state.rest.left <= 0) {
      dismissRest();
      return;
    }
    const el = document.getElementById("rest-count");
    if (el) el.textContent = String(state.rest.left);
  }, 1000);
}

function dismissRest() {
  stopRestTicker();
  state.rest = null;
  render();
  startRestTimer();
}

function renderRest() {
  if (!state.rest) return "";
  return `
    <div class="rest-overlay">
      <div class="rest-card" role="dialog" aria-modal="true" aria-labelledby="rest-title">
        <div class="rest-face">🌿</div>
        <h2 id="rest-title">让小眼睛休息一下</h2>
        <p>看看窗外最远的地方，慢慢数 20 下。</p>
        <div class="rest-count" id="rest-count">${state.rest.left}</div>
        <button class="primary-btn small" data-action="rest-done">休息好了</button>
      </div>
    </div>
  `;
}

/* ---------------- 学习流程 ---------------- */

async function startSession() {
  if (state.starting) return;
  state.starting = true;
  stopAudioChain();
  try {
    const today = await api.today();
    state.boot.settings = today.settings;
    state.boot.stats = today.stats;
    state.boot.queue = today.queue;

    const items = [
      ...today.queue.reviews.map((item) => ({
        ...item,
        mode: "review",
        stage: "quiz",
        showPinyin: false,
      })),
      ...today.queue.new.map((item) => ({
        ...item,
        mode: "new",
        stage: "learn",
        showPinyin: true,
      })),
    ];

    if (!items.length) {
      toast("今天学完啦，去字卡册看看吧");
      navigate("cards");
      return;
    }

    const session = await api.startSession();
    state.session = {
      id: session.id,
      items,
      index: 0,
      answers: [],
      finished: false,
    };
    state.quiz = null;
    state.modal = null;
    state.rest = null;
    startRestTimer();
    navigate("session");
  } catch (error) {
    toast(`开始失败：${error.message}`);
  } finally {
    state.starting = false;
  }
}

function renderSession() {
  if (!state.session) {
    navigate("home");
    return "";
  }
  if (state.session.finishing) return loadingScreen("正在结算…");
  if (state.session.finished) return renderResult();

  const item = currentItem();
  if (!item) {
    finishSession();
    return loadingScreen("正在收尾…");
  }

  const index = state.session.index;
  const total = state.session.items.length;
  const percent = Math.round(((index + 1) / total) * 100);

  const body = item.stage === "learn" ? renderLearnCard(item) : renderQuizCard(item);
  const source = item.book_title
    ? `${esc(item.book_title)} · ${esc(item.unit_title || "")} · ${esc(item.lesson_title || item.lesson || "")}`
    : esc(item.lesson || "");
  const recognition = state.session.kind === "recognition";
  const metaLabel = recognition
    ? item.stage === "learn"
      ? "先认一认"
      : "艾宾浩斯复习"
    : item.mode === "new"
      ? "学新字"
      : "复习";
  const sourceLabel = recognition
    ? `艾宾浩斯 · ${item.self_report === "known" ? "自评认识" : "自评不认识"} · R${item.recognition_stage ?? 0}`
    : source;

  return `
    <div class="session-top">
      <button class="close-btn" data-action="close-session" aria-label="结束学习">×</button>
      <div class="session-progress">
        <div class="meta">
          <span>${metaLabel}</span>
          <span>${index + 1} / ${total}</span>
        </div>
        <div class="track"><div class="fill" style="width:${percent}%"></div></div>
        <div class="session-source">${sourceLabel}</div>
      </div>
    </div>
    ${body}
  `;
}

function renderLearnCard(item) {
  const showPinyin = item.showPinyin !== false;
  if (!item.chainPlayed) {
    item.chainPlayed = true;
    if (autoPlayOn()) playLearnChain(item);
  }
  return `
    <article class="learn-card">
      ${charIdentityHtml(item, { mode: "learn", showPinyin })}
      ${charInfoBlocksHtml(item, { showConfusions: true })}

      <div class="action-row">
        <button class="ghost-btn" data-action="replay-learn">听读音</button>
        <button class="primary-btn small" data-action="learn-next">开始认字</button>
      </div>
    </article>
  `;
}

function renderQuizCard(item) {
  if (!state.quiz || state.quiz.index !== state.session.index) {
    state.quiz = makeQuestion(item);
    state.quiz.index = state.session.index;
    state.quiz.answered = false;
    state.quiz.kbdIndex = -1; // 进入题目时不预选，按方向键才出现高亮
    const quiz = state.quiz;
    if (quiz.type === "audio") {
      setTimeout(() => {
        if (state.quiz === quiz && !quiz.answered) audio.speakChar(item.char, item.audio_key);
      }, 300);
    }
  }

  const quiz = state.quiz;
  const answered = Boolean(quiz.answered);
  const options = quiz.options
    .map((option, index) => {
      let cls = "";
      if (answered) {
        if (option.value === quiz.correctAnswer) cls = "correct";
        else if (option.value === quiz.selected) cls = "wrong";
        else cls = "dim";
      } else if (index === quiz.kbdIndex) {
        cls = "kbd-focus";
      }
      return `
        <button class="option-btn ${cls}" data-action="answer" data-value="${esc(option.value)}" ${answered ? "disabled" : ""}>
          ${esc(option.value)}
        </button>
      `;
    })
    .join("");

  const feedback = answered ? renderFeedback(item, quiz) : "";

  return `
    <article class="quiz-card" data-char="${esc(item.char)}" data-type="${esc(quiz.type)}">
      <div class="quiz-prompt">${esc(quiz.prompt)}</div>
      ${quiz.targetHtml || ""}
      <div class="center-row">
        <button class="ghost-btn" data-action="replay-quiz">${quiz.type === "audio" ? "再听一遍" : "听读音"}</button>
      </div>
      <div class="option-grid">${options}</div>
      ${feedback}
    </article>
  `;
}

function renderFeedback(item, quiz) {
  const right = quiz.isCorrect;
  const title = right ? "答对啦！" : "再认一认";
  const detail = right
    ? `「${esc(item.char)}」读 ${esc(item.pinyin)}。${esc(item.meaning)}`
    : `正确答案是「${esc(quiz.correctAnswer)}」。「${esc(item.char)}」读 ${esc(item.pinyin)}。${esc(item.meaning)}`;

  let recognitionNote = "";
  if (state.session?.kind === "recognition") {
    const result = quiz.recognitionResult;
    if (result) {
      const notes = [`下次复习：${dueLabel(result.due_at)}（R${result.stage}）`];
      if (result.overconfident) {
        notes.push("你自评「认识」，但这次没答对，已标记为「高估」，会早点再复习。");
      }
      if (result.underestimated) {
        notes.push("自评「不认识」但答对了，已经跳一级，避免重复太多次。");
      }
      recognitionNote = `<p class="recognition-feedback-note">${notes.map(esc).join("<br />")}</p>`;
    } else {
      recognitionNote = `<p class="recognition-feedback-note">正在安排下次复习…</p>`;
    }
  }

  return `
    <div class="feedback ${right ? "" : "wrong"}">
      <span class="badge">${right ? "✓" : "!"}</span>
      <div>
        <b>${title}</b>
        <p>${detail}</p>
        ${quiz.type === "cloze" && item.sentence ? `<p style="margin-top:4px">${highlightChar(item.sentence, item.char)}</p>` : ""}
        ${recognitionNote}
      </div>
    </div>
    <button class="primary-btn small" style="margin-top:12px" data-action="next-item">${state.session?.kind === "recognition" ? "下一个字" : "下一个"}</button>
  `;
}

/* ---------------- 出题 ---------------- */

function charOptions(item) {
  // 干扰项只从三处抽：形近字 → 同课字 → 已学字；不够 3 个才用常见字兜底。
  const pools = [
    (item.confusions || []).filter((char) => char && char !== item.char),
    sameLessonChars(item).map((c) => c.char),
    learnedChars().map((c) => c.char),
  ];
  let pool = unique(pools.flat()).filter((char) => char !== item.char);
  if (pool.length < 3) {
    const fallback = "人口日月水火山木土田禾大小上下天中".split("");
    pool = unique([...pool, ...fallback]).filter((char) => char !== item.char);
  }
  return shuffle([item.char, ...shuffle(pool).slice(0, 3)]);
}

function canMake(type, item) {
  if (type === "cloze") {
    if (!item.sentence) return false;
    // 只在这个字正好出现一次时出填空题，避免一句话里挖两个空。
    return item.sentence.split(item.char).length - 1 === 1;
  }
  if (type === "pinyin") return Boolean(item.pinyin);
  return true;
}

function chooseType(item) {
  const available = item.quiz_types?.length ? item.quiz_types : ["audio"];
  const preferred =
    item.mode === "recognition"
      ? ["pinyin", "audio", "cloze"]
      : item.mode === "new"
        ? ["audio", "cloze", "pinyin"]
        : ["cloze", "audio", "pinyin"];
  // 新字按“听音 → 填空 → 拼音”轮换；复习也轮换，避免只做一种题。
  const newSeen = state.session
    ? state.session.items.slice(0, state.session.index).filter((entry) => entry.mode === "new").length
    : 0;
  const offset =
    item.mode === "new"
      ? newSeen % preferred.length
      : (state.session?.index || 0) % preferred.length;
  for (let i = 0; i < preferred.length; i += 1) {
    const type = preferred[(i + offset) % preferred.length];
    if (available.includes(type) && canMake(type, item)) return type;
  }
  return "audio";
}

function makeQuestion(item) {
  const type = chooseType(item);

  if (type === "cloze" && canMake("cloze", item)) {
    const blank = item.sentence.replace(item.char, "（　）");
    return {
      type,
      prompt: "选一个字，把句子补完整",
      targetHtml: `<div class="sentence-line" style="text-align:center;font-size:20px;margin-bottom:6px">${esc(blank)}</div>`,
      options: charOptions(item).map((value) => ({ value })),
      correctAnswer: item.char,
      startedAt: performance.now(),
    };
  }

  if (type === "pinyin") {
    return {
      type,
      prompt: "看拼音，点出这个字",
      targetHtml: `<div class="quiz-target pinyin-target">${esc(item.pinyin)}</div>`,
      options: charOptions(item).map((value) => ({ value })),
      correctAnswer: item.char,
      startedAt: performance.now(),
    };
  }

  return {
    type: "audio",
    prompt: "听一听，点出这个字",
    targetHtml: `<div class="quiz-sub">先听声音，再点字</div>`,
    options: charOptions(item).map((value) => ({ value })),
    correctAnswer: item.char,
    startedAt: performance.now(),
  };
}

function answerQuestion(value) {
  const quiz = state.quiz;
  const item = currentItem();
  if (!quiz || quiz.answered || !item) return;

  quiz.answered = true;
  quiz.selected = value;
  quiz.isCorrect = value === quiz.correctAnswer;
  quiz.responseMs = Math.max(0, Math.round(performance.now() - quiz.startedAt));

  state.bootDirty = true;
  state.session.answers.push({
    char: item.char,
    type: quiz.type,
    correct: quiz.isCorrect,
    response_ms: quiz.responseMs,
  });

  if (state.session.kind === "recognition") {
    quiz.recognitionPending = true;
    api
      .recognitionAttempt(item.char, quiz.isCorrect, quiz.responseMs)
      .then((result) => {
        quiz.recognitionResult = result;
        quiz.recognitionPending = false;
        if (state.quiz === quiz) render();
      })
      .catch((error) => {
        quiz.recognitionPending = false;
        toast(`记录失败：${error.message}`);
      });
  } else {
    api
      .submitAttempts(state.session.id, [
        {
          char: item.char,
          question_type: quiz.type,
          selected: value,
          correct_answer: quiz.correctAnswer,
          response_ms: quiz.responseMs,
        },
      ])
      .then((result) => {
        if (state.boot && result.stats) state.boot.stats = result.stats;
      })
      .catch((error) => toast(`记录失败：${error.message}`));
  }

  audio.chime(quiz.isCorrect);
  setTimeout(() => audio.speakChar(item.char, item.audio_key), 180);
  render();
}

/* 学字卡 → 进入认字题（按钮和回车共用）。 */
function advanceLearn(item) {
  if (!item) return;
  item.stage = "quiz";
  state.quiz = null;
  stopAudioChain();
  render();
}

function nextItem() {
  if (!state.session) return;
  state.session.index += 1;
  state.quiz = null;
  if (state.session.index >= state.session.items.length) {
    finishSession();
  } else {
    render();
  }
}

function finishSession() {
  if (!state.session) return;
  const recognition = state.session.kind === "recognition";
  state.bootDirty = true;
  clearRestTimer();
  stopRestTicker();
  state.rest = null;

  if (recognition) {
    // 先刷新统计再显示结果，避免用旧的「到期数」显示“再复习一组”。
    state.session.finishing = true;
    refreshBoot().then(() => {
      if (!state.session) return;
      state.session.finishing = false;
      state.session.finished = true;
      if (state.route === "session") render();
    });
    render();
    return;
  }

  state.session.finished = true;
  api.endSession(state.session.id).catch(() => {});
  refreshBoot().then(() => {
    if (state.route === "session" && state.session?.finished) render();
  });
  render();
}

async function closeSession() {
  if (!state.session) {
    navigate("home");
    return;
  }
  const recognition = state.session.kind === "recognition";
  if (
    !state.session.finished &&
    !confirm(recognition ? "结束这次认字复习吗？已经答过的题会保存。" : "结束这次学习吗？已经答过的题会保存。")
  ) {
    return;
  }
  stopAudioChain();
  clearRestTimer();
  stopRestTicker();
  state.rest = null;
  if (!recognition) {
    try {
      await api.endSession(state.session.id);
    } catch (_) {
      /* 已经结束也没关系 */
    }
  }
  state.session = null;
  state.quiz = null;
  await refreshBoot();
  navigate(recognition ? "recognition" : "home");
}

async function refreshBoot() {
  try {
    state.boot = await api.bootstrap();
    state.bootDirty = false;
    audio.setEnabled(state.boot.settings.sound !== false);
    applyReduceMotion();
  } catch (error) {
    console.warn(error);
  }
}

function renderRecognitionReviewResult() {
  const answers = state.session.answers;
  const total = state.session.items.length;
  const correct = answers.filter((item) => item.correct).length;
  const accuracy = answers.length ? Math.round((correct / answers.length) * 100) : 0;
  const stars = accuracy >= 90 ? 3 : accuracy >= 70 ? 2 : 1;
  const remaining = recognitionGroupSize(state.boot?.recognition?.due || 0);
  const message =
    accuracy >= 90
      ? "记得很牢，下次复习会隔得更久。"
      : accuracy >= 70
        ? "不错，答错的字已经安排了更近的复习。"
        : "没关系，答错的字会很快再出现。";

  return `
    <article class="result-card recognition-result">
      <div class="result-stars">${[1, 2, 3].map((n) => (n <= stars ? "★" : '<span class="off">★</span>')).join("")}</div>
      <h2>这一组复习完啦</h2>
      <p>${message}</p>
      <div class="result-stats">
        <div><b>${total}</b><span>复习字数</span></div>
        <div><b>${correct}</b><span>答对</span></div>
        <div><b>${accuracy}%</b><span>正确率</span></div>
      </div>
      <div class="result-actions">
        ${
          remaining
            ? `<button class="primary-btn" data-action="start-recognition-review">再复习一组 · ${remaining} 个到期</button>`
            : `<button class="primary-btn" data-action="open-recognition">今天的复习完成</button>`
        }
        <button class="ghost-btn" style="width:100%" data-nav="home">回小岛</button>
      </div>
    </article>
  `;
}

function renderResult() {
  if (state.session?.kind === "recognition") return renderRecognitionReviewResult();
  const answers = state.session.answers;
  const total = state.session.items.length;
  const correct = answers.filter((item) => item.correct).length;
  const accuracy = answers.length ? Math.round((correct / answers.length) * 100) : 0;
  const stars = accuracy >= 90 ? 3 : accuracy >= 70 ? 2 : 1;
  const message =
    accuracy >= 90
      ? "太棒了，今天记得很牢！"
      : accuracy >= 70
        ? "不错，明天再复习一次会更稳。"
        : "没关系，明天再认一次就记住了。";

  return `
    <article class="result-card">
      <div class="result-stars">${[1, 2, 3].map((n) => (n <= stars ? "★" : '<span class="off">★</span>')).join("")}</div>
      <h2>今天学完啦</h2>
      <p>${message}</p>
      <div class="result-stats">
        <div><b>${total}</b><span>过了一遍</span></div>
        <div><b>${correct}</b><span>答对</span></div>
        <div><b>${accuracy}%</b><span>正确率</span></div>
      </div>
      <div class="result-actions">
        <button class="primary-btn" data-action="start-session">再学一组</button>
        <button class="ghost-btn" style="width:100%" data-nav="home">回小岛</button>
      </div>
    </article>
  `;
}

/* ---------------- 字卡册 ---------------- */

function charCard(item) {
  const mastery = item.progress?.mastery || "new";
  return `
    <button class="char-card ${mastery}" data-action="open-char" data-char="${esc(item.char)}" title="${esc(item.pinyin)} · ${masteryLabel(mastery)}">
      <span class="c">${esc(item.char)}</span>
      <span class="p">${esc(item.pinyin)}</span>
    </button>
  `;
}

function cardUnits() {
  if (state.ui.cardBookId === "all") {
    return books().flatMap((book) =>
      (book.units || []).map((unit) => ({ ...unit, bookTitle: book.title })),
    );
  }
  return bookById(state.ui.cardBookId)?.units || [];
}

function shortBookTitle(title) {
  return String(title || "").replace("一年级", "");
}

function ensurePolyphonic() {
  if (state.polyphonic !== null || state.polyLoading) return;
  state.polyLoading = true;
  api
    .polyphonic()
    .then((data) => {
      state.polyphonic = data.items || [];
    })
    .catch(() => {
      state.polyphonic = [];
    })
    .finally(() => {
      state.polyLoading = false;
      if (state.route === "cards" || state.modal?.type === "char") render();
    });
}

function radicalGroups() {
  const map = new Map();
  for (const item of allChars()) {
    const radical = (item.radical || "").trim();
    if (!radical) continue;
    if (!map.has(radical)) map.set(radical, new Set());
    map.get(radical).add(item.char);
  }
  return [...map.entries()]
    .map(([radical, members]) => ({ radical, members: [...members], count: members.size }))
    .filter((entry) => entry.count >= 2)
    .sort((a, b) => b.count - a.count || a.radical.localeCompare(b.radical, "zh"));
}

function familyChip(char) {
  const known = findChar(char)?.progress?.first_seen_at ? "known" : "";
  return charChip(char, `family-chip ${known}`);
}

function radicalMembersHtml(radical) {
  const group = radicalGroups().find((entry) => entry.radical === radical);
  return group ? group.members.map(familyChip).join("") : "";
}

/* 点部首 chip 或下拉框时只更新这一块，避免整页重绘、滚动位置跳动。 */
function selectRadical(radical) {
  state.ui.familyRadical = radical;
  saveUi();
  const board = document.querySelector(".radical-board");
  if (!board) return;
  board.querySelectorAll(".radical-chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.radical === radical);
  });
  const select = board.querySelector("#radical-select");
  if (select) select.value = radical;
  const container = board.querySelector(".radical-members");
  if (container) container.innerHTML = radicalMembersHtml(radical);
}

/* 部首分类放在字卡册最前面，作为主入口，而不是藏在折叠面板里。 */
function radicalBoardHtml() {
  const groups = radicalGroups();
  if (!groups.length) return "";
  const selected =
    groups.find((entry) => entry.radical === state.ui.familyRadical) || groups[0];
  const quick = groups.slice(0, 8);
  const covered = groups.reduce((sum, entry) => sum + entry.count, 0);
  return `
    <section class="radical-board no-print" aria-label="按部首认字">
      <div class="radical-board-head">
        <div>
          <h3>按部首认字</h3>
          <p>同一个部首的字排在一起，点字就能看字卡。共 ${groups.length} 组，覆盖 ${covered} 个字。</p>
        </div>
        <label class="radical-picker" for="radical-select">
          <span>全部部首</span>
          <select id="radical-select">
            ${groups
              .map(
                (entry) =>
                  `<option value="${esc(entry.radical)}" ${entry.radical === selected.radical ? "selected" : ""}>${esc(entry.radical)}（${entry.count} 字）</option>`,
              )
              .join("")}
          </select>
        </label>
      </div>
      <div class="radical-quick">
        ${quick
          .map(
            (entry) => `
          <button class="radical-chip ${entry.radical === selected.radical ? "active" : ""}" data-action="select-radical" data-radical="${esc(entry.radical)}">
            <b>${esc(entry.radical)}</b><span>${entry.count} 字</span>
          </button>
        `,
          )
          .join("")}
      </div>
      <div class="family-members radical-members">${selected.members.map(familyChip).join("")}</div>
    </section>
  `;
}

function familyPanel() {
  const families = (state.boot?.families || [])
    .map((entry) => ({
      family: entry.family,
      members: (entry.members || []).filter((char) => findChar(char)),
    }))
    .filter((entry) => entry.members.length >= 3);
  if (!families.length) return "";

  return `
    <details class="tool-panel no-print">
      <summary>精选字族 · ${families.length} 组（按声旁/部件）</summary>
      <p class="tool-hint">精选字族按声旁/部件整理，和上面的同部首分类互补。</p>
      <div class="family-list">
        ${families
          .map(
            (entry) => `
          <div class="family-row">
            <span class="family-key">${esc(entry.family)}</span>
            <span class="family-members">${entry.members.map(familyChip).join("")}</span>
          </div>
        `,
          )
          .join("")}
      </div>
    </details>
  `;
}

function polyRow(item) {
  return `
    <div class="poly-row">
      <span class="poly-char">${esc(item.char)}</span>
      <div class="poly-readings">
        ${(item.readings || []).map((reading) => polyReadingButton(item.char, reading)).join("")}
      </div>
    </div>
  `;
}

function polyPanel() {
  if (state.polyphonic === null) {
    return state.polyLoading
      ? `<div class="tool-panel loading-panel no-print">正在读多音字…</div>`
      : "";
  }
  const items = state.polyphonic;
  if (!items.length) return "";
  const textbook = items.filter((item) => item.source !== "common");
  const common = items.filter((item) => item.source === "common");
  return `
    <details class="tool-panel no-print">
      <summary>多音字 · 教材 ${textbook.length} 个${common.length ? ` + 常见 ${common.length} 个` : ""}</summary>
      <p class="tool-hint">教材标注的读音按课文；常见补充按常用词。点读音听一听。</p>
      ${
        textbook.length
          ? `<div class="poly-group-title">教材多音字</div>
             <div class="poly-list">${textbook.map(polyRow).join("")}</div>`
          : ""
      }
      ${
        common.length
          ? `<div class="poly-group-title">常见多音字（补充）</div>
             <div class="poly-chips">
               ${common.map((item) => charChip(item.char, "family-chip")).join("")}
             </div>`
          : ""
      }
    </details>
  `;
}

function renderCards() {
  const stats = state.boot.stats;
  const allMode = state.ui.cardBookId === "all";
  const units = cardUnits();

  // 默认选第一个有内容的单元；切册时同样找第一个有内容的单元。
  if (!state.ui.cardUnitId || !units.some((unit) => unit.id === state.ui.cardUnitId)) {
    state.ui.cardUnitId = (units.find(unitHasContent) || units[0] || {}).id || null;
  }
  const unit = units.find((item) => item.id === state.ui.cardUnitId) || null;
  const unitLessons = (unit?.lessons || [])
    .map((lesson) => lessonDetail(lesson.id))
    .filter((lesson) => lesson && (lesson.chars || []).length > 0);

  ensurePolyphonic();

  return `
    <div class="print-head"><b>汉字小岛 · 字卡</b><span>${esc(new Date().toLocaleDateString("zh-CN"))}</span></div>
    ${sectionHead("字卡册", `学过 ${stats.learned} / ${stats.total}`, { style: "margin-top:8px" })}
    <p class="card-hint">点一个字，可以听读音、看组词和句子。颜色越深，说明越熟悉。</p>
    ${bookTabs(state.ui.cardBookId, "select-card-book")}
    ${
      units.length
        ? `<div class="unit-chips no-print">
            ${units
              .map((item) => {
                const has = unitHasContent(item);
                return `
                  <button class="unit-chip ${item.id === state.ui.cardUnitId ? "active" : ""} ${has ? "" : "disabled"}"
                    data-action="select-card-unit" data-unit="${esc(item.id)}" ${has ? "" : "disabled"}>
                    ${allMode ? `<i class="unit-book">${esc(shortBookTitle(item.bookTitle))}</i>` : ""}${esc(item.title)}
                  </button>
                `;
              })
              .join("")}
          </div>`
        : ""
    }
    <div class="tool-row no-print">
      <button class="ghost-btn small" data-action="print-cards">打印这一页</button>
    </div>
    ${radicalBoardHtml()}
    ${familyPanel()}
    ${polyPanel()}
    ${
      unitLessons.length
        ? unitLessons
            .map(
              (lesson) => `
          ${sectionHead(lesson.title, `${lesson.learned}/${lesson.total}`, { small: true })}
          <div class="card-grid" style="margin-bottom:18px">
            ${lesson.chars.map(charCard).join("")}
          </div>
        `,
            )
            .join("")
        : `<div class="empty"><p>这个单元的字还在准备中，先看看别的单元吧。</p></div>`
    }
  `;
}

/* ---------------- 读一读 ---------------- */

const READ_PUNCT = new Set(["，", "。", "！", "？", "、", "；", "：", "“", "”", "‘", "’", "（", "）", "《", "》", "…", "—"]);

/* 整句朗读：逐字播放拼音音节 mp3，避开系统 TTS 在某些 Mac 上没声音的问题。 */
let lineToken = 0;

function stopLineSpeech() {
  lineToken += 1;
}

function speakLine(line) {
  stopAudioChain();
  stopLineSpeech();
  const token = lineToken;
  audio.stop();
  const reading = (state.boot?.readings || []).find((item) => item.id === state.readingId);
  const parts = [...String(line || "")];
  let index = 0;

  const next = () => {
    if (token !== lineToken) return;
    while (index < parts.length && READ_PUNCT.has(parts[index])) {
      index += 1;
      setTimeout(next, 260);
      return;
    }
    if (index >= parts.length) return;
    const char = parts[index];
    index += 1;
    const item = findChar(char);
    const pronunciation = reading?.pronunciations?.[char];
    audio.speakChar(char, pronunciation?.audio_key || item?.audio_key, () => setTimeout(next, 90));
  };

  next();
}

function unitTitle(unitId) {
  for (const book of books()) {
    for (const unit of book.units || []) {
      if (unit.id === unitId) return unit.title;
    }
  }
  return "";
}

function readingChars(reading) {
  return unique([...reading.text].filter((char) => !READ_PUNCT.has(char)));
}

function readingStats(reading) {
  const chars = readingChars(reading);
  const body = [...reading.text].filter((char) => !READ_PUNCT.has(char));
  const known = chars.filter((char) => findChar(char)?.progress?.first_seen_at).length;
  return { total: body.length, distinct: chars.length, known };
}

function readingRow(reading) {
  const { total, distinct, known } = readingStats(reading);
  return `
    <button class="reading-row" data-action="open-reading" data-reading="${esc(reading.id)}">
      <span class="reading-row-main">
        <b>${esc(reading.title)}</b>
        <span>${esc(unitTitle(reading.unit_id))} · ${reading.lines.length} 句 · ${total} 字</span>
      </span>
      <span class="reading-row-known">认识 ${known}/${distinct}</span>
    </button>
  `;
}

function readCharHtml(char, showPinyin, pronunciation = null) {
  if (READ_PUNCT.has(char)) return `<span class="read-punct">${esc(char)}</span>`;
  const item = findChar(char);
  const known = Boolean(item?.progress?.first_seen_at);
  const pinyin = pronunciation?.pinyin || item?.pinyin || "";
  const audioKey = pronunciation?.audio_key || item?.audio_key || "";
  const pinyinClass = showPinyin && pinyin ? "" : "hidden";
  return `
    <button class="read-char ${known ? "known" : "unknown"}" data-action="speak-read-char" data-char="${esc(char)}" data-audio="${esc(audioKey)}">
      <span class="read-pinyin ${pinyinClass}">${esc(pinyin || " ")}</span>
      <span class="read-glyph">${esc(char)}</span>
    </button>
  `;
}

function renderReadingDetail(reading) {
  const showPinyin = state.ui.readPinyin !== false;
  return `
    <div class="reading-top">
      <button class="ghost-btn small" data-action="back-readings">← 全部短文</button>
      <button class="ghost-btn small" data-action="toggle-read-pinyin">${showPinyin ? "隐藏拼音" : "显示拼音"}</button>
    </div>
    <article class="reading-card">
      <h2>${esc(reading.title)}</h2>
      <div class="reading-lines">
        ${reading.lines
          .map(
            (line) => `
          <div class="reading-line">
            <div class="read-chars">${[...line].map((char) => readCharHtml(char, showPinyin, reading.pronunciations?.[char])).join("")}</div>
            <button class="line-speak" data-action="speak-line" data-line="${esc(line)}" title="读这句" aria-label="读这句">▶</button>
          </div>
        `,
          )
          .join("")}
      </div>
      <p class="reading-hint">点字听读音，点 ▶ 听整句。</p>
    </article>
  `;
}

function readBookFilter() {
  const readings = state.boot?.readings || [];
  const all = books();
  if (all.length <= 1) return "";
  const entries = [
    { id: "all", title: "全部", count: readings.length },
    ...all.map((book) => ({
      id: book.id,
      title: book.title,
      count: readings.filter((reading) => reading.book_id === book.id).length,
    })),
  ];
  return `
    <div class="read-filter" role="tablist" aria-label="按册筛选短文">
      ${entries
        .map((entry) => {
          const active = entry.id === state.ui.readBookId;
          return `
            <button class="read-filter-btn ${active ? "active" : ""}" role="tab" aria-selected="${active}" data-action="select-read-book" data-book="${esc(entry.id)}">
              <b>${esc(entry.title)}</b><span>${entry.count} 篇</span>
            </button>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderRead() {
  const readings = state.boot?.readings || [];
  if (state.readingId) {
    const reading = readings.find((item) => item.id === state.readingId);
    if (reading) return renderReadingDetail(reading);
    state.readingId = null;
  }

  const selected = state.ui.readBookId || "all";
  const visible =
    selected === "all" ? readings : readings.filter((reading) => reading.book_id === selected);
  const groups = books()
    .map((book) => ({ book, items: visible.filter((reading) => reading.book_id === book.id) }))
    .filter((group) => group.items.length);

  return `
    ${sectionHead("读一读", `${visible.length} 篇`, { style: "margin-top:8px" })}
    <p style="margin:0 2px 16px;color:var(--ink-soft);font-size:14px">
      点句子听整句，点单个字听读音。灰色的字还没学过，也可以点。
    </p>
    ${readBookFilter()}
    ${
      groups.length
        ? groups
            .map(
              ({ book, items }) => `
          ${sectionHead(book.title, `${items.length} 篇`, { small: true })}
          <div class="reading-list">${items.map(readingRow).join("")}</div>
        `,
            )
            .join("")
        : `<div class="empty"><p>这一册的短文还在准备中，先学几个字吧。</p></div>`
    }
  `;
}

/* ---------------- 艾宾浩斯认字 ---------------- */

function dueLabel(value) {
  if (!value) return "";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${value}T00:00:00`);
  const days = Math.round((target - today) / 86400000);
  if (Number.isNaN(days) || days <= 0) return "今天";
  if (days === 1) return "明天";
  return `${days} 天后`;
}

function recognitionGroupSize(due) {
  return Math.min(Number(due || 0), Number(state.boot?.recognition?.review_limit || 15));
}

function recognitionScopeButtons(restart) {
  const scopes = state.boot?.recognition?.scopes || [];
  return `
    <div class="scope-grid">
      ${scopes
        .map(
          (scope) => `
        <button class="scope-btn ${scope.id === "literacy" ? "recommended" : ""}" data-action="start-recognition-run" data-scope="${esc(scope.id)}" data-restart="${restart ? "true" : "false"}">
          <b>${esc(scope.title)}${scope.id === "literacy" ? '<em class="scope-badge">推荐</em>' : ""}</b>
          <span>${scope.total} 个字</span>
        </button>
      `,
        )
        .join("")}
    </div>
  `;
}

function renderRecognition() {
  const rec = state.boot?.recognition;
  if (!rec) return loadingScreen("正在整理认字记录…");
  const active = rec.active_run;
  const latest = rec.latest_run;
  const due = Number(rec.due || 0);
  const finished = latest && latest.status === "finished";
  const printable = Number(rec.self_unknown || 0) + Number(rec.overconfident || 0);

  return `
    ${sectionHead("认字", "幼儿识字 1300 · 自评 + 答题验证", { style: "margin-top:8px" })}
    <p style="margin:0 2px 16px;color:var(--ink-soft);font-size:14px">
      先整体过一遍 1300 字：认识的点「认识」，不认识的点「不认识」。之后按 1 / 2 / 4 / 7 / 15 / 30 / 60 天复习，用答题结果验证自评。
    </p>

    <section class="stats-grid recognition-stats">
      <div class="stat-card gold"><b>${rec.reported}</b><span>已自评 / ${rec.total}</span></div>
      <div class="stat-card green"><b>${rec.self_known}</b><span>自评认识</span></div>
      <div class="stat-card red"><b>${rec.self_unknown}</b><span>自评不认识</span></div>
      <div class="stat-card"><b>${due}</b><span>今天待复习</span></div>
    </section>

    <div class="tool-row no-print">
      <button class="ghost-btn small" data-action="open-recognition-edit">自评标错了？改几个字</button>
      ${
        printable
          ? `<button class="ghost-btn small" data-action="open-recognition-print">打印不会的字 · ${printable} 个</button>`
          : ""
      }
    </div>

    ${
      active
        ? `<section class="recognition-card active-run">
            <div class="recognition-card-head">
              <div>
                <span class="eyebrow">正在过一遍</span>
                <h2>${esc(active.scope_title)} · ${active.reported} / ${active.total}</h2>
                <p>认识 ${active.known}，不认识 ${active.unknown}。中途退出不会丢，下次接着上次的字继续。</p>
              </div>
              <span class="recognition-ring"><b>${active.percent}%</b><i>已过</i></span>
            </div>
            <div class="recognition-progress"><span style="width:${active.percent}%"></span></div>
            <div class="recognition-actions">
              <button class="primary-btn small" data-action="continue-recognition">继续过一遍</button>
              ${due ? `<button class="ghost-btn small" data-action="start-recognition-review">先复习 ${recognitionGroupSize(due)} 个字</button>` : ""}
            </div>
          </section>`
        : finished
          ? `<section class="recognition-card">
              <div class="recognition-card-head">
                <div>
                  <span class="eyebrow">整体过一遍已完成</span>
                  <h2>${esc(latest.scope_title)} · 认识 ${latest.known} 个，不认识 ${latest.unknown} 个</h2>
                  <p>自评只是分桶，不等于已经掌握。每天复习时答对，才会慢慢升级。</p>
                </div>
                <span class="recognition-ring"><b>${rec.mastered}</b><i>掌握</i></span>
              </div>
              <div class="recognition-actions">
                ${
                  due
                    ? `<button class="primary-btn small" data-action="start-recognition-review">开始复习 ${recognitionGroupSize(due)} 个字</button>`
                    : `<button class="ghost-btn small" data-action="start-recognition-review">看看今天有没有复习</button>`
                }
              </div>
            </section>`
          : `<section class="recognition-card">
              <div class="recognition-card-head">
                <div>
                  <span class="eyebrow">还没有开始</span>
                  <h2>先选一个范围</h2>
                  <p>推荐先过「幼儿识字 1300」；也可以只过课内一年级上册或下册。中途退出不会丢。</p>
                </div>
              </div>
              ${recognitionScopeButtons(false)}
            </section>`
    }

    ${
      active
        ? `<details class="tool-panel recognition-restart">
            <summary>重新开始一轮（会重置自评和复习安排）</summary>
            <p class="tool-hint">答题历史会保留在数据库备份里，但当前自评和复习时间会按新一轮重置。</p>
            ${recognitionScopeButtons(true)}
          </details>`
        : latest
          ? `<details class="tool-panel recognition-restart">
              <summary>换一个范围重新过一遍</summary>
              <p class="tool-hint">重新过一遍会重置这些字的自评和下一次复习时间。</p>
              ${recognitionScopeButtons(true)}
            </details>`
          : ""
    }

    <section class="panel recognition-help">
      <h3>怎么算“记住”</h3>
      <ul>
        <li>自评「认识」→ 进入 R1，次日先答一题验证。</li>
        <li>自评「不认识」→ 进入 R0，复习时先看字卡，再答题。</li>
        <li>答对升级，下次间隔变长；答错降级，下次更早出现。</li>
        <li>自评「认识」但第一次答错，会在家长页标成「高估」。</li>
      </ul>
    </section>
  `;
}

function recognitionEditResultsHtml() {
  if (state.recognitionEditError) {
    return `<div class="empty"><p>读取失败：${esc(state.recognitionEditError)}</p></div>`;
  }
  const data = state.recognitionEdit;
  if (!data) {
    return `<p class="panel-hint">正在读取自评记录…</p>`;
  }
  if (!data.items.length) {
    return `<div class="empty"><p>${data.query ? "没有找到匹配的字。" : "还没有自评记录，先去整体过一遍吧。"}</p></div>`;
  }

  return `
    <div class="recognition-edit-list">
      ${data.items
        .map((item) => {
          const isKnown = item.self_report === "known";
          const nextReport = isKnown ? "unknown" : "known";
          const first =
            item.first_quiz_correct === 0
              ? " · 首次验证答错"
              : item.first_quiz_correct === 1
                ? " · 首次验证答对"
                : "";
          const review =
            item.attempts > 0
              ? `已复习 ${item.attempts} 次`
              : "还没复习";
          return `
            <article class="recognition-edit-row" aria-label="${esc(item.char)}，${esc(item.pinyin || "")}，${isKnown ? "自评认识" : "自评不认识"}，R${item.stage}，${review}，${dueLabel(item.due_at)}">
              <div class="re-glyph">${esc(item.char)}</div>
              <div class="re-main">
                <b>${esc(item.pinyin || "")}</b>
                <span>${esc(item.meaning || item.lesson || "")}</span>
              </div>
              <div class="re-side">
                <span class="re-badge ${isKnown ? "known" : "unknown"}">${isKnown ? "自评认识" : "自评不认识"}</span>
                <span class="re-meta">R${item.stage} · ${review} · ${dueLabel(item.due_at)}${first}</span>
              </div>
              <button class="ghost-btn small re-change" data-action="recognition-set-report" data-char="${esc(item.char)}" data-report="${nextReport}" aria-label="把「${esc(item.char)}」改成${nextReport === "known" ? "认识" : "不认识"}">
                改成${nextReport === "known" ? "认识" : "不认识"}
              </button>
            </article>
          `;
        })
        .join("")}
    </div>
    <p class="panel-hint">找到 ${data.total} 个${data.total > data.items.length ? `，先显示前 ${data.items.length} 个` : ""}。还没复习的字会按新自评重排复习时间；已经复习过的字只改标签，不改下次复习时间。</p>
  `;
}

async function loadRecognitionEdit(query = "") {
  const token = ++recognitionEditToken;
  const hadData = Boolean(state.recognitionEdit);
  state.recognitionEditLoading = true;
  state.recognitionEditError = null;
  state.recognitionEditQuery = query;
  if (hadData) {
    const box = document.getElementById("recognition-edit-results");
    if (box) box.innerHTML = `<p class="panel-hint">正在查找…</p>`;
  }
  try {
    const data = await api.recognitionItems(query, 60);
    if (token !== recognitionEditToken) return;
    state.recognitionEdit = data;
  } catch (error) {
    if (token !== recognitionEditToken) return;
    state.recognitionEditError = error.message;
  } finally {
    if (token !== recognitionEditToken) return;
    state.recognitionEditLoading = false;
    if (state.route !== "recognition-edit") return;
    const box = document.getElementById("recognition-edit-results");
    if (box && hadData) box.innerHTML = recognitionEditResultsHtml();
    else render();
  }
}

function renderRecognitionEdit() {
  if (!state.recognitionEdit && !state.recognitionEditLoading && !state.recognitionEditError) {
    loadRecognitionEdit("");
    return loadingScreen("正在读取自评记录…");
  }
  const reported = Number(state.boot?.recognition?.reported || 0);
  return `
    ${sectionHead("改自评", `已自评 ${reported} 个字`, { style: "margin-top:8px" })}
    <p class="recognition-edit-hint">
      标错了可以在这里改。查找汉字、拼音或组词，找到后点「改成认识 / 不认识」。
    </p>
    <div class="recognition-edit-search">
      <input id="recognition-edit-search" type="search" value="${esc(state.recognitionEditQuery)}"
             placeholder="查汉字、拼音或组词，例如：块 / kuai / 块头" autocomplete="off" />
    </div>
    <div id="recognition-edit-results">${recognitionEditResultsHtml()}</div>
    <div class="tool-row">
      <button class="ghost-btn small" data-action="back-recognition">返回认字</button>
    </div>
  `;
}

async function updateRecognitionReport(char, report) {
  const current = state.recognitionEdit;
  const item = current?.items?.find((entry) => entry.char === char);
  if (!item || item.self_report === report) return;
  try {
    const data = await api.recognitionUpdateItem(char, report);
    Object.assign(item, data.item);
    current.items.sort((a, b) => {
      const rank = (entry) => (entry.self_report === "unknown" ? 0 : 1);
      return (
        rank(a) - rank(b) ||
        String(b.updated_at || "").localeCompare(String(a.updated_at || "")) ||
        a.char.localeCompare(b.char)
      );
    });
    if (data.summary && state.boot) state.boot.recognition = data.summary;
    const box = document.getElementById("recognition-edit-results");
    if (box) box.innerHTML = recognitionEditResultsHtml();
    if (!data.changed) {
      toast("自评没有变化");
    } else if (data.schedule_changed) {
      toast(
        `已改成「${report === "known" ? "认识" : "不认识"}」，${
          report === "known" ? "明天验证" : "今天复习"
        }`,
      );
    } else {
      toast("自评已改；这个字已经复习过，下次复习时间不变");
    }
  } catch (error) {
    toast(`修改失败：${error.message}`);
  }
}

function ensureRecognitionPrint() {
  if (state.recognitionPrint || state.recognitionPrintLoading) return;
  state.recognitionPrintLoading = true;
  state.recognitionPrintError = null;
  api
    .recognitionPrint()
    .then((data) => {
      state.recognitionPrint = data;
    })
    .catch((error) => {
      state.recognitionPrintError = error.message;
    })
    .finally(() => {
      state.recognitionPrintLoading = false;
      if (state.route === "recognition-print") render();
    });
}

function recognitionPrintCard(item) {
  const source = [item.book_title, item.lesson_title].filter(Boolean).join(" · ");
  return `
    <article class="recognition-print-card ${item.reason === "overconfident" ? "overconfident" : ""}">
      <span class="rpc-check" aria-hidden="true"></span>
      ${item.reason === "overconfident" ? '<span class="rpc-tag">高估</span>' : ""}
      <div class="rpc-glyph">${esc(item.char)}</div>
      ${state.printShowPinyin ? `<div class="rpc-pinyin">${esc(item.pinyin)}</div>` : ""}
      ${state.printShowWords && (item.words || []).length ? `<div class="rpc-words">${esc(item.words.join(" · "))}</div>` : ""}
      ${source ? `<div class="rpc-source">${esc(source)}</div>` : ""}
    </article>
  `;
}

function renderRecognitionPrint() {
  const data = state.recognitionPrint;
  if (!data) {
    if (!state.recognitionPrintError) {
      ensureRecognitionPrint();
      return loadingScreen("正在整理不会的字…");
    }
    return `
      <div class="empty">
        <p>打印清单没有加载出来：${esc(state.recognitionPrintError)}</p>
        <button class="ghost-btn small" data-action="open-recognition-print">重试</button>
        <button class="ghost-btn small" data-action="back-recognition">返回认字</button>
      </div>
    `;
  }

  const items = (data.items || []).filter(
    (item) => item.reason === "unknown" || state.printIncludeOver,
  );
  const date = new Date().toLocaleDateString("zh-CN");

  return `
    ${sectionHead("打印不会的字", `${items.length} 个`, { style: "margin-top:8px" })}
    <div class="print-controls no-print">
      <label class="print-check">
        <input type="checkbox" data-action="toggle-print-over" ${state.printIncludeOver ? "checked" : ""} />
        包含高估字（自评认识，但答题错过）
      </label>
      <label class="print-check">
        <input type="checkbox" data-action="toggle-print-pinyin" ${state.printShowPinyin ? "checked" : ""} />
        显示拼音
      </label>
      <label class="print-check">
        <input type="checkbox" data-action="toggle-print-words" ${state.printShowWords ? "checked" : ""} />
        显示组词
      </label>
      <div class="tool-row">
        <button class="primary-btn small" data-action="print-recognition">打印</button>
        <button class="ghost-btn small" data-action="back-recognition">返回认字</button>
      </div>
      <p class="print-hint">A4 纸，每页约 20 个字。打印后可以让孩子逐张认读，认识的在方框里打勾。</p>
    </div>
    ${
      items.length
        ? `<div class="recognition-print-sheet">
            <header class="recognition-print-head">
              <div><b>汉字小岛 · 我不会的字</b><span>${esc(date)} · 共 ${items.length} 个</span></div>
              <span>读一遍，会了就在方框里打勾</span>
            </header>
            <div class="recognition-print-grid">${items.map(recognitionPrintCard).join("")}</div>
          </div>`
        : `<div class="empty">
            <p>还没有自评「不认识」的字。先去过一遍 1300 字吧。</p>
            <button class="ghost-btn small" data-action="back-recognition">去认字</button>
          </div>`
    }
  `;
}

function renderRecognitionRun() {
  const current = state.recognitionRun;
  if (!current) {
    navigate("recognition");
    return "";
  }
  const { run, next } = current;

  if (!next) {
    const due = Number(current.summary?.due || 0);
    return `
      <article class="recognition-result">
        <div class="result-stars">${run.known >= run.unknown ? "★★★" : "★★"}</div>
        <h2>这一轮过完啦</h2>
        <p>${esc(run.scope_title)} · 共 ${run.total} 个字</p>
        <div class="result-stats">
          <div><b>${run.known}</b><span>自评认识</span></div>
          <div><b>${run.unknown}</b><span>自评不认识</span></div>
          <div><b>${due}</b><span>今天待复习</span></div>
        </div>
        <p class="recognition-result-note">自评不认识的字会先安排复习；自评认识的字次日验证。答对才算真的记住。</p>
        <div class="result-actions">
          ${
            due
              ? `<button class="primary-btn" data-action="start-recognition-review">开始复习 ${recognitionGroupSize(due)} 个字</button>`
              : `<button class="primary-btn" data-action="open-recognition">看认字报告</button>`
          }
          ${
            run.unknown > 0
              ? `<button class="ghost-btn" style="width:100%" data-action="open-recognition-print">打印不会的字 · ${run.unknown} 个</button>`
              : ""
          }
          <button class="ghost-btn" style="width:100%" data-action="open-recognition-edit">改几个自评</button>
          <button class="ghost-btn" style="width:100%" data-nav="home">回小岛</button>
        </div>
      </article>
    `;
  }

  const index = next.index;
  const total = next.total;
  const percent = total ? Math.round((index / total) * 100) : 0;
  const submitting = state.recognitionSubmitting;

  return `
    <div class="session-top">
      <button class="close-btn" data-action="close-recognition-run" aria-label="结束过字">×</button>
      <div class="session-progress">
        <div class="meta">
          <span>整体过一遍</span>
          <span>第 ${index} / ${total} 个字</span>
        </div>
        <div class="track"><div class="fill" style="width:${percent}%"></div></div>
        <div class="session-source">认识 ${run.known} · 不认识 ${run.unknown}</div>
      </div>
    </div>

    <article class="recognition-stage-card">
      <p class="recognition-question">这个字，你认识吗？</p>
      <div class="recognition-glyph" aria-label="${esc(next.char)}">${esc(next.char)}</div>
      <p class="recognition-hint">不显示拼音，凭第一眼判断。不确定就点「不认识」。</p>
      <div class="recognition-choice-row">
        <button class="recognition-choice known" data-action="recognition-report" data-report="known" ${submitting ? "disabled" : ""}>
          <b>认识</b><span>← 或 1</span>
        </button>
        <button class="recognition-choice unknown" data-action="recognition-report" data-report="unknown" ${submitting ? "disabled" : ""}>
          <b>不认识</b><span>→ 或 2</span>
        </button>
      </div>
    </article>
  `;
}

async function openRecognitionRun(scope, restart = false) {
  if (state.recognitionSubmitting) return;
  state.recognitionSubmitting = true;
  try {
    const data = await api.recognitionStartRun(scope, restart);
    state.recognitionRun = data;
    if (state.boot && data.summary) state.boot.recognition = data.summary;
    state.recognitionSubmitting = false;
    navigate("recognition-run");
  } catch (error) {
    state.recognitionSubmitting = false;
    toast(`开始失败：${error.message}`);
  }
}

async function reportRecognition(value) {
  const current = state.recognitionRun;
  if (!current?.next || state.recognitionSubmitting) return;
  state.recognitionSubmitting = true;
  render();
  try {
    const data = await api.recognitionReport(current.run.id, current.next.char, value);
    state.recognitionRun = data;
    if (state.boot && data.summary) state.boot.recognition = data.summary;
  } catch (error) {
    toast(`记录失败：${error.message}`);
  } finally {
    state.recognitionSubmitting = false;
    render();
  }
}

async function startRecognitionReview() {
  if (state.starting) return;
  state.starting = true;
  stopAudioChain();
  try {
    const today = await api.recognitionToday();
    if (state.boot) state.boot.recognition = today.summary;
    if (!today.items.length) {
      toast(today.due ? "这一组已经复习完了" : "今天没有到期复习");
      await refreshBoot();
      if (state.route !== "home") navigate("recognition");
      else render();
      return;
    }
    const items = today.items.map((item) => ({
      ...item,
      mode: "recognition",
      showPinyin: true,
      chainPlayed: false,
    }));
    state.session = {
      kind: "recognition",
      id: null,
      items,
      index: 0,
      answers: [],
      finished: false,
      recognitionDue: today.due,
    };
    state.quiz = null;
    state.modal = null;
    state.rest = null;
    startRestTimer();
    navigate("session");
  } catch (error) {
    toast(`开始复习失败：${error.message}`);
  } finally {
    state.starting = false;
  }
}

/* ---------------- 家长页 ---------------- */

function weeklyChart(weekly) {
  if (!weekly) return "";
  const max = Math.max(1, ...weekly.days.map((day) => day.attempts));
  return `
    <div class="week-bars" aria-label="最近 7 天答题量">
      ${weekly.days
        .map((day) => {
          const height = Math.round((day.attempts / max) * 100);
          const label = day.date.slice(5).replace("-", "/");
          return `
            <div class="week-bar" title="${esc(day.date)} · 答 ${day.attempts} 次 · 新字 ${day.new_chars}">
              <span class="week-bar-num">${day.attempts || ""}</span>
              <span class="week-bar-track"><span class="week-bar-fill" style="height:${height}%"></span></span>
              <span class="week-bar-label">${label}</span>
            </div>
          `;
        })
        .join("")}
    </div>
    <div class="week-summary">
      学习 <b>${weekly.active_days}</b> 天 · <b>${weekly.minutes}</b> 分钟 · 新字 <b>${weekly.new_chars}</b> 个 · 正确率 <b>${weekly.accuracy}%</b>
    </div>
    <p class="weekly-suggestion">${esc(weekly.suggestion)}</p>
  `;
}

function radicalBadges() {
  const source = state.parent?.progress?.characters?.length
    ? state.parent.progress.characters
    : allChars();
  const counts = new Map();
  for (const item of source) {
    if (!item.progress?.first_seen_at) continue;
    const radical = (item.radical || "").trim();
    if (!radical) continue;
    counts.set(radical, (counts.get(radical) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
}

function badgesHtml() {
  const list = radicalBadges();
  if (!list.length) return "";
  return `
    <section class="panel">
      <h3>部首徽章</h3>
      <p class="panel-hint">学过的字里，这些部首最多。集满 5 个是银章，10 个是金章。</p>
      <div class="badge-grid">
        ${list
          .map(([radical, count]) => {
            const tier = count >= 10 ? "gold" : count >= 5 ? "silver" : "bronze";
            return `<div class="radical-badge ${tier}"><b>${esc(radical)}</b><span>${count} 字</span></div>`;
          })
          .join("")}
      </div>
    </section>
  `;
}

function recognitionParentHtml(rec) {
  if (!rec) return "";
  const over = rec.overconfident_items || [];
  const under = rec.underestimated_items || [];
  return panel(
    "艾宾浩斯认字",
    `
      <div class="parent-grid recognition-parent-grid">
        <div class="parent-stat"><b>${rec.reported}</b><span>已自评 / ${rec.total}</span></div>
        <div class="parent-stat"><b>${rec.self_known}</b><span>自评认识</span></div>
        <div class="parent-stat"><b>${rec.self_unknown}</b><span>自评不认识</span></div>
        <div class="parent-stat"><b>${rec.verified}</b><span>已答题验证</span></div>
        <div class="parent-stat"><b>${rec.overconfident}</b><span>高估字</span></div>
        <div class="parent-stat"><b>${rec.due}</b><span>今天待复习</span></div>
      </div>
      <p class="panel-hint" style="margin-top:12px">
        自评认识但第一次答错的字会列为「高估」，优先复习。
        ${rec.today_attempts ? `今天认字复习 ${rec.today_attempts} 题，正确率 ${rec.today_accuracy}%。` : "今天还没有认字复习答题。"}
      </p>
      ${
        over.length
          ? `<div class="recognition-parent-list"><b>高估字</b><div class="word-chips">${over.map((item) => charChip(item.char, "family-chip")).join("")}</div></div>`
          : ""
      }
      ${
        under.length
          ? `<div class="recognition-parent-list"><b>低估字</b><div class="word-chips">${under.map((item) => charChip(item.char, "family-chip")).join("")}</div></div>`
          : ""
      }
    `,
    "自评认识 / 不认识，和实际答题结果分开记录。",
  );
}

function renderParent() {
  if (!state.parent) {
    if (!state.parentLoading) {
      state.parentLoading = true;
      loadParent().finally(() => {
        state.parentLoading = false;
      });
    }
    return loadingScreen("正在读学习记录…");
  }

  const { stats, weak, weekly } = state.parent;
  const settings = state.boot.settings;

  const weakHtml = weak.length
    ? `<div class="weak-list">${weak
        .map(
          (item) => `
            <button class="weak-row" data-action="open-char" data-char="${esc(item.char)}">
              <span class="wc">${esc(item.char)}</span>
              <span class="wm"><b>${esc(item.pinyin)} · ${esc(item.lesson)}</b><span>答 ${item.attempts} 次 · 错 ${item.wrong} 次</span></span>
              <span class="wr">${item.wrong ? `错 ${item.wrong}` : "—"}</span>
            </button>
          `,
        )
        .join("")}</div>`
    : `<p style="margin:0;color:var(--ink-faint);font-size:14px">${stats.learned ? "还没有易错字，继续保持。" : "还没有答题记录，先学一组吧。"}</p>`;

  const settingsHtml = `
      <div class="setting-row">
        <label for="new-per-day">每天新字 <span class="hint">建议 3–6 个</span></label>
        <div style="display:flex;align-items:center;gap:10px">
          <input id="new-per-day" type="range" min="1" max="10" value="${settings.new_per_day}" />
          <b id="npd-value" style="font-variant-numeric:tabular-nums">${settings.new_per_day}</b>
        </div>
      </div>
      <div class="setting-row">
        <label for="sound-setting">声音</label>
        <input id="sound-setting" type="checkbox" ${settings.sound ? "checked" : ""} />
      </div>
      <div class="setting-row">
        <label for="auto-play-setting">自动播放读音 <span class="hint">点开字卡时自动读</span></label>
        <input id="auto-play-setting" type="checkbox" ${settings.auto_play_audio !== false ? "checked" : ""} />
      </div>
      <div class="setting-row">
        <label for="reduce-motion-setting">减少动效 <span class="hint">关闭动画和过渡</span></label>
        <input id="reduce-motion-setting" type="checkbox" ${settings.reduce_motion ? "checked" : ""} />
      </div>
      <p style="margin:10px 0 0;color:var(--ink-faint);font-size:12px">
        每天的学习量封顶在 10–12 分钟。复习多的时候，新字会自动减少。
      </p>
  `;

  const dataHtml = `
      <p style="margin:0 0 10px;color:var(--ink-soft);font-size:13px">
        学习记录在 <code>data/stats.db</code>，字表在 <code>data/content.db</code>。可以随时备份，不上传网络。
      </p>
      <div class="link-row">
        ${linkButton("/api/export/attempts.csv", "导出答题 CSV")}
        ${linkButton("/api/backup/stats", "备份学习记录")}
        ${linkButton("/api/backup/content", "备份字库")}
        <button class="danger-btn" data-action="reset">清空进度</button>
      </div>
  `;

  return `
    ${sectionHead("家长看板", "数据只在本机", { style: "margin-top:8px" })}

    <section class="parent-grid">
      <div class="parent-stat"><b>${stats.learned}</b><span>学过 / ${stats.total}</span></div>
      <div class="parent-stat"><b>${stats.mastered}</b><span>已掌握</span></div>
      <div class="parent-stat"><b>${stats.accuracy}%</b><span>今日正确率</span></div>
      <div class="parent-stat"><b>${stats.streak}</b><span>连续学习天数</span></div>
    </section>

    ${panel("最近 7 天", weekly ? weeklyChart(weekly) : '<p class="panel-hint">暂时读不到周报。</p>')}

    ${badgesHtml()}

    ${recognitionParentHtml(state.parent.recognition)}

    ${panel("易错字", weakHtml)}

    ${panel("学习设置", settingsHtml)}

    ${panel(
      "使用说明",
      `<div class="link-row">${linkButton("/manual.html", "打开家长使用手册", 'target="_blank" rel="noopener"')}</div>`,
      "第一次用，或者想看看每个按钮是做什么的，可以打开家长手册。",
    )}

    ${panel("数据", dataHtml)}
  `;
}

async function loadParent() {
  try {
    const [summary, progress, weekly] = await Promise.all([
      api.stats(),
      api.progress(),
      api.weekly().catch(() => null),
    ]);
    state.parent = { ...summary, progress, weekly };
    if (summary.settings) state.boot.settings = summary.settings;
    if (state.route === "parent") render();
  } catch (error) {
    state.error = error.message;
    render();
  }
}

async function resetProgress() {
  if (!confirm("确定要清空所有学习进度吗？答题记录也会删除。")) return;
  if (!confirm("真的确定吗？这个操作不能撤销。")) return;
  try {
    await api.reset();
    state.parent = null;
    state.session = null;
    state.quiz = null;
    state.recognitionRun = null;
    await refreshBoot();
    toast("已经清空，重新开始吧");
    navigate("home");
  } catch (error) {
    toast(`清空失败：${error.message}`);
  }
}

/* ---------------- 弹层 ---------------- */

function renderModal() {
  if (!state.modal) return "";

  if (state.modal.type === "lesson") {
    const lesson = lessonDetail(state.modal.lessonId);
    if (!lesson) return "";
    return `
      <div class="modal-overlay" data-modal-overlay>
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="${esc(lesson.title)}">
          <button class="modal-close" data-action="close-modal" aria-label="关闭">×</button>
          <h2 style="font-family:var(--kai);margin:4px 0 2px">${esc(lesson.title)}</h2>
          <p style="margin:0 0 4px;color:var(--ink-soft);font-size:13px">学过 ${lesson.learned} / ${lesson.total}</p>
          <p style="margin:0 0 14px;color:var(--ink-faint);font-size:12px">同一个字在多课出现时，只算第一次出现的那一课；绿色字表示已经在别处学过。</p>
          <div class="card-grid">${lesson.chars.map(charCard).join("")}</div>
        </div>
      </div>
    `;
  }

  if (state.modal.type === "char") {
    const item = findChar(state.modal.char);
    if (!item) return "";
    return `
      <div class="modal-overlay" data-modal-overlay>
        <div class="modal-card char-modal" role="dialog" aria-modal="true" aria-label="${esc(item.char)} 字卡">
          <button class="modal-close" data-action="close-modal" aria-label="关闭">×</button>
          <div class="char-modal-side">
            ${charIdentityHtml(item)}
          </div>
          <div class="char-modal-main">
            ${charInfoBlocksHtml(item, {
              extra: `${charFamilyHtml(item.char)}${charRadicalFamilyHtml(item.char)}${charPolyHtml(item.char)}`,
              showProgress: true,
            })}
          </div>
          <div class="action-row char-modal-actions">
            <button class="ghost-btn" data-action="replay-detail" data-char="${esc(item.char)}">听读音</button>
            <button class="primary-btn small" data-action="close-modal">知道啦</button>
          </div>
        </div>
      </div>
    `;
  }

  return "";
}

/* ---------------- 渲染 ---------------- */

function render() {
  if (state.loading) {
    app.innerHTML = loadingScreen();
    return;
  }
  if (state.error) {
    app.innerHTML = shell(errorScreen(state.error), "home");
    return;
  }

  const route = state.route;
  let content = "";
  let active = "home";
  let showNav = true;

  if (route === "session") {
    content = renderSession();
    showNav = false;
  } else if (route === "cards") {
    content = renderCards();
    active = "cards";
  } else if (route === "read") {
    content = renderRead();
    active = "read";
  } else if (route === "parent") {
    content = renderParent();
    active = "parent";
  } else if (route === "recognition") {
    content = renderRecognition();
    active = "recognition";
  } else if (route === "recognition-run") {
    content = renderRecognitionRun();
    active = "recognition";
    showNav = false;
  } else if (route === "recognition-edit") {
    content = renderRecognitionEdit();
    active = "recognition";
    showNav = false;
  } else if (route === "recognition-print") {
    content = renderRecognitionPrint();
    active = "recognition";
    showNav = false;
  } else {
    state.route = "home";
    content = renderHome();
  }

  app.innerHTML = shell(content, active, showNav) + renderModal() + renderRest();
  if (state.modal) {
    // 弹层内容比一屏长，打开时从顶部开始，先看到大字。
    requestAnimationFrame(() => {
      const modal = document.querySelector(".modal-card");
      if (modal) modal.scrollTop = 0;
    });
  }
}

/* ---------------- 事件 ---------------- */

function setSound(value) {
  if (state.boot) state.boot.settings.sound = Boolean(value);
  audio.setEnabled(Boolean(value));
  api.saveSettings({ sound: Boolean(value) }).catch((error) => toast(error.message));
  render();
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    navigate(nav.dataset.nav);
    return;
  }

  const actionEl = event.target.closest("[data-action]");
  if (!actionEl) {
    if (event.target.hasAttribute?.("data-modal-overlay")) {
      state.modal = null;
      render();
    }
    return;
  }

  const action = actionEl.dataset.action;
  if (action !== "speak-line") stopLineSpeech();
  switch (action) {
    case "start-session":
      startSession();
      break;
    case "open-recognition":
      navigate("recognition");
      break;
    case "open-recognition-edit":
      navigate("recognition-edit");
      break;
    case "recognition-set-report":
      updateRecognitionReport(actionEl.dataset.char, actionEl.dataset.report);
      break;
    case "open-recognition-print":
      navigate("recognition-print");
      break;
    case "back-recognition":
      navigate("recognition");
      break;
    case "print-recognition":
      window.print();
      break;
    case "toggle-print-over":
      state.printIncludeOver = Boolean(actionEl.checked);
      render();
      break;
    case "toggle-print-pinyin":
      state.printShowPinyin = Boolean(actionEl.checked);
      render();
      break;
    case "toggle-print-words":
      state.printShowWords = Boolean(actionEl.checked);
      render();
      break;
    case "continue-recognition": {
      const active = state.boot?.recognition?.active_run;
      if (active) openRecognitionRun(active.scope, false);
      else navigate("recognition");
      break;
    }
    case "start-recognition-run": {
      const scope = actionEl.dataset.scope;
      const restart = actionEl.dataset.restart === "true";
      if (restart && !confirm("重新开始一轮吗？当前未完成的过字会结束，这些字的自评和复习时间会重置。")) break;
      if (scope) openRecognitionRun(scope, restart);
      break;
    }
    case "recognition-report":
      reportRecognition(actionEl.dataset.report);
      break;
    case "close-recognition-run":
      navigate("recognition");
      break;
    case "start-recognition-review":
      startRecognitionReview();
      break;
    case "close-session":
      closeSession();
      break;
    case "toggle-sound": {
      const current = state.boot?.settings?.sound !== false;
      setSound(!current);
      break;
    }
    case "retry":
      init();
      break;
    case "open-lesson":
      state.modal = { type: "lesson", lessonId: actionEl.dataset.lesson };
      render();
      break;
    case "select-home-book": {
      const bookId = actionEl.dataset.book;
      if (bookId && (bookId === "all" || bookById(bookId))) {
        state.ui.homeBookId = bookId;
        saveUi();
        render();
      }
      break;
    }
    case "select-card-book": {
      const bookId = actionEl.dataset.book;
      if (bookId && (bookId === "all" || bookById(bookId))) {
        state.ui.cardBookId = bookId;
        state.ui.cardUnitId = null; // 切册后重新选默认单元
        saveUi();
        render();
      }
      break;
    }
    case "select-card-unit": {
      const unitId = actionEl.dataset.unit;
      state.ui.cardUnitId = unitId;
      saveUi();
      render();
      break;
    }
    case "select-read-book": {
      const bookId = actionEl.dataset.book;
      if (bookId && (bookId === "all" || bookById(bookId))) {
        state.ui.readBookId = bookId;
        saveUi();
        render();
      }
      break;
    }
    case "select-radical":
      selectRadical(actionEl.dataset.radical);
      break;
    case "open-char":
      state.modal = { type: "char", char: actionEl.dataset.char };
      render();
      ensurePolyphonic();
      if (autoPlayOn()) {
        const item = findChar(state.modal.char);
        if (item) audio.speakChar(item.char, item.audio_key);
      }
      break;
    case "close-modal":
      state.modal = null;
      render();
      break;
    case "toggle-pinyin": {
      const item = currentItem();
      if (item) {
        item.showPinyin = item.showPinyin === false;
        render();
      }
      break;
    }
    case "replay-learn": {
      const item = currentItem();
      if (item) {
        stopAudioChain();
        audio.speakChar(item.char, item.audio_key);
      }
      break;
    }
    case "replay-quiz": {
      const item = currentItem();
      if (item) audio.speakChar(item.char, item.audio_key);
      break;
    }
    case "replay-detail": {
      const item = findChar(actionEl.dataset.char);
      if (item) audio.speakChar(item.char, item.audio_key);
      break;
    }
    case "speak-word":
      stopAudioChain();
      audio.speak(actionEl.dataset.word);
      break;
    case "speak-poly":
      audio.speakChar(actionEl.dataset.char, actionEl.dataset.audio || undefined);
      break;
    case "print-cards":
      window.print();
      break;
    case "learn-next":
      advanceLearn(currentItem());
      break;
    case "answer":
      answerQuestion(actionEl.dataset.value);
      break;
    case "next-item":
      nextItem();
      break;
    case "rest-done":
      dismissRest();
      break;
    case "open-reading":
      state.readingId = actionEl.dataset.reading;
      render();
      break;
    case "back-readings":
      state.readingId = null;
      render();
      break;
    case "speak-read-char": {
      const char = actionEl.dataset.char;
      const item = findChar(char);
      const audioKey = actionEl.dataset.audio || item?.audio_key;
      if (audioKey) audio.speakChar(char, audioKey);
      else audio.speak(char);
      break;
    }
    case "speak-line":
      speakLine(actionEl.dataset.line);
      break;
    case "toggle-read-pinyin":
      state.ui.readPinyin = state.ui.readPinyin === false;
      saveUi();
      render();
      break;
    case "reset":
      resetProgress();
      break;
    default:
      break;
  }
});

/* ---------------- 键盘操作 ---------------- */

/* 方向键移动选项焦点，回车确认/前进，Esc 关弹窗。输入框聚焦时不抢按键。 */
document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const tag = event.target?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

  if (state.rest) {
    if (event.key === "Enter" || event.key === "Escape") {
      event.preventDefault();
      dismissRest();
    }
    return;
  }

  if (state.modal) {
    if (event.key === "Enter" || event.key === "Escape") {
      event.preventDefault();
      state.modal = null;
      render();
    }
    return;
  }

  if (state.route === "recognition-print" || state.route === "recognition-edit") {
    if (event.key === "Escape") {
      event.preventDefault();
      navigate("recognition");
    }
    return;
  }

  if (state.route === "recognition-run") {
    if (state.recognitionSubmitting) return;
    if (event.key === "Escape") {
      event.preventDefault();
      navigate("recognition");
    } else if (event.key === "ArrowLeft" || event.key === "1") {
      event.preventDefault();
      reportRecognition("known");
    } else if (event.key === "ArrowRight" || event.key === "2") {
      event.preventDefault();
      reportRecognition("unknown");
    }
    return;
  }

  if (state.route !== "session" || !state.session) return;

  if (state.session.finished) {
    if (event.key === "Enter") {
      event.preventDefault();
      startSession();
    }
    return;
  }

  const item = currentItem();
  if (!item) return;

  if (item.stage === "learn") {
    if (event.key === "Enter") {
      event.preventDefault();
      advanceLearn(item);
    }
    return;
  }

  const quiz = state.quiz;
  if (!quiz || !quiz.options?.length) return;
  const count = quiz.options.length;

  if (!quiz.answered) {
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      event.preventDefault();
      quiz.kbdIndex = quiz.kbdIndex < 0 ? 0 : (quiz.kbdIndex + 1) % count;
      render();
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      event.preventDefault();
      quiz.kbdIndex = quiz.kbdIndex < 0 ? count - 1 : (quiz.kbdIndex - 1 + count) % count;
      render();
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (quiz.kbdIndex < 0) return; // 还没选，回车不答题
      const option = quiz.options[quiz.kbdIndex];
      if (option) answerQuestion(option.value);
    }
  } else if (event.key === "Enter") {
    event.preventDefault();
    nextItem();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "new-per-day") {
    const label = document.getElementById("npd-value");
    if (label) label.textContent = event.target.value;
    return;
  }
  if (event.target.id === "recognition-edit-search") {
    const value = event.target.value;
    clearTimeout(recognitionEditSearchTimer);
    recognitionEditSearchTimer = setTimeout(() => loadRecognitionEdit(value), 250);
  }
});

document.addEventListener("change", async (event) => {
  if (event.target.id === "radical-select") {
    selectRadical(event.target.value);
    return;
  }
  if (event.target.id === "new-per-day") {
    const value = Number(event.target.value);
    if (state.boot) state.boot.settings.new_per_day = value;
    try {
      await api.saveSettings({ new_per_day: value });
      toast(`每天新字：${value} 个`);
    } catch (error) {
      toast(error.message);
    }
  }
  if (event.target.id === "sound-setting") {
    setSound(event.target.checked);
  }
  if (event.target.id === "auto-play-setting") {
    const value = event.target.checked;
    if (state.boot) state.boot.settings.auto_play_audio = value;
    api
      .saveSettings({ auto_play_audio: value })
      .then(() => toast(value ? "点开字卡会自动读" : "已改为手动点读"))
      .catch((error) => toast(error.message));
  }
  if (event.target.id === "reduce-motion-setting") {
    const value = event.target.checked;
    if (state.boot) state.boot.settings.reduce_motion = value;
    applyReduceMotion();
    api
      .saveSettings({ reduce_motion: value })
      .then(() => toast(value ? "已减少动效" : "已恢复动效"))
      .catch((error) => toast(error.message));
  }
});

window.addEventListener("hashchange", () => {
  state.route = routeFromHash();
  if (state.route !== "session") {
    clearRestTimer();
    stopRestTicker();
    state.rest = null;
  }
  if (state.route === "session" && !state.session) {
    navigate("home");
    return;
  }
  if (state.route === "recognition-run" && !state.recognitionRun) {
    navigate("recognition");
    return;
  }
  if (state.route === "recognition") {
    // 认字总览每次进入都刷新一次，避免另一轮刚结束还显示旧进度。
    refreshBoot().then(() => {
      if (state.route === "recognition") render();
    });
    return;
  }
  if (state.route === "recognition-edit") {
    state.recognitionEdit = null;
    state.recognitionEditError = null;
    state.recognitionEditQuery = "";
    render();
    return;
  }
  if (
    (state.route === "home" || state.route === "cards") &&
    (state.bootDirty || (state.session && !state.session.finished))
  ) {
    // 从学习页返回时，首页/字卡册的进度可能已经变了，重新拉一次。
    refreshBoot().then(() => {
      if (state.route === "home" || state.route === "cards") render();
    });
    return;
  }
  render();
});

/* ---------------- 启动 ---------------- */

async function init() {
  state.loading = true;
  state.error = null;
  Object.assign(state.ui, loadUi());
  render();
  try {
    state.boot = await api.bootstrap();
    audio.setEnabled(state.boot.settings.sound !== false);
    applyReduceMotion();
    // 校验记住的册/单元还存在（CSV 改动可能换 id）。
    const validBooks = new Set(["all", ...books().map((book) => book.id)]);
    if (!validBooks.has(state.ui.homeBookId)) state.ui.homeBookId = books()[0]?.id || "1a";
    if (!validBooks.has(state.ui.cardBookId)) state.ui.cardBookId = books()[0]?.id || "1a";
    if (!validBooks.has(state.ui.readBookId)) state.ui.readBookId = "all";
    const units = cardUnits();
    if (state.ui.cardUnitId && !units.some((unit) => unit.id === state.ui.cardUnitId)) {
      state.ui.cardUnitId = null;
    }
    if (!location.hash) history.replaceState(null, "", "#/home");
    state.route = routeFromHash();
    if (state.route === "session" && !state.session) state.route = "home";
    if (state.route === "recognition-run") state.route = "recognition";
    state.loading = false;
    render();
  } catch (error) {
    state.loading = false;
    state.error = error.message;
    render();
  }
}

init();
