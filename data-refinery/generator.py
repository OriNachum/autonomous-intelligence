#!/usr/bin/env python3
"""
Generator CLI - Generate documents and Q&A pairs from Neo4j graph knowledge.

Examples:
  # Generate 5 documents
  python generator.py documents --count 5

  # Generate Q&A pairs with guidance
  python generator.py qa --count 10 --guidance "Focus on beginner-level questions"

  # Use custom vLLM endpoint
  python generator.py documents --count 3 --vllm-url http://gpu-server:8100/v1
"""
import argparse
import sys
from pathlib import Path

from src.generator_app import (
    GeneratorConfig,
    DocumentGenerator,
    QAGenerator,
    save_documents,
    save_qa_pairs,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate documents or Q&A pairs from Neo4j graph knowledge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Generation mode")
    
    # Common arguments for both commands
    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument(
        "--count", "-n",
        type=int,
        required=True,
        help="Number of items to generate"
    )
    common_args.add_argument(
        "--guidance", "-g",
        type=str,
        default=None,
        help="Optional guidance to steer generation"
    )
    common_args.add_argument(
        "--output", "-o",
        type=str,
        default="output/generated",
        help="Output directory (default: output/generated)"
    )
    common_args.add_argument(
        "--vllm-url",
        type=str,
        default="http://localhost:8100/v1",
        help="vLLM API URL (default: http://localhost:8100/v1)"
    )
    
    # Documents subcommand
    doc_parser = subparsers.add_parser(
        "documents", 
        parents=[common_args],
        help="Generate synthetic documents"
    )
    
    # Q&A subcommand
    qa_parser = subparsers.add_parser(
        "qa",
        parents=[common_args],
        help="Generate question-answer pairs"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Create config
    config = GeneratorConfig(
        vllm_url=args.vllm_url,
        output_dir=args.output,
    )
    
    output_dir = Path(args.output)
    
    print(f"=== Generator ===")
    print(f"Mode: {args.command}")
    print(f"Count: {args.count}")
    print(f"Output: {output_dir}")
    if args.guidance:
        print(f"Guidance: {args.guidance}")
    print()
    
    if args.command == "documents":
        print("Generating documents...")
        generator = DocumentGenerator(config)
        try:
            documents = generator.generate_documents(args.count, args.guidance)
            print(f"\nGenerated {len(documents)} documents")
            save_documents(documents, output_dir)
        finally:
            generator.close()
    
    elif args.command == "qa":
        print("Generating Q&A pairs...")
        generator = QAGenerator(config)
        try:
            pairs = generator.generate_qa_pairs(args.count, args.guidance)
            print(f"\nGenerated {len(pairs)} Q&A pairs")
            save_qa_pairs(pairs, output_dir)
        finally:
            generator.close()
    
    print("\n✓ Generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
