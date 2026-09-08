import functools
import asyncio
import os
import contextvars
import logging
from logging.handlers import TimedRotatingFileHandler
from pythonjsonlogger import json as jsonlogger
from .errors import LLMParseError,LLMAPIError
import datetime
import uuid

# 三层日志共享的 trace_id 上下文（中间件 set，各层日志 get）
trace_id_var = contextvars.ContextVar("trace_id", default="")

base_path = os.path.dirname(os.path.abspath(__file__))
prompts_path = os.path.join(base_path, "prompts")
prompts_names = [f[:-5] for f in os.listdir(prompts_path) if f.endswith(".yaml")]


def get_logger(name: str, log_path: str, level: str = "INFO",
               backup_count: int = 7) -> logging.Logger:
    """统一的 logger 工厂：JSON 格式 + 按天轮转文件，可选控制台输出。幂等，重复调用返回同一 logger。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(str(level).upper())

    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = TimedRotatingFileHandler(log_path, encoding="utf-8", when="midnight", backupCount=backup_count)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


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
        prompts[name] = get_prompts_from_yaml(os.path.join(prompts_path, f"{name}.yaml"))
    return prompts


def retry(func):
    """支持 async 和 sync 的重试装饰器，失败后打印异常并重试。"""
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if isinstance(e,(LLMParseError, LLMAPIError)) and e.retryable: # 可重试异常进行重试
                        print(f"第 {attempt + 1} 次失败: {type(e).__name__}: {e}")
                        if attempt == max_retries - 1: # 最后一次失败，抛出异常
                            raise RuntimeError(f"LLM 调用失败，已重试 {max_retries} 次: {type(e).__name__}: {e}") from e
                    else:# 非可重试异常直接抛出
                        raise RuntimeError(f"LLM 调用失败: {type(e).__name__}: {e}") from e
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 如果是可重试异常，打印错误信息并重试
                    if isinstance(e,(LLMParseError, LLMAPIError)) and e.retryable:
                        print(f"第 {attempt + 1} 次失败: {type(e).__name__}: {e}")
                        if attempt == max_retries - 1:
                            raise RuntimeError(f"LLM 调用失败，已重试 {max_retries} 次: {type(e).__name__}: {e}") from e
                    else:
                        raise RuntimeError(f"LLM 调用失败: {type(e).__name__}: {e}") from e
        return sync_wrapper

def log_server_event(event_type,logger):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                logger.info(f"[{event_type}] 执行成功",
                            extra={"event_type": event_type,
                                   "event_status": "success",
                                   "timestamp": datetime.datetime.now().isoformat(),
                                   "trace_id": trace_id_var.get(),
                                   "event_id": str(datetime.datetime.now().timestamp())})
                logger.debug(f"[{event_type}] 执行成功: {result}")
                return result
            except Exception as e:
                logger.info(f"[{event_type}] 执行失败: {e}",
                    extra={"event_type": event_type,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "trace_id": trace_id_var.get(),
                        "event_id":str(datetime.datetime.now().timestamp()),
                        "event_status":"failure",})
                logger.debug(f"[{event_type}] 执行失败: {e}", exc_info=True)
                raise RuntimeError(f"[{event_type}] 执行失败: {e}") from e
        return wrapper
    return decorator


def log_llm_helper(llm_logger, info, status, function, response_time,
                   input_usage, output_usage, total_usage,
                   skill_name, user, demand, actions_summary=None):
    """LLM 层统一日志：直接传参，公共字段自动组装。"""
    llm_logger.info(info,
        extra={"trace_id": trace_id_var.get(),
               "status": status,
               "function": function,
               "response_time": response_time,
               "input_usage": input_usage,
               "output_usage": output_usage,
               "total_usage": total_usage,
               "skill_name": skill_name,
               "user": user,
               "demand": demand,
               "actions_summary": actions_summary,
               "ID": uuid.uuid4().hex})
