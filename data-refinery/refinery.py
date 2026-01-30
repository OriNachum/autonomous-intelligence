#!/usr/bin/env python3
"""
Data Refinery - Extract entities and relationships from documents.

This script processes documents using a 3-page sliding window,
extracts entities and relationships using vLLM with Nemotron model,
and generates Cypher instructions for Neo4j import.
"""
import argparse
import sys
from pathlib import Path
import os

from tqdm import tqdm

from src.document_processor import DocumentProcessor
from src.extractor import Extractor
from src.json_writer import JsonWriter
from src.cypher_generator import CypherGenerator
from src.state import ProcessingState
from src.embeddings import EmbeddingClient

STATE_FILE = ".refinery_state.json"


def main():
    parser = argparse.ArgumentParser(
        description="Extract entities and relationships from documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single PDF
  python refinery.py --input document.pdf --output output/

  # Process all PDFs in a directory
  python refinery.py --input docs/ --output output/

  # Use custom vLLM endpoint
  python refinery.py --input doc.pdf --output output/ --vllm-url http://gpu-server:8000/v1

  # Generate Cypher only (from existing JSON)
  python refinery.py --output output/ --cypher-only
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="Input document (PDF) or directory of PDFs"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Output directory for JSON and Cypher files"
    )
    parser.add_argument(
        "--vllm-url",
        type=str,
        default="http://localhost:8000/v1",
        help="vLLM OpenAI-compatible API URL (default: http://localhost:8000/v1)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MODEL_ID", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"),
        help="Model to use for extraction"
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=3,
        help="Sliding window size in pages (default: 3)"
    )
    parser.add_argument(
        "--max-relationship-iterations",
        type=int,
        default=5,
        help="Max iterations for relationship extraction (default: 5)"
    )
    parser.add_argument(
        "--cypher-only",
        action="store_true",
        help="Only generate Cypher from existing JSON files"
    )
    parser.add_argument(
        "--skip-cypher",
        action="store_true",
        help="Skip Cypher generation"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous run, skipping already processed windows"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean previous state and start fresh"
    )
    parser.add_argument(
        "--generate-embeddings",
        action="store_true",
        help="Generate embeddings for entities using TEI service"
    )
    parser.add_argument(
        "--embeddings-url",
        type=str,
        default="http://localhost:8101/v1",
        help="TEI embeddings service URL (default: http://localhost:8101/v1)"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Cypher-only mode
    if args.cypher_only:
        print("=== Generating Cypher from existing JSON files ===")
        generator = CypherGenerator()
        cypher_path = output_dir / "import.cypher"
        generator.generate_from_directory(str(output_dir), str(cypher_path))
        print(f"✓ Cypher written to: {cypher_path}")
        return 0
    
    # Validate input
    if not args.input:
        parser.error("--input is required unless using --cypher-only")
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}", file=sys.stderr)
        return 1
    
    # Initialize components
    print("=== Data Refinery ===")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    print(f"Model: {args.model}")
    print(f"Window size: {args.window_size} pages")
    print()
    
    processor = DocumentProcessor(window_size=args.window_size)
    
    # Initialize embedding client if requested
    embedding_client = None
    if args.generate_embeddings:
        print(f"Embeddings: enabled (TEI at {args.embeddings_url})")
        embedding_client = EmbeddingClient(tei_url=args.embeddings_url)
    
    extractor = Extractor(
        vllm_url=args.vllm_url,
        model=args.model,
        max_relationship_iterations=args.max_relationship_iterations,
        embedding_client=embedding_client,
    )
    writer = JsonWriter(str(output_dir))
    
    # Handle state for resume support
    state_file = output_dir / STATE_FILE
    state = ProcessingState()
    
    if args.clean and state_file.exists():
        state_file.unlink()
        print("Cleaned previous state.")
    elif args.resume:
        state = ProcessingState.load(state_file)
        if state.processed_windows:
            print(f"Resuming: {len(state.processed_windows)} windows already processed")
    
    # Process documents
    print("=== Processing Documents ===")
    
    if input_path.is_file():
        windows = list(processor.process_document(str(input_path)))
    else:
        windows = list(processor.process_directory(str(input_path)))
    
    # Filter out already processed windows
    if args.resume:
        original_count = len(windows)
        windows = [
            w for w in windows
            if not state.is_processed(w.document_name, w.start_page)
        ]
        skipped = original_count - len(windows)
        if skipped > 0:
            print(f"Skipping {skipped} already processed windows")
    
    print(f"Found {len(windows)} windows to process")
    
    results = []
    for window in tqdm(windows, desc="Extracting"):
        try:
            result = extractor.extract_all(window)
            filepath = writer.write(result)
            results.append(result)
            
            # Update state and save
            state.mark_processed(
                window.document_name,
                window.start_page,
                len(result.entities),
                len(result.relationships)
            )
            state.save(state_file)
            
            tqdm.write(f"  ✓ {window.document_name} pages {window.start_page}-{window.end_page}: "
                      f"{len(result.entities)} entities, {len(result.relationships)} relationships")
        except Exception as e:
            tqdm.write(f"  ✗ {window.document_name} pages {window.start_page}-{window.end_page}: {e}")
    
    print()
    print(f"=== Extraction Complete ===")
    print(f"Processed {len(results)} windows")
    
    # Use state totals if resuming, otherwise compute from results
    if args.resume:
        total_entities = state.total_entities
        total_relationships = state.total_relationships
    else:
        total_entities = sum(len(r.entities) for r in results)
        total_relationships = sum(len(r.relationships) for r in results)
    print(f"Total entities: {total_entities}")
    print(f"Total relationships: {total_relationships}")
    
    # Generate Cypher
    if not args.skip_cypher:
        print()
        print("=== Generating Cypher ===")
        generator = CypherGenerator()
        cypher_path = output_dir / "import.cypher"
        generator.generate_from_directory(str(output_dir), str(cypher_path))
        print(f"✓ Cypher written to: {cypher_path}")
        print()
        print("To import into Neo4j:")
        print(f"  cat {cypher_path} | docker exec -i data-refinery-neo4j cypher-shell -u neo4j -p refinerypass")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
