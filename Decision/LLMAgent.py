from openai import AsyncOpenAI,APIConnectionError, APITimeoutError, APIStatusError, APIError
import json
from Decision.utils import retry, trace_id_var, get_logger,log_llm_helper
from Decision.LLMData import LLMResponse, LLMReflect,LLMGenerateSkill,get_all_prompts
from jinja2 import Template
from typing import Optional
import datetime
import uuid
from .config import settings
import Decision.errors as errors

_prompts = None
_logger = None

class LLMClient:
    def __init__(self, model_name: str, url: str, api_key: str, temperature: float) -> None:
        self.model_name: str = model_name
        self.url: str = url
        try:
            self.client = AsyncOpenAI(api_key=api_key, base_url=url)
        except Exception as e:
            raise errors.LLMAPIError(f"LLM API 初始化失败: {e}") from e
        self.temperature: float = temperature

    async def create_session(self,messages:list,res_format = {"type": "text"})->str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=False,
                response_format=res_format,
                temperature=self.temperature
            )
        except (APIConnectionError, APITimeoutError, APIStatusError, APIError) as e:
            log_llm_helper(_logger, f"LLM API 调用失败: {e}", "error", "Response", None,
                           None, None, None, None,
                           messages[-1].get("role", "unknown") if messages else "unknown",
                           messages[-1]["content"] if messages else "")
            if isinstance(e, APIConnectionError):
                raise errors.LLMAPIError(f"LLM API 连接失败",retryable=True) from e
            elif isinstance(e, APITimeoutError):
                raise errors.LLMAPIError(f"LLM API 请求超时",retryable=True) from e
            else:
                raise errors.LLMAPIError(f"LLM API 调用失败") from e
        return response

    async def get_response(self, messages: list) -> str:
        start_time = datetime.datetime.now()
        response = await self.create_session(messages, res_format=LLMResponse)
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        response_time = round(response_time, 2)
        user = messages[-1].get("role", "unknown") if messages else "unknown"
        try:
            usage = response.usage
            output = response.choices[0].message.content.parsed
            actions_summary = [step.name for step in output.actions] if output.actions else []
            log_llm_helper(_logger, "LLM 响应成功", "success", "Response", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           actions_summary, user, messages[-1]["content"] if messages else "")
            
        except Exception as e:
            log_llm_helper(_logger, f"LLM 响应解析失败: {e}", "error", "Response", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           None, user, messages[-1]["content"] if messages else "")
            raise errors.LLMParseError("LLM 响应解析失败", retryable=True) from e
        # 解析actions字段为字典
        actions_dict = [step.model_dump() for step in output.actions]
        skill_progress_dict = output.skillProgress.model_dump() if output.skillProgress else None
        # 构建最终的字典
        result_dict = {
            "actions": actions_dict,
            "continue": output.continue_,
            "skillProgress": skill_progress_dict
        }
        # 然后再序列化，转换为 JSON 字符串
        return result_dict

    async def get_reflection(self, messages: list) -> str:
        start_time = datetime.datetime.now()
        response = await self.create_session(messages, res_format=LLMReflect)
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        response_time = round(response_time, 2)
        user = messages[-1].get("role", "unknown") if messages else "unknown"
        try:
            output = response.choices[0].message.content.parsed
            usage = response.usage
            log_llm_helper(_logger, "LLM 反思成功响应", "success", "Reflection", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           None, user, messages[-1]["content"][:100] if messages else "")
        except Exception as e:
            log_llm_helper(_logger, f"LLM 反思响应解析失败: {e}", "error", "Reflection", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           None, user, messages[-1]["content"][:100] if messages else "")
            raise errors.LLMParseError("LLM 反思响应解析失败", retryable=True) from e
        # 构建最终的字典
        result_dict = {
            "failure": output.failure,
            "reason": output.reason,
            "label": output.label.value if output.label else None
        }
        return json.dumps(result_dict, ensure_ascii=False)

    async def get_skill_generation(self, messages: list) -> str:
        start_time = datetime.datetime.now()
        response = await self.create_session(messages, res_format=LLMGenerateSkill)
        response_time = (datetime.datetime.now() - start_time).total_seconds()
        response_time = round(response_time, 2)
        user = messages[-1].get("role", "unknown") if messages else "unknown"
        try:
            output = response.choices[0].message.content.parsed
            usage = response.usage
            log_llm_helper(_logger, "LLM 技能生成成功响应", "success", "SkillGeneration", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           output.name, user, messages[-1]["content"][:100] if messages else "")
        except Exception as e:
            log_llm_helper(_logger, f"LLM 技能生成响应解析失败: {e}", "error", "SkillGeneration", response_time,
                           usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
                           None, user, messages[-1]["content"][:100] if messages else "")
            raise errors.LLMParseError("LLM 技能生成响应解析失败", retryable=True) from e
        output_dict = {
            "name": output.name,
            "description": output.description,
            "action_sequences": [seq.model_dump() for seq in output.action_sequences]
        }
        return output_dict

@retry
async def decide(llm: LLMClient, demand:str, chatHistory: list, tools: list, skill_progress: Optional[dict] = None, extra_context: str = "") -> str:
    """根据聊天历史调用 LLM，返回严格的动作 JSON（序列化的字符串）。

    参数:
        chatHistory   — 聊天历史
        tools         — 可选工具列表
        skill_progress  — 技能续行信息，字典
        extra_context — 额外的上下文知识（如物品信息），注入到聊天历史之前
    """
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2) # 把聊天历史转换为 JSON 字符串，方便在 prompt 直接填充
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2) # 把工具列表转换为 JSON 字符串，方便在 prompt 直接填充
    skill_progress_json = json.dumps(skill_progress, ensure_ascii=False, indent=2) if skill_progress else "null" # 把技能续行信息转换为 JSON 字符串，方便在 prompt 直接填充
    extra_context_json = json.dumps(extra_context, ensure_ascii=False, indent=2) if extra_context else "null" # 把额外上下文转换为 JSON 字符串，方便在 prompt 直接填充

    data = {"tools": tools_json, "extra_context": extra_context_json, "history": history_json,
            "skill_progress": skill_progress_json}

    prompt = _prompts.get("decide", {}).get("system_prompt", "")
    prompt = Template(prompt["template"]).render(data)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": demand}
    ]
    raw = await llm.get_response(messages)
    return raw

@retry
async def reflect_on_failure(llm: LLMClient,chatHistory: list) -> str:
    """反思：LLM 分析任务失败原因，生成改进建议。"""
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2) # 把聊天历史转换为 JSON 字符串，方便在 prompt 直接填充
    prompt = _prompts.get("reflect", {}).get("system_prompt", "")
    data = {"history": history_json}
    prompt = Template(prompt["template"]).render(data)

    raw = await llm.get_reflection([{"role": "system", "content": prompt}])
    return raw

@retry
async def generate_skill(llm: LLMClient, chatHistory: list, skill_name: str) -> str:
    """用 LLM 总结保存技能。"""
    history_json = json.dumps(chatHistory, ensure_ascii=False, indent=2)
    skill_name_json = json.dumps(skill_name, ensure_ascii=False)
    prompt = _prompts.get("generateSkill", {}).get("system_prompt", "")
    data = {"history": history_json, "skill_name": skill_name_json}
    prompt = Template(prompt["template"]).render(data)
    raw = await llm.get_skill_generation([{"role": "system", "content": prompt}])
    return raw


_logger = get_logger("aip.llm", settings.logging.llm_log_path,
                     settings.logging.log_level, settings.logging.log_backup_count, with_stream=True)
_prompts = get_all_prompts()
