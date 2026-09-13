import logging
from datetime import datetime
from typing import Any
from db.supabase import supabase

logger = logging.getLogger(__name__)


class FlightEvent:
    def __init__(self, operation_id: str, stage: str, message: str, details: dict | None = None):
        self.operation_id = operation_id
        self.stage = stage
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "message": self.message,
            "details": self.details,
        }


class SafeSubmitFlightRecorder:
    def __init__(self, operation_id: str):
        self.operation_id = operation_id
        self._events: list[FlightEvent] = []

    def record(self, stage: str, message: str, details: dict | None = None) -> None:
        event = FlightEvent(self.operation_id, stage, message, details)
        self._events.append(event)
        logger.info("[FlightRecorder] %s: %s", stage, message)

    def events(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def timeline(self) -> str:
        lines = []
        for e in self._events:
            lines.append(f"{e.timestamp} {e.stage}: {e.message}")
        return "\n".join(lines)


def record_flight_event(operation_id: str, stage: str, message: str, details: dict | None = None) -> None:
    recorder = SafeSubmitFlightRecorder(operation_id)
    recorder.record(stage, message, details)
