import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict
from utils.logger import logger


class ParallelExecutor:
    """
    Ejecuta lotes de tareas en paralelo.

    Si ya hay un event loop activo en el hilo actual, usa threads para evitar
    llamar a asyncio.run() dentro de FastAPI/Uvicorn. En contexto síncrono,
    usa asyncio para coordinar las tareas concurrentes.
    """

    def __init__(self, router, max_workers: int = 8):
        self.router = router
        self.max_workers = max_workers

    def execute(self, tasks_with_commands: Dict[str, Dict]) -> Dict[str, Any]:
        if not tasks_with_commands:
            return {}

        start = time.time()
        logger.info(
            f"[ParallelExecutor] Ejecutando {len(tasks_with_commands)} tareas en paralelo"
        )

        if self._has_running_loop():
            logger.debug("[ParallelExecutor] Event loop activo, usando ThreadPoolExecutor")
            results = self._execute_threaded(tasks_with_commands)
        else:
            results = self._execute_async(tasks_with_commands)

        elapsed = time.time() - start
        logger.info(f"[ParallelExecutor] {len(results)} tareas completadas en {elapsed:.2f}s")
        return results

    def _execute_async(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        return asyncio.run(self._gather_tasks(tasks))

    @staticmethod
    def _has_running_loop() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    async def _gather_tasks(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        results: Dict[str, Any] = {}

        async def run_task(task_id: str, data: Dict) -> tuple[str, Any]:
            commands = data.get("commands", [])
            if not commands:
                return task_id, {"status": "skipped", "reason": "No commands"}
            try:
                result = await loop.run_in_executor(None, self.router.execute, commands)
                return task_id, result
            except Exception as e:
                logger.error(f"[ParallelExecutor] Error en tarea {task_id}: {e}")
                return task_id, {"error": str(e), "commands": commands}

        pairs = await asyncio.gather(
            *(run_task(task_id, data) for task_id, data in tasks.items()),
            return_exceptions=False,
        )

        for task_id, result in pairs:
            results[task_id] = result

        return results

    def _execute_threaded(self, tasks: Dict[str, Dict]) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for task_id, data in tasks.items():
                commands = data.get("commands", [])
                if not commands:
                    results[task_id] = {"status": "skipped", "reason": "No commands"}
                    continue
                future = executor.submit(self.router.execute, commands)
                futures[future] = task_id

            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    results[task_id] = future.result()
                except Exception as e:
                    logger.error(f"[ParallelExecutor] Tarea {task_id} falló: {e}")
                    results[task_id] = {"error": str(e), "task_id": task_id}

        return results
