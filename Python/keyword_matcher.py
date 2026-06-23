"""
中文关键词 → MCP 工具 预匹配器

在嵌入模型筛选之前，先用中文关键词做一轮硬匹配。
玩家消息命中关键词 → 对应工具必定入选，防止嵌入模型误杀掉明显匹配的工具。
"""

# 每个工具对应的中文触发关键词/短语列表
# 注意：匹配不分词，直接用子串包含判断，所以短词要小心（"放" 比 "放置" 更容易误杀）
TOOL_KEYWORDS: dict[str, list[str]] = {
    "Chat": [
        "说话", "说", "告诉", "回答", "回复", "聊", "讲", "问",
        "回答", "聊天", "对话", "对", "打招呼", "传达", "转告",
        "说一句", "讲一句", "喊", "叫",
    ],
    "Move": [
        "移动", "走", "前进", "后退", "向左", "向右", "往前",
        "往后", "往左", "往右", "向前", "向后", "往前走",
        "往后走", "向左走", "向右走", "前走", "后退",
        "走几步", "走一格", "挪",
    ],
    "Jump": [
        "跳", "跳跃", "蹦", "跳起来", "跳一下", "蹦一下",
    ],
    "Turn": [
        "转", "转身", "回头", "向左转", "向右转", "转向",
        "看向", "面对", "朝向", "朝南", "朝北", "朝东", "朝西",
        "看后面", "转过来", "转过去",
    ],
    "Sneak": [
        "潜行", "蹲", "蹲下", "偷偷", "悄悄", "潜行状态",
    ],
    "run": [
        "跑", "冲刺", "加速", "跑步", "疾跑", "快跑", "冲",
        "跑起来", "全速",
    ],
    "LookAt": [
        "看", "看向", "盯着", "注视", "望着", "望",
        "看我", "看着",
    ],
    "MoveTo": [
        "去", "前往", "走到", "到达", "到", "到…去",
        "来到", "赶去", "奔", "到位置", "到坐标",
        "去那里", "过去",
    ],
    "EquipItemInHand": [
        "装备", "拿", "手里拿", "手持", "拿起", "掏出",
        "切换", "握", "抓", "取出", "拿在手上",
        "手上拿", "拿上", "拿好",
    ],
    "UseItemInHand": [
        "使用物品", "用", "右键", "激活", "交互", "用一下",
        "用手中的", "使用手中的",
    ],
    "ThrowItemInHand": [
        "扔", "丢", "丢弃", "抛出", "丢掉", "扔掉", "投掷",
        "丢出去", "丢掉", "抛",
    ],
    "PlaceBlock": [
        "放置", "放", "摆放", "搭建", "建造", "放下",
        "放一个", "铺", "架", "搭",
    ],
    "BreakBlock": [
        "破坏", "挖", "挖掘", "摧毁", "拆", "打碎", "敲",
        "拆掉", "打掉", "挖掉", "砸", "打烂",
    ],
    "GetPosition": [
        "位置", "坐标", "在哪", "哪里", "你在哪", "你在哪里",
        "当前坐标", "在什么位置", "你在什么位置",
    ],
    "GetState": [
        "状态", "血量", "生命值", "饥饿度", "饱食度", "健康",
        "好不好", "你怎么样", "你还好吗", "身体", "状况",
        "你状态", "还有多少血",
    ],
    "GetInventory": [
        "背包", "物品", "有什么", "携带", "身上有", "你身上",
        "你有啥", "你有什么", "看一下背包", "打开背包",
        "背包里", "物品栏",
    ],
    "GetItemInHand": [
        "手里", "手上", "拿着什么", "手上的物品", "手里拿",
        "手里有", "拿的什么", "手上拿的",
    ],
    "GetAroundEntities": [
        "附近", "周围", "旁边", "附近有", "周围有",
        "有什么生物", "有谁", "附近有什么", "周围有什么",
        "周边", "旁边有谁", "什么怪", "有怪物吗","有没有",
        "看看"
    ],
    "GetAroundNearestTargetBlocks": [
        "找", "找到", "最近的", "附近有没有", "搜索",
        "找一找", "搜寻", "哪里有", "发现", "寻找",
        "附近哪里有", "最近的在哪里","周围", "周围哪里有",
        "看看","有没有",
    ],
    "FollowPlayer": [
        "跟随", "跟着", "追随", "尾随", "跟", "跟玩家",
        "跟某人", "跟他", "跟她", "跟它",
    ],
    "GetRecipesForItem": [
        "配方", "做法", "怎么做", "怎么合成", "怎么制造",
        "怎么获得", "有什么用", "用途", "用处","合成","制造", "做", "造", "合成表", "配方表",
    ],
    "GraftItem": [
        "合成", "制造", "做", "造", "合成一个", "制造一个",
        "做一个", "造一个", "合成几个", "制造几个",
        "做几个", "造几个",
    ],

}


def keyword_match(message: str, tools: list[dict]) -> list[dict]:
    """对玩家中文消息进行关键词预匹配，返回命中的工具列表。

    参数:
        message — 玩家最新的消息（中文）
        tools   — 全部可用工具的列表（与 server_of_mcp 中的格式一致）

    返回:
        命中的工具列表（可能为空）
    """
    if not message or not tools:
        return []

    # 构建 tool name → tool dict 的映射
    tool_map = {tool["name"]: tool for tool in tools if "name" in tool}

    matched_tools: list[dict] = []
    seen_names: set[str] = set()

    for tool_name, keywords in TOOL_KEYWORDS.items():
        if tool_name in seen_names:
            continue
        for keyword in keywords:
            if keyword in message:
                tool = tool_map.get(tool_name)
                if tool and tool_name not in seen_names:
                    matched_tools.append(tool)
                    seen_names.add(tool_name)
                break  # 一个工具只要命中一个关键词就够，跳出关键词循环

    return matched_tools


def keyword_match_boosted(message: str, tools: list[dict], threshold: float = 0.15) -> list[dict]:
    """增强版：关键词匹配 + 模糊计分。

    不只是子串包含，还可以计算消息中关键词密度。
    当命中关键词比例超过 threshold 时算匹配。

    参数:
        message  — 玩家消息
        tools    — 工具列表
        threshold — 关键词占比阈值（默认 0.15 = 消息中 15% 的内容是关键词）

    返回:
        命中的工具列表
    """
    if not message or not tools:
        return []

    tool_map = {tool["name"]: tool for tool in tools if "name" in tool}
    matched: list[dict] = []
    seen: set[str] = set()

    msg_len = len(message)
    if msg_len == 0:
        return []

    for tool_name, keywords in TOOL_KEYWORDS.items():
        if tool_name in seen:
            continue
        # 计算消息中该工具关键词的覆盖率
        match_chars = 0
        for kw in keywords:
            # 每个关键词出现次数 × 关键词长度
            count = message.count(kw)
            match_chars += count * len(kw)

        ratio = match_chars / msg_len
        if ratio >= threshold:
            tool = tool_map.get(tool_name)
            if tool and tool_name not in seen:
                matched.append(tool)
                seen.add(tool_name)

    return matched
