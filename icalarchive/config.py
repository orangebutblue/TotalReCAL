"""Configuration management for ICalArchive."""
try:
    import tomllib as tomli
except ImportError:
    import tomli
import tomli_w
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class SourceConfig:
    """Configuration for an iCal source."""
    url: str
    fetch_interval_minutes: int = 30
    enabled: bool = True


@dataclass
class OutputConfig:
    """Configuration for an output feed."""
    filter_by_category: list[str] = field(default_factory=list)
    exclude_category: list[str] = field(default_factory=list)
    include_summary_regex: Optional[str] = None
    exclude_summary_regex: Optional[str] = None
    include_sources: list[str] = field(default_factory=list)


@dataclass
class RuleConfig:
    """Configuration for an auto-hide rule."""
    rule_id: str
    rule_type: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    """Main application configuration."""
    sources: Dict[str, SourceConfig] = field(default_factory=dict)
    outputs: Dict[str, OutputConfig] = field(default_factory=dict)
    rules: list[RuleConfig] = field(default_factory=list)
    calendar_port: int = 8000
    ui_port: int = 8001


class ConfigManager:
    """Manages configuration loading and saving."""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
    def load(self) -> AppConfig:
        """Load configuration from TOML file."""
        if not self.config_path.exists():
            return AppConfig()
            
        with open(self.config_path, 'rb') as f:
            data = tomli.load(f)
        
        sources = {}
        for name, src_data in data.get('sources', {}).items():
            sources[name] = SourceConfig(**src_data)
        
        outputs = {}
        for name, out_data in data.get('outputs', {}).items():
            outputs[name] = OutputConfig(**out_data)
        
        rules = []
        for rule_data in data.get('rules', []):
            rules.append(RuleConfig(**rule_data))
        
        return AppConfig(
            sources=sources,
            outputs=outputs,
            rules=rules,
            calendar_port=data.get('calendar_port', 8000),
            ui_port=data.get('ui_port', 8001),
        )
    
    def save(self, config: AppConfig) -> None:
        """Save configuration to TOML file."""
        data = {
            'sources': {name: asdict(src) for name, src in config.sources.items()},
            'outputs': {name: asdict(out) for name, out in config.outputs.items()},
            'rules': [asdict(rule) for rule in config.rules],
            'calendar_port': config.calendar_port,
            'ui_port': config.ui_port,
        }
        
        with open(self.config_path, 'wb') as f:
            tomli_w.dump(data, f)
