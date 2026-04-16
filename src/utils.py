"""
utils.py
--------
Shared helpers: config loading, logging setup, dotenv resolution.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(config_path: str | Path = "config/config.yaml") -> dict[str, Any]:
    """
    Load YAML config and overlay any environment-variable overrides.
    Also loads .env from the same directory as config_path.
    """
    config_path = Path(config_path)
    env_file = config_path.parent / ".env"
    if not env_file.exists():
        env_file = Path(".env")
    load_dotenv(dotenv_path=env_file, override=True)

    with open(config_path, encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)

    return cfg


def setup_logging(cfg: dict[str, Any]) -> None:
    """Configure root logger from config."""
    log_cfg = cfg.get("logging", {})
    level_name = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_file: str | None = log_cfg.get("log_file")

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
