import logging
import os
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class PersistentMemory:
    """File-based cross-session persistent memory for the Aletheia agent."""

    def __init__(self, memory_dir: str = "~/.aletheia/memory"):
        self.memory_dir = Path(os.path.expanduser(memory_dir))
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.memory_dir / "MEMORY.md"

    def _get_file_path(self, memory_type: str, memory_id: str) -> Path:
        return self.memory_dir / f"{memory_type}_{memory_id}.md"

    def store(self, memory_type: str, content: str, memory_id: str = None) -> str:
        """Stores a new memory snippet."""
        if not memory_id:
            import uuid

            memory_id = str(uuid.uuid4())[:8]

        file_path = self._get_file_path(memory_type, memory_id)

        # Write content with basic frontmatter
        data = f"---\ntype: {memory_type}\nid: {memory_id}\n---\n\n{content}\n"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data)

        self._rebuild_index()
        logger.info(f"Stored {memory_type} memory: {memory_id}")
        return memory_id

    def recall(self, memory_type: str, memory_id: str) -> str | None:
        """Recalls a specific memory."""
        file_path = self._get_file_path(memory_type, memory_id)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def search(self, query: str) -> List[Dict[str, str]]:
        """Simple keyword search across memories."""
        results = []
        for file_path in self.memory_dir.glob("*.md"):
            if file_path.name == "MEMORY.md":
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if query.lower() in content.lower():
                    results.append({"file": file_path.name, "content_snippet": content[:200]})
        return results

    def _rebuild_index(self):
        """Rebuilds the index file."""
        entries = []
        for file_path in self.memory_dir.glob("*.md"):
            if file_path.name == "MEMORY.md":
                continue
            entries.append(file_path.name)

        with open(self.index_file, "w", encoding="utf-8") as f:
            f.write("# Memory Index\n\n")
            for entry in entries:
                f.write(f"- {entry}\n")
