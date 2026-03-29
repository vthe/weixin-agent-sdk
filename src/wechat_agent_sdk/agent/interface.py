"""Agent interface — any AI backend that can handle a chat message."""

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    """Any AI backend that can handle a chat message."""

    async def chat(self, request: "ChatRequest") -> "ChatResponse":
        """Process a single message and return a reply."""
        ...


@dataclass
class ChatMedia:
    type: str
    filePath: str
    mimeType: str
    fileName: Optional[str] = None


@dataclass
class ChatRequest:
    conversationId: str
    text: str
    media: Optional[ChatMedia] = None


@dataclass
class ChatResponse:
    text: Optional[str] = None
    media: Optional[ChatMedia] = None
