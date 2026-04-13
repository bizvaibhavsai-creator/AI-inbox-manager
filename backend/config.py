import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Instantly.ai
    instantly_api_key: str = ""
    instantly_webhook_secret: str = ""  # Optional: verify webhook authenticity

    # OpenAI
    openai_api_key: str = ""

    # n8n internal webhook URLs
    n8n_slack_webhook_url: str = "http://n8n:5678/webhook/slack-notify"
    n8n_base_url: str = "http://n8n:5678"

    # Google Sheets (handled by n8n, but sheet ID needed for reference)
    google_sheet_id: str = ""

    # Database
    database_url: str = "sqlite:///./inbox_manager.db"

    # Playbook paths
    playbook_path: str = str(Path(__file__).parent.parent / "playbook.md")
    followups_path: str = str(Path(__file__).parent.parent / "followups.md")
    linkedin_playbook_path: str = str(Path(__file__).parent.parent / "linkedin_playbook.md")

    # HeyReach (LinkedIn automation)
    heyreach_api_key: str = ""

    # Follow-up windows (hours)
    # Follow-up 1: 2 hours, Follow-up 2: 24h, Follow-up 3-9: every 24h
    followup_windows_hours: list[int] = [2, 24, 24, 24, 24, 24, 24, 24, 24]

    # API base URLs
    instantly_api_base: str = "https://api.instantly.ai/api/v2"

    # CORS origins for dashboard
    cors_origins: list[str] = ["http://localhost:8080", "http://localhost:3000"]

    # Test mode - uses mock AI responses when API keys aren't set
    test_mode: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
