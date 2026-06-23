"""
物品查询模块 — 负责物品数据的加载、索引构建、匹配、上下文构建

所有物品相关状态在模块内部维护，server_of_mcp.py 只调用 build_item_context()。
"""

import os
import json
from item_name_map import cn_to_en, fuzzy_cn_match

# ── 模块级状态 ──
db: dict | None = None
item_display_names: list[str] = []
item_name_to_id: dict[str, str] = {}

# 物品触发关键词
_ITEM_TRIGGER_KEYWORDS = {
    "什么", "多少", "啥", "吗", "是不是", "能不能", "可以", "能",
    "怎么", "如何", "是", "有", "要", "给",
    "挖", "放", "拿", "装备", "用", "吃", "喝", "扔", "丢",
    "找", "做", "合成", "造", "建", "种", "烧", "煮", "烤",
    "堆叠", "上限", "数量", "物品", "材料", "东西",
    "哪个", "哪些", "哪里", "怎么获得", "如何获得",
}


# ═══════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════

def init(items_json_path: str) -> None:
    """初始化物品知识库：加载 JSON + 构建索引。启动时调用一次。"""
    global db, item_display_names, item_name_to_id

    # 加载 JSON
    try:
        with open(items_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"✗ 文件未找到: {items_json_path}")
        db = None
        return

    # 构建 db 字典
    db = {}
    for item in data:
        name = item.get("name", "").lower().strip()
        db[name] = {
            "display_name": item.get("displayName", name),
            "stack_size": item.get("stackSize", 64),
        }

    # 构建显示名索引
    item_display_names = []
    item_name_to_id = {}
    for eng_id, info in db.items():
        display = info.get("display_name", eng_id).lower()
        item_display_names.append(display)
        item_name_to_id[display] = eng_id
    for eng_id in db:
        item_name_to_id[eng_id] = eng_id
        if eng_id not in item_display_names:
            item_display_names.append(eng_id)

    print(f"物品知识库加载完成: {len(db)} 个物品")


# ═══════════════════════════════════════════════
# 内部逻辑
# ═══════════════════════════════════════════════

def _should_check_item(message: str) -> bool:
    """判断玩家消息是否值得去查物品库。"""
    if not message or db is None:
        return False
    msg_lower = message.lower().strip()
    for kw in _ITEM_TRIGGER_KEYWORDS:
        if kw in msg_lower:
            return True
    if cn_to_en(msg_lower):
        return True
    if msg_lower in db:
        return True
    if fuzzy_cn_match(msg_lower):
        return True
    return False


def _resolve_item_info(query: str, embedding_model=None) -> dict | None:
    """物品查询的内部实现：先查映射/索引，再嵌入兜底。"""
    if db is None:
        return None

    query_stripped = query.strip().lower()

    # 1a. 中文名精确匹配
    eng_id = cn_to_en(query_stripped)
    if eng_id and eng_id in db:
        info = db[eng_id]
        return {"name": eng_id, "display_name": info["display_name"], "stack_size": info["stack_size"]}

    # 1b. 英文精确匹配
    if query_stripped in db:
        info = db[query_stripped]
        return {"name": query_stripped, "display_name": info["display_name"], "stack_size": info["stack_size"]}

    # 1c. displayName 子串匹配
    matched_displays = [d for d in item_display_names if query_stripped in d]
    if matched_displays:
        best = min(matched_displays, key=len)
        eid = item_name_to_id.get(best)
        if eid and eid in db:
            info = db[eid]
            return {"name": eid, "display_name": info["display_name"], "stack_size": info["stack_size"]}

    # 1d. 中文子串匹配
    fuzzy_hits = fuzzy_cn_match(query_stripped)
    if fuzzy_hits:
        cn_name, eid = fuzzy_hits[0]
        if eid in db:
            info = db[eid]
            return {"name": eid, "display_name": info["display_name"], "stack_size": info["stack_size"]}

    # 第 2 层：嵌入匹配（兜底）
    if embedding_model:
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            query_emb = embedding_model.encode([query_stripped])[0]
            display_embs = embedding_model.encode(item_display_names)
            sims = cosine_similarity([query_emb], display_embs)[0]

            scored = [(i, sims[i]) for i in range(len(sims)) if sims[i] > 0.2]
            scored.sort(key=lambda x: x[1], reverse=True)

            if scored:
                results = []
                for idx, score in scored[:3]:
                    disp = item_display_names[idx]
                    eid = item_name_to_id.get(disp)
                    if eid and eid in db:
                        results.append({
                            "name": eid,
                            "display_name": db[eid]["display_name"],
                            "stack_size": db[eid]["stack_size"],
                            "similarity": round(float(score), 3),
                        })
                if results:
                    return {"results": results}
        except Exception:
            pass

    return None


# ═══════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════

def build_item_context(message: str, embedding_model=None) -> str:
    """根据玩家消息构建物品上下文文本（供注入 LLM prompt）。"""
    if not _should_check_item(message):
        return ""

    result = _resolve_item_info(message, embedding_model)
    if not result:
        return ""

    lines = []
    if "results" in result:
        lines.append("玩家可能提到了以下物品（按相似度排序）：")
        for r in result["results"]:
            lines.append(f"  - {r['name']} (英文ID) → 堆叠上限: {r['stack_size']}")
    else:
        lines.append("玩家提到的物品信息：")
        lines.append(f"  - 物品: {result['name']} (英文ID)")
        lines.append(f"  - 堆叠上限: {result['stack_size']}")

    return "\n".join(lines)


def query_item(query: str, embedding_model=None) -> str:
    """查询物品信息，返回 JSON 字符串。"""
    result = _resolve_item_info(query, embedding_model)
    if result:
        print(f"[query_item] 命中: '{query}' → {result.get('name', 'multi')}")
        return json.dumps(result, ensure_ascii=False)
    return json.dumps({"error": f"未找到与 '{query}' 匹配的物品"}, ensure_ascii=False)
