from openai import AsyncOpenAI
from pydantic import BaseModel,Field,model_validator
from typing import Optional,Any
import enum
import os
from .config import settings

prompts_path = settings.files.prompts_path
prompts_names = [f[:-5] for f in os.listdir(prompts_path) if f.endswith(".yaml")]
_tools_schema = []  # 工具 schema 缓存，避免重复读取文件


def set_tools_schemas(tool_data):
    global _tools_schema
    _tools_schema = tool_data
    return _tools_schema

class FailureLabel(str, enum.Enum):
    LLM_DECISION_ORDER = "LLM_DECISION_ORDER_FAILURE"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    LLM_OUTPUT = "LLM_OUTPUT_FAILURE"

class ActionSequence(BaseModel):
    step: int = Field(..., description="动作序列的步骤索引")
    actions: list[str] = Field(..., description="动作名称列表")

class Step(BaseModel):
    name: str = Field(..., description="动作/工具/函数名称")
    args:  Optional[dict[str, Any]] = Field(..., description="动作参数")

    @model_validator(mode="after")
    def validate_args(self) -> Optional[dict[str, Any]]:
        """验证动作参数是否符合预期格式，如果不符合则抛出异常"""
        tool = next((tool for tool in _tools_schema if tool["name"] == self.name), None)
        if tool is None:
            raise ValueError(f"动作名称 '{self.name}' 不在工具列表中，请检查工具配置。")
        params_schema = tool.get("args", [])
        if not params_schema and self.args:
            raise ValueError(f"动作 '{self.name}' 不需要参数，但提供了参数: {self.args}")
        if params_schema and not self.args:
            required_params = [param["name"] for param in params_schema if param.get("required", False)]
            if required_params:
                raise ValueError(f"动作 '{self.name}' 需要参数，但未提供参数。")
        if params_schema and self.args:
            for param_schema in params_schema:
                param_name = param_schema["name"]
                required = param_schema.get("required", False)
                if param_name not in self.args:
                    if required:
                        raise ValueError(f"动作 '{self.name}' 缺少参数 '{param_name}'。")
                    continue
                arg = self.args[param_name]
                ptype = param_schema.get("type")
                enum_values = param_schema.get("enum",[])
                if ptype == "number" and not isinstance(arg, (int, float)):
                    raise ValueError(f"动作 '{self.name}' 的参数 '{param_name}' 应为数字类型，但提供了: {arg.__class__.__name__}")
                if ptype == "string" and not isinstance(arg, str):
                    raise ValueError(f"动作 '{self.name}' 的参数 '{param_name}' 应为字符串类型，但提供了: {arg.__class__.__name__}")
                if ptype == "integer" and not isinstance(arg, int):
                    raise ValueError(f"动作 '{self.name}' 的参数 '{param_name}' 应为整数类型，但提供了: {arg.__class__.__name__}")
                if enum_values and arg not in enum_values:
                    raise ValueError(f"动作 '{self.name}' 的参数 '{param_name}' 的值必须在 {enum_values} 中，但提供了: {arg}")
        return self

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