"""Memory tools - gives agents direct control over their knowledge.

Provides four tools: memory_add, memory_query, memory_verify, memory_reinforce.
These are registered as Strands @tool functions and added to every agent.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from strands import tool

logger = logging.getLogger("qq.memory_tools")

# Importance level mapping
IMPORTANCE_LEVELS = {
    "low": 0.3,
    "normal": 0.5,
    "high": 0.7,
    "core": 0.9,
}

# Valid sections for notes.md
VALID_SECTIONS = [
    "Key Topics",
    "Important Facts",
    "People & Entities",
    "Ongoing Threads",
    "File Knowledge",
]

# Similarity thresholds
DEDUP_THRESHOLD = 0.85
RELATED_THRESHOLD = 0.6
REINFORCE_THRESHOLD = 0.75

# Core promotion threshold
CORE_THRESHOLD = 0.8


def _generate_note_id() -> str:
    """Generate a unique note ID."""
    return f"note_{uuid.uuid4().hex[:12]}"


def _format_source_summary(source: dict) -> str:
    """Format a source dict into a short human-readable string."""
    if not source:
        return "unknown source"
    st = source.get("source_type", "unknown")
    if st == "file":
        name = source.get("file_name") or source.get("file_path", "unknown file")
        return f"file: {name}"
    if st == "conversation":
        sid = source.get("session_id", "")
        return f"conversation: {sid[:12]}" if sid else "conversation"
    return st


def create_memory_tools(
    file_manager=None,
    memory_dir: Optional[str] = None,
):
    """Create memory tool functions with shared backend instances.

    Backends are initialized lazily on first tool invocation to avoid
    startup cost for agents that never use memory tools.

    Source registry for citations is accessed dynamically via
    file_manager.source_registry (set per-turn by app.py).

    Args:
        file_manager: Optional FileManager instance for source provenance.
        memory_dir: Directory for notes/core files (default: MEMORY_DIR or ./memory).

    Returns:
        List of @tool-decorated functions.
    """
    # Lazy-initialized backends stored in a mutable container
    _backends = {}

    def _get_backends():
        """Initialize and cache all memory backends on first use."""
        if _backends:
            return _backends

        _memory_dir = memory_dir or os.getenv("MEMORY_DIR", "./memory")

        # Embedding client
        try:
            from qq.embeddings import EmbeddingClient
            _backends["embeddings"] = EmbeddingClient()
        except Exception as e:
            logger.warning(f"Embeddings unavailable: {e}")
            _backends["embeddings"] = None

        # MongoDB notes store
        try:
            from qq.memory.mongo_store import MongoNotesStore
            _backends["mongo"] = MongoNotesStore()
        except Exception as e:
            logger.warning(f"MongoDB unavailable: {e}")
            _backends["mongo"] = None

        # Notes file manager
        try:
            from qq.memory.notes import get_notes_manager
            _backends["notes"] = get_notes_manager(_memory_dir)
        except Exception as e:
            logger.warning(f"Notes manager unavailable: {e}")
            _backends["notes"] = None

        # Core notes
        try:
            from qq.memory.core_notes import CoreNotesManager
            _backends["core"] = CoreNotesManager(_memory_dir)
        except Exception as e:
            logger.warning(f"Core notes unavailable: {e}")
            _backends["core"] = None

        # Neo4j knowledge graph
        try:
            from qq.knowledge.neo4j_client import Neo4jClient
            _backends["neo4j"] = Neo4jClient()
        except Exception as e:
            logger.warning(f"Neo4j unavailable: {e}")
            _backends["neo4j"] = None

        # Archive manager
        try:
            from qq.memory.archive import ArchiveManager
            _backends["archive"] = ArchiveManager(
                memory_dir=_memory_dir,
                mongo_store=_backends.get("mongo"),
            )
        except Exception as e:
            logger.warning(f"Archive unavailable: {e}")
            _backends["archive"] = None

        return _backends

    def _get_embedding(text: str) -> Optional[List[float]]:
        """Get embedding for text, returning None if unavailable."""
        backends = _get_backends()
        client = backends.get("embeddings")
        if client and client.is_available:
            try:
                return client.get_embedding(text)
            except Exception as e:
                logger.warning(f"Embedding failed: {e}")
        return None

    def _collect_source() -> dict:
        """Collect source provenance from file_manager or session context."""
        try:
            from qq.memory.source import collect_file_source, collect_conversation_source

            # Check if there are pending file reads (file was the source)
            if file_manager:
                pending = getattr(file_manager, "pending_file_reads", [])
                if pending:
                    # Use the most recent file read as source
                    return collect_file_source(pending[-1]).to_dict()

            # Fall back to conversation source
            session_id = os.environ.get("QQ_SESSION_ID", "")
            agent_id = os.environ.get("QQ_AGENT_ID", "")
            return collect_conversation_source(session_id, agent_id).to_dict()
        except Exception as e:
            logger.debug(f"Source collection failed: {e}")
            return {"source_type": "unknown", "timestamp": datetime.utcnow().isoformat()}

    def _search_similar(embedding, limit=5, threshold=0.0):
        """Search MongoDB for similar notes, returning those above threshold."""
        backends = _get_backends()
        mongo = backends.get("mongo")
        if not mongo or not embedding:
            return []

        try:
            results = mongo.search_similar(embedding, limit=limit)
            return [r for r in results if r.get("score", 0) >= threshold]
        except Exception as e:
            logger.warning(f"Similarity search failed: {e}")
            return []

    def _search_entities(embedding, limit=5, threshold=0.0):
        """Search Neo4j for similar entities."""
        backends = _get_backends()
        neo4j = backends.get("neo4j")
        if not neo4j or not embedding:
            return []

        try:
            results = neo4j.search_entities_by_embedding(embedding, limit=limit)
            return [r for r in results if r.get("score", 0) >= threshold]
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Tool 1: memory_add
    # ------------------------------------------------------------------

    @tool
    def memory_add(
        content: str,
        section: str = "Important Facts",
        importance: str = "normal",
    ) -> str:
        """
        Store information in long-term memory.

        Use this when you learn something worth remembering across conversations:
        new facts, user preferences, project details, decisions made, or
        conclusions drawn from analysis.

        Args:
            content: The information to remember. Be specific and self-contained.
            section: Category - one of: Key Topics, Important Facts,
                     People & Entities, Ongoing Threads, File Knowledge.
            importance: Priority level - "low", "normal", "high", or "core".
                        Use "core" only for user identity, key relationships,
                        or critical project info that should never be forgotten.
        """
        backends = _get_backends()
        mongo = backends.get("mongo")
        notes = backends.get("notes")
        core = backends.get("core")

        if not mongo:
            return "Error: Memory storage (MongoDB) is not available."

        # Validate section
        if section not in VALID_SECTIONS:
            section = "Important Facts"

        # Map importance
        imp_float = IMPORTANCE_LEVELS.get(importance, 0.5)

        # Generate embedding
        embedding = _get_embedding(content)

        # Check for near-duplicates
        if embedding:
            duplicates = _search_similar(embedding, limit=1, threshold=DEDUP_THRESHOLD)
            if duplicates:
                match = duplicates[0]
                # Reinforce instead of duplicating
                source = _collect_source()
                mongo.append_source_history(
                    match["note_id"], source, boost_importance=0.1
                )
                if notes:
                    try:
                        notes.load_notes()
                    except Exception:
                        pass
                return (
                    f"Reinforced existing memory (similarity {match['score']:.2f}): "
                    f"{match['content'][:100]}..."
                    if len(match["content"]) > 100
                    else f"Reinforced existing memory (similarity {match['score']:.2f}): "
                    f"{match['content']}"
                )

        # Store new note
        note_id = _generate_note_id()
        source = _collect_source()

        try:
            mongo.upsert_note(
                note_id=note_id,
                content=content,
                embedding=embedding or [],
                section=section,
                importance=imp_float,
                source=source,
            )
        except Exception as e:
            return f"Error storing to MongoDB: {e}"

        # Also add to notes.md
        if notes:
            try:
                notes.add_item(section, content)
            except Exception as e:
                logger.warning(f"Failed to add to notes.md: {e}")

        # Handle core notes
        if importance == "core" and core:
            # Try to determine best core category
            is_candidate, category = core.is_core_candidate(content)
            if not is_candidate:
                category = "Projects"  # default core category
            try:
                core.add_core(content, category, source="memory_add")
            except Exception as e:
                logger.warning(f"Failed to add to core notes: {e}")

        return f"Stored in memory [{section}] (importance: {importance}, id: {note_id})"

    # ------------------------------------------------------------------
    # Tool 2: memory_query
    # ------------------------------------------------------------------

    @tool
    def memory_query(
        query: str,
        scope: str = "all",
        limit: int = 5,
    ) -> str:
        """
        Search your memory for specific information.

        Use this when you need to recall something specific that may not have
        been included in your automatic context, or to check what you know
        about a topic before responding.

        Args:
            query: What to search for. Can be a topic, question, or keywords.
            scope: Where to search - "notes" (working memory), "knowledge"
                   (entity graph), "archive" (forgotten notes), or "all".
            limit: Maximum results to return (default 5).
        """
        backends = _get_backends()
        embedding = _get_embedding(query)
        results_parts = []

        # Search notes (MongoDB)
        if scope in ("notes", "all"):
            mongo = backends.get("mongo")
            if mongo and embedding:
                try:
                    notes_results = mongo.search_similar(embedding, limit=limit)
                    # Enrich with full note data
                    enriched = []
                    for r in notes_results:
                        if r.get("score", 0) < 0.3:
                            continue
                        full = mongo.get_full_note(r["note_id"])
                        imp = full.get("importance", 0.5) if full else 0.5
                        src = _format_source_summary(full.get("source", {})) if full else ""
                        # Register in source registry for citations
                        ref_tag = ""
                        if file_manager and getattr(file_manager, "source_registry", None):
                            idx = file_manager.source_registry.add(
                                "note",
                                r["content"][:60],
                                f"note:{r['note_id']} [{r.get('section', '?')}] "
                                f"score={r['score']:.2f}",
                            )
                            ref_tag = f"[{idx}] "
                        enriched.append(
                            f"  - {ref_tag}[{r.get('section', '?')}] (relevance: {r['score']:.2f}, "
                            f"importance: {imp:.2f}) {r['content']}"
                            + (f" [from {src}]" if src else "")
                        )
                        # Track access
                        try:
                            mongo.increment_access(r["note_id"])
                        except Exception:
                            pass
                    if enriched:
                        results_parts.append("**Notes:**\n" + "\n".join(enriched))
                except Exception as e:
                    results_parts.append(f"**Notes:** Error searching: {e}")
            elif not embedding:
                results_parts.append("**Notes:** Embeddings unavailable, cannot search.")

        # Search knowledge graph (Neo4j)
        if scope in ("knowledge", "all"):
            neo4j = backends.get("neo4j")
            if neo4j and embedding:
                try:
                    entities = neo4j.search_entities_by_embedding(
                        embedding, limit=limit
                    )
                    entity_lines = []
                    for e in entities:
                        if e.get("score", 0) < 0.3:
                            continue
                        desc = e.get("description", "")
                        # Register in source registry for citations
                        ref_tag = ""
                        if file_manager and getattr(file_manager, "source_registry", None):
                            idx = file_manager.source_registry.add(
                                "entity",
                                f"{e['name']} ({e.get('type', '?')})",
                                f"score={e['score']:.2f}",
                            )
                            ref_tag = f"[{idx}] "
                        entity_lines.append(
                            f"  - {ref_tag}[{e.get('type', '?')}] {e['name']} "
                            f"(relevance: {e['score']:.2f})"
                            + (f": {desc}" if desc else "")
                        )
                        # Get relationships for top entity
                        if len(entity_lines) == 1:
                            try:
                                related = neo4j.get_related_entities(
                                    e["name"], depth=1, limit=3
                                )
                                for rel in related:
                                    entity_lines.append(
                                        f"    -> {rel['name']} ({rel.get('type', '?')}, "
                                        f"distance: {rel.get('distance', '?')})"
                                    )
                            except Exception:
                                pass
                    if entity_lines:
                        results_parts.append(
                            "**Knowledge Graph:**\n" + "\n".join(entity_lines)
                        )
                except Exception as e:
                    results_parts.append(f"**Knowledge Graph:** Error searching: {e}")

        # Search archive
        if scope in ("archive", "all"):
            archive = backends.get("archive")
            if archive:
                try:
                    archived = archive.search_archive(query, limit=limit)
                    if archived:
                        archive_lines = []
                        for a in archived:
                            ref_tag = ""
                            if file_manager and getattr(file_manager, "source_registry", None):
                                idx = file_manager.source_registry.add(
                                    "archive",
                                    a.content[:60],
                                    f"archived:{a.archived_at.strftime('%Y-%m-%d')}",
                                )
                                ref_tag = f"[{idx}] "
                            archive_lines.append(
                                f"  - {ref_tag}[{a.section}] (was importance: {a.importance:.2f}, "
                                f"archived: {a.archived_at.strftime('%Y-%m-%d')}, "
                                f"reason: {a.reason}) {a.content}"
                            )
                        results_parts.append(
                            "**Archive (forgotten):**\n" + "\n".join(archive_lines)
                        )
                except Exception as e:
                    results_parts.append(f"**Archive:** Error searching: {e}")

        if not results_parts:
            return "No matching memories found."

        return "\n\n".join(results_parts)

    # ------------------------------------------------------------------
    # Tool 3: memory_verify
    # ------------------------------------------------------------------

    @tool
    def memory_verify(claim: str) -> str:
        """
        Verify a claim against existing memory.

        Use this before storing new information to check for conflicts,
        or when you want to validate something you've been told against
        what you already know.

        Args:
            claim: A statement to verify against existing memory.
                   Be specific - e.g., "The database runs on port 5432"
                   rather than "database port".
        """
        backends = _get_backends()
        embedding = _get_embedding(claim)

        if not embedding:
            return "Verification unavailable: embeddings service is not running."

        findings = []

        # Search notes
        mongo = backends.get("mongo")
        if mongo:
            try:
                results = mongo.search_similar(embedding, limit=3)
                for r in results:
                    score = r.get("score", 0)
                    if score < RELATED_THRESHOLD:
                        continue
                    full = mongo.get_full_note(r["note_id"])
                    src = _format_source_summary(full.get("source", {})) if full else ""
                    imp = full.get("importance", 0.5) if full else 0.5

                    if score >= DEDUP_THRESHOLD:
                        status = "CONFIRMED"
                    else:
                        status = "RELATED"

                    findings.append({
                        "status": status,
                        "score": score,
                        "content": r["content"],
                        "source": src,
                        "importance": imp,
                        "store": "notes",
                    })
            except Exception as e:
                logger.warning(f"Note search failed during verify: {e}")

        # Search knowledge graph
        neo4j = backends.get("neo4j")
        if neo4j:
            try:
                entities = neo4j.search_entities_by_embedding(embedding, limit=3)
                for e in entities:
                    score = e.get("score", 0)
                    if score < RELATED_THRESHOLD:
                        continue
                    desc = e.get("description", "")
                    if score >= DEDUP_THRESHOLD:
                        status = "CONFIRMED"
                    else:
                        status = "RELATED"

                    findings.append({
                        "status": status,
                        "score": score,
                        "content": f"{e['name']}: {desc}" if desc else e["name"],
                        "source": "knowledge graph",
                        "importance": None,
                        "store": "knowledge",
                    })
            except Exception as e:
                logger.warning(f"Entity search failed during verify: {e}")

        # Format report
        if not findings:
            return (
                "**Status: NEW** - No existing knowledge matches this claim. "
                "This appears to be new information."
            )

        # Sort by score descending
        findings.sort(key=lambda f: f["score"], reverse=True)
        top = findings[0]

        lines = [f"**Status: {top['status']}** (best match: {top['score']:.2f})"]
        lines.append("")

        for f in findings:
            imp_str = f" | importance: {f['importance']:.2f}" if f["importance"] is not None else ""
            lines.append(
                f"- [{f['status']}] (similarity: {f['score']:.2f}{imp_str}) "
                f"{f['content']}"
            )
            if f["source"]:
                lines.append(f"  Source: {f['source']}")

        # Check for potential conflicts
        confirmed = [f for f in findings if f["status"] == "CONFIRMED"]
        related = [f for f in findings if f["status"] == "RELATED"]

        if confirmed:
            lines.append("")
            lines.append("This claim is already recorded in memory.")
        elif related:
            lines.append("")
            lines.append(
                "Related information exists but is not an exact match. "
                "Review the matches above for potential conflicts."
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool 4: memory_reinforce
    # ------------------------------------------------------------------

    @tool
    def memory_reinforce(content: str, new_evidence: str = "") -> str:
        """
        Reinforce existing memory with additional evidence or a new source.

        Use this when you encounter information that confirms something
        already in memory, especially from a different source. This increases
        the information's importance and records the additional provenance.

        Args:
            content: The information to reinforce (will be matched against
                     existing memory by similarity).
            new_evidence: Optional additional context, quote, or source
                          description that supports the existing memory.
        """
        backends = _get_backends()
        mongo = backends.get("mongo")

        if not mongo:
            return "Error: Memory storage (MongoDB) is not available."

        embedding = _get_embedding(content)
        if not embedding:
            return "Error: Embeddings unavailable, cannot match against memory."

        # Find best match
        matches = _search_similar(embedding, limit=1, threshold=REINFORCE_THRESHOLD)

        if not matches:
            return (
                "No matching memory found to reinforce (threshold: "
                f"{REINFORCE_THRESHOLD}). Use memory_add to store new information."
            )

        match = matches[0]
        note_id = match["note_id"]
        full = mongo.get_full_note(note_id)
        old_importance = full.get("importance", 0.5) if full else 0.5

        # Collect new source
        source = _collect_source()
        if new_evidence:
            source["evidence"] = new_evidence

        # Boost importance and append source
        try:
            mongo.append_source_history(
                note_id, source, boost_importance=0.1
            )
        except Exception as e:
            return f"Error reinforcing memory: {e}"

        new_importance = min(old_importance + 0.1, 1.0)

        # Count total sources
        source_count = 1  # original
        if full:
            source_count += len(full.get("source_history", []))
        source_count += 1  # this reinforcement

        # Try to reinforce in knowledge graph too
        neo4j = backends.get("neo4j")
        if neo4j and embedding:
            try:
                entities = neo4j.search_entities_by_embedding(
                    embedding, limit=1
                )
                if entities and entities[0].get("score", 0) >= REINFORCE_THRESHOLD:
                    neo4j.increment_mention_count(entities[0]["name"])
            except Exception:
                pass

        # Check for core promotion
        core = backends.get("core")
        promotion_msg = ""
        if core and new_importance >= CORE_THRESHOLD:
            suggested = core.suggest_promotion(match["content"], new_importance)
            if suggested and not core.is_protected(match["content"]):
                try:
                    core.add_core(match["content"], suggested, source="memory_reinforce")
                    promotion_msg = f" Promoted to core memory [{suggested}]."
                except Exception:
                    pass

        return (
            f"Reinforced: {match['content'][:120]}\n"
            f"Importance: {old_importance:.2f} -> {new_importance:.2f} "
            f"(from {source_count} sources).{promotion_msg}"
        )

    return [memory_add, memory_query, memory_verify, memory_reinforce]
