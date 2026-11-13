# 字体资源

## lxgw-wenkai-subset.woff2

- 来源：[霞鹜文楷 LXGW WenKai](https://github.com/lxgw/LxgwWenKai)（SIL Open Font License 1.1，见同目录 `OFL.txt`）
- 用途：站内楷体字形（`--kai`），仅作网页字体，不做可安装桌面字体分发（符合 OFL 附加许可）
- 范围：`data/characters.csv` 的课内 688 字 + `data/literacy_1300.csv` 的 1300 字及释义/组词 + `data/readings.csv` + 界面文案 + 拼音声调字母 + 常用标点，共约 1872 个字符
- 体积：约 436KB（woff2）

### 重新生成子集

字表、短文、字族或界面文案有新字时（重新生成后记得把 `style.css` 和 `index.html` 里的 `?v=` 加一，避免浏览器继续用旧字体缓存）：

```bash
# 一次性准备工具
python3 -m venv /tmp/fontvenv
/tmp/fontvenv/bin/pip install fonttools brotli

# 下载原字体
curl -sL -o /tmp/LXGWWenKai-Regular.ttf \
  https://github.com/lxgw/LxgwWenKai/releases/latest/download/LXGWWenKai-Regular.ttf

# 收集用字（字表 + 短文 + 字族 + 前端文案）
python3 - <<'EOF'
import csv, glob, re
chars = set()
for path, cols in [
    ("data/characters.csv", ["char"]),
    ("data/readings.csv", ["title", "lines"]),
    ("data/families.csv", ["family", "members"]),
    ("data/polyphonic.csv", ["char", "readings"]),
]:
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for col in cols:
                chars.update(row.get(col) or "")
for path in glob.glob("web/js/*.js") + ["web/index.html"]:
    chars.update(re.findall(r"[^\x00-\x7f]", open(path, encoding="utf-8").read()))
chars.update("　★☆▶←→↑↓·—…“”‘’《》〈〉！？：；、，。（）【】＋－")
open("/tmp/fontchars.txt", "w", encoding="utf-8").write("".join(sorted(c for c in chars if c.strip())))
EOF

# 子集化
/tmp/fontvenv/bin/pyftsubset /tmp/LXGWWenKai-Regular.ttf \
  --text-file=/tmp/fontchars.txt \
  --unicodes="U+0020-007E,U+00A0-00FF,U+0100-01FF,U+2000-206F,U+2190-21FF,U+25A0-25FF,U+3000-303F,U+FF00-FFEF" \
  --flavor=woff2 \
  --output-file=web/assets/fonts/lxgw-wenkai-subset.woff2 \
  --no-hinting --desubroutinize
```
