from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.config import Settings, get_settings
from backend.app.domain.models import CommandPlan, CommandRequest
from backend.app.services.interpreter_graph import CommandInterpreter


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Voice Draw",
        version="0.1.0",
        description="Voice-only AI drawing tool using LangChain and LangGraph.",
    )
    app.state.interpreter = CommandInterpreter(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health(current_settings: Settings = Depends(get_settings)) -> dict[str, object]:
        return {
            "status": "ok",
            "env": current_settings.app_env,
            "llm_ready": current_settings.llm_ready,
        }

    @app.post("/api/commands/interpret", response_model=CommandPlan)
    def interpret_command(request: CommandRequest) -> CommandPlan:
        return app.state.interpreter.interpret(request)

    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
