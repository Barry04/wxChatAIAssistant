"""FastAPI 应用组装点：挂载各功能域路由、生命周期与前端静态资源。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    automation,
    contacts,
    generate,
    imports,
    meta,
    settings,
    state,
    wechat,
)
from .services import get_runtime_settings
from .storage import FRONTEND_DIST, ensure_storage

# 兼容绑定：测试通过 main_module.AUTOMATION_WORKER 控制同一工作线程实例。
AUTOMATION_WORKER = state.AUTOMATION_WORKER


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：初始化存储与自动化工作线程，关闭时确保线程停止。"""
    ensure_storage()
    state.RUNTIME_API_KEY = get_runtime_settings().api_key
    state.AUTOMATION_WORKER.start()
    try:
        yield
    finally:
        state.AUTOMATION_WORKER.stop()


app = FastAPI(title="关系型微信聊天助手", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router_module in (meta, contacts, imports, wechat, automation, generate, settings):
    app.include_router(router_module.router)

if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/{full_path:path}")
def frontend(full_path: str):
    index = FRONTEND_DIST / "index.html"
    requested = FRONTEND_DIST / full_path
    if full_path and requested.is_file():
        return FileResponse(requested)
    if index.exists():
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    return {
        "message": "前端尚未构建，请在 frontend 目录执行 npm install 和 npm run build。"
    }
