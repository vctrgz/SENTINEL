from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from utils.logger import setup_logger
from utils.task_execution_engine import TaskExecutionEngine
from utils.task_intent import is_parallel_safe_task

logger = setup_logger()


class DAGExecutor:
    """
    Ejecuta un plan de tareas respetando dependencias (DAG).
    Modos: parallel | sequential | exclusive

    El paralelismo se reintroduce de forma conservadora: solo para tareas
    independientes marcadas como seguras para paralelizar. Las tareas de
    edicion/reparacion y las que puedan replanificar se mantienen secuenciales.
    """

    def __init__(self, parallel_executor, router, max_parallel_tasks: int = 4) -> None:
        self.parallel_executor = parallel_executor
        self.router = router
        self.engine = TaskExecutionEngine(router)
        self.max_parallel_tasks = max_parallel_tasks

    def run(
        self,
        plan: dict,
        translator,
        supervisor,
        context: Optional[dict] = None,
    ) -> dict:
        tasks = plan.get("tasks", [])
        if not tasks:
            logger.warning("[DAGExecutor] El plan no contiene tareas.")
            return {}

        task_context = context or {}
        completed: dict = {}
        pending = {t["id"]: t for t in tasks}

        while pending:
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.get("depends_on", []))
            ]

            if not ready:
                raise Exception(
                    f"Deadlock en el DAG. Tareas bloqueadas: {list(pending.keys())}"
                )

            parallel_tasks: list = []
            sequential_tasks: list = []
            exclusive_tasks: list = []

            for task in ready:
                mode = task.get("mode", "parallel")
                if mode == "sequential":
                    sequential_tasks.append(task)
                elif mode == "exclusive":
                    exclusive_tasks.append(task)
                else:
                    parallel_tasks.append(task)

            for task in exclusive_tasks:
                logger.info(f"[DAGExecutor] Exclusiva: {task['id']}")
                result = self.engine.execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            for task in sequential_tasks:
                logger.info(f"[DAGExecutor] Secuencial: {task['id']}")
                result = self.engine.execute_task(task, translator, supervisor, task_context)
                completed[task["id"]] = result
                del pending[task["id"]]

            if parallel_tasks:
                safe_parallel = [task for task in parallel_tasks if is_parallel_safe_task(task)]
                fallback_sequential = [task for task in parallel_tasks if not is_parallel_safe_task(task)]

                if safe_parallel:
                    logger.info(f"[DAGExecutor] Paralelizando {len(safe_parallel)} tarea(s) seguras")
                    parallel_results = self._execute_parallel(safe_parallel, translator, supervisor, task_context)
                    for task_id, result in parallel_results.items():
                        completed[task_id] = result
                        if task_id in pending:
                            del pending[task_id]

                for task in fallback_sequential:
                    logger.info(f"[DAGExecutor] Paralela degradada a secuencial: {task['id']}")
                    result = self.engine.execute_task(task, translator, supervisor, task_context)
                    completed[task["id"]] = result
                    del pending[task["id"]]

        return completed

    def _execute_parallel(self, tasks: list[dict], translator, supervisor, context: dict) -> dict:
        results: dict = {}
        max_workers = max(1, min(self.max_parallel_tasks, len(tasks)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.engine.execute_task, task, translator, supervisor, context): task["id"]
                for task in tasks
            }

            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    results[task_id] = future.result()
                except Exception as exc:
                    logger.error(f"[DAGExecutor] Tarea paralela {task_id} fallo: {exc}")
                    results[task_id] = {
                        "task_id": task_id,
                        "status": "fatal",
                        "reason": str(exc),
                        "action_results": [],
                        "execution_state": {
                            "task_id": task_id,
                            "status": "fatal",
                            "last_failure": str(exc),
                        },
                    }

        return results
