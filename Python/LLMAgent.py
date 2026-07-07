from openai import AsyncOpenAI
import os
import json
import re


class LLMClient:
    def __init__(self, model_name: str, url: str, api_key: str) -> None:
        self.model_name: str = model_name
        self.url: str = url
        self.client = AsyncOpenAI(api_key=api_key, base_url=url)

    async def get_response(self, messages: list) -> str:
        response = await self.client.chat.completions.create(
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
    """从 LLM 回复中提取 JSON 区块并解析。兼容单引号、代码块包裹、首尾括号截取。"""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    source = fenced.group(1) if fenced else text

    # 尝试直接解析（兼容单引号）
    try:
        return json.loads(source)
    except json.JSONDecodeError:
        try:
            return json.loads(source.replace("'", '"'))
        except Exception:
            pass
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

        extracted = source[start:end + 1]
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            return json.loads(extracted.replace("'", '"'))


async def decide(chatHistory: list, tools: list, extra_context: str = "") -> str:
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
你是 AIPlayer，一个 Minecraft 机器人，输出下一轮要执行的动作序列。

---

# 输出格式（严格 JSON）
{{{{"actions": [{{{{"name":"Chat","args":{{{{"message":"..."}}}}}}}}], "continue": true/false, "skillProgress": null/{{{{"name":"技能名","next":索引}}}}}}}}

---

# 规则

## R1 — 身份
- 你是 "bot"（名字 AIPlayer）role=bot
- role=player 是玩家，role=system 是系统

## R2 — 纯 JSON
- 只有 JSON，无解释、无注释

## R3 — 工具合法性
- 工具名必须来自下面的「可选工具列表」
- 禁止编造不存在的工具

## R4 — 技能执行
- 当处于非技能续行阶段时，只有当玩家的需求比较明确地指向或者与某个已保存的技能高度相关时，才考虑使用技能
- 玩家只是打招呼、自我介绍、无意义内容或空消息时，不要执行任何技能，直接输出 Chat
- 执行技能时，严格按照「当前已知信息」中提供的子序列输出动作，不得修改、不得跳过、不得添加额外动作
- 如果明确告知是技能续行阶段，必须执行续行子序列
- 如果该技能还有后续子序列，输出正确的 skillProgress 和 continue=true
- 如果这是最后一个子序列，skillProgress=null，continue=false

## R5 — 动作序列截断
- 1.遇到查询类工具时，该工具必须是 actions 中最后一个，且 continue=true
- 2.当 actions 中已累计 10 个动作时，必须在此截断输出，continue 根据任务是否完成决定

## R6 — Chat 包裹
- 非续行场景：序列必须用 Chat 开头告知开始，Chat 结尾告知完成（除开R5中的规则1），中途不输出 Chat
- 续行场景：根据技能要求进行chat处理。

## R7 — 错误处理
- 错误由系统自动处理，你不需要在输出中处理失败情况

## R8 — 历史数据时效性
- 坐标/位置信息超过 10 秒不可靠，需重新查询
- 实体/怪物信息超过 15 秒不可靠，需重新查询
- 血量/状态信息超过 30 秒不可靠，需重新查询
- 背包/物品信息超过 60 秒不可靠，建议重新查询
- 配方信息玩家消息始终有效

---

# 示例

## 正常执行
{{{{"actions":[{{{{"name":"Chat","args":{{{{"message":"开始检查"}}}}}}}},{{{{"name":"GetState","args":{{{{}}}}}}}}],"continue":false,"skillProgress":null}}}}

## 技能续行（还有后续子序列）
{{{{"actions":[{{{{"name":"Chat","args":{{{{"message":"继续执行"}}}}}}}},{{{{"name":"Move","args":{{{{"direction":"forward","blocks":5}}}}}}}}],"continue":true,"skillProgress":{{{{"name":"转圈","next":1}}}}}}}}

## 技能最后一个子序列
{{{{"actions":[{{{{"name":"Chat","args":{{{{"message":"继续执行"}}}}}}}}],"continue":false,"skillProgress":null}}}}

## 查询工具截断
{{{{"actions":[{{{{"name":"GetPosition","args":{{{{}}}}}}}}],"continue":true,"skillProgress":null}}}}



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

    raw = await _llm.get_response(messages)
    parsed = parse_json_candidate(raw)

    if not isinstance(parsed, dict) or 'actions' not in parsed:
        raise ValueError('LLM 未返回包含 actions 字段的 JSON')

    # 返回序列化的 JSON 字符串，FastMCP 会把它原样返回给调用方（Node）
    return json.dumps(parsed, ensure_ascii=False)


async def summarize_history(chatHistory: list) -> str:
    """用 LLM 总结会话内容，用于跨会话记忆持久化。"""
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2)

    prompt = f"""请用中文简要总结这次 Minecraft 游戏会话的关键信息，控制在 100 字以内。

关注点：
- 你是谁
- 玩家做了什么（要求你做了什么）
- 达成了什么目标（做了哪些事情，做的怎么样）

聊天历史：
{history_json}

请直接输出总结内容，不要多余格式。"""

    raw = await _llm.get_response([{"role": "system", "content": prompt}])
    return raw.strip()


async def generate_skill(chatHistory: list, skill_name: str) -> str:
    """用 LLM 总结保存技能。"""
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2)

    prompt = f"""请根据以下聊天历史，保存技能 "{skill_name}"，要求如下：
    ## R1 - 输出格式（严格Json，无多余解释内容）：
      {{
        "name": "{skill_name}",
        "description": "...",
        "action_sequences_length": N,
        "action_sequences": [
            {{"step": 0, "actions": [func1, func2, ..., funcK_1]}},
            {{"step": 1, "actions": [func1, func2, ..., funcK_2]}},
            ...
            {{"step": N-1, "actions": [func1, func2, ..., funcK_N]}}
        ]
      }}
    
    ## R2 - 规则：
    - action_sequences内部包含多个子动作序列，每一个子动作序列包含一个执行索引step和一个动作列表actions，动作列表中每个元素都是一个动作的名称，可以重复。
    - actions中每个动作只是工具函数名，且必须是聊天历史中出现的系统执行输出的工具函数名，其参数args不需要保存
    - step表示该子动作序列在技能中的索引位置和执行顺序，从 0 开始，
    - description 字段请简要描述该技能的用途和功能，控制在 100 字以内。
    - 在提取动作并确定每一个动作子序列时，若出现查询类工具时，必须以此查询工具结尾，完成一个动作子序列生成，然后在下一个动作子序列中继续划分后续动作。
    - 以玩家的最近消息作为意图参考，不要编造玩家意图，不要保存与玩家意图无关的动作。
    - 请直接输出 JSON，不要多余格式或解释。
    正确示例：
    {{
        "name": "{skill_name}",
        "description": "这是一个示例技能",
        "action_sequences_length": 2,
        "action_sequences": [
            {{"step": 0, "actions": ["Move", "GetPosition"]}},
            {{"step": 1, "actions": ["BreakBlock", "PlaceBlock"]}}
        ]
    }}

    错误示例（划分子动作序列时遇到查询工具不结尾）：
    {{
        "name": "{skill_name}",
        "description": "这是一个示例技能",
        "action_sequences_length": 2,
        "action_sequences": [
            {{"step": 0, "actions": ["Move", "GetPosition","BreakBlock"]}},
            {{"step": 1, "actions": ["PlaceBlock"]}}
        ]
    }}
    聊天历史：
{history_json}
"""
    raw = await _llm.get_response([{"role": "system", "content": prompt}])
    parsed = parse_json_candidate(raw)

    if not isinstance(parsed, dict) or 'name' not in parsed or 'action_sequences' not in parsed:
        raise ValueError('LLM 未返回包含 name 和 action_sequences 字段的 JSON')
    
    return json.dumps(parsed, ensure_ascii=False)



if __name__ == '__main__':
    # 简单的命令行测试：从文件读取历史并打印决策结果
    import sys

    if len(sys.argv) < 2:
        print('用法: python LLMAgent.py history.json')
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        history = json.load(f)

    print(decide(history))
