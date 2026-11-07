"""Talon ingest gateway (Phase 1 scaffold).

Phase 1 only stores the scammer's turn in SpacetimeDB so the dashboard shows it.
Phase 2 adds triage, the decoy reply, the safety guard and extraction here.

Run:  uvicorn app:app --reload --port 8000   (from the services/ folder)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from talon.ids import new_id
from talon.spacetime import Spacetime, SpacetimeError

app = FastAPI(title="Talon ingest gateway")
db = Spacetime()


class InboundMessage(BaseModel):
    canary_id: int = Field(..., ge=1)
    text: str = Field(..., min_length=1, max_length=2000)
    conversation_id: int | None = Field(None, description="omit to start a new conversation")
    channel: str = Field("sms", pattern="^(sms|voice)$")
    run_id: str = Field("", description="recorded run id; empty for live traffic")


class IngestResult(BaseModel):
    conversation_id: int
    turn_id: int
    reply: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/ingest/message", response_model=IngestResult)
def ingest_message(msg: InboundMessage) -> IngestResult:
    try:
        conversation_id = msg.conversation_id
        if conversation_id is None:
            conversation_id = new_id()
            db.call("start_conversation", conversation_id, msg.canary_id, msg.channel, msg.run_id)
        turn_id = new_id()
        # Triage isn't built yet (Phase 2), so the label is empty and confidence 0.
        db.call("add_turn", turn_id, conversation_id, "scammer", msg.text, "", 0.0, True)
    except SpacetimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return IngestResult(conversation_id=conversation_id, turn_id=turn_id, reply=None)
