// 语音：
// 1) 单字优先播放 mp3-chinese-pinyin-sound 的拼音音节音频（public domain）；
// 2) 词语、句子、以及 mp3 加载失败时，退回系统 Web Speech API。

let enabled = true;
let voices = [];
let audioContext = null;
let currentAudio = null;
const audioCache = new Map();

const PINYIN_AUDIO_BASE = "/assets/audio/pinyin";

function loadVoices() {
  if (!("speechSynthesis" in window)) return;
  voices = window.speechSynthesis.getVoices() || [];
}

if ("speechSynthesis" in window) {
  loadVoices();
  window.speechSynthesis.onvoiceschanged = loadVoices;
}

function pickVoice() {
  if (!voices.length) loadVoices();
  const zh = voices.filter((v) => (v.lang || "").toLowerCase().startsWith("zh"));
  if (!zh.length) return null;
  return (
    zh.find((v) => /tingting|ting-ting|meijia|mei-jia|sinji|huihui|yaoyao/i.test(v.name)) ||
    zh.find((v) => v.lang === "zh-CN") ||
    zh[0]
  );
}

function stopSpeech() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

function stopCurrentAudio() {
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch (_) {
      /* ignore */
    }
    currentAudio = null;
  }
}

export function setEnabled(value) {
  enabled = Boolean(value);
  if (!enabled) stop();
}

export function isEnabled() {
  return enabled;
}

export function stop() {
  stopSpeech();
  stopCurrentAudio();
}

export function speak(text, options = {}) {
  if (!enabled || !text) return;
  if (!("speechSynthesis" in window)) return;
  stop();
  const utter = new SpeechSynthesisUtterance(String(text));
  utter.lang = "zh-CN";
  utter.rate = options.rate ?? 0.82;
  utter.pitch = options.pitch ?? 1;
  utter.volume = options.volume ?? 0.95;
  if (typeof options.onEnd === "function") utter.onend = options.onEnd;
  const voice = pickVoice();
  if (voice) utter.voice = voice;
  window.speechSynthesis.speak(utter);
}

/**
 * 读一个单字。
 * @param {string} char 汉字
 * @param {string} [audioKey] 例如 tian1 / ri4，对应拼音音节 mp3
 * @param {Function} [onEnd] 播放结束（或失败回退结束）后调用
 */
export function speakChar(char, audioKey, onEnd) {
  if (!enabled || !char) return;

  if (audioKey) {
    const url = `${PINYIN_AUDIO_BASE}/${encodeURIComponent(audioKey)}.mp3`;
    let el = audioCache.get(url);
    if (!el) {
      el = new Audio(url);
      el.preload = "auto";
      audioCache.set(url, el);
    }
    if (currentAudio && currentAudio !== el) stopCurrentAudio();
    stopSpeech();
    try {
      el.currentTime = 0;
    } catch (_) {
      /* metadata not ready yet */
    }
    el.onended = typeof onEnd === "function" ? onEnd : null;
    const promise = el.play();
    if (promise && typeof promise.catch === "function") {
      promise.catch(() => speak(char, { rate: 0.72, onEnd }));
    }
    currentAudio = el;
    return;
  }

  speak(char, { rate: 0.72, onEnd });
}

export function speakSlow(text) {
  speak(text, { rate: 0.62 });
}

export function chime(ok = true) {
  if (!enabled) return;
  try {
    audioContext =
      audioContext ||
      new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === "suspended") audioContext.resume();
    const now = audioContext.currentTime;
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(ok ? 660 : 220, now);
    if (ok) osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.06, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);
    osc.connect(gain).connect(audioContext.destination);
    osc.start(now);
    osc.stop(now + 0.22);
  } catch (_) {
    /* audio is optional */
  }
}
