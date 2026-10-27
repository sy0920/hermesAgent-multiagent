"""FastAPI application entrypoint for the Hermes multi-agent platform."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.experts import router as experts_router
from app.hermes_client import HermesError
from app.kanban import router as kanban_router
from app.teams import ensure_advance_loop, router as teams_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep the board advancing even without the Hermes gateway running.
    ensure_advance_loop()
    yield


app = FastAPI(
    title="Hermes Multi-Agent Platform",
    description="可视化 Kanban + 专家 / 专家团协作平台（基于 Hermes Agent）",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experts_router)
app.include_router(kanban_router)
app.include_router(teams_router)


@app.exception_handler(HermesError)
async def hermes_error_handler(request: Request, exc: HermesError) -> JSONResponse:
    """Map CLI failures to a structured response instead of a bare 500."""
    return JSONResponse(
        status_code=502,
        content={"detail": f"Hermes 调用失败: {exc}"},
    )


@app.get("/api/health", response_model=dict)
def health() -> dict:
    return {"status": "ok", "service": "hermes-multiagent-platform"}