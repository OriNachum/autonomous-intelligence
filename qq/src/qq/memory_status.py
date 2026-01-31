"""qq-memory - CLI tool to peek into memory status."""

import os
import sys


def get_notes_snapshot():
    """Get the notes.md content."""
    from qq.memory.notes import NotesManager
    
    try:
        manager = NotesManager()
        return manager.get_notes()
    except Exception as e:
        return f"Error loading notes: {e}"


def get_mongo_stats():
    """Get MongoDB record count and status."""
    try:
        from pymongo import MongoClient
        
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        
        # Force connection check
        client.admin.command('ping')
        
        db = client["qq_memory"]
        notes_count = db["notes"].count_documents({})
        
        # Get sample notes
        sample_notes = list(db["notes"].find({}, {"content": 1, "section": 1}).limit(5))
        
        return {
            "status": "connected",
            "count": notes_count,
            "samples": [
                {"section": n.get("section", ""), "content": n.get("content", "")[:100]}
                for n in sample_notes
            ]
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "count": 0}


def get_neo4j_stats():
    """Get Neo4j record count and status."""
    try:
        from neo4j import GraphDatabase
        
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "refinerypass")
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            # Count all nodes
            result = session.run("MATCH (n) RETURN count(n) as count")
            node_count = result.single()["count"]
            
            # Count relationships
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            rel_count = result.single()["count"]
            
            # Get entity type breakdown
            result = session.run(
                "MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC LIMIT 5"
            )
            types = [(r["type"], r["count"]) for r in result]
        
        driver.close()
        
        return {
            "status": "connected",
            "node_count": node_count,
            "relationship_count": rel_count,
            "entity_types": types,
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e), "node_count": 0, "relationship_count": 0}


def main():
    """Main entry point for qq-memory CLI."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.markdown import Markdown
        console = Console()
        use_rich = True
    except ImportError:
        use_rich = False
    
    # Parse arguments
    show_notes = "--notes" in sys.argv or len(sys.argv) == 1
    show_mongo = "--mongo" in sys.argv or len(sys.argv) == 1
    show_neo4j = "--neo4j" in sys.argv or len(sys.argv) == 1
    show_help = "--help" in sys.argv or "-h" in sys.argv
    
    if show_help:
        print("""qq-memory - Peek into QQ's memory stores

Usage:
  qq-memory           Show all memory stores
  qq-memory --notes   Show notes.md snapshot only
  qq-memory --mongo   Show MongoDB stats only
  qq-memory --neo4j   Show Neo4j stats only

Environment variables:
  MEMORY_DIR       Directory for notes.md (default: ./memory)
  MONGODB_URI      MongoDB connection URI (default: mongodb://localhost:27017)
  NEO4J_URI        Neo4j Bolt URI (default: bolt://localhost:7687)
  NEO4J_USER       Neo4j username (default: neo4j)
  NEO4J_PASSWORD   Neo4j password (default: refinerypass)
""")
        return
    
    if use_rich:
        console.print("[bold cyan]QQ Memory Snapshot[/bold cyan]\n")
    else:
        print("=== QQ Memory Snapshot ===\n")
    
    # Notes
    if show_notes:
        if use_rich:
            notes = get_notes_snapshot()
            console.print(Panel(Markdown(notes), title="📝 Notes (notes.md)", expand=False))
            console.print()
        else:
            print("--- Notes (notes.md) ---")
            print(get_notes_snapshot())
            print()
    
    # MongoDB
    if show_mongo:
        mongo_stats = get_mongo_stats()
        if use_rich:
            if mongo_stats["status"] == "connected":
                table = Table(title="🍃 MongoDB (qq_memory.notes)")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Status", "✅ Connected")
                table.add_row("Record Count", str(mongo_stats["count"]))
                console.print(table)
                
                if mongo_stats.get("samples"):
                    sample_table = Table(title="Sample Notes")
                    sample_table.add_column("Section", style="dim")
                    sample_table.add_column("Content Preview")
                    for s in mongo_stats["samples"]:
                        sample_table.add_row(s["section"], s["content"][:60] + "..." if len(s["content"]) > 60 else s["content"])
                    console.print(sample_table)
            else:
                console.print(Panel(
                    f"[red]❌ Disconnected[/red]\n{mongo_stats.get('error', '')}",
                    title="🍃 MongoDB",
                ))
            console.print()
        else:
            print("--- MongoDB ---")
            print(f"Status: {mongo_stats['status']}")
            if mongo_stats["status"] == "connected":
                print(f"Record Count: {mongo_stats['count']}")
            else:
                print(f"Error: {mongo_stats.get('error', '')}")
            print()
    
    # Neo4j
    if show_neo4j:
        neo4j_stats = get_neo4j_stats()
        if use_rich:
            if neo4j_stats["status"] == "connected":
                table = Table(title="🔗 Neo4j Knowledge Graph")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Status", "✅ Connected")
                table.add_row("Nodes", str(neo4j_stats["node_count"]))
                table.add_row("Relationships", str(neo4j_stats["relationship_count"]))
                console.print(table)
                
                if neo4j_stats.get("entity_types"):
                    type_table = Table(title="Entity Types")
                    type_table.add_column("Type", style="blue")
                    type_table.add_column("Count", style="green")
                    for t, c in neo4j_stats["entity_types"]:
                        type_table.add_row(str(t), str(c))
                    console.print(type_table)
            else:
                console.print(Panel(
                    f"[red]❌ Disconnected[/red]\n{neo4j_stats.get('error', '')}",
                    title="🔗 Neo4j",
                ))
        else:
            print("--- Neo4j ---")
            print(f"Status: {neo4j_stats['status']}")
            if neo4j_stats["status"] == "connected":
                print(f"Nodes: {neo4j_stats['node_count']}")
                print(f"Relationships: {neo4j_stats['relationship_count']}")
            else:
                print(f"Error: {neo4j_stats.get('error', '')}")


if __name__ == "__main__":
    main()

