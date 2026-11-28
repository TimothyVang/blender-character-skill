"""Telemetry settings. blender-mcp-plus sends no telemetry: disabled, with no backend address or key."""
from dataclasses import dataclass


@dataclass
class TelemetryConfig:
    enabled: bool = False
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_bucket: str = ""
    timeout: float = 5.0
    max_prompt_length: int = 0


telemetry_config = TelemetryConfig()
