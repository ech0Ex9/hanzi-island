# 拼音音节音频

这些 mp3 来自开源仓库：

- 仓库：https://github.com/davinfifield/mp3-chinese-pinyin-sound
- 内容：普通话拼音音节（带声调）的 MP3
- 许可证：Unlicense（public domain）

文件名就是 `audio_key`，例如 `ri4.mp3`、`tian1.mp3`。当前共 505 个音节文件（约 10 MB），覆盖 2024/2025 新版一上下两册识字表全部引用音节（十和石共用 `shi2.mp3`）。

- 497 个文件来自上述开源仓库（Unlicense，公有领域）。
- 8 个轻声文件（me5、men5、zhe5、a5、ba5、la5、na5、ya5）来自百度汉语拼音音节 CDN，开源库缺失而补录，仅建议个人/家用；若要商业发行请自行录制或用商业 TTS 重新生成。

继续扩字时运行：

```bash
python3 tools/fetch_pinyin_audio.py
```

说明：这是**拼音音节**音频，不是整字朗读。单字听读音优先播放它；词语和句子仍由系统 TTS 兜底，因此语气更自然。若音频加载失败，前端会自动退回系统语音。
