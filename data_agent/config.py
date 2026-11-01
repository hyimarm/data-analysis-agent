from __future__ import annotations
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("MPLCONFIGDIR", str(BASE_DIR / ".mplconfig"))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 模型服务：ollama（本地）| deepseek（云端）
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-flash"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    temperature: float = 0.1

    # 数据库
    db_path: Path = BASE_DIR / "data" / "business.db"

    # SQL 安全边界
    sql_max_rows: int = 200
    sql_timeout_seconds: int = 10
    sql_temp_store: str = "MEMORY"

    # 产物路径
    chart_dir: Path = BASE_DIR / "charts"
    output_dir: Path = BASE_DIR / "outputs"

    @field_validator("db_path", "chart_dir", "output_dir", mode="after")
    @classmethod
    def _to_absolute(cls, value: Path) -> Path:
        """相对路径一律按项目根解析，避免受启动目录影响。

        .env 里写 data/business.db 时，如果直接用它，结果取决于 cwd；
        统一拼上 BASE_DIR 后，从任何目录启动都指向同一个文件。
        """
        return value if value.is_absolute() else (BASE_DIR / value).resolve()



settings = Settings()