"""Document processor with 3-page sliding window."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import fitz  # pymupdf


@dataclass
class PageContent:
    """Content of a single page."""
    page_number: int
    text: str
    # Optional: image bytes for multimodal processing
    image_bytes: Optional[bytes] = None


@dataclass 
class SlidingWindow:
    """A sliding window over document pages."""
    document_name: str
    document_path: str
    start_page: int
    end_page: int
    pages: list[PageContent]
    
    @property
    def combined_text(self) -> str:
        """Get all text from pages in this window."""
        return "\n\n---\n\n".join(
            f"[Page {p.page_number}]\n{p.text}" 
            for p in self.pages
        )
    
    @property
    def output_filename(self) -> str:
        """Generate output filename for this window."""
        doc_base = Path(self.document_name).stem
        return f"{doc_base}_page_{self.start_page:04d}.json"


class DocumentProcessor:
    """Process documents with a sliding window approach."""
    
    def __init__(self, window_size: int = 3, extract_images: bool = False):
        """
        Initialize the document processor.
        
        Args:
            window_size: Number of pages per window
            extract_images: Whether to extract page images for multimodal
        """
        self.window_size = window_size
        self.extract_images = extract_images
    
    def process_document(self, document_path: str) -> Iterator[SlidingWindow]:
        """
        Process a document and yield sliding windows.
        
        Args:
            document_path: Path to the PDF document
            
        Yields:
            SlidingWindow objects for each window position
        """
        document_path = Path(document_path)
        if not document_path.exists():
            raise FileNotFoundError(f"Document not found: {document_path}")
        
        doc = fitz.open(str(document_path))
        total_pages = len(doc)
        
        if total_pages == 0:
            doc.close()
            return
        
        # Extract all page content first
        pages = []
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text()
            
            image_bytes = None
            if self.extract_images:
                # Render page as image
                pix = page.get_pixmap(dpi=150)
                image_bytes = pix.tobytes("png")
            
            pages.append(PageContent(
                page_number=page_num + 1,  # 1-indexed
                text=text,
                image_bytes=image_bytes,
            ))
        
        doc.close()
        
        # Generate sliding windows
        for start_idx in range(0, total_pages, 1):  # Move by 1 page for overlap
            end_idx = min(start_idx + self.window_size, total_pages)
            window_pages = pages[start_idx:end_idx]
            
            yield SlidingWindow(
                document_name=document_path.name,
                document_path=str(document_path),
                start_page=start_idx + 1,  # 1-indexed
                end_page=end_idx,  # 1-indexed
                pages=window_pages,
            )
            
            # Stop if we've reached the end
            if end_idx >= total_pages:
                break
    
    def process_directory(self, directory_path: str) -> Iterator[SlidingWindow]:
        """
        Process all PDF documents in a directory.
        
        Args:
            directory_path: Path to directory containing PDFs
            
        Yields:
            SlidingWindow objects from all documents
        """
        directory = Path(directory_path)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")
        
        for pdf_path in sorted(directory.glob("*.pdf")):
            yield from self.process_document(str(pdf_path))
