from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from ..config import Settings
from ..tools.apps import AppIndex
from ..tools.reminders import ReminderService


@dataclass
class Services:
    settings: Settings
    llm: Any
    apps: AppIndex
    reminders: ReminderService
