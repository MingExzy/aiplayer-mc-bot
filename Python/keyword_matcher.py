"""
中文关键词 → MCP 工具 预匹配器（轻量版）

关键词命中 → 该工具的完整描述直接注入第一轮 prompt。
未命中的工具 LLM 仍可通过 tool_queries 查询，不会漏。
只负责"提前给"，不负责"拦截"。
"""

TOOL_KEYWORDS: dict[str, list[str]] = {
    "Move": ["移动", "走", "前进", "后退", "向左", "向右", "往前", "往后", "向前", "向后", "走几步", "挪"],
    "Jump": ["跳", "跳跃", "蹦", "跳起来", "跳一下"],
    "Turn": ["转", "转身", "回头", "向左转", "向右转", "转向", "看向", "面对", "朝向"],
    "Sneak": ["潜行", "蹲", "蹲下", "偷偷", "悄悄"],
    "run": ["跑", "冲刺", "加速", "跑步", "疾跑", "快跑"],
    "LookAt": ["看", "看向", "盯着", "注视", "望着"],
    "MoveTo": ["去", "前往", "走到", "到达", "到", "来到", "过去"],
    "EquipItemInHand": ["装备", "拿", "手持", "拿起", "掏出", "握", "取出", "拿在手上"],
    "UseItemInHand": ["使用物品", "用", "右键", "激活", "交互"],
    "ThrowItems": ["扔", "丢", "丢弃", "抛出", "丢掉", "扔掉", "投掷"],
    "PlaceBlock": ["放置", "放", "摆放", "搭建", "建造", "放下", "铺", "搭"],
    "BreakBlock": ["破坏", "挖", "挖掘", "摧毁", "拆", "打碎", "敲", "挖掉", "砸"],
    "GetPosition": ["位置", "坐标", "在哪", "哪里", "你在哪", "你在哪里"],
    "GetState": ["状态", "血量", "生命值", "饥饿度", "饱食度", "健康", "你怎么样", "你还好吗", "还有多少血"],
    "GetInventory": ["背包", "物品", "有什么", "身上有", "你有什么", "打开背包", "物品栏"],
    "GetItemInHand": ["手里", "手上", "拿着什么", "手上的物品", "拿的什么"],
    "GetAroundEntities": ["附近", "周围", "旁边", "附近有", "周围有", "什么怪", "有怪物吗"],
    "GetAroundNearestTargetBlocks": ["找", "找到", "最近的", "附近有没有", "搜索", "哪里有", "发现", "寻找"],
    "GetRecipesForItem": ["配方", "合成", "怎么做", "怎么造", "怎么制作", "recipe"],
    "FollowPlayer": ["跟随", "跟着", "跟", "跟着我", "follow"],
    "CraftItem": ["合成", "制作", "造", "做", "craft", "合成一个"],
    "Chat": ["说话", "说", "告诉", "回答", "回复", "聊", "讲", "问", "打招呼", "喊", "叫"],
}


def keyword_preselect(message: str) -> set[str]:
    """根据玩家消息预选工具名集合。只负责提前给，不负责拦截。"""
    if not message:
        return set()
    msg = message.strip().lower()
    matched: set[str] = set()
    for tool_name, keywords in TOOL_KEYWORDS.items():
        for kw in keywords:
            if kw in msg:
                matched.add(tool_name)
                break
    return matched
