from fastmcp import FastMCP
import json
import os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from keyword_matcher import keyword_match
from item_query import init as init_items, build_item_context
from skill_manager import init as init_skills, build_skill_context, check_save_skill, cache_action_sequence, get_skill_tool_names

script_dir = os.path.dirname(os.path.abspath(__file__))

# ── 启动时初始化 ──
init_items(os.path.join(script_dir, "../ItemsData/item/items.json"))
init_skills(os.path.join(script_dir, "skills"))

# ── 嵌入模型 ──
local_model_path = os.path.join(script_dir, "../EembeddingModelFiles/paraphrase-multilingual-MiniLM-L12-v2")
print(f"正在加载模型，路径: {local_model_path}")
try:
    embedding_model = SentenceTransformer(local_model_path, local_files_only=True)
    print("模型加载成功")
except OSError as e:
    print(f"✗ 模型加载失败: {e}")
    embedding_model = None

mcp = FastMCP(name="minecraft-bot", version="1.0.0")


def make_decision(chatHistory, tools, extra_context=""):
    """调用 LLMAgent 决策并返回动作 JSON 字符串。"""
    try:
        from LLMAgent import decide
        return decide(chatHistory, tools, extra_context=extra_context)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ═══════════════════════════════════════════════
# MCP 工具: plan（唯一对外接口）
# ═══════════════════════════════════════════════

@mcp.tool()
def plan(chatHistory, tools):
    latest_message = chatHistory[-1]['content'] if chatHistory else ""

    # ── 上下文构建 ──
    item_context = build_item_context(latest_message, embedding_model)
    skill_context = build_skill_context(latest_message, embedding_model)
    extra_parts = [p for p in [item_context, skill_context] if p]
    extra_context = "\n\n---\n\n".join(extra_parts) if extra_parts else ""

    # ── 工具筛选 ──
    filtered_tools = filter_tools(latest_message, tools)

    # ── 技能工具补全 ──
    if skill_context:
        skill_tool_names = get_skill_tool_names(latest_message, embedding_model)
        if skill_tool_names:
            existing_names = {t["name"] for t in filtered_tools}
            added = [t for t in tools if t["name"] in skill_tool_names and t["name"] not in existing_names]
            if added:
                filtered_tools.extend(added)
                print(f"补入技能工具: {[t['name'] for t in added]}")

    # ── 决策 ──
    action_json_str = make_decision(chatHistory, filtered_tools, extra_context=extra_context)

    # ── 缓存动作序列供保存 skill ──
    try:
        action_data = json.loads(action_json_str)
        cache_action_sequence(action_data.get("actions", []))
    except Exception:
        pass

    return action_json_str


# ═══════════════════════════════════════════════
# 内部函数: 工具筛选
# ═══════════════════════════════════════════════

def filter_tools(latest_messages, tools):
    # 第 1 层：中文关键词预匹配
    keyword_matched = keyword_match(latest_messages, tools)
    if keyword_matched:
        print(f"关键词预匹配命中: {[t['name'] for t in keyword_matched]}")

    # 第 2 层：嵌入语义过滤
    tool_descriptions = [tool['description'] for tool in tools]
    tool_embeddings = embedding_model.encode(tool_descriptions)
    latest_embedding = embedding_model.encode([latest_messages])[0]
    similarities = cosine_similarity([latest_embedding], tool_embeddings)[0]
    threshold = 0.3
    embedding_matched = [
        tools[i] for i in range(len(tools))
        if similarities[i] > threshold
    ]

    # 合并 + 去重
    seen = set()
    merged = []
    for t in keyword_matched + embedding_matched:
        if t["name"] not in seen:
            merged.append(t)
            seen.add(t["name"])

    # 始终保留 Chat
    if "Chat" not in seen:
        chat_tool = next((t for t in tools if t["name"] == "Chat"), None)
        if chat_tool:
            merged.append(chat_tool)
            seen.add("Chat")

    if not merged:
        print("关键词 + 嵌入均未匹配，返回全部工具")
        return tools

    print(f"最终筛选出 {len(merged)} 个工具: {[t['name'] for t in merged]}")
    return merged


@mcp.tool()
def summarize(chatHistory: list) -> str:
    """根据聊天历史生成自然语言总结，用于跨会话记忆。"""
    try:
        from LLMAgent import summarize_history
        return summarize_history(chatHistory)
    except Exception as e:
        return f"总结生成失败: {e}"


@mcp.tool()
def saveSkill(chatHistory, skill_name: str) -> str:
    """根据聊天历史和技能名称生成并保存技能。"""
    try:
        from LLMAgent import generate_skill
        result = generate_skill(chatHistory, skill_name)
        return check_save_skill(result)
    except Exception as e:
        return f"技能保存失败: {e}"

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
