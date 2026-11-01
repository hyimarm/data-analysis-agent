"""FastAPI 服务：用 SSE 把 Agent 的执行过程实时推给前端。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from .agent import build_agent
from .config import settings

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# 全局只构建一次：MCP 工具加载要拉起子进程，每次请求都重建会很慢
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["agent"] = await build_agent()
    yield
    _state.clear()


app = FastAPI(title="数据分析助手", lifespan=lifespan)

settings.chart_dir.mkdir(parents=True, exist_ok=True)
app.mount("/charts", StaticFiles(directory=settings.chart_dir), name="charts")


class ChatRequest(BaseModel):
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def _content_text(content) -> str:
    """MCP 工具返回的是内容块列表，取出其中的文本。

    content 可能是 str，也可能是 [{"type": "text", "text": "..."}]。
    直接 str() 会打出 Python 的 repr，前端没法看。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


async def _stream(message: str):
    agent = _state["agent"]
    yield _sse("start", {"message": message})

    try:
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            stream_mode="updates",
        ):
            for _node, payload in chunk.items():
                for msg in (payload or {}).get("messages", []) or []:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        for call in msg.tool_calls:
                            yield _sse("tool", {"name": call["name"], "args": call["args"]})
                    elif isinstance(msg, ToolMessage):
                        yield _sse(
                            "result",
                            {"name": msg.name, "text": _content_text(msg.content)[:600]},
                        )
                    elif isinstance(msg, AIMessage) and msg.content:
                        yield _sse("answer", {"text": _content_text(msg.content)})
    except Exception as exc:  # 任何异常都要让前端看到，而不是连接静默断开
        yield _sse("error", {"message": str(exc)})

    yield "event: done\ndata: {}\n\n"


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _stream(request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")