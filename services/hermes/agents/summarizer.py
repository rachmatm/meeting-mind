"""Summarizer Agent - generates meeting summary from transcript.

Blueprint section 6.1 - Input: Raw transcript, Output: {summary, key_points[], action_items[]}
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from services.hermes.core.settings import get_settings


# Output schema per blueprint section 6.1
SUMMARIZER_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "action_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "key_points", "action_items"],
}


SYSTEM_PROMPT = """You are a professional meeting summarizer.
Your task is to analyze meeting transcripts and create concise, actionable summaries.

Instructions:
1. Read the meeting transcript carefully
2. Create a summary (2-3 sentences capturing the main topic and outcome)
3. Extract key points (5-7 bullet points of important discussion items)
4. Identify action items (tasks that need to be done, with clear owners if mentioned)

Output Format: JSON with the following structure:
{
  "summary": "string",
  "key_points": ["string"],
  "action_items": ["string"]
}

Constraint: Output must be valid JSON only, no markdown formatting."""


class SummarizerAgent:
    """Agent for generating meeting summaries."""
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
        )
        self.model = settings.llm_model
        self.max_tokens = settings.llm_max_tokens * 4  # Larger for summarization
    
    async def summarize(self, transcript: str) -> dict:
        """Generate meeting summary from transcript.
        
        Args:
            transcript: Raw transcript text
            
        Returns:
            Dict with summary, key_points, and action_items
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Meeting Transcript:\n\n{transcript}"},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,  # Lower for more deterministic output
            )
            
            content = response.choices[0].message.content
            if content:
                # Parse JSON response
                result = json.loads(content)
                return self._validate_output(result)
            
        except Exception as e:
            print(f"Summarizer error: {e}")
        
        # Fallback: return mock summary for testing
        return self._fallback_summary(transcript)
    
    def _validate_output(self, result: dict) -> dict:
        """Validate output matches expected schema."""
        validated = {
            "summary": result.get("summary", "Summary not available"),
            "key_points": result.get("key_points", []),
            "action_items": result.get("action_items", []),
        }
        
        # Ensure arrays
        if not isinstance(validated["key_points"], list):
            validated["key_points"] = []
        if not isinstance(validated["action_items"], list):
            validated["action_items"] = []
        
        return validated
    
    def _fallback_summary(self, transcript: str) -> dict:
        """Generate fallback summary when LLM is unavailable."""
        # Simple extract for testing
        words = transcript.split()
        preview = " ".join(words[:50]) if words else "No transcript"
        
        return {
            "summary": f"Meeting transcript contains {len(words)} words. {preview}...",
            "key_points": ["Transcript processing requires LLM API configuration"],
            "action_items": ["Configure LLM API key for summarization"],
        }


# Singleton
_summarizer: SummarizerAgent | None = None


def get_summarizer() -> SummarizerAgent:
    """Get or create summarizer agent."""
    global _summarizer
    if _summarizer is None:
        _summarizer = SummarizerAgent()
    return _summarizer


async def summarize_transcript(transcript: str) -> dict:
    """Convenience function to summarize transcript."""
    agent = get_summarizer()
    return await agent.summarize(transcript)