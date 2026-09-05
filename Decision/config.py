from pydantic_settings import BaseSettings
from pydantic import Field
import os
from typing import Optional
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))

def check_before_settings():
    log_dir = os.path.join(base_dir, "logs")
    skill_dir = os.path.join(base_dir, "skills")
    prompts_dir = os.path.join(base_dir, "prompts")
    tools_dir = os.path.join(base_dir, "..", "Control")
    env_file = os.path.join(base_dir, "..", ".env")
    if not os.path.exists(env_file):
        raise FileNotFoundError(f"环境变量文件 {env_file} 不存在，请创建并配置必要的环境变量。")
    for d in [log_dir, skill_dir, prompts_dir, tools_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

class FastAPISettings(BaseSettings):
    fastapi_url: str = Field("http://localhost:8000", description="FastAPI 服务的 URL 地址")
    global_llm_semaphore: int = Field(10, description="限制同时进行的 LLM 调用数量")

class LLMSettings(BaseSettings):
    llm_model: Optional[str] = Field(None, description="LLM 模型名称")
    llm_temperature: float = Field(0.7, description="LLM 模型的温度参数")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API Key，用于访问 OpenAI 的 LLM 服务")
    model_base_url: Optional[str] = Field(None, description="LLM 模型的基础 URL 地址，用于访问自定义 LLM 服务")

class LoggingSettings(BaseSettings):
    log_level: str = Field("info", description="日志记录的级别")
    fastapi_log_path : str = Field(os.path.join(base_dir, "logs", "fastapi.log"), description="FastAPI 日志文件路径")
    server_log_path : str = Field(os.path.join(base_dir, "logs", "server.log"), description="服务器日志文件路径")
    llm_log_path : str = Field(os.path.join(base_dir, "logs", "llm.log"), description="LLM 日志文件路径")
    log_backup_count: int = Field(7, description="日志文件的备份数量")

class FileSettings(BaseSettings):
    skill_path:str = Field(os.path.join(base_dir, "skills"), description="技能文件存储路径")
    prompts_path:str = Field(os.path.join(base_dir, "prompts"), description="prompts 文件存储路径")
    tools_path:str = Field(os.path.join(base_dir, "..", "Control", "tools.json"), description="工具配置文件路径")


class Settings(BaseSettings):
    load_dotenv()
    llm_model: Optional[str] = os.getenv("LLM_MODEL")
    openai_api_key: Optional[str] = os.getenv("OpenAI_API_KEY")
    model_base_url: Optional[str] = os.getenv("MODEL_BASE_URL")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", 0.7))


    fastapi: FastAPISettings = FastAPISettings()
    llm: LLMSettings = LLMSettings(llm_model=llm_model, openai_api_key=openai_api_key, model_base_url=model_base_url, llm_temperature=llm_temperature)
    logging: LoggingSettings = LoggingSettings()
    files: FileSettings = FileSettings()

check_before_settings()
settings = Settings()