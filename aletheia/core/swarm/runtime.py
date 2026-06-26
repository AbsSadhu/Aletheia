import asyncio
import logging
from typing import List, Dict, Any, AsyncGenerator
from aletheia.core.swarm.worker import SwarmWorker
from aletheia.core.agent.streaming import StreamEvent

logger = logging.getLogger(__name__)

class SwarmRuntime:
    """Coordinates execution of multiple SwarmWorkers."""

    def __init__(self, workers: List[SwarmWorker]):
        self.workers = workers

    async def execute_parallel(self, prompt: str, portfolio=None) -> AsyncGenerator[StreamEvent, None]:
        """Runs all workers in parallel and yields their stream events."""
        queue = asyncio.Queue()
        
        async def worker_task(worker: SwarmWorker):
            try:
                async for event in worker.execute(prompt, portfolio):
                    await queue.put(event)
            except Exception as e:
                logger.error(f"Worker {worker.name} failed: {e}")
                await queue.put(StreamEvent("error", {"worker": worker.name, "message": str(e)}))
            finally:
                await queue.put(None) # Signal completion
                
        tasks = [asyncio.create_task(worker_task(w)) for w in self.workers]
        
        active_workers = len(self.workers)
        while active_workers > 0:
            event = await queue.get()
            if event is None:
                active_workers -= 1
            else:
                yield event
                
        # Wait for all tasks to cleanly exit
        await asyncio.gather(*tasks)
