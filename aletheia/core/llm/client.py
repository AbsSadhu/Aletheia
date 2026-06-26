"""
Ollama Async Client for Local LLM Inference
"""

import httpx
import json
from loguru import logger
from typing import Dict, Any, Optional


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    async def generate_structured(
        self, prompt: str, model: str = "llama3", format: str = "json"
    ) -> Optional[Dict[str, Any]]:
        """
        Call Ollama API to generate a JSON response.
        """
        url = f"{self.base_url}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False, "format": format}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                if "response" in data:
                    try:
                        return json.loads(data["response"])
                    except json.JSONDecodeError:
                        logger.error(
                            f"Failed to parse JSON from Ollama response: {data['response']}"
                        )
                        return None
                return None
            except Exception as e:
                logger.error(f"Ollama generation failed: {str(e)}")
                return None
