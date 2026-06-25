"""
技能管理器 — 负责 skill 的加载、匹配、保存

所有 skill 相关状态（索引、缓存）都在本模块内维护，server_of_mcp.py 只调用接口。
"""

import os
import json
from pydantic import BaseModel

# ── 模块级状态 ──
SKILLS_DIR: str = ""
_skill_index: list[dict] = []         # 内存索引 [{name, description, actions, rules}]
_last_action_sequence: list | None = None  # plan() 缓存的上一次动作序列

# 保存触发词
_SAVE_TRIGGER_KEYWORDS = {"保存", "存为", "记录", "存储"}


class SkillConfig(BaseModel):
    name: str
    description: str
    action_sequences_length: int
    action_sequences: list[dict]  # [{"step": 0, "actions": ["Move", "GetPosition"]}, ...]


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
    matched_skills = match_skills(message, embedding_model=embedding_model)
    if not matched_skills:
        return ""
    
    skill_prompts = []
    for skill in matched_skills:
        s = SkillConfig(**skill)
        prompt_text = (
            f"技能开始\n"
            f"  {s.name}: {s.description}\n"
            f"  共{s.action_sequences_length}个动作子序列\n"
            f"  执行顺序：\n"
        )
        for index in range(s.action_sequences_length):
            seq = s.action_sequences[index]
            step_num = seq.get("step", index) + 1
            actions = seq.get("actions", [])
            action_str = "->".join(str(a) for a in actions)
            prompt_text += f"    子动作序列{step_num}: {action_str}\n"
        prompt_text += "技能结束"
        skill_prompts.append(prompt_text)

    lines = [
        f"⚠ 技能匹配: {len(matched_skills)} 个技能命中",
        "\n".join(skill_prompts)
    ]

    return "\n".join(lines)


def get_skill_tool_names(message: str, embedding_model=None) -> set[str]:
    """返回匹配技能中用到的所有工具名集合。"""
    skills = match_skills(message, embedding_model)
    names = set()
    for s in skills:
        for seq in s.get("action_sequences", []):
            for action_name in seq.get("actions", []):
                if isinstance(action_name, str):
                    names.add(action_name)
    return names


# ═══════════════════════════════════════════════
# 写 — 保存技能（内部函数，不经过 LLM）
# ═══════════════════════════════════════════════

def _SkillGenerate(skill_config: SkillConfig) -> None:
    """保存技能到 skills/{name}/skill.json，同时更新内存索引。"""
    name = skill_config.name.strip()
    if not name:
        raise ValueError("技能名称不能为空")

    skill_dir = os.path.join(SKILLS_DIR, name)
    os.makedirs(skill_dir, exist_ok=True)

    with open(os.path.join(skill_dir, "skill.json"), "w", encoding="utf-8") as f:
        json.dump(skill_config.model_dump(), f, ensure_ascii=False, indent=2)

    # 更新内存索引
    global _skill_index
    _skill_index = [s for s in _skill_index if s.get("name") != name]
    _skill_index.append(skill_config.model_dump())  

    print(f"[skill] 已保存: 技能{name})")


def check_save_skill(llm_saveskill_output: str) -> str | None:
    """校验输出结果并尝试保存技能"""

    try:
        raw_dict = json.loads(llm_saveskill_output)
    except json.JSONDecodeError as e:
        raise ValueError("LLM 输出不是有效的 JSON")

    try:
        skill_config = SkillConfig(**raw_dict)
    except Exception as e:
        raise ValueError(f"LLM 输出不符合 SkillConfig 结构: {e}")
    
    # 强制转换 action_sequences_length 为 int和实际长度，避免LLM输出错误
    skill_config.action_sequences_length = len(skill_config.action_sequences)
    for seq in skill_config.action_sequences:
        # 强制设置 step 为实际索引，避免LLM输出错误
        seq["step"] = skill_config.action_sequences.index(seq)

    _SkillGenerate(skill_config)
    return f"技能 {skill_config.name} 已保存成功"


# ═══════════════════════════════════════════════
# 缓存接口（plan 在返回前调用）
# ═══════════════════════════════════════════════

def cache_action_sequence(actions: list) -> None:
    """缓存最近一次动作序列，供下次保存 skill 使用。"""
    global _last_action_sequence
    _last_action_sequence = actions
