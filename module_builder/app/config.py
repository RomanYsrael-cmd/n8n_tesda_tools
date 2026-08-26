from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODULE_BUILDER_", env_file=".env", extra="ignore")
    data_root: Path = Path("data")
    template: Path = Path("template/Module Template.docx")
    base_url: str = "http://localhost:8080"
    n8n_webhook_base: str = ""
    use_n8n: bool = True
    quiz_questions: int = 10

    def resolved(self) -> "Settings":
        self.data_root = self.data_root.expanduser().resolve()
        self.template = self.template.expanduser().resolve()
        return self


settings = Settings().resolved()


def ensure_secret(root: Path) -> bytes:
    from cryptography.fernet import Fernet

    secret_path = root / ".app-secret"
    if not secret_path.exists():
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
    return secret_path.read_bytes().strip()
