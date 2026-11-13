// 通用展示组件：不依赖应用状态，学习页、字卡册、弹窗、家长页共用。
// 只负责把数据转成 HTML；状态查询和事件处理留在 app.js。

import { PICTOGRAPHS } from "./pictographs.js?v=3";

export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function highlightChar(text, char) {
  if (!text || !char) return esc(text || "");
  const parts = String(text).split(char);
  return parts.map((part) => esc(part)).join(`<span class="target">${esc(char)}</span>`);
}

export function masteryLabel(mastery) {
  return {
    new: "新字",
    learning: "学习中",
    familiar: "熟悉",
    mastered: "掌握",
  }[mastery] || "新字";
}

/* 统一的「标签 + 内容」块：字卡、学习页、弹窗共用。 */
export function infoBlock(label, inner) {
  return `<div class="info-block"><span class="info-label">${esc(label)}</span>${inner}</div>`;
}

export function metaChip(text) {
  return `<span class="meta-chip">${esc(text)}</span>`;
}

/* 打开字卡的 chip：字族、同部首、多音字补充共用。 */
export function charChip(char, className = "word-chip") {
  return `<button class="${className}" data-action="open-char" data-char="${esc(char)}">${esc(char)}</button>`;
}

export function wordChips(words) {
  return (words || [])
    .map(
      (word) =>
        `<button class="word-chip" data-action="speak-word" data-word="${esc(word)}">${esc(word)}</button>`,
    )
    .join("");
}

/* 多音字读音按钮：字卡弹窗和字卡册面板共用。 */
export function polyReadingButton(char, reading) {
  const source = reading.source === "common" ? "补充 · " : "";
  return `
    <button class="poly-reading" data-action="speak-poly" data-char="${esc(char)}" data-audio="${esc(reading.audio_key || "")}">
      <b>${esc(reading.pinyin)}</b>
      <span>${source}${esc((reading.contexts || []).join(" / "))}</span>
    </button>
  `;
}

/* 页面小节标题：首页、字卡册、读一读、家长页共用。 */
export function sectionHead(title, meta = "", { small = false, style = "" } = {}) {
  return `
    <div class="section-head"${style ? ` style="${style}"` : ""}>
      <h2${small ? ' style="font-size:18px"' : ""}>${esc(title)}</h2>
      <span>${esc(meta)}</span>
    </div>
  `;
}

/* 家长页面板：统一 h3 + 说明 + 内容。 */
export function panel(title, inner, hint = "") {
  return `
    <section class="panel">
      <h3>${esc(title)}</h3>
      ${hint ? `<p class="panel-hint">${esc(hint)}</p>` : ""}
      ${inner}
    </section>
  `;
}

export function linkButton(href, label, attrs = "") {
  return `<a class="link-btn" href="${esc(href)}"${attrs ? ` ${attrs}` : ""}>${esc(label)}</a>`;
}

/* 象形字：古字 SVG → 今字。没在图集里的字返回空。 */
export function pictographHtml(char) {
  const pict = PICTOGRAPHS[char];
  if (!pict) return "";
  return infoBlock(
    "字形演变",
    `<div class="pictograph-row">
        <div class="pictograph-cell ancient">${pict.ancient}</div>
        <span class="pictograph-arrow">→</span>
        <div class="pictograph-cell today"><span class="pictograph-char">${esc(char)}</span></div>
      </div>
      <p class="pictograph-note">${esc(pict.note)}</p>`,
  );
}

/* 字的大字头：学习页和字卡弹窗共用。 */
export function charIdentityHtml(item, { mode = "modal", showPinyin = true } = {}) {
  const pinyin =
    mode === "learn"
      ? `<button class="char-pinyin ${showPinyin ? "" : "hidden"}" data-action="toggle-pinyin">
          ${showPinyin ? esc(item.pinyin) : "点一下显示拼音"}
        </button>`
      : `<div class="char-pinyin">${esc(item.pinyin)}</div>`;
  const lastMeta = mode === "learn" ? item.origin || "—" : masteryLabel(item.progress?.mastery);
  return `
    <div class="char-stage"><div class="char-glyph">${esc(item.char)}</div></div>
    ${pinyin}
    <div class="char-meta">
      ${metaChip(`${item.radical || "—"}部`)}
      ${metaChip(`${item.strokes || "—"}画`)}
      ${metaChip(item.structure || "—")}
      ${metaChip(lastMeta)}
    </div>
  `;
}

/* 字的内容块：学习页显示形近字，弹窗显示学习记录，其余共用。 */
export function charInfoBlocksHtml(
  item,
  { extra = "", showConfusions = false, showProgress = false } = {},
) {
  return `
    ${item.meaning ? infoBlock("意思", `<div class="info-text">${esc(item.meaning)}</div>`) : ""}
    ${pictographHtml(item.char)}
    ${extra}
    ${item.words?.length ? infoBlock("组词", `<div class="word-chips">${wordChips(item.words)}</div>`) : ""}
    ${item.sentence ? infoBlock("句子", `<div class="sentence-line">${highlightChar(item.sentence, item.char)}</div>`) : ""}
    ${item.mnemonic ? infoBlock("记忆口诀", `<div class="info-text soft">${esc(item.mnemonic)}</div>`) : ""}
    ${
      showConfusions && item.confusions?.length
        ? infoBlock(
            "形近字",
            `<div class="info-text soft">${item.confusions.map((c) => esc(c)).join("、")}</div>`,
          )
        : ""
    }
    ${
      showProgress && item.progress?.attempts
        ? infoBlock(
            "学习记录",
            `<div class="info-text soft">见过 ${item.progress?.exposures || 0} 次 · 对 ${item.progress?.correct || 0} · 错 ${item.progress?.wrong || 0}</div>`,
          )
        : ""
    }
  `;
}
