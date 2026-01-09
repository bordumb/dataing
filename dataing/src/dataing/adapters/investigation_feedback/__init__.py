"""Investigation feedback adapter for event logging and feedback collection."""

from .adapter import InvestigationFeedbackAdapter
from .types import EventType, FeedbackEvent

__all__ = ["EventType", "FeedbackEvent", "InvestigationFeedbackAdapter"]
