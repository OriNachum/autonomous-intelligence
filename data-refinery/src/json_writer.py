"""JSON writer for extraction results."""
import json
from pathlib import Path
from typing import Union

from .models import WindowExtractionResult


class JsonWriter:
    """Write extraction results to JSON files."""
    
    def __init__(self, output_dir: str):
        """
        Initialize the JSON writer.
        
        Args:
            output_dir: Directory to write JSON files to
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write(self, result: WindowExtractionResult) -> Path:
        """
        Write an extraction result to a JSON file.
        
        Filename format: <document_name>_page_<start_page>.json
        
        Args:
            result: The extraction result to write
            
        Returns:
            Path to the written file
        """
        # Generate filename
        doc_base = Path(result.document_name).stem
        filename = f"{doc_base}_page_{result.start_page:04d}.json"
        filepath = self.output_dir / filename
        
        # Write JSON
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def write_batch(self, results: list[WindowExtractionResult]) -> list[Path]:
        """
        Write multiple extraction results.
        
        Args:
            results: List of extraction results
            
        Returns:
            List of paths to written files
        """
        return [self.write(result) for result in results]
