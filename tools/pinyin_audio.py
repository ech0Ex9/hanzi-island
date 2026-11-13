"""拼音 → 音频文件名的小工具。

拼音带声调（shǔ），音频 key 用数字声调（shu3）；轻声没有声调符号，按 5 处理。
"""

from __future__ import annotations

TONE_MAP = {
    "ā": ("a", "1"), "á": ("a", "2"), "ǎ": ("a", "3"), "à": ("a", "4"),
    "ē": ("e", "1"), "é": ("e", "2"), "ě": ("e", "3"), "è": ("e", "4"),
    "ī": ("i", "1"), "í": ("i", "2"), "ǐ": ("i", "3"), "ì": ("i", "4"),
    "ō": ("o", "1"), "ó": ("o", "2"), "ǒ": ("o", "3"), "ò": ("o", "4"),
    "ū": ("u", "1"), "ú": ("u", "2"), "ǔ": ("u", "3"), "ù": ("u", "4"),
    "ǖ": ("uu", "1"), "ǘ": ("uu", "2"), "ǚ": ("uu", "3"), "ǜ": ("uu", "4"),
    "ü": ("uu", "5"),
}


def pinyin_to_audio_key(pinyin: str) -> str:
    tone = "5"
    letters: list[str] = []
    for char in pinyin:
        if char in TONE_MAP:
            base, tone = TONE_MAP[char]
            letters.append(base)
        else:
            letters.append(char)
    return "".join(letters) + tone
