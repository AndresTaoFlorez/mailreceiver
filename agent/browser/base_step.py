from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from shared.logger import get_logger

logger = get_logger("agent")


@dataclass
class StepContext:
    page: Page
    shared: dict[str, Any] = field(default_factory=dict)


class BaseStep(ABC):
    name: str = "unnamed_step"
    is_critical: bool = True

    @abstractmethod
    async def execute(self, ctx: StepContext) -> StepContext: ...

    async def on_failure(self, ctx: StepContext, error: Exception) -> None:
        logger.error("Step '%s' falló: %s", self.name, error)
        try:
            await ctx.page.screenshot(path=f"screenshots/error_{self.name}.png")
        except Exception:
            logger.warning("No se pudo capturar screenshot para '%s'", self.name)
