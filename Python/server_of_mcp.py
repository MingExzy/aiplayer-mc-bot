from fastmcp import FastMCP
import json
import os
from skill_manager import init as init_skills, build_skill_context, check_save_skill, list_all_skills, query_skill_detail

script_dir = os.path.dirname(os.path.abspath(__file__))
init_skills(os.path.join(script_dir, "skills"))

# ── 加载 tools.json ──
_tools_path = os.path.join(script_dir, "..", "tools.json")
with open(_tools_path, "r", encoding="utf-8") as f:
    _tools_data = json.load(f)
print(f"加载了 {len(_tools_data)} 个原子工具")

_skill_summaries = list_all_skills()
print(f"加载了 {len(_skill_summaries)} 个技能")

mcp = FastMCP(name="minecraft-bot", version="1.0.0")


@mcp.tool()
async def plan(chatHistory, skill_progress: str = ""):
    # ── 技能续行 ──
    if skill_progress:
        try:
            progress = json.loads(skill_progress)
        except Exception:
            progress = None
        if progress:
            name = progress.get("name", "")
            next_seq = progress.get("next", 0)
            skill_detail = query_skill_detail(name)
            if not skill_detail:
                return json.dumps({"actions": [{"name": "Chat", "args": {"message": f"技能 {name} 未找到"}}]})
            current_seq = skill_detail["action_sequences"][next_seq]
            used_tools = set(current_seq.get("actions", []))
            used_tools.add("Chat")
            tool_details = [t for t in _tools_data if t["name"] in used_tools]
            skill_context = build_skill_context(name, next_seq)
            ctx = skill_context
            ctx += "\n\n你正在执行已保存的技能（续行），必须严格按照技能要求输出动作，不可修改、不可跳过、不可添加额外步骤。"
            if tool_details:
                ctx += "\n\n可用工具详情：\n" + "\n".join(
                    f"{t['name']}: args={t['args']} — {t['description']}" for t in tool_details
                )
            from LLMAgent import decide
            return await decide(chatHistory, tool_details, ctx)

    # ── 正常执行 ──
    # 所有工具全部加载
    all_tools = _tools_data

    # 技能摘要（名称 + 描述 + 第一个子序列）
    skill_text = ""
    if _skill_summaries:
        lines = ["已保存技能："]
        for s in _skill_summaries:
            skill_ctx = build_skill_context(s["name"], 0)
            lines.append(skill_ctx)
        skill_text = "\n".join(lines)

    ctx = skill_text if skill_text else ""

    from LLMAgent import decide
    try:
        result_str = await decide(chatHistory, all_tools, ctx)
    except Exception as e:
        print(f"[plan] 决策异常: {e}")
        return json.dumps({"actions":[{"name":"Chat","args":{"message":"规划异常"}}],"continue":False})
    return result_str


@mcp.tool()
async def summarize(chatHistory: list) -> str:
    try:
        from LLMAgent import summarize_history
        return await summarize_history(chatHistory)
    except Exception as e:
        return f"总结生成失败: {e}"


@mcp.tool()
async def saveSkill(chatHistory, skill_name: str) -> str:
    try:
        from LLMAgent import generate_skill
        result = await generate_skill(chatHistory, skill_name)
        return check_save_skill(result)
    except Exception as e:
        print(f"技能保存失败: {e}")
        return f"技能保存失败: {e}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
