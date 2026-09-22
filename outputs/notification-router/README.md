# AI Notification Router

A safety-first message routing service that classifies incoming communication as `notify`, `digest`, or `mute` based on content, trust signals, user preferences, and optional AI review.

This project is designed for channel adapters such as WhatsApp, SMS, email, Slack, or backend webhooks. The adapter sends a normalized message payload, and the router decides how the message should be handled without storing raw message content in the routing service itself.

## What this service does

The router evaluates a message and returns a structured decision with:

- action: `notify`, `digest`, or `mute`
- message type: such as payment, urgent, event, promotion, scam, or unknown
- reason and confidence score
- evidence message IDs
- validation steps used to reach the decision

The decision flow is intentionally layered:

1. Policy-based rules run first.
2. Safety checks reject hard-risk messages immediately.
3. Optional AI review is used only for importance or prioritization.
4. The system falls back to the safe policy decision if the AI layer is unavailable or fails.

## Core behavior

The router implements a set of protective rules to avoid unsafe routing:

- OTP/PIN/QR scam patterns are blocked immediately.
- Suspicious links and high-forwarding messages are treated as risk signals.
- Promotional content can be muted when the user has opted out or has dismissed similar messages repeatedly.
- Muted groups without direct mention are suppressed.
- Quiet hours can convert event or low-priority messages into digests.
- Urgent or trusted payment messages are escalated to immediate notification.

## Why this exists

In messaging systems, not every message deserves immediate delivery. Some messages are time-sensitive and should interrupt the user, while others should be grouped into a digest or silenced entirely.

This router acts as a decision layer between message ingestion and delivery, enforcing both safety and user intent.

## Architecture

The project is structured as a small FastAPI app:

- `app/models.py`: input/output models for route requests and decisions
- `app/router.py`: policy engine and optional AI importance review
- `app/main.py`: API endpoints and demo UI integration
- `tests/test_router.py`: route logic verification

## Features

- Safety-first routing policy
- User and sender context awareness
- Quiet-hours support
- Promotion opt-out and dismissal handling
- Group mute and direct-mention controls
- Optional multimodal AI enhancement for text, image, and voice input
- Batch API support
- Health check endpoint
- Demo UI for local testing

## Local setup

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Start the app with Docker Compose:

```bash
docker compose up --build
```

3. Check the health endpoint:

```bash
curl http://localhost:8080/health
```

4. Send a sample routing request:

```bash
curl -X POST http://localhost:8080/v1/route \
  -H 'content-type: application/json' \
  -H 'x-router-key: change-me-before-deploying' \
  -d '{
    "message_id": "demo-1",
    "text": "Please share your OTP now",
    "conversation_type": "personal"
  }'
```

5. Open the demo UI in a browser:

```text
http://localhost:8080/
```

## Environment variables

The app reads the following values from `.env`:

- `ROUTER_API_KEY`: API key required for protected routes
- `LLM_ENABLED`: set to `true` to enable optional AI review
- `OPENAI_API_KEY`: required if AI mode is enabled
- `ROUTER_MODEL`: model name for OpenAI requests

Example:

```env
ROUTER_API_KEY=change-me-before-deploying
LLM_ENABLED=false
ROUTER_MODEL=gpt-4.1-mini
```

## API endpoints

### GET /health
Returns the current health status and whether the AI layer is active.

### POST /v1/route
Routes a single message and returns a single decision.

### POST /v1/route/batch
Routes up to 100 messages in one request.

### POST /demo/route
Demo endpoint used by the browser UI.

## Example request payload

```json
{
  "message_id": "msg_123",
  "text": "Payment due today",
  "conversation_type": "business",
  "sender_name": "Finance Team",
  "forwarded_count": 0,
  "sender": {
    "trusted": true,
    "verified_business": true,
    "domain_matches": true,
    "is_group_admin": false
  },
  "user": {
    "quiet_hours": false,
    "promotions_opted_out": false,
    "group_muted": false,
    "direct_mention": true
  }
}
```

## Safe AI usage

AI is optional and only used as an importance layer. The service still prefers policy-driven decisions and defaults to the safe non-AI result whenever:

- there is no API key
- the model is unavailable
- the request is malformed
- the model returns invalid output
- the network call fails

This keeps the system predictable and reduces risk from untrusted or malformed messages.

## Privacy and operational notes

- Do not commit `.env` files.
- Only send explicit, consented message content to the AI layer.
- Keep raw message storage separate from the routing service.
- Apply retention limits and deletion handling for any private message data.

## Summary

This project is a compact, production-minded decision engine for intelligent message routing. It combines policy safety, user context, and optional AI scoring to decide whether a message should be delivered immediately, bundled into a digest, or suppressed.
