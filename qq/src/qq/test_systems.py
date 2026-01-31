"""qq-test - Test all QQ system components."""

import sys
import time


def test_mongodb():
    """Test MongoDB connection."""
    print("🍃 Testing MongoDB...")
    try:
        import os
        from pymongo import MongoClient
        
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        start = time.time()
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command('ping')
        elapsed = time.time() - start
        
        db = client["qq_memory"]
        count = db["notes"].count_documents({})
        
        print(f"   ✅ Connected ({elapsed*1000:.0f}ms)")
        print(f"   📊 Notes collection: {count} documents")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_neo4j():
    """Test Neo4j connection."""
    print("🔗 Testing Neo4j...")
    try:
        import os
        from neo4j import GraphDatabase
        
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "refinerypass")
        
        start = time.time()
        driver = GraphDatabase.driver(uri, auth=(user, password))
        
        with driver.session() as session:
            result = session.run("RETURN 1 as n")
            result.single()
        elapsed = time.time() - start
        
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            node_count = result.single()["count"]
        
        driver.close()
        
        print(f"   ✅ Connected ({elapsed*1000:.0f}ms)")
        print(f"   📊 Nodes: {node_count}")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_vllm():
    """Test vLLM/Nemotron connection."""
    print("🤖 Testing vLLM (Nemotron)...")
    try:
        import os
        from openai import OpenAI
        import httpx
        
        base_url = os.getenv("VLLM_URL", "http://localhost:8100/v1")
        
        start = time.time()
        client = OpenAI(
            base_url=base_url,
            api_key="not-needed",
            timeout=httpx.Timeout(10.0, connect=3.0),
            max_retries=0,
        )
        
        # Get model info
        models = client.models.list()
        model_id = models.data[0].id if models.data else "unknown"
        elapsed = time.time() - start
        
        print(f"   ✅ Connected ({elapsed*1000:.0f}ms)")
        print(f"   🧠 Model: {model_id}")
        
        # Quick inference test
        print("   ⏳ Testing inference...")
        start = time.time()
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Say 'ok' and nothing else."}],
            max_tokens=10,
        )
        elapsed = time.time() - start
        reply = response.choices[0].message.content.strip()
        print(f"   ✅ Inference OK ({elapsed*1000:.0f}ms): '{reply[:30]}'")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_embeddings():
    """Test embeddings (TEI or local)."""
    print("🧠 Testing Embeddings...")
    try:
        import os
        prefer_local = os.getenv("EMBEDDINGS_LOCAL", "").lower() in ("1", "true", "yes")
        
        from qq.embeddings import EmbeddingClient
        
        start = time.time()
        client = EmbeddingClient()
        
        if not client.is_available:
            print("   ❌ No embedding backend available")
            return False
        
        elapsed_init = time.time() - start
        
        start = time.time()
        embedding = client.get_embedding("test embedding for qq")
        elapsed_embed = time.time() - start
        
        print(f"   ✅ Backend: {client.backend_name} (init: {elapsed_init*1000:.0f}ms)")
        print(f"   📊 Embedding dim: {len(embedding)} (embed: {elapsed_embed*1000:.0f}ms)")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def main():
    """Run all system tests."""
    print("=" * 50)
    print("QQ System Tests")
    print("=" * 50)
    print()
    
    # Parse args
    tests_to_run = sys.argv[1:] if len(sys.argv) > 1 else ["mongo", "neo4j", "vllm", "embeddings"]
    
    if "--help" in tests_to_run or "-h" in tests_to_run:
        print("""qq-test - Test QQ system components

Usage:
  qq-test                    Run all tests
  qq-test mongo              Test MongoDB only
  qq-test neo4j              Test Neo4j only
  qq-test vllm               Test vLLM/Nemotron only
  qq-test embeddings         Test embeddings only
  qq-test mongo neo4j        Test multiple components

Environment variables:
  MONGODB_URI        MongoDB connection (default: mongodb://localhost:27017)
  NEO4J_URI          Neo4j Bolt URI (default: bolt://localhost:7687)
  NEO4J_USER         Neo4j user (default: neo4j)
  NEO4J_PASSWORD     Neo4j password (default: refinerypass)
  VLLM_URL           vLLM API URL (default: http://localhost:8100/v1)
  EMBEDDINGS_LOCAL   Use local embeddings (default: false)
  TEI_URL            TEI API URL (default: http://localhost:8101/v1)
""")
        return
    
    results = {}
    
    if "mongo" in tests_to_run:
        results["MongoDB"] = test_mongodb()
        print()
    
    if "neo4j" in tests_to_run:
        results["Neo4j"] = test_neo4j()
        print()
    
    if "vllm" in tests_to_run:
        results["vLLM"] = test_vllm()
        print()
    
    if "embeddings" in tests_to_run:
        results["Embeddings"] = test_embeddings()
        print()
    
    # Summary
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, ok in results.items():
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {name}: {status}")
    
    print()
    print(f"Result: {passed}/{total} tests passed")
    
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
