"""

    Minecraft Bot Server
    1. 初始化服务器后，注册机器人
    2. 机器人向服务器发送聊天记录，服务器返回下一步动作序列

"""
from fastapi import FastAPI, Path
from Decision.server import init_server, plan, saveSkill, reflect
import Decision.server as server
from pydantic import BaseModel,Field
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import uuid
import datetime
from utils import trace_id_var, get_logger
from config import settings
import json
from fastapi.responses import JSONResponse

_logger = None  # 模块级日志记录器，启动时初始化一次
_bots = {}  # 存储注册的机器人状态，键为 bot_id，值为状态字典
GLOBAL_LLM_SEMAPHORE = asyncio.Semaphore(settings.fastapi.global_llm_semaphore) # 限制同时进行的 LLM 调用数量


class ChatRequest(BaseModel):
    user: str = Field(..., description="用户名称")
    chatHistory: list[str] = Field(..., description="聊天历史记录")
    skillprogress: Optional[str] = Field(None, description="技能进度，JSON 字符串",example=[None])
    status: dict[str, str] = Field(..., description="机器人状态")
    trace_id: Optional[str] = Field(None, description="请求追踪 ID，用于日志追踪",example=[None])

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _logger
    _logger = get_logger("aip.fastapi", settings.logging.fastapi_log_path,
                         settings.logging.log_level, settings.logging.log_backup_count)
    server._llm,stat = await init_server()
    yield

app = FastAPI(title="Minecraft Bot Server", lifespan=lifespan)

@app.middleware("http")
async def response_middleware(request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    token = trace_id_var.set(trace_id)
    start_time = datetime.datetime.now()
    bot = request.path_params.get("bot_id", "unknown")  # 获取 bot_id，如果没有则为 "unknown"
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        actions = [{"name": "Chat", "args": {"message": f"[error] 请求处理异常: {e}"}}]
        res = {"actions": actions, "continue": False, "skill_progress": None}
        response = JSONResponse(content=json.dumps(res), status_code=500, media_type="application/json")
        return response
    finally:
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        response_time = round(response_time, 2)
        content = "请求处理成功" if response.status_code == 200 else f"请求处理失败: {response.status_code}"
        _logger.info(content,
                    extra={"trace_id": trace_id,
                           "response_time": response_time, 
                           "bot": bot,
                           "status_code": response.status_code,})

        response.headers["X-Trace-ID"] = trace_id  # 将 trace_id 添加到响应头中
        trace_id_var.reset(token)  # 清除 trace_id，避免影响后续请求

@app.post("/register")
async def register(data: dict):
    bid = str(data.get("bot_id"))
    _bots[bid] = {"status": "alive"}
    return {"ok": True}

@app.post("/unregister")
async def unregister(data: dict):
    bid = str(data.get("bot_id"))
    if bid in _bots:
        _bots[bid] = {"status": "offline"}
    return {"ok": True}

@app.post("/plan/{bot_id}")
async def plan_for_bot(request: ChatRequest, bot_id: int = Path(..., ge=1, le=3)):
    async with GLOBAL_LLM_SEMAPHORE:
        return await plan(request.chatHistory, request.skillprogress, request.status)

@app.post("/reflect/{bot_id}")
async def reflect_for_bot(request: ChatRequest, bot_id: int = Path(..., ge=1, le=3)):
    async with GLOBAL_LLM_SEMAPHORE:
        return await reflect(request.chatHistory)

@app.post("/saveSkill/{bot_id}")
async def save_skill_for_bot(request: ChatRequest, skill_name: str, bot_id: int = Path(..., ge=1, le=3)):
    async with GLOBAL_LLM_SEMAPHORE:
        return await saveSkill(request.chatHistory, skill_name)

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}
