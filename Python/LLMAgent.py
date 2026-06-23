from openai import OpenAI
import os
import json
import re


class LLMClient:
    def __init__(self, model_name: str, url: str, api_key: str) -> None:
        self.model_name: str = model_name
        self.url: str = url
        self.client = OpenAI(api_key=api_key, base_url=url)

    def get_response(self, messages: list) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False
        )

        return response.choices[0].message.content


# ── 模块级 LLM 客户端单例（启动时初始化一次）──
_api_key = os.getenv('DeepSeek_API_KEY')
if not _api_key:
    raise RuntimeError('DeepSeek_API_KEY 环境变量未设置')

_llm = LLMClient(
    model_name='deepseek-v4-flash',
    url='https://api.deepseek.com',
    api_key=_api_key
)


def parse_json_candidate(text: str):
    """从 LLM 回复中提取 JSON 区块并解析。支持 ```json ``` 包裹或从首尾大括号/中括号截取。"""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    source = fenced.group(1) if fenced else text

    try:
        return json.loads(source)
    except Exception:
        first_brace = source.find('{')
        first_bracket = source.find('[')
        starts = [i for i in (first_brace, first_bracket) if i >= 0]
        if not starts:
            raise ValueError('LLM 回复不包含可解析的 JSON')

        start = min(starts)
        end = max(source.rfind('}'), source.rfind(']'))
        if end <= start:
            raise ValueError('LLM 回复 JSON 边界不完整')

        return json.loads(source[start:end + 1])


def decide(chatHistory: list, tools: list, extra_context: str = "") -> str:
    """根据聊天历史调用 LLM，返回严格的动作 JSON（序列化的字符串）。

    本函数会构建与原 `mcp.make_decision` 相同的提示词，调用 OpenAI，然后解析并返回 LLM 给出的 JSON。

    参数:
        chatHistory   — 聊天历史
        tools         — 可选工具列表
        extra_context — 额外的上下文知识（如物品信息），注入到聊天历史之前
    """
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2)
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)

    # 如果有额外上下文，注入到聊天历史之前
    extra_section = ""
    if extra_context:
        extra_section = f"""

---

# 当前已知信息（供参考）

{extra_context}
"""

    prompt = f"""# 角色

你是 AIPlayer，一个 Minecraft 机器人。你的任务是分析聊天历史，输出**下一轮**要执行的工具动作序列。

---

# 输出格式（严格 JSON，无注释无解释）

{{
    "actions": [
        {{"name": "Chat", "args": {{"message": "..."}}}},
        ...
    ]
}}

---

# 规则（按优先级排列）

## R1 — 身份
- 你在聊天历史中身份是 **"bot"**（名字 AIPlayer）
- 玩家消息 role="player"，系统消息 role="system"
- 所有 role="bot" 的历史条目都是你之前的输出，请参考它们保持行为一致

## R2 — 纯 JSON
- 输出**只有** JSON，无自然语言、无代码块包裹、无注释

## R3 — 工具合法性（防幻觉）
- 工具名必须来自下面的「可选工具列表」
- 参数名和取值必须匹配该工具的 args 定义
- **禁止**编造不存在的工具或参数值
- 每个动作必须能从聊天历史中找到合理依据
- **例外**：如果「当前已知信息」中提供了已保存的技能（以 ⚠ 技能匹配 开头），技能中的工具不受上述限制，必须直接输出完整动作序列

## R4 — 闲聊处理
当玩家只是闲聊、提问、或没有明确动作需求时 → 只输出一个 `Chat` 动作，不要画蛇添足加其他工具。

正确例子：{{"actions": [{{"name": "Chat", "args": {{"message": "我在出生点附近"}}}}]}}

## R5 — 动作序列规则（核心）

### R5a — 必须用 Chat 包裹
序列必须**以 Chat 开头，以 Chat 结尾**。除非序列只有单个 Chat以及存 在查询的（R4、R5b 场景）。

- **开头 Chat**：告知玩家"开始执行"
- **结尾 Chat**：告知玩家完成情况或下一步提示

### R5b — 查询类工具的使用限制
当序列中出现**查询类工具**（class="QueryTools"，且描述带"Query"字样）时：
- 查询工具后面不得再出现其他任意工具
- 

正确（查询后结束）：
{{"actions": [
    {{"name": "GetPosition", "args": {{}}}},
]}}

错误（查询后面还加任意动作）：
{{"actions": [
    {{"name": "GetPosition", "args": {{}}}},
    {{"name": "Move", "args": {{"direction": "forward", "blocks": 5}}}},
    {{"name": "Chat", "args": {{"message": "..."}}}}
]}}

## R6 — 错误处理（你不需要管）
- 任何工具执行失败时，系统会自动将错误信息以聊天形式反馈给你
- **不要在动作序列中处理失败情况**，只管规划"正常情况下"的流程

## R7 — 结尾 Chat 的 message 策略
结尾 Chat 的 message 应该写**预期执行成功后**的汇报内容，不要写"如果失败"之类的条件分支。
- 例如执行（如 Move, BreakBlock, PlaceBlock...）+ Chat（结尾） → 告知完成情况或下一步提示

---

## R8 -历史聊天记录的可用时限规则：
每条历史消息会带有一个时间戳（ts，单位秒）。以最新消息的时间戳为基准，根据消息类型不同，超过一定时间后可能不再可靠，不能复用，需要重新查询：
- 坐标/位置类信息超过10秒，则不再可靠，不能复用，需要时必须重新查询
- 实体/怪物信息超过15秒，则不再可靠，不能复用，需要时必须重新查询
- 血量/状态类信息超过30秒，则不再可靠，不能复用，需要时必须重新查询
- 背包/物品类信息超过60秒，可能已经过时，需要时建议重新查询
- 合成配方信息始终有效，不受时限影响
- 玩家消息始终有效，不受时限影响

# 总结：动作序列的三种基本形态

| 场景 | 序列模式 |
|---|---|
| 纯聊天/问答 | `[Chat]` |
| 执行动作后汇报 | `[Chat开头] → 工具动作... → Chat结尾]` |
| 查询后询问 | `[Chat开头] → 查询工具]` |

---

# 可选工具列表

{tools_json}{extra_section}

---

# 聊天历史（按时间顺序）

{history_json}
"""

    messages = [{"role": "system", "content": prompt}]

    raw = _llm.get_response(messages)
    parsed = parse_json_candidate(raw)

    if not isinstance(parsed, dict) or 'actions' not in parsed:
        raise ValueError('LLM 未返回包含 actions 字段的 JSON')

    # 返回序列化的 JSON 字符串，FastMCP 会把它原样返回给调用方（Node）
    return json.dumps(parsed, ensure_ascii=False)


def summarize_history(chatHistory: list) -> str:
    """用 LLM 总结会话内容，用于跨会话记忆持久化。"""
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2)

    prompt = f"""请用中文简要总结这次 Minecraft 游戏会话的关键信息，控制在 100 字以内。

关注点：
- 玩家做了什么
- 达成了什么目标
- 有哪些未完成的事

聊天历史：
{history_json}

请直接输出总结内容，不要多余格式。"""

    raw = _llm.get_response([{"role": "system", "content": prompt}])
    return raw.strip()


if __name__ == '__main__':
    # 简单的命令行测试：从文件读取历史并打印决策结果
    import sys

    if len(sys.argv) < 2:
        print('用法: python LLMAgent.py history.json')
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        history = json.load(f)

    print(decide(history))
