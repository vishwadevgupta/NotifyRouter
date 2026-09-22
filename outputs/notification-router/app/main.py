import os
from pathlib import Path
from typing import List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .models import RouteDecision, RouteRequest
from .router import NotificationRouter


class Settings:
    def __init__(self):
        self.router_api_key = os.getenv("ROUTER_API_KEY")
        self.llm_enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.router_model = os.getenv("ROUTER_MODEL", "gpt-4.1-mini")


settings = Settings()
app = FastAPI(title="AI Notification Router", version="1.0.0")
router = NotificationRouter(settings)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class DemoRouteRequest(BaseModel):
    payload: RouteRequest


def authorize(x_router_key: Optional[str] = Header(None)):
    if settings.router_api_key and x_router_key != settings.router_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@app.get("/", include_in_schema=False)
def serve_demo():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "llm_enabled": settings.llm_enabled and router.can_use_llm}


@app.post("/v1/route", response_model=RouteDecision)
def route(request: RouteRequest, authorized: bool = Depends(authorize)):
    return router.route(request)


@app.post("/v1/route/batch", response_model=List[RouteDecision])
def route_batch(requests: List[RouteRequest], authorized: bool = Depends(authorize)):
    if len(requests) > 100:
        raise HTTPException(status_code=422, detail="Maximum batch size is 100")
    return [router.route(payload) for payload in requests]


@app.post("/demo/route", response_model=RouteDecision)
def demo_route(request: DemoRouteRequest):
    return router.route(request.payload)
