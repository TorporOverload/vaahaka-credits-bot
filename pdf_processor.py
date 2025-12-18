import hashlib
import io
from typing import Optional, Tuple

from pypdf import PdfReader


class PDFProcessor:
    @staticmethod
    async def process_pdf(
        file_data: bytes, file_name: str
    ) -> Optional[Tuple[str, int]]:
        """
        Process a PDF file to extract its hash and page count.

        Args:
            file_data: The PDF file as bytes
            file_name: The name of the file

        Returns:
            Tuple of (file_hash, page_count) or None if processing fails
        """
        try:
            # Calculate SHA-256 hash for duplicate detection
            file_hash = hashlib.sha256(file_data).hexdigest()

            # Extract page count using pypdf
            pdf_stream = io.BytesIO(file_data)
            reader = PdfReader(pdf_stream)
            page_count = len(reader.pages)

            return (file_hash, page_count)

        except Exception as e:
            print(f"Error processing PDF '{file_name}': {e}")
            return None

    @staticmethod
    def is_pdf(filename: str) -> bool:
        """Check if a filename has a PDF extension."""
        return filename.lower().endswith(".pdf")
