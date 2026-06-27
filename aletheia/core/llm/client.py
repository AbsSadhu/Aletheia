"""
Ollama Async Client for Local LLM Inference
"""

import asyncio
import httpx
import json
import time
from loguru import logger
from typing import Dict, Any, Optional


class OllamaCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_secs: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_secs = cooldown_secs
        self.failures = 0
        self.open_until = 0.0
        self._lock = asyncio.Lock()

    async def check_available(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            if self.open_until > 0 and now < self.open_until:
                return False
            if self.open_until > 0:
                # reset
                self.failures = 0
                self.open_until = 0.0
            return True

    async def record_failure(self):
        async with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.open_until = time.monotonic() + self.cooldown_secs
                logger.warning(
                    f"OllamaCircuitBreaker: circuit opened for {self.cooldown_secs}s due to consecutive failures."
                )

    async def record_success(self):
        async with self._lock:
            self.failures = 0
            self.open_until = 0.0


class OllamaClient:
    _circuit = OllamaCircuitBreaker()
    _call_history: list[dict[str, Any]] = []

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    async def generate_structured(
        self, prompt: str, model: str = "llama3", format: str = "json"
    ) -> Optional[Dict[str, Any]]:
        """
        Call Ollama API to generate a JSON response with retries, backoff, and circuit breaking.
        """
        if not await self._circuit.check_available():
            logger.error("OllamaClient: Circuit is open. Skipping request.")
            return None

        url = f"{self.base_url}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False, "format": format}

        max_attempts = 3
        backoff_base = 1.0

        for attempt in range(1, max_attempts + 1):
            start_time = time.monotonic()
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, timeout=30.0)
                    response.raise_for_status()
                    data = response.json()

                latency = time.monotonic() - start_time
                await self._circuit.record_success()
                
                # Ollama is locally hosted and free
                cost = 0.0
                logger.info(
                    f"OllamaClient: successfully generated output. latency={latency:.2f}s cost=${cost:.2f} model={model}"
                )

                if "response" in data:
                    try:
                        parsed = json.loads(data["response"])
                        OllamaClient._call_history.append({
                            "provider": "ollama",
                            "model": model,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "latency_secs": latency,
                            "cost_usd": 0.0,
                            "timestamp": time.time(),
                        })
                        return parsed
                    except json.JSONDecodeError:
                        logger.error(
                            f"Failed to parse JSON from Ollama response: {data['response']}"
                        )
                        return None
                return None

            except Exception as e:
                latency = time.monotonic() - start_time
                await self._circuit.record_failure()
                logger.warning(
                    f"OllamaClient: attempt {attempt}/{max_attempts} failed (latency={latency:.2f}s): {str(e)}"
                )
                if attempt < max_attempts:
                    sleep_time = backoff_base * (2 ** (attempt - 1))
                    await asyncio.sleep(sleep_time)

        logger.error("OllamaClient: all retry attempts exhausted.")
        return None
