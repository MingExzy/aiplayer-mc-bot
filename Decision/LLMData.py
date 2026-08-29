from openai import AsyncOpenAI
from pydantic import BaseModel,Field
from typing import Optional
import enum
import os
from config import settings

prompts_path = settings.files.prompts_path
prompts_names = [f[:-5] for f in os.listdir(prompts_path) if f.endswith(".yaml")]

class FailureLabel(str, enum.Enum):
    LLM_DECISION_ORDER = "LLM_DECISION_ORDER_FAILURE"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    LLM_OUTPUT = "LLM_OUTPUT_FAILURE"

class ActionSequence(BaseModel):
    step: int = Field(..., description="动作序列的步骤索引")
    sub_action_seq: list[str] = Field(..., description="动作名称列表")

class Step(BaseModel):
    name: str = Field(..., description="动作/工具/函数名称")
    args:  Optional[dict[str, str]] = Field(..., description="动作参数")

class SkillProgress(BaseModel):
    name: str = Field(..., description="技能名")
    next: int = Field(..., description="下一个子序列索引")

class LLMResponse(BaseModel):
    actions: list[Step] = Field(..., description="动作序列")
    continue_: bool = Field(..., alias="continue", description="是否继续执行后续动作")
    skillProgress: Optional[SkillProgress] = Field(None, description="技能续行信息，包含技能名和下一个子序列索引")

class LLMReflect(BaseModel):
    failure: Optional[str] = Field(..., description="失败之处")
    reason: Optional[str] = Field(..., description="失败原因")
    label: Optional[FailureLabel] = Field(..., description="失败标签,包括决策顺序失败（不符合逻辑）、环境因素（外部环境导致失败）、LLM输出失败（LLM输出不符合预期以及参数不正确）")

class LLMGenerateSkill(BaseModel):
    name: str = Field(..., description="技能名")
    description: str = Field(..., description="技能描述",lt=200)
    action_sequences_length: int = Field(..., description="总的子动作序列个数")
    action_sequences: list[ActionSequence] = Field(..., description="动作序列列表，每个元素包含 step 和 actions 字段")


def get_prompts_from_yaml(yaml_path: str) -> dict:
    """从 YAML 文件中读取 prompts 配置"""
    import yaml
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def get_all_prompts() -> dict:
    """根据提示名称列表获取所有提示配置"""
    prompts = {}
    for name in prompts_names:
        prompts[name] = get_prompts_from_yaml(os.path.join(prompts_path, f"{name}.yaml"))["template"]
    return prompts