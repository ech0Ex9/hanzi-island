#!/bin/bash
# 汉字小岛 · 停止本地服务
# 只停止 start.command 记录的那个进程，不会误杀别的 Python 程序。

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.run/server.pid"
PORT_FILE="$ROOT/.run/server.port"

if [ ! -f "$PID_FILE" ]; then
  echo "没有找到运行记录，服务可能已经停止。"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${PID:-}" ] || ! kill -0 "$PID" 2>/dev/null; then
  echo "进程已经不在，清理运行记录。"
  rm -f "$PID_FILE" "$PORT_FILE"
  exit 0
fi

CMD="$(ps -p "$PID" -o command= 2>/dev/null || true)"
if ! echo "$CMD" | grep -q "app.py"; then
  echo "PID $PID 不是本项目的 app.py，已停止操作，只清理记录。"
  rm -f "$PID_FILE" "$PORT_FILE"
  exit 0
fi

echo "正在停止汉字小岛（PID ${PID}）…"
kill "$PID" 2>/dev/null || true
for _ in $(seq 1 25); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "已停止。"
    rm -f "$PID_FILE" "$PORT_FILE"
    exit 0
  fi
  sleep 0.2
done

echo "进程没有在 5 秒内退出，强制结束。"
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE" "$PORT_FILE"
echo "已停止。"
