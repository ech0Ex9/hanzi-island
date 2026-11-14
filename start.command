#!/bin/bash
# 汉字小岛 · macOS 启动脚本
# 双击运行：检查进程/端口 → 启动本地服务 → 打开浏览器

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

PORT_START=8765
PORT_END=8775
PID_FILE="$ROOT/.run/server.pid"
PORT_FILE="$ROOT/.run/server.port"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/server.log"

mkdir -p "$ROOT/.run" "$LOG_DIR"

fail_dialog() {
  local msg="$1"
  echo "$msg"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$msg\" buttons {\"好\"} default button 1" >/dev/null 2>&1 || true
  fi
}

echo "======================================"
echo "  汉字小岛 · 本地学习服务"
echo "======================================"

# 1. 已经在运行？直接打开浏览器
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    OLD_CMD="$(ps -p "$OLD_PID" -o command= 2>/dev/null || true)"
    if echo "$OLD_CMD" | grep -q "app.py"; then
      OLD_PORT="$(cat "$PORT_FILE" 2>/dev/null || echo "$PORT_START")"
      echo "服务已经在运行（PID ${OLD_PID}，端口 ${OLD_PORT}），直接打开。"
      open "http://127.0.0.1:$OLD_PORT"
      exit 0
    fi
  fi
  echo "清理旧的运行记录。"
  rm -f "$PID_FILE" "$PORT_FILE"
fi

# 2. 找 Python 和依赖
PYTHON=""
PY_VERSION_CHECK='import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'

if command -v python3 >/dev/null 2>&1 \
  && python3 -c "$PY_VERSION_CHECK" >/dev/null 2>&1 \
  && python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  PYTHON="python3"
elif [ -x "$ROOT/.venv/bin/python" ] \
  && "$ROOT/.venv/bin/python" -c "$PY_VERSION_CHECK" >/dev/null 2>&1 \
  && "$ROOT/.venv/bin/python" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  PYTHON="$ROOT/.venv/bin/python"
else
  echo "没有找到可用的 FastAPI/uvicorn，正在创建 .venv 并安装依赖…"
  if ! command -v python3 >/dev/null 2>&1; then
    fail_dialog "找不到 python3。请先安装 Python 3.9 或更新版本：https://www.python.org/downloads/macos/（也可以在终端运行 xcode-select --install）"
    exit 1
  fi
  if ! python3 -c "$PY_VERSION_CHECK" >/dev/null 2>&1; then
    fail_dialog "Python 3 版本太旧，需要 3.9 或更新版本。请到 https://www.python.org/downloads/macos/ 安装新版 Python 3。"
    exit 1
  fi
  python3 -m venv "$ROOT/.venv" || {
    fail_dialog "创建 .venv 失败，请查看终端输出。"
    exit 1
  }
  "$ROOT/.venv/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
  if ! "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"; then
    fail_dialog "安装依赖失败。第一次安装需要联网，请检查网络后重试。"
    exit 1
  fi
  PYTHON="$ROOT/.venv/bin/python"
fi

# 3. 找一个空闲端口
find_free_port() {
  local p
  for p in $(seq "$PORT_START" "$PORT_END"); do
    if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

PORT="$(find_free_port)" || {
  fail_dialog "端口 $PORT_START-$PORT_END 都被占用了，请先关闭其他程序。"
  exit 1
}

# 4. 启动服务
echo "启动服务：$PYTHON app.py --port $PORT"
nohup "$PYTHON" "$ROOT/app.py" --port "$PORT" >>"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" >"$PID_FILE"
echo "$PORT" >"$PORT_FILE"

# 5. 等健康检查
for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "启动成功：http://127.0.0.1:$PORT"
    open "http://127.0.0.1:$PORT"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 0.2
done

# 6. 失败：清理并提示
kill "$PID" >/dev/null 2>&1 || true
rm -f "$PID_FILE" "$PORT_FILE"
echo "启动失败，日志最后 20 行："
tail -n 20 "$LOG_FILE" 2>/dev/null || true
fail_dialog "汉字小岛启动失败，请查看 logs/server.log。"
exit 1
