#!/usr/bin/env python3
"""汉字小岛 · 本地服务入口。

双击 start.command 启动；也可以手动运行：
    python3 app.py --port 8765
"""

from __future__ import annotations

import argparse
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from server.db import init_db
from server.routes import router

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="汉字小岛", version=APP_VERSION, lifespan=lifespan)
# bootstrap 约 430KB；本地虽快，压缩后约 100KB，也方便以后放 iPad。
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(router)


@app.middleware("http")
async def revalidate_assets(request, call_next):
    """JS/CSS 每次重新验证，避免 ES module 子文件被浏览器长期缓存。"""
    response = await call_next(request)
    if request.url.path.startswith(("/js/", "/css/")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


def asset_version() -> str:
    """用前端文件的最新修改时间做缓存戳，改 js/css 后刷新页面即可生效。"""
    files = list((WEB_DIR / "js").glob("*.js")) + list((WEB_DIR / "css").glob("*.css"))
    latest = max((path.stat().st_mtime_ns for path in files), default=time.time_ns())
    return str(latest)


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(
        html.replace("__ASSET_VERSION__", asset_version()),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="汉字小岛本地服务")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8765")),
        help="监听端口，默认 8765",
    )
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
