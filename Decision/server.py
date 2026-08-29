from LLMAgent import LLMClient,decide,reflect_on_failure,generate_skill
import LLMAgent
from LLMData import get_all_prompts
import json
import os
from typing import Optional
from skill_manager import init_skills, build_skill_context, check_save_skill, list_all_skills, query_skill_detail
import datetime
from utils import trace_id_var, get_logger,log_server_event
from config import settings

_llm = None  # 模块级 LLM 客户端单例，启动时初始化一次
_logger = None  # 模块级日志记录器，启动时初始化一次

_logger = get_logger("aip.server", settings.logging.server_log_path,
                         settings.logging.log_level, settings.logging.log_backup_count)


async def get_llm_client() -> LLMClient:
    global _llm
    if _llm is None:
        try:
            api_key = settings.llm.openai_api_key
            url = settings.llm.model_base_url
            model_name = settings.llm.llm_model
            _llm = LLMClient(model_name=model_name, url=url, api_key=api_key,temperature=settings.llm.llm_temperature)
        except Exception as e:
            raise RuntimeError(f"初始化 LLM 客户端失败: {e}") from e
    return _llm

async def get_prompts() -> dict:
    if LLMAgent._prompts is None:
        try:
            LLMAgent._prompts = get_all_prompts()
        except Exception as e:
            raise RuntimeError(f"加载 prompts 配置失败: {e}") from e
    return LLMAgent._prompts

async def init_server():
    global _tools_path, _tools_mtime, _tools_data, _skill_summaries, _logger

    try:
        init_skills(settings.files.skill_path)
        _tools_path = settings.files.tools_path
        _tools_mtime = 0
        _tools_data = []
        await _try_reload_tools()
        _skill_summaries = list_all_skills()
        _llm = await get_llm_client()  # 初始化 LLM 客户端
        await get_prompts()  # 初始化 prompts 配置
        _logger.info(f"[server] 初始化完成，技能数量: {len(_skill_summaries)}，工具数量: {len(_tools_data)}",
                     extra={"event_type": "server_init",
                            "timestamp": datetime.datetime.now().isoformat(),
                            "trace_id": trace_id_var.get(),
                            "event_id":str(datetime.datetime.now().timestamp()),
                            "event_status":"success",})
    except Exception as e:
        _logger.info(f"[server] 初始化失败: {e}",
                     extra={"event_type": "server_init",
                            "timestamp": datetime.datetime.now().isoformat(),
                            "trace_id": trace_id_var.get(),
                            "event_id":str(datetime.datetime.now().timestamp()),
                            "event_status":"failure",})
        raise RuntimeError(f"服务器初始化失败: {e}") from e
    return _llm,{"status":"ok","message":"初始化完成"}

@log_server_event("tool_reload",_logger)
async def _try_reload_tools():
    """stat 时间戳，变了才重读 tools.json"""
    global _tools_data, _tools_mtime
    mt = os.path.getmtime(_tools_path)
    if mt > _tools_mtime:
        with open(_tools_path, "r", encoding="utf-8") as f:
            _tools_data = json.load(f)
        _tools_mtime = mt
        return f"更新成功，工具数量: {len(_tools_data)}"
    return f"未检测到更新，工具数量: {len(_tools_data)}"

def _build_status_text(status: Optional[dict]) -> str:
    """把 Node 端自动采集的 Bot 状态（GetState / GetAroundBlocks）拼成 prompt 文本"""
    if not status:
        return ""
    lines = ["当前 Bot 状态（已自动获取，除非玩家明确要求，否则不要重复调用 GetState/GetAroundBlocks）："]
    for name, detail in status.items():
        lines.append(f"- {name}: {detail}")
    return "\n".join(lines)

@log_server_event("plan",_logger)
async def excute_skill(chatHistory,skill_progress:Optional[str]="",status_text:Optional[str]="",
                       demand:Optional[str]=""):
    progress = json.loads(skill_progress) if skill_progress else None
    name = progress.get("name", "")
    next_seq = progress.get("next", 0)
    skill_detail = query_skill_detail(name)
    current_seq = skill_detail["action_sequences"][next_seq]
    used_tools = set(current_seq.get("sub_actions_seq", []))
    used_tools.add("Chat")
    tool_details = [t for t in _tools_data if t["name"] in used_tools]
    skill_context = build_skill_context(name, next_seq)
    ctx = status_text
    if ctx:
        ctx += "\n\n"
    ctx += f"你正在执行技能{name}（续行），必须严格按照技能要求输出动作，不可修改、不可跳过、不可添加额外步骤。"
    ctx += skill_context
    result = await decide(_llm, demand, chatHistory, tool_details, skill_progress, ctx)
    return result

@log_server_event("plan",_logger)
async def normal_plan(chatHistory,status_text:Optional[str]="",demand:Optional[str]=""):
    all_tools = _tools_data
    ctx = status_text
    if _skill_summaries:
        if ctx:
            ctx += "\n\n"
        lines = ["已保存技能："]
        for s in _skill_summaries:
            lines.append(f"{build_skill_context(s['name'], 0)}")
        ctx += "\n".join(lines)
    result = await decide(_llm, demand, chatHistory, all_tools, None, ctx)
    return result

@log_server_event("plan",_logger)
async def plan(chatHistory, skill_progress: Optional[str] = "", status: Optional[dict] = None):
    await _try_reload_tools()  # 工具热更新：stat 时间戳，变了就重读
    demand = chatHistory[-1]["content"] if chatHistory else ""
    chatHistory = chatHistory[:-1]  # 去掉最后一条用户输入，剩下的作为历史上下文
    status_text = _build_status_text(status)
    # ── 技能续行 ──
    if skill_progress:
        result = await excute_skill(chatHistory, skill_progress, status_text, demand)
        return result

    # ── 普通规划 ──
    result = await normal_plan(chatHistory, status_text, demand)
    return result

@log_server_event("reflect",_logger)
async def reflect(chatHistory: list) -> str:
    """反思：LLM 分析失败原因，输出到历史"""
    result = await reflect_on_failure(_llm, chatHistory)
    actions = [{"action": "Chat", "args": {"message": result}}]
    return {"actions": actions, "continue": False, "skill_progress": None}

@log_server_event("saveSkill",_logger)
async def saveSkill(chatHistory, skill_name: str) -> str:
    global _skill_summaries
    result = await generate_skill(_llm, chatHistory, skill_name)
    check_save_skill(result)
    _skill_summaries = list_all_skills()  # 更新技能索引
    actions = [{"action": "Chat", "args": {"message": f"技能 {skill_name} 已保存成功"}}]
    return {"actions": actions, "continue": False, "skill_progress": None}