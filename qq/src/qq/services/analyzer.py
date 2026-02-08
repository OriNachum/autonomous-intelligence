"""File analyzer — deeply reads, dissects, and internalizes files into memory.

Provides the analyze_files tool that delegates to a dedicated Strands Agent
for structured extraction, then stores results in MongoDB notes, notes.md,
and the Neo4j knowledge graph.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from strands import Agent, tool

logger = logging.getLogger("qq.analyzer")

# Chunk size for large files (~7500 tokens)
MAX_CHARS_PER_CHUNK = 30000

# Importance for analyzer-extracted notes (slightly above normal)
ANALYZER_IMPORTANCE = 0.8

# Max files to analyze in a single pattern match
MAX_PATTERN_FILES = 1000

# Dedup threshold (same as memory tools)
DEDUP_THRESHOLD = 0.85


def _generate_note_id() -> str:
    return f"note_{uuid.uuid4().hex[:12]}"


def _load_analyzer_prompt() -> str:
    """Load the analyzer agent system prompt."""
    prompt_path = (
        Path(__file__).parent.parent / "agents" / "analyzer_agent" / "analyzer_agent.system.md"
    )
    if prompt_path.exists():
        return prompt_path.read_text().strip()
    raise FileNotFoundError(f"Analyzer agent prompt not found: {prompt_path}")


def _clean_json_response(response: str) -> str:
    """Clean LLM response to extract valid JSON."""
    if not response or not isinstance(response, str):
        return "{}"

    # Remove thinking tags if present
    if "</think>" in response:
        response = response.split("</think>")[-1]

    response = response.strip()

    # Strip markdown code fences
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]

    return response.strip() or "{}"


class FileAnalyzer:
    """Orchestrates file reading, LLM extraction, and knowledge storage."""

    def __init__(self, file_manager, model=None):
        """
        Args:
            file_manager: FileManager instance for path resolution and document reading.
            model: Optional model instance. If None, uses get_model() on first call.
        """
        self.file_manager = file_manager
        self._model = model
        self._agent = None

        # Lazy-initialized backends
        self._backends = {}

    def _get_model(self):
        if self._model is None:
            from qq.agents import get_model
            self._model = get_model()
        return self._model

    def _get_agent(self) -> Agent:
        if self._agent is None:
            prompt = _load_analyzer_prompt()
            self._agent = Agent(
                name="file_analyzer",
                system_prompt=prompt,
                model=self._get_model(),
            )
        return self._agent

    def _get_backends(self):
        if self._backends:
            return self._backends

        try:
            from qq.embeddings import EmbeddingClient
            self._backends["embeddings"] = EmbeddingClient()
        except Exception as e:
            logger.warning(f"Embeddings unavailable: {e}")
            self._backends["embeddings"] = None

        try:
            from qq.memory.mongo_store import MongoNotesStore
            self._backends["mongo"] = MongoNotesStore()
        except Exception as e:
            logger.warning(f"MongoDB unavailable: {e}")
            self._backends["mongo"] = None

        try:
            from qq.memory.notes import get_notes_manager
            memory_dir = os.getenv("MEMORY_DIR", "./memory")
            self._backends["notes"] = get_notes_manager(memory_dir)
        except Exception as e:
            logger.warning(f"Notes manager unavailable: {e}")
            self._backends["notes"] = None

        try:
            from qq.services.graph import KnowledgeGraphAgent
            self._backends["graph"] = KnowledgeGraphAgent(
                model=self._get_model(),
            )
        except Exception as e:
            logger.warning(f"Knowledge graph unavailable: {e}")
            self._backends["graph"] = None

        return self._backends

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        backends = self._get_backends()
        client = backends.get("embeddings")
        if client and client.is_available:
            try:
                return client.get_embedding(text)
            except Exception as e:
                logger.warning(f"Embedding failed: {e}")
        return None

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def _read_full_file(self, path: str) -> Tuple[str, Dict[str, Any]]:
        """Read entire file content and collect source metadata."""
        resolved = self.file_manager._resolve_path(path)

        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {resolved}")
        if not resolved.is_file():
            raise ValueError(f"Not a file: {resolved}")

        # Read content (binary formats via DocumentReader)
        suffix = resolved.suffix.lower()
        if suffix in [".pdf", ".docx", ".xlsx", ".pptx"]:
            content = self.file_manager.document_reader.convert(resolved)
        else:
            content = resolved.read_text()

        # Collect source metadata
        from qq.memory.source import compute_file_checksum, collect_git_metadata

        checksum = compute_file_checksum(str(resolved))
        git_meta = collect_git_metadata(str(resolved))

        source_meta = {
            "source_type": "file",
            "file_path": str(resolved),
            "file_name": resolved.name,
            "checksum": checksum,
            "git_metadata": git_meta,
            "analyzed_at": datetime.utcnow().isoformat(),
        }

        return content, source_meta

    # ------------------------------------------------------------------
    # Re-analysis detection
    # ------------------------------------------------------------------

    def _already_analyzed(self, file_path: str, checksum: Optional[str]) -> bool:
        """Check if file was already analyzed with this exact checksum."""
        if not checksum:
            return False

        backends = self._get_backends()
        mongo = backends.get("mongo")
        if not mongo:
            return False

        try:
            existing = mongo.find_by_source_file(file_path)
            for note in existing:
                src = note.get("source", {})
                if src.get("checksum") == checksum:
                    return True
        except Exception as e:
            logger.debug(f"Re-analysis check failed: {e}")

        return False

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------

    def _run_extraction(
        self, content: str, focus: str, chunk_context: str = ""
    ) -> Dict[str, Any]:
        """Run the analyzer agent on file content and parse JSON result."""
        agent = self._get_agent()

        # Build user message
        parts = []
        if chunk_context:
            parts.append(chunk_context)
        if focus:
            parts.append(f"Focus area: {focus}")
        parts.append(f"File content:\n\n{content}")
        user_message = "\n\n".join(parts)

        try:
            response = str(agent(user_message))
            cleaned = _clean_json_response(response)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analyzer JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Analyzer extraction failed: {e}")
            return {}

    def _split_into_chunks(self, content: str, max_chars: int) -> List[str]:
        """Split content into chunks at line boundaries."""
        if len(content) <= max_chars:
            return [content]

        lines = content.splitlines(keepends=True)
        chunks = []
        current_chunk = []
        current_size = 0

        for line in lines:
            if current_size + len(line) > max_chars and current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_size = 0
            current_chunk.append(line)
            current_size += len(line)

        if current_chunk:
            chunks.append("".join(current_chunk))

        return chunks

    def _merge_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge extraction results from multiple chunks."""
        merged = {
            "overview": "",
            "notes": [],
            "entities": [],
            "relationships": [],
        }

        overviews = []
        seen_entities = set()
        seen_rels = set()

        for r in results:
            if r.get("overview"):
                overviews.append(r["overview"])

            for note in r.get("notes", []):
                merged["notes"].append(note)

            for entity in r.get("entities", []):
                key = entity.get("name", "")
                if key and key not in seen_entities:
                    seen_entities.add(key)
                    merged["entities"].append(entity)

            for rel in r.get("relationships", []):
                key = (rel.get("source", ""), rel.get("target", ""), rel.get("type", ""))
                if key not in seen_rels:
                    seen_rels.add(key)
                    merged["relationships"].append(rel)

        # Combine overviews
        if overviews:
            merged["overview"] = " ".join(overviews)

        return merged

    # ------------------------------------------------------------------
    # Knowledge storage
    # ------------------------------------------------------------------

    def _store_knowledge(
        self, extraction: Dict[str, Any], source_meta: Dict[str, Any]
    ) -> Dict[str, int]:
        """Store extracted knowledge in memory and knowledge graph.

        Returns:
            Dict with counts: notes_new, notes_reinforced, entities, relationships
        """
        backends = self._get_backends()
        mongo = backends.get("mongo")
        notes_mgr = backends.get("notes")
        graph = backends.get("graph")

        stats = {
            "notes_new": 0,
            "notes_reinforced": 0,
            "entities": len(extraction.get("entities", [])),
            "relationships": len(extraction.get("relationships", [])),
        }

        # Store notes in MongoDB + notes.md
        for note in extraction.get("notes", []):
            content = note.get("content", "")
            section = note.get("section", "Important Facts")
            if not content:
                continue

            # Validate section
            valid_sections = [
                "Key Topics", "Important Facts", "People & Entities",
                "Ongoing Threads", "File Knowledge",
            ]
            if section not in valid_sections:
                section = "Important Facts"

            embedding = self._get_embedding(content)

            # Dedup check
            if mongo and embedding:
                try:
                    duplicates = mongo.search_similar(embedding, limit=1)
                    if duplicates and duplicates[0].get("score", 0) >= DEDUP_THRESHOLD:
                        # Reinforce existing note
                        mongo.append_source_history(
                            duplicates[0]["note_id"],
                            source_meta,
                            boost_importance=0.1,
                        )
                        stats["notes_reinforced"] += 1
                        continue
                except Exception as e:
                    logger.warning(f"Dedup check failed: {e}")

            # Store new note
            note_id = _generate_note_id()
            if mongo:
                try:
                    mongo.upsert_note(
                        note_id=note_id,
                        content=content,
                        embedding=embedding or [],
                        section=section,
                        importance=ANALYZER_IMPORTANCE,
                        source=source_meta,
                    )
                    stats["notes_new"] += 1
                except Exception as e:
                    logger.warning(f"Failed to store note in MongoDB: {e}")

            if notes_mgr:
                try:
                    notes_mgr.add_item(section, content)
                except Exception as e:
                    logger.warning(f"Failed to add to notes.md: {e}")

        # Store entities + relationships in Neo4j
        if graph and (extraction.get("entities") or extraction.get("relationships")):
            graph_data = {
                "entities": extraction.get("entities", []),
                "relationships": extraction.get("relationships", []),
            }
            file_sources = {source_meta["file_path"]: source_meta}
            try:
                graph._store_extraction(
                    graph_data,
                    file_sources=file_sources,
                )
            except Exception as e:
                logger.warning(f"Failed to store in knowledge graph: {e}")
                stats["entities"] = 0
                stats["relationships"] = 0

        return stats

    # ------------------------------------------------------------------
    # Pattern-based batch analysis
    # ------------------------------------------------------------------

    def analyze_pattern(self, pattern: str, base_path: str = "", focus: str = "") -> str:
        """Analyze multiple files matching a regex pattern.

        Args:
            pattern: Regex pattern to match against relative file paths.
            base_path: Base directory to search in (defaults to file_manager cwd).
            focus: Optional focus area for analysis.

        Returns:
            Aggregated summary of all analyzed files.
        """
        base = self.file_manager._resolve_path(base_path) if base_path else Path(self.file_manager.cwd)

        if not base.exists():
            return f"Error: directory not found: {base}"
        if not base.is_dir():
            return f"Error: not a directory: {base}"

        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex pattern: {e}"

        matched_files = []
        for file_path in sorted(base.rglob("*")):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(base))
            if compiled.search(relative):
                matched_files.append(file_path)

        if not matched_files:
            return f"No files matched pattern '{pattern}' in {base}"

        if len(matched_files) > MAX_PATTERN_FILES:
            return (
                f"Pattern matched {len(matched_files)} files (limit is {MAX_PATTERN_FILES}). "
                f"Use a more specific pattern or narrow the base path."
            )

        summaries = []
        for file_path in matched_files:
            result = self.analyze(str(file_path), focus)
            summaries.append(f"## {file_path.relative_to(base)}\n{result}")

        header = f"Batch analysis: {len(matched_files)} files matching '{pattern}' in {base}\n"
        return header + "\n\n".join(summaries)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def analyze(self, path: str, focus: str = "") -> str:
        """Analyze a file: read, extract knowledge, store in memory.

        Args:
            path: File path (absolute or relative to session directory).
            focus: Optional focus area for analysis.

        Returns:
            Summary string describing what was analyzed and stored.
        """
        # Step 1: Read full file
        try:
            content, source_meta = self._read_full_file(path)
        except (FileNotFoundError, ValueError) as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {e}"

        if not content.strip():
            return f"File is empty: {source_meta['file_name']}"

        # Add focus to source metadata
        if focus:
            source_meta["analyzer_focus"] = focus

        # Step 2: Check for re-analysis
        if self._already_analyzed(source_meta["file_path"], source_meta.get("checksum")):
            return (
                f"File already analyzed with same content: {source_meta['file_name']}\n"
                f"Checksum: {source_meta.get('checksum', 'unknown')}\n"
                "Use memory_query to search for previously extracted knowledge."
            )

        # Step 3: Extract knowledge (chunked if needed)
        line_count = len(content.splitlines())
        file_info = f"{source_meta['file_name']} ({line_count} lines)"

        if len(content) > MAX_CHARS_PER_CHUNK:
            chunks = self._split_into_chunks(content, MAX_CHARS_PER_CHUNK)
            chunk_results = []
            for i, chunk in enumerate(chunks):
                chunk_ctx = f"[Chunk {i + 1}/{len(chunks)} of {source_meta['file_name']}]"
                result = self._run_extraction(chunk, focus, chunk_ctx)
                if result:
                    chunk_results.append(result)
            extraction = self._merge_results(chunk_results) if chunk_results else {}
        else:
            extraction = self._run_extraction(content, focus)

        if not extraction:
            return f"Analysis produced no results for {file_info}."

        # Step 4: Store knowledge
        stats = self._store_knowledge(extraction, source_meta)

        # Step 5: Build summary
        overview = extraction.get("overview", "No overview extracted.")
        total_notes = stats["notes_new"] + stats["notes_reinforced"]

        summary_parts = [
            f"Analyzed {file_info}",
            f"Extracted: {total_notes} notes ({stats['notes_new']} new, "
            f"{stats['notes_reinforced']} reinforced), "
            f"{stats['entities']} entities, {stats['relationships']} relationships",
            f"Overview: {overview}",
        ]

        # Key findings from notes
        key_notes = [
            n["content"] for n in extraction.get("notes", [])[:3]
        ]
        if key_notes:
            summary_parts.append("Key findings:")
            for kn in key_notes:
                summary_parts.append(f"  - {kn}")

        return "\n".join(summary_parts)


def create_analyzer_tool(file_manager):
    """Create the analyze_files tool with a shared FileAnalyzer instance.

    Args:
        file_manager: FileManager instance for path resolution.

    Returns:
        The analyze_files tool function.
    """
    analyzer = FileAnalyzer(file_manager)

    @tool
    def analyze_files(path: str = "", focus: str = "", pattern: str = "") -> str:
        """
        Deeply analyze a file: read, dissect, and internalize its contents into memory.

        Unlike read_file (which shows raw content), this tool:
        - Reads the entire file regardless of size
        - Extracts key concepts, entities, relationships, and important facts
        - Stores everything in long-term memory and knowledge graph
        - Returns a concise analysis summary

        Use this when you want to truly understand and remember a file's contents,
        not just glance at it.

        Args:
            path: Path to the file to analyze (absolute or relative to session directory).
                  When used with pattern, this acts as the base directory to search in.
            focus: Optional focus area to guide analysis (e.g., "API endpoints",
                   "error handling patterns", "data model"). If empty, performs
                   general-purpose analysis.
            pattern: Optional regex pattern to match multiple files for batch analysis.
                     When provided, all files under path matching the pattern are analyzed.
                     Example: r"\\.py$" to analyze all Python files.
        """
        if pattern:
            return analyzer.analyze_pattern(pattern, path, focus)
        if not path:
            return "Error: path is required when pattern is not provided."
        return analyzer.analyze(path, focus)

    return analyze_files
