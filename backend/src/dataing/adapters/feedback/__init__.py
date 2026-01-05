"""Feedback adapter for event logging and feedback collection."""

from .adapter import FeedbackAdapter
from .types import EventType, FeedbackEvent

__all__ = ["EventType", "FeedbackAdapter", "FeedbackEvent"]
