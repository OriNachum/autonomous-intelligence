
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, "/home/spark/git/autonomous-intelligence/qq/src")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_neo4j")

try:
    from qq.knowledge.neo4j_client import Neo4jClient
    print("Successfully imported Neo4jClient")
except ImportError as e:
    print(f"Failed to import Neo4jClient: {e}")
    sys.exit(1)

def check_graph():
    client = Neo4jClient()
    
    print("\n--- Current Nodes ---")
    try:
        # Verify connectivity and count
        summary = client.get_graph_summary()
        print(f"Summary: {summary}")
        
        # List actual nodes
        with client.driver.session() as session:
            result = session.run("MATCH (n) RETURN n.name, labels(n) LIMIT 20")
            nodes = [record for record in result]
            if nodes:
                for record in nodes:
                    print(f"Node: {record['n.name']} {record['labels(n)']}")
            else:
                print("No nodes found.")
                
        print("\n--- Current Relationships ---")
        with client.driver.session() as session:
            result = session.run("MATCH (a)-[r]->(b) RETURN a.name, type(r), b.name LIMIT 20")
            rels = [record for record in result]
            if rels:
                for record in rels:
                    print(f"Rel: ({record['a.name']}) -[{record['type(r)']}]-> ({record['b.name']})")
            else:
                print("No relationships found.")

    except Exception as e:
        print(f"Error checking graph: {e}")
        return

    # Try manual insertion
    print("\n--- Attempting Manual Test ---")
    try:
        # Create Ori if not exists
        client.create_entity("Person", "Ori_Test", {"desc": "Test user"})
        client.create_entity("Project", "QQ_Test", {"desc": "Test project"})
        
        # Create relation
        client.create_relationship("Ori_Test", "QQ_Test", "TESTS")
        print("Manual insertion successful.")
        
        # Verify
        with client.driver.session() as session:
            result = session.run("MATCH (a {name: 'Ori_Test'})-[r:TESTS]->(b {name: 'QQ_Test'}) RETURN r")
            if result.single():
                print("Verified: Relationship exists.")
            else:
                print("Verification FAILED: Relationship not found.")
                
        # Cleanup
        # with client.driver.session() as session:
        #    session.run("MATCH (n {name: 'Ori_Test'}) DETACH DELETE n")
        #    session.run("MATCH (n {name: 'QQ_Test'}) DETACH DELETE n")
        # print("Cleanup successful.")

    except Exception as e:
        print(f"Manual test failed: {e}")

if __name__ == "__main__":
    check_graph()
