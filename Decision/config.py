from pydantic_settings import BaseSettings
from pydantic import Field
import os
from typing import Optional

base_dir = os.path.dirname(os.path.abspath(__file__))

def check_before_settings():
    log_dir = os.path.join(base_dir, "logs")
    skill_dir = os.path.join(base_dir, "skills")
    prompts_dir = os.path.join(base_dir, "prompts")
    tools_dir = os.path.join(base_dir, "..", "Control")
    for d in [log_dir, skill_dir, prompts_dir, tools_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

class FastAPISettings(BaseSettings):
    fastapi_url: str = Field("http://localhost:8000", env="FASTAPI_URL", description="FastAPI 服务的 URL 地址")
    global_llm_semaphore: int = Field(10, env="GLOBAL_LLM_SEMAPHORE", description="限制同时进行的 LLM 调用数量",example=10)

class LLMSettings(BaseSettings):
    llm_model: str = Field("deepseek-v4-flash", env="LLM_MODEL", description="LLM 模型名称")
    llm_temperature: float = Field(0.7, env="LLM_TEMPERATURE", description="LLM 模型的温度参数",example=0.7)
    openai_api_key: Optional[str] = Field(None, env="OpenAI_API_KEY", description="OpenAI API Key，用于访问 OpenAI 的 LLM 服务")
    model_base_url: str = Field("https://api.deepseek.com", env="MODEL_BASE_URL", description="LLM 模型的基础 URL 地址，用于访问自定义 LLM 服务")

class LoggingSettings(BaseSettings):
    log_level: str = Field("info", env="LOG_LEVEL", description="日志记录的级别",example="info")
    fastapi_log_path : str = Field(os.path.join(base_dir, "logs", "fastapi.log"), env="FASTAPI_LOG_PATH", description="FastAPI 日志文件路径",example=os.path.join(base_dir, "logs", "fastapi.log"))
    server_log_path : str = Field(os.path.join(base_dir, "logs", "server.log"), env="SERVER_LOG_PATH", description="服务器日志文件路径",example=os.path.join(base_dir, "logs", "server.log"))
    llm_log_path : str = Field(os.path.join(base_dir, "logs", "llm.log"), env="LLM_LOG_PATH", description="LLM 日志文件路径",example=os.path.join(base_dir, "logs", "llm.log"))
    log_backup_count: int = Field(7, env="LOG_BACKUP_COUNT", description="日志文件的备份数量",example=7)

class FileSettings(BaseSettings):
    skill_path:str = Field(os.path.join(base_dir, "skills"), env="SKILL_PATH", description="技能文件存储路径",example=os.path.join(base_dir, "skills"))
    prompts_path:str = Field(os.path.join(base_dir, "prompts"), env="PROMPTS_PATH", description="prompts 文件存储路径",example=os.path.join(base_dir, "prompts"))
    tools_path:str = Field(os.path.join(base_dir, "..", "Control", "tools.json"), env="TOOLS_PATH", description="工具配置文件路径",example=os.path.join(base_dir, "..", "Control", "tools.json"))


class Settings(BaseSettings):
    fastapi: FastAPISettings = FastAPISettings()
    llm: LLMSettings = LLMSettings()
    logging: LoggingSettings = LoggingSettings()
    files: FileSettings = FileSettings()

    env: str = Field("development", env="ENV", description="运行环境，development 或 production",example="development")

    class Config:
        env_file = os.path.join(base_dir,"..", ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略未定义的环境变量

check_before_settings()
settings = Settings()
if not settings.llm.openai_api_key:
    raise ValueError("OpenAI API Key 未设置，请在环境变量或根目录 .env 中设置 OpenAI_API_KEY")
