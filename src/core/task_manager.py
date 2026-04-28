from __future__ import annotations

import threading
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    import multiprocessing

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TaskProgress:
    current: int = 0
    total: int = 0
    current_item: str = ""
    status: TaskStatus = TaskStatus.PENDING
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    log_messages: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BackgroundTask:
    task_id: str
    collection_name: str
    process_name: str
    checklist_name: str
    process_data: Dict[str, Any]
    papers: List[Dict[str, Any]]
    progress: TaskProgress = field(default_factory=TaskProgress)
    thread: Optional[threading.Thread] = None
    process: Optional["multiprocessing.Process"] = None
    stop_event: threading.Event = field(default_factory=threading.Event)


class TaskManager:
    _instance: Optional['TaskManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: Dict[str, BackgroundTask] = {}
        self._tasks_lock = threading.RLock()
    
    def create_task(
        self,
        collection_name: str,
        process_name: str,
        checklist_name: str,
        process_data: Dict[str, Any],
        papers: List[Dict[str, Any]],
    ) -> str:
        task_id = str(uuid.uuid4())
        
        task = BackgroundTask(
            task_id=task_id,
            collection_name=collection_name,
            process_name=process_name,
            checklist_name=checklist_name,
            process_data=process_data,
            papers=papers,
        )
        task.progress.status = TaskStatus.PENDING
        task.progress.total = len(papers)
        task.progress.started_at = datetime.now()
        
        with self._tasks_lock:
            self._tasks[task_id] = task
        
        return task_id
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        with self._tasks_lock:
            return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, BackgroundTask]:
        with self._tasks_lock:
            return self._tasks.copy()
    
    def get_tasks_for_collection(self, collection_name: str) -> List[BackgroundTask]:
        with self._tasks_lock:
            return [
                task for task in self._tasks.values()
                if task.collection_name == collection_name
            ]
    
    def get_running_task_for_collection(self, collection_name: str) -> Optional[BackgroundTask]:
        tasks = self.get_tasks_for_collection(collection_name)
        for task in tasks:
            if task.progress.status == TaskStatus.RUNNING:
                return task
        return None
    
    def stop_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        if task.progress.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task.stop_event.set()
            logger.info(f"Stop event set for task {task_id}")
            if task.progress.status == TaskStatus.PENDING:
                task.progress.status = TaskStatus.STOPPED
                task.progress.completed_at = datetime.now()
                logger.info(f"Task {task_id} marked as STOPPED (was PENDING)")
            
            return True
        
        return False
    
    def stop_all_tasks_for_collection(self, collection_name: str) -> int:
        tasks = self.get_tasks_for_collection(collection_name)
        stopped_count = 0
        for task in tasks:
            if task.progress.status == TaskStatus.RUNNING:
                if self.stop_task(task.task_id):
                    stopped_count += 1
        return stopped_count
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task (after it's completed or stopped)."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task and task.progress.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED):
                del self._tasks[task_id]
                return True
            return False
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        with self._tasks_lock:
            to_delete = [
                task_id for task_id, task in self._tasks.items()
                if task.progress.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED)
                and task.progress.completed_at
                and task.progress.completed_at < cutoff
            ]
            for task_id in to_delete:
                del self._tasks[task_id]
        
        logger.info(f"Cleaned up {len(to_delete)} old tasks")
