"""Cypher generator for Neo4j import."""
import json
from pathlib import Path
from typing import List, Set

from .models import Entity, Relationship, WindowExtractionResult


class CypherGenerator:
    """Generate Cypher statements from extraction results."""
    
    def __init__(self):
        """Initialize the Cypher generator."""
        self._seen_entities: Set[str] = set()
        self._seen_relationships: Set[tuple] = set()
    
    def _escape_string(self, s: str) -> str:
        """Escape a string for Cypher."""
        return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    
    def _entity_to_cypher(self, entity: Entity) -> str:
        """
        Generate MERGE statement for an entity.
        
        Uses MERGE to avoid duplicates across windows.
        """
        entity_id = self._escape_string(entity.id)
        name = self._escape_string(entity.name)
        description = self._escape_string(entity.description)
        entity_type = entity.type.capitalize()
        
        return f"""MERGE (n:{entity_type} {{id: '{entity_id}'}})
ON CREATE SET n.name = '{name}', n.description = '{description}', n.source_page = {entity.source_page}
ON MATCH SET n.name = '{name}', n.description = '{description}';"""
    
    def _relationship_to_cypher(self, rel: Relationship) -> str:
        """
        Generate MERGE statement for a relationship.
        
        Uses MERGE to avoid duplicate relationships.
        """
        source_id = self._escape_string(rel.source_entity_id)
        target_id = self._escape_string(rel.target_entity_id)
        rel_type = rel.type.upper().replace(" ", "_").replace("-", "_")
        description = self._escape_string(rel.description)
        
        return f"""MATCH (a {{id: '{source_id}'}}), (b {{id: '{target_id}'}})
MERGE (a)-[r:{rel_type}]->(b)
ON CREATE SET r.description = '{description}', r.source_page = {rel.source_page};"""
    
    def generate_from_json(self, json_path: str) -> str:
        """
        Generate Cypher from a single JSON file.
        
        Args:
            json_path: Path to the JSON extraction file
            
        Returns:
            Cypher statements as a string
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        cypher_statements = []
        cypher_statements.append(f"// Source: {Path(json_path).name}")
        cypher_statements.append(f"// Document: {data.get('document_name', 'unknown')}")
        cypher_statements.append(f"// Pages: {data.get('start_page', '?')}-{data.get('end_page', '?')}")
        cypher_statements.append("")
        
        # Generate entity statements
        cypher_statements.append("// === ENTITIES ===")
        for entity_data in data.get("entities", []):
            entity = Entity(**entity_data)
            if entity.id not in self._seen_entities:
                cypher_statements.append(self._entity_to_cypher(entity))
                self._seen_entities.add(entity.id)
        
        cypher_statements.append("")
        
        # Generate relationship statements
        cypher_statements.append("// === RELATIONSHIPS ===")
        for rel_data in data.get("relationships", []):
            rel = Relationship(**rel_data)
            rel_key = (rel.source_entity_id, rel.target_entity_id, rel.type)
            if rel_key not in self._seen_relationships:
                cypher_statements.append(self._relationship_to_cypher(rel))
                self._seen_relationships.add(rel_key)
        
        return "\n".join(cypher_statements)
    
    def generate_from_directory(self, json_dir: str, output_path: str = None) -> str:
        """
        Generate Cypher from all JSON files in a directory.
        
        Args:
            json_dir: Directory containing JSON extraction files
            output_path: Optional path to write consolidated Cypher file
            
        Returns:
            Combined Cypher statements
        """
        json_dir = Path(json_dir)
        json_files = sorted(json_dir.glob("*.json"))
        
        all_cypher = []
        all_cypher.append("// ==========================================")
        all_cypher.append("// Data Refinery - Neo4j Import Script")
        all_cypher.append("// ==========================================")
        all_cypher.append("")
        all_cypher.append("// Create indexes for better performance")
        all_cypher.append("CREATE INDEX entity_id IF NOT EXISTS FOR (n:Name) ON (n.id);")
        all_cypher.append("CREATE INDEX concept_id IF NOT EXISTS FOR (n:Concept) ON (n.id);")
        all_cypher.append("CREATE INDEX feature_id IF NOT EXISTS FOR (n:Feature) ON (n.id);")
        all_cypher.append("CREATE INDEX location_id IF NOT EXISTS FOR (n:Location) ON (n.id);")
        all_cypher.append("")
        
        for json_file in json_files:
            all_cypher.append(self.generate_from_json(str(json_file)))
            all_cypher.append("")
        
        combined = "\n".join(all_cypher)
        
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(combined)
        
        return combined
    
    def reset(self):
        """Reset seen entities and relationships for fresh generation."""
        self._seen_entities.clear()
        self._seen_relationships.clear()
