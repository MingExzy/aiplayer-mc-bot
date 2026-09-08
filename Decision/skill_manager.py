"""
技能管理器 — 负责 skill 的加载、匹配、保存

所有 skill 相关状态（索引、缓存）都在本模块内维护，server.py 只调用接口。
"""

import os
import json
from pydantic import BaseModel

# ── 模块级状态 ──

class SkillConfig(BaseModel):
    name: str
    description: str
    action_sequences_length: int
    action_sequences: list[dict]  # [{"step": 0, "actions": ["Move", "GetPosition"]}, ...]

SKILLS_DIR = None
_skill_index: list[SkillConfig] = []         # 内存索引 [{name, description, actions, rules}]


# ═══════════════════════════════════════════════
# 初始加载
# ═══════════════════════════════════════════════

def init_skills(skill_dir:str)-> None:
    """初始化技能管理器，加载 skills/ 目录下的所有 skill.json。"""
    global SKILLS_DIR
    SKILLS_DIR = skill_dir
    load_skills()

def load_skills() -> None:
    """扫描 skills/ 目录，加载所有 skill.json。"""
    global _skill_index
    _skill_index = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_path = os.path.join(SKILLS_DIR, entry, "SKILL.json")
        if os.path.isfile(skill_path):
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data_model = SkillConfig(**data)  # 转化成 SkillConfig对象，便于后续使用
                _skill_index.append(data_model)
            except Exception as e:
                raise RuntimeError(f"[skill] 加载技能 {entry} 失败: {e}") from e


# ═══════════════════════════════════════════════
# 读 — 列出 & 查询详情
# ═══════════════════════════════════════════════

def list_all_skills() -> list[dict]:
    """返回技能索引列表，包含 name、description、action_sequences_length。"""
    return [
        {
            "name": s.name,
            "description": s.description,
            "action_sequences_length": s.action_sequences_length,
            "actions": s.action_sequences
        }
        for s in _skill_index
    ]

def query_skill_detail(skill_name: str) -> SkillConfig | None:
    """根据技能名称返回完整详情（供 LLM 第二轮查询用）。"""
    for s in _skill_index:
        if s.name == skill_name:
            return s
    raise ValueError(f"技能 {skill_name} 不存在")


def build_skill_context(skill_name: str, next_sequence_index: int = 0) -> str:
    """构建单个技能的下一个子序列上下文，供 LLM 续行执行使用。"""
    s = query_skill_detail(skill_name)
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
    """保存技能到 skills/{name}/SKILL.json，同时更新内存索引。"""
    name = skill_config.name.strip()
    if not name:
        raise ValueError("技能名称不能为空")

    skill_dir = os.path.join(SKILLS_DIR, name)
    os.makedirs(skill_dir, exist_ok=True)

    with open(os.path.join(skill_dir, "SKILL.json"), "w", encoding="utf-8") as f:
        json.dump(skill_config.model_dump(), f, ensure_ascii=False, indent=2)

    # 更新内存索引
    global _skill_index
    _skill_index = [s for s in _skill_index if s.name != name]  # 移除旧的索引
    _skill_index.append(skill_config)  


def check_save_skill(llm_saveskill_output: str) -> str | None:
    """校验输出结果并尝试保存技能"""

    try:
        name = llm_saveskill_output.get("name", "").strip()
        description = llm_saveskill_output.get("description", "").strip()
        action_sequences = llm_saveskill_output.get("action_sequences", [])
    except Exception as e:
        raise ValueError(f"LLM 输出不符合预期格式: {e}")

    skillConfig_dict = {
        "name": name,
        "description": description,
        "action_sequences_length": len(action_sequences),
        "action_sequences": action_sequences
    }

    try:
        skill_config = SkillConfig(**skillConfig_dict)
    except Exception as e:
        raise ValueError(f"LLM 输出不符合 SkillConfig 结构: {e}")
    
    for seq in skill_config.action_sequences:
        # 强制设置 step 为实际索引，避免LLM输出错误
        seq["step"] = skill_config.action_sequences.index(seq)
    
    _SkillGenerate(skill_config)