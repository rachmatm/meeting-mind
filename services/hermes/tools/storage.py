"""File storage service for audio uploads.

Handles local file storage. Can be extended to S3/GCS for production.
"""

from __future__ import annotations

import aiofiles
import uuid
from pathlib import Path


class StorageService:
    """File storage for uploaded audio files."""
    
    def __init__(self, storage_path: str = "uploads"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    async def save(self, content: bytes, original_filename: str) -> str:
        """Save file and return stored URL/path.
        
        Args:
            content: File bytes
            original_filename: Original filename for extension
            
        Returns:
            Storage path/URL for the saved file
        """
        # Generate unique filename
        ext = Path(original_filename).suffix
        unique_name = f"{uuid.uuid4()}{ext}"
        file_path = self.storage_path / unique_name
        
        # Write file
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        
        return str(file_path)
    
    async def delete(self, path: str) -> bool:
        """Delete stored file."""
        try:
            file_path = Path(path)
            if file_path.exists():
                file_path.unlink()
                return True
        except Exception:
            pass
        return False


# Singleton
_storage: StorageService | None = None


def get_storage_service() -> StorageService:
    """Get or create storage service."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage