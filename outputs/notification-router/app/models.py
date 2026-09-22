from enum import Enum
from typing import Literal, List, Optional
from pydantic import BaseModel, Field


class Action(str, Enum):
    notify = "notify"
    digest = "digest"
    mute = "mute"


class MessageType(str, Enum):
    personal = "personal"
    urgent = "urgent"
    event = "event"
    payment = "payment"
    business_update = "business_update"
    promotion = "promotion"
    greeting = "greeting"
    forward = "forward"
    spam = "spam"
    scam = "scam"
    unknown = "unknown"


class Media(BaseModel):
    kind: Literal["image", "voice"]
    transcript: str = ""
    image_data_url: Optional[str] = None
    audio_data_url: Optional[str] = None


class SenderContext(BaseModel):
    trusted: bool = False
    verified_business: bool = False
    domain_matches: bool = False
    is_group_admin: bool = False
    report_count_30d: int = 0


class UserContext(BaseModel):
    quiet_hours: bool = False
    sender_opened_30d: int = 0
    sender_dismissed_30d: int = 0
    sender_replied_30d: int = 0
    promotions_opted_out: bool = False
    group_muted: bool = False
    direct_mention: bool = False
    similar_message_ids: List[str] = Field(default_factory=list, max_length=5)


class RouteRequest(BaseModel):
    message_id: str
    text: str = ""
    conversation_type: Literal["personal", "group", "business"]
    sender_name: str = ""
    forwarded_count: int = Field(default=0, ge=0)
    media: Optional[Media] = None
    sender: SenderContext = Field(default_factory=SenderContext)
    user: UserContext = Field(default_factory=UserContext)

    def combined_text(self) -> str:
        media_text = self.media.transcript if self.media else ""
        return " ".join(part for part in (self.text.strip(), media_text.strip()) if part)


class RouteDecision(BaseModel):
    message_id: str
    action: Action
    message_type: MessageType
    reason: str = Field(max_length=180)
    confidence: float = Field(ge=0, le=1)
    evidence_message_ids: List[str] = Field(default_factory=list)
    validation_steps: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    engine: Literal["policy", "hybrid-ai"]
