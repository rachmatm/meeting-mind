"""Qdrant vector database client for project memory isolation.

Blueprint section 8 - Project memory with strict project_id filtering.
"""

from __future__ import annotations

from typing import Any

from services.hermes.core.settings import get_settings


class QdrantClient:
    """Qdrant client for semantic memory storage and retrieval."""
    
    # Collection names per blueprint section 8.1
    COLLECTION_PARTICIPANT_HISTORY = "participant_history"
    COLLECTION_PROJECT_CONTEXT = "project_context"
    
    def __init__(self):
        settings = get_settings()
        self.url = settings.qdrant_url
        self.api_key = settings.qdrant_api_key
        self.embedding_dim = settings.embedding_dim
        self._session = None
    
    async def _get_headers(self) -> dict[str, str]:
        """Get headers for Qdrant API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key.get_secret_value()
        return headers
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make HTTP request to Qdrant."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.url}{path}",
                headers=await self._get_headers(),
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
    
    async def ensure_collections(self) -> None:
        """Create collections if they don't exist."""
        await self._ensure_collection(
            self.COLLECTION_PARTICIPANT_HISTORY,
            "User roles and past task assignments per project",
        )
        await self._ensure_collection(
            self.COLLECTION_PROJECT_CONTEXT,
            "Meeting summaries and decisions per project",
        )
    
    async def _ensure_collection(self, name: str, description: str) -> None:
        """Create collection if it doesn't exist."""
        try:
            await self._request("GET", f"/collections/{name}")
        except Exception:
            # Collection doesn't exist, create it
            payload = {
                "name": name,
                "vectors": {
                    "size": self.embedding_dim,
                    "distance": "Cosine"
                },
                "description": description,
            }
            await self._request("POST", "/collections", json=payload)
    
    # --- Participant History ---
    
    async def add_participant_context(
        self,
        user_id: str,
        project_id: str,
        role: str,
        divisions: list[str],
        past_tasks: str,
        embedding: list[float],
    ) -> str:
        """Add participant context to memory.
        
        Args:
            user_id: User identifier
            project_id: Project identifier (REQUIRED for filtering)
            role: User role in project
            divisions: User divisions/teams
            past_tasks: Description of past tasks
            embedding: Vector embedding of the context
            
        Returns:
            Point ID
        """
        payload = {
            "points": [{
                "id": f"{project_id}_{user_id}",
                "vector": embedding,
                "payload": {
                    "user_id": user_id,
                    "project_id": project_id,
                    "role": role,
                    "divisions": divisions,
                    "past_tasks": past_tasks,
                }
            }]
        }
        
        result = await self._request(
            "PUT",
            f"/collections/{self.COLLECTION_PARTICIPANT_HISTORY}/points",
            json=payload,
        )
        return result.get("result", {}).get("upserted_id", "")
    
    async def find_similar_participants(
        self,
        project_id: str,
        query_embedding: list[float],
        divisions: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar participants in a project.
        
        Args:
            project_id: Project identifier (REQUIRED filter)
            query_embedding: Query vector
            divisions: Optional division filter
            limit: Max results
            
        Returns:
            List of similar participants with scores
        """
        # MUST filter by project_id to ensure isolation (blueprint 8.2)
        must_conditions = [{"key": "project_id", "match": {"value": project_id}}]
        
        payload = {
            "vector": query_embedding,
            "filter": {
                "must": must_conditions
            },
            "limit": limit,
            "score_threshold": 0.5,
        }
        
        result = await self._request(
            "POST",
            f"/collections/{self.COLLECTION_PARTICIPANT_HISTORY}/points/search",
            json=payload,
        )
        
        return [
            {
                "user_id": p["payload"]["user_id"],
                "role": p["payload"].get("role"),
                "divisions": p["payload"].get("divisions", []),
                "past_tasks": p["payload"].get("past_tasks"),
                "score": p["score"],
            }
            for p in result.get("result", [])
        ]
    
    # --- Project Context ---
    
    async def add_meeting_summary(
        self,
        project_id: str,
        meeting_id: str,
        summary: str,
        key_points: list[str],
        embedding: list[float],
    ) -> str:
        """Add meeting summary to project context.
        
        Args:
            project_id: Project identifier (REQUIRED for filtering)
            meeting_id: Meeting identifier
            summary: Meeting summary text
            key_points: Key points from meeting
            embedding: Vector embedding
            
        Returns:
            Point ID
        """
        payload = {
            "points": [{
                "id": f"{project_id}_{meeting_id}",
                "vector": embedding,
                "payload": {
                    "project_id": project_id,
                    "meeting_id": meeting_id,
                    "summary": summary,
                    "key_points": key_points,
                }
            }]
        }
        
        result = await self._request(
            "PUT",
            f"/collections/{self.COLLECTION_PROJECT_CONTEXT}/points",
            json=payload,
        )
        return result.get("result", {}).get("upserted_id", "")
    
    async def search_project_context(
        self,
        project_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search project context for relevant information.
        
        Args:
            project_id: Project identifier (REQUIRED filter)
            query_embedding: Query vector
            limit: Max results
            
        Returns:
            List of relevant context with scores
        """
        # MUST filter by project_id to ensure isolation (blueprint 8.2)
        payload = {
            "vector": query_embedding,
            "filter": {
                "must": [{"key": "project_id", "match": {"value": project_id}}]
            },
            "limit": limit,
            "score_threshold": 0.3,
        }
        
        result = await self._request(
            "POST",
            f"/collections/{self.COLLECTION_PROJECT_CONTEXT}/points/search",
            json=payload,
        )
        
        return [
            {
                "meeting_id": p["payload"]["meeting_id"],
                "summary": p["payload"].get("summary"),
                "key_points": p["payload"].get("key_points", []),
                "score": p["score"],
            }
            for p in result.get("result", [])
        ]
    
    # --- Embedding helper ---
    
    async def get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using configured provider.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        from openai import AsyncOpenAI
        from services.hermes.core.settings import get_settings
        
        settings = get_settings()
        client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
        )
        
        # Use the embedding model configured in settings
        model = f"text-embedding-3-small"  # or voyage-3 based on settings
        
        response = await client.embeddings.create(
            model=model,
            input=text,
        )
        
        return response.data[0].embedding


# Singleton instance
_qdrant_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client singleton."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient()
    return _qdrant_client


async def search_similar_participants(
    project_id: str,
    task_description: str,
    divisions: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Convenience function to find similar participants."""
    client = get_qdrant_client()
    embedding = await client.get_embedding(task_description)
    return await client.find_similar_participants(
        project_id,
        embedding,
        divisions,
        limit,
    )


async def add_meeting_to_context(
    project_id: str,
    meeting_id: str,
    summary: dict[str, Any],
) -> str:
    """Convenience function to add meeting to project context."""
    client = get_qdrant_client()
    
    # Combine summary fields for embedding
    text = f"{summary.get('summary', '')} {' '.join(summary.get('key_points', []))}"
    embedding = await client.get_embedding(text)
    
    return await client.add_meeting_summary(
        project_id,
        meeting_id,
        summary.get("summary", ""),
        summary.get("key_points", []),
        embedding,
    )