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
# 读 — 列出 & 查询详情
# ═══════════════════════════════════════════════

def list_all_skills() -> list[dict]:
    """返回所有技能的名称和描述（供 LLM 第一轮查询用）。"""
    return [{"name": s["name"], "description": s.get("description", "")} for s in _skill_index]


def query_skill_detail(skill_name: str) -> dict | None:
    """根据技能名称返回完整详情（供 LLM 第二轮查询用）。"""
    for s in _skill_index:
        if s["name"] == skill_name:
            return s
    return None


def build_skill_context(skill_name: str, next_sequence_index: int = 0) -> str:
    """构建单个技能的下一个子序列上下文，供 LLM 续行执行使用。"""
    skill = query_skill_detail(skill_name)
    if not skill:
        return ""

    s = SkillConfig(**skill)
    if next_sequence_index >= s.action_sequences_length:
        return ""

    next_seq = s.action_sequences[next_sequence_index]
    actions = next_seq.get("actions", [])
    total = s.action_sequences_length
    is_last = (next_sequence_index == total - 1)
    lines = [f"技能 — {s.name}: {s.description}"]
    lines.append(f"  子序列 {next_sequence_index + 1} / {total}")
    lines.append("  动作: " + " -> ".join(str(a) for a in actions))
    if is_last:
        lines.append("  最后一个子序列，完成后结束。")
    else:
        lines.append("  后续还有子序列。")

    return "\n".join(lines)






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
    if skill_config.action_sequences_length > 10:
        raise ValueError(f"子序列数量 {skill_config.action_sequences_length} 超过上限 10")
    for seq in skill_config.action_sequences:
        # 强制设置 step 为实际索引，避免LLM输出错误
        seq["step"] = skill_config.action_sequences.index(seq)

    _SkillGenerate(skill_config)
    return f"技能 {skill_config.name} 已保存成功"



