"""SQLAlchemy models.

Every model class is imported here so that `Base.metadata` sees them at import time
(used both by `ensure_schema()` and Alembic autogenerate).
"""

from app.infra.db import Base
from app.models.admin import AdminAuditLog, IngestionJob
from app.models.ai import AIMessage, AISession, DocumentChunk
from app.models.auth import RefreshToken
from app.models.chat import ChatThread, ChatThreadParticipant, Message
from app.models.event import Event, EventInterest, EventSpeaker, Speaker
from app.models.interaction import EventCardReaction, EventInteraction
from app.models.interest import Interest, UserInterest
from app.models.mission import Mission, UserMissionProgress
from app.models.networking import Connection, Match
from app.models.notification import Notification
from app.models.reel import Reel, ReelInteraction
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Interest",
    "UserInterest",
    "Event",
    "Speaker",
    "EventSpeaker",
    "EventInterest",
    "EventInteraction",
    "EventCardReaction",
    "Reel",
    "ReelInteraction",
    "Connection",
    "Match",
    "ChatThread",
    "ChatThreadParticipant",
    "Message",
    "DocumentChunk",
    "AISession",
    "AIMessage",
    "Mission",
    "UserMissionProgress",
    "Notification",
    "IngestionJob",
    "AdminAuditLog",
    "RefreshToken",
]
