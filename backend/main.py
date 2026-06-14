from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from backend.config import Settings, get_settings
from backend.interpreter_graph import CommandInterpreter
from backend.models import CommandRequest


class VoiceDrawApp:
    """轻量 ASGI 应用，负责 API 路由和前端静态资源托管。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.interpreter = CommandInterpreter(self.settings)
        project_root = Path(__file__).parent.parent
        preferred_static_dir = project_root / "voicedraw" / "fronted"
        fallback_static_dir = project_root / "fronted"
        self.static_dir = preferred_static_dir if preferred_static_dir.exists() else fallback_static_dir

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """根据 HTTP method/path 分发请求。"""
        if scope["type"] != "http":
            await self._send_response(send, 404, b"Not Found", "text/plain; charset=utf-8")
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")

        try:
            if method == "GET" and path == "/api/health":
                # 健康检查同时暴露 LLM 配置状态，方便前端决定是否提示用户。
                await self._send_json(
                    send,
                    {
                        "status": "ok",
                        "env": self.settings.app_env,
                        "llm_ready": self.interpreter.llm_parser.is_configured,
                        "llm_model": self.settings.llm_model,
                        "planner_mode": "ai_enum_vector_planner",
                    },
                )
                return

            if method == "POST" and path == "/api/commands/interpret":
                # 语音文本解析入口：请求体转换成领域模型后交给解释器。
                payload = await self._read_json(receive)
                request = CommandRequest.from_dict(payload)
                plan = self.interpreter.interpret(request)
                await self._send_json(send, plan.model_dump())
                return

            if method == "GET":
                await self._send_static(send, path)
                return

            await self._send_response(send, 405, b"Method Not Allowed", "text/plain; charset=utf-8")
        except ValueError as exc:
            await self._send_json(send, {"detail": str(exc)}, status=400)
        except Exception as exc:
            await self._send_json(send, {"detail": f"Internal server error: {exc}"}, status=500)

    async def _read_body(self, receive: Any) -> bytes:
        """读取 ASGI 分块请求体并合并为 bytes。"""
        chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            chunks.append(message.get("body", b""))
            more_body = bool(message.get("more_body", False))
        return b"".join(chunks)

    async def _read_json(self, receive: Any) -> dict[str, Any]:
        """读取 JSON 请求体，业务接口只接受对象类型。"""
        body = await self._read_body(receive)
        if not body:
            return {}
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    async def _send_static(self, send: Any, path: str) -> None:
        """返回静态文件，并阻止路径穿越访问 static 目录外的文件。"""
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (self.static_dir / relative).resolve()
        static_root = self.static_dir.resolve()

        # resolve 后再次检查前缀，避免 ../ 形式逃出 static 目录。
        if not str(target).startswith(str(static_root)) or not target.is_file():
            await self._send_response(send, 404, b"Not Found", "text/plain; charset=utf-8")
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type = f"{content_type}; charset=utf-8"
        await self._send_response(send, 200, target.read_bytes(), content_type)

    async def _send_json(self, send: Any, data: Any, status: int = 200) -> None:
        """统一 JSON 响应编码，保留中文提示文本。"""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        await self._send_response(send, status, body, "application/json; charset=utf-8")

    async def _send_response(self, send: Any, status: int, body: bytes, content_type: str) -> None:
        """发送最小 HTTP 响应头和响应体。"""
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", content_type.encode("ascii")),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"access-control-allow-origin", b"*"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def create_app() -> VoiceDrawApp:
    """供 ASGI 服务器导入的应用工厂。"""
    return VoiceDrawApp()


app = create_app()
