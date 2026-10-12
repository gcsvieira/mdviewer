"""Persistent viewer preferences, stored under ~/.config/mdviewer."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    vim_mode: bool = False
    file_navigation_style: str = 'scroll'
    element_color: str = 'white'


OPTIONS = (('vim-mode', (False, True)),
           ('file-navigation-style', ('scroll', 'paginated')),
           ('element-color', ('white', 'black')))


def config_path() -> Path:
    return Path.home() / '.config/mdviewer/settings.json'


def load_settings(path: Path | None = None) -> Settings:
    settings = Settings()
    try:
        data = json.loads((path or config_path()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return settings
    if not isinstance(data, dict):
        return settings
    for name, choices in OPTIONS:
        value = data.get(name)
        if type(value) is type(choices[0]) and value in choices:
            setattr(settings, name.replace('-', '_'), value)
    return settings


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {name: getattr(settings, name.replace('-', '_')) for name, _ in OPTIONS}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
