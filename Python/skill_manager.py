"""
技能管理器 — 负责 skill 的加载、匹配、保存

所有 skill 相关状态（索引、缓存）都在本模块内维护，server_of_mcp.py 只调用接口。
"""

import os
import json

# ── 模块级状态 ──
SKILLS_DIR: str = ""
_skill_index: list[dict] = []         # 内存索引 [{name, description, actions, rules}]
_last_action_sequence: list | None = None  # plan() 缓存的上一次动作序列

# 保存触发词
_SAVE_TRIGGER_KEYWORDS = {"保存", "存为", "记录", "存储"}


# ═══════════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════════

def init(skills_dir: str) -> None:
    """模块初始化：设置技能目录 + 加载索引。启动时调用一次。"""
    global SKILLS_DIR
    SKILLS_DIR = skills_dir
    _load_skill_index()


def _load_skill_index() -> None:
    """扫描 skills/ 目录，加载所有 skill.json。"""
    global _skill_index
    _skill_index = []

    if not os.path.isdir(SKILLS_DIR):
        os.makedirs(SKILLS_DIR, exist_ok=True)
        print(f"[skill] 目录已创建: {SKILLS_DIR}")
        return

    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_path = os.path.join(SKILLS_DIR, entry, "skill.json")
        if os.path.isfile(skill_path):
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _skill_index.append(data)
                print(f"[skill]   加载: {data.get('name', entry)}")
            except Exception as e:
                print(f"[skill]   ⚠ 加载失败 {skill_path}: {e}")

    print(f"[skill] 技能库加载完成: {len(_skill_index)} 个技能")


# ═══════════════════════════════════════════════
# 读 — 匹配 & 构建上下文
# ═══════════════════════════════════════════════

def match_skills(message: str, embedding_model=None) -> list[dict]:
    """匹配技能：第 1 层查名称关键词，第 2 层嵌入 description（需传入 embedding_model）。"""
    if not message or not _skill_index:
        return []
    msg = message.strip()
    # 去掉 "username: " 前缀
    colon_idx = msg.find(': ')
    if colon_idx > 0:
        msg = msg[colon_idx + 2:]
    msg_lower = msg.lower().strip()
    matched = []
    seen = set()

    # 第 1 层：技能名称包含匹配
    for skill in _skill_index:
        sname = skill.get("name", "").lower()
        if sname and sname in msg_lower:
            print(f"  [skill] 名称匹配: '{msg_lower}' 包含 '{sname}'")
            if skill["name"] not in seen:
                matched.append(skill)
                seen.add(skill["name"])

    # 第 2 层：description 嵌入匹配（只对第一层没命中的跑，阈值 0.5）
    unmatched = [s for s in _skill_index if s["name"] not in seen]
    if unmatched and embedding_model:
        try:
            descs = [s.get("description", "") for s in unmatched]
            desc_embs = embedding_model.encode(descs)
            msg_emb = embedding_model.encode([msg_lower])[0]

            from sklearn.metrics.pairwise import cosine_similarity
            sims = cosine_similarity([msg_emb], desc_embs)[0]

            scored = [(i, sims[i]) for i in range(len(sims)) if sims[i] > 0.5]
            scored.sort(key=lambda x: x[1], reverse=True)

            for idx, score in scored[:2]:
                skill = unmatched[idx]
                matched.append(skill)
                seen.add(skill["name"])
                print(f"  [skill] 嵌入匹配: '{message}' → {skill['name']} ({score:.3f})")
        except Exception:
            pass

    return matched


def build_skill_context(message: str, embedding_model=None) -> str:
    """构建技能上下文字符串供注入 LLM prompt。"""
    skills = match_skills(message, embedding_model)
    if not skills:
        return ""

    lines = ["## ⚠ 技能匹配 — 此技能已被保存验证，其动作不受工具列表限制，你必须直接输出以下完整动作序列，不要修改，不要重新规划"]
    for s in skills:
        lines.append(f"""
技能: {s['name']}
描述: {s.get('description', '')}
动作序列:""")
        for i, act in enumerate(s.get("actions", []), 1):
            name = act.get("name", "?")
            args = act.get("args", {})
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            lines.append(f"  {i}. {name}({args_str})")
        lines.append("此技能动作已被验证，不受工具列表限制，你必须直接输出上述完整动作序列，不要修改。")

    return "\n".join(lines)


# ═══════════════════════════════════════════════
# 写 — 保存技能（内部函数，不经过 LLM）
# ═══════════════════════════════════════════════

def _SkillGenerate(name: str, description: str, actions: list) -> None:
    """保存技能到 skills/{name}/skill.json，同时更新内存索引。"""
    # 过滤掉 原有 Chat 动作
    filtered_actions = [a for a in actions if a.get("name") != "Chat"]

    # 新增Chat动作：
    if filtered_actions:
        filtered_actions.insert(0, {
            "name": "Chat",
            "args": {"message": f"即将执行技能「{name}」，包含 {len(filtered_actions)} 个动作。"}
        })
        filtered_actions.append({
            "name": "Chat",
            "args": {"message": f"技能「{name}」执行完毕。"}})
    skill_data = {
        "name": name,
        "description": description or "",
        "actions": filtered_actions,
        "rules": "当你读取并决定采用这项 skill 时，直接输出上述 actions 作为结果，无需额外的 Chat 输出或决策。",
    }

    skill_dir = os.path.join(SKILLS_DIR, name)
    os.makedirs(skill_dir, exist_ok=True)

    with open(os.path.join(skill_dir, "skill.json"), "w", encoding="utf-8") as f:
        json.dump(skill_data, f, ensure_ascii=False, indent=2)

    # 更新内存索引
    global _skill_index
    _skill_index = [s for s in _skill_index if s.get("name") != name]
    _skill_index.append(skill_data)

    print(f"[skill] 已保存: {name} ({len(filtered_actions)} 个动作)")


def check_save_skill(latest_message: str, chatHistory: list) -> str | None:
    """检测玩家是否请求保存技能。命中时直接保存并返回确认消息（plan 以此短路 LLM 调用）。"""
    if not latest_message:
        return None

    msg = latest_message.strip()

    # 去掉 "username: " 前缀，提取实际消息内容
    colon_idx = msg.find(': ')
    if colon_idx > 0:
        msg = msg[colon_idx + 2:]

    # 检查触发词开头
    matched_trigger = None
    for kw in _SAVE_TRIGGER_KEYWORDS:
        if msg.startswith(kw):
            matched_trigger = kw
            break
    if not matched_trigger:
        return None

    # 提取技能名
    skill_name = msg[len(matched_trigger):].strip()
    if not skill_name:
        skill_name = f"skill_{len(_skill_index) + 1}"

    # 从历史中提取原始请求作为 description
    description = ""
    for entry in reversed(chatHistory):
        if entry.get("role") == "player":
            player_msg = entry.get("content", "").strip()
            # 去掉 "username: " 前缀
            colon_idx = player_msg.find(': ')
            if colon_idx > 0:
                player_msg = player_msg[colon_idx + 2:]
            is_save_req = any(player_msg.startswith(kw) for kw in _SAVE_TRIGGER_KEYWORDS)
            if not is_save_req:
                description = player_msg[:80]
                break

    # 从缓存中获取最近一次动作序列
    global _last_action_sequence
    actions_to_save = _last_action_sequence or []

    try:
        _SkillGenerate(skill_name, description, actions_to_save)
        print(f"[skill] 已保存技能: {skill_name}")
        return f"已自动保存技能「{skill_name}」，下次可以直接复用。"
    except Exception as e:
        print(f"[skill] 保存失败: {e}")
        return f"保存失败: {e}"


# ═══════════════════════════════════════════════
# 缓存接口（plan 在返回前调用）
# ═══════════════════════════════════════════════

def cache_action_sequence(actions: list) -> None:
    """缓存最近一次动作序列，供下次保存 skill 使用。"""
    global _last_action_sequence
    _last_action_sequence = actions
