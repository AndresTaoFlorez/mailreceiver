from __future__ import annotations

from typing import Any

from agent.browser.base_step import BaseStep, StepContext
from api.shared.logger import get_logger

logger = get_logger("agent")


class StepPipeline:

    def __init__(self, steps: list[BaseStep]):
        self.steps = steps

    async def run(self, ctx: StepContext) -> dict[str, Any]:
        results: dict[str, Any] = {}

        for step in self.steps:
            logger.info("Ejecutando step '%s'", step.name)
            try:
                ctx = await step.execute(ctx)
                results[step.name] = {"status": "ok"}
                logger.info("Step '%s' completado", step.name)
            except Exception as exc:
                results[step.name] = {"status": "failed", "error": str(exc)}
                await step.on_failure(ctx, exc)

                if step.is_critical:
                    logger.error("Step crítico '%s' falló — abortando pipeline", step.name)
                    break

                logger.warning("Step no-crítico '%s' falló — continuando", step.name)

        return results
