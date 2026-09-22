import json
import re
from typing import Any, Dict, List, Optional
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
from .models import Action, MessageType, RouteDecision, RouteRequest

SCAM = re.compile(r"(?i)\b(share.*(?:otp|pin|code)|one.?time password|scan.*qr.*pay|bank details.*(?:send|share)|processing fee|bit\.ly|tinyurl|lottery|prize)\b")
URL_RISK = re.compile(r"(?i)\b[\w-]+(?:verify|secure|refund|kyc|delivery|login)[\w-]*\.(?:in|net|com)\b")
PROMO = re.compile(r"(?i)\b(sale|% off|discount|coupon|offer|buy now|unsubscribe)\b")
URGENT = re.compile(r"(?i)\b(emergency|urgent|help(?:ing|ful)?|support|assist(?:ance)?|call me(?: now)?|accident|injury|hospital|ambulance|today|in \d+ min|before \d+|pickup|appointment|meeting|water|maintenance|delivery)\b")
PAYMENT = re.compile(r"(?i)\b(payment|due|invoice|receipt|rent|upi|bill|statement)\b")
URGENT_PAYMENT = re.compile(r"(?i)\b(now|immediately|asap|as soon as possible|without delay|otherwise|or else|disconnected|connection will be lost|cut off|shut off)\b")
EVENT = re.compile(r"(?i)\b(event|class|school|notice|holiday|schedule|society|lift)\b")

ROUTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": [x.value for x in Action]},
        "message_type": {"type": "string", "enum": [x.value for x in MessageType]},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_message_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
    "required": ["action", "message_type", "reason", "confidence", "evidence_message_ids"],
}


class _DefaultSettings:
    llm_enabled = False
    openai_api_key = None
    router_model = "gpt-4.1-mini"


class NotificationRouter:
    def __init__(self, settings: Optional[Any] = None):
        self.settings = settings or _DefaultSettings()
        self.enabled = bool(self.settings.llm_enabled and self.settings.openai_api_key and OpenAI)
        self.model = self.settings.router_model
        self.client = OpenAI(api_key=self.settings.openai_api_key) if self.enabled else None

    @property
    def can_use_llm(self) -> bool:
        return self.enabled and self.client is not None

    def _combined_text(self, request: RouteRequest) -> str:
        media_text = request.media.transcript if request.media else ""
        return " ".join(part for part in (request.text.strip(), media_text.strip()) if part)

    def _make_decision(
        self,
        request: RouteRequest,
        action: Action,
        message_type: MessageType,
        reason: str,
        confidence: float,
        validation_steps: Optional[List[str]] = None,
    ) -> RouteDecision:
        summary = f"Router chose {action.value.upper()} because {reason}"
        return RouteDecision(
            message_id=request.message_id,
            action=action,
            message_type=message_type,
            reason=reason,
            confidence=confidence,
            evidence_message_ids=request.user.similar_message_ids,
            validation_steps=validation_steps or [],
            summary=summary,
            engine="policy",
        )

    def _is_hard_risk(self, request: RouteRequest, text: str) -> bool:
        suspicious_business = (
            request.conversation_type == "business"
            and (not request.sender.verified_business or not request.sender.domain_matches)
        )
        suspicious_group = request.conversation_type == "group" and not request.sender.is_group_admin
        return bool(
            SCAM.search(text)
            or request.forwarded_count >= 10
            or (URL_RISK.search(text) and (suspicious_business or suspicious_group))
        )

    def policy(self, request: RouteRequest) -> RouteDecision:
        text = self._combined_text(request)
        steps = [f"Combined text and media transcript: '{text}'."]

        if self._is_hard_risk(request, text):
            steps.append("Detected hard-risk indicators; blocking the message as scam/spam.")
            return self._make_decision(
                request,
                Action.mute,
                MessageType.scam,
                "Credential, payment, link, or forwarding risk detected.",
                0.97,
                validation_steps=steps,
            )

        steps.append("No hard-risk indicators were found.")

        if PROMO.search(text) and (request.user.promotions_opted_out or request.user.sender_dismissed_30d > request.user.sender_opened_30d):
            steps.append("Promotional text found and user preference indicates mute.")
            return self._make_decision(
                request,
                Action.mute,
                MessageType.promotion,
                "Promotion denied based on opt-out or dismissal history.",
                0.88,
                validation_steps=steps,
            )

        if request.user.group_muted and not request.user.direct_mention:
            steps.append("Group is muted and there is no direct mention.")
            return self._make_decision(
                request,
                Action.mute,
                MessageType.unknown,
                "Muted group message without a direct mention.",
                0.90,
                validation_steps=steps,
            )

        if EVENT.search(text):
            steps.append("Event-related language detected.")
            steps.append(
                "Quiet hours is " + ("enabled" if request.user.quiet_hours else "disabled") + ", so the action is chosen accordingly."
            )
            return self._make_decision(
                request,
                Action.digest if request.user.quiet_hours else Action.notify,
                MessageType.event,
                "Event update delivered based on quiet-hours preference.",
                0.75,
                validation_steps=steps,
            )

        urgent_payment = PAYMENT.search(text) and URGENT_PAYMENT.search(text)
        if URGENT.search(text) or urgent_payment or (PAYMENT.search(text) and (request.sender.trusted or request.sender.is_group_admin)):
            steps.append("Urgent or trusted payment language detected.")
            return self._make_decision(
                request,
                Action.notify,
                MessageType.payment if PAYMENT.search(text) else MessageType.urgent,
                "Time-sensitive update from a trusted or urgent payment message.",
                0.85,
                validation_steps=steps,
            )

        if PROMO.search(text):
            steps.append("Promotional content detected and no mute rule applies.")
            return self._make_decision(
                request,
                Action.digest,
                MessageType.promotion,
                "Promotional content that can be reviewed later.",
                0.70,
                validation_steps=steps,
            )

        steps.append("No special pattern matched; defaulting to digest for non-urgent content.")
        return self._make_decision(
            request,
            Action.digest,
            MessageType.personal if request.conversation_type == "personal" else MessageType.unknown,
            "Non-urgent message for later review.",
            0.62,
            validation_steps=steps,
        )

    def importance_layer(self, request: RouteRequest, baseline: RouteDecision) -> RouteDecision:
        if baseline.action == Action.mute or not self.can_use_llm:
            return baseline

        payload = request.model_dump(mode="json")
        payload["policy_baseline"] = baseline.model_dump(mode="json")
        payload["importance_check"] = True

        inputs = [{"type": "input_text", "text": json.dumps(payload)}]
        if request.media:
            if request.media.kind == "image" and request.media.image_data_url:
                inputs.append({"type": "input_image", "image_url": request.media.image_data_url, "detail": "low"})
            if request.media.kind == "voice" and request.media.audio_data_url:
                inputs.append({"type": "input_audio", "audio_url": request.media.audio_data_url, "detail": "low"})

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": "Review the message. Return only a structured routing decision that preserves the safe policy baseline."},
                    {"role": "user", "content": inputs},
                ],
                text={"format": {"type": "json_schema", "name": "route", "strict": True, "schema": ROUTE_SCHEMA}},
            )
            result = json.loads(response.output_text)
            final = RouteDecision(message_id=request.message_id, **result, engine="hybrid-ai")
            if not final.validation_steps:
                final.validation_steps = baseline.validation_steps + [
                    "Hybrid AI importance review completed and preserved the policy baseline.",
                ]
            if not final.summary:
                final.summary = baseline.summary or f"Hybrid AI review completed with action {final.action.value.upper()}."
            return final
        except Exception:
            return baseline

    def route(self, request: RouteRequest) -> RouteDecision:
        baseline = self.policy(request)
        if self._is_hard_risk(request, self._combined_text(request)):
            return baseline
        return self.importance_layer(request, baseline)
