import asyncio
import contextlib
import os
from contextvars import ContextVar
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableGenerator
from langgraph.checkpoint.memory import InMemorySaver
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from assemblyai_stt import AssemblyAISTT
from cartesia_tts import CartesiaTTS
from events import (
    AgentChunkEvent,
    AgentEndEvent,
    ToolCallEvent,
    ToolResultEvent,
    VoiceAgentEvent,
    event_to_dict,
)
from orders import OrderManager
from utils import merge_async_iters

load_dotenv()

# Static files are served from the shared web build output
STATIC_DIR = Path(__file__).parent.parent.parent / "web" / "dist"

if not STATIC_DIR.exists():
    raise RuntimeError(
        f"Web build not found at {STATIC_DIR}. "
        "Run 'make build-web' or 'make dev-py' from the project root."
    )

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


order_manager = OrderManager()
current_thread_id: ContextVar[str | None] = ContextVar(
    "current_thread_id", default=None
)


async def add_to_order(item: str, quantity: int) -> str:
    """Add an item to the customer's sandwich order."""
    thread_id = current_thread_id.get()
    if not thread_id:
        return f"Agregue {quantity} x {item} al pedido."
    return await order_manager.add_item(thread_id, item, quantity)


async def confirm_order(order_summary: str) -> str:
    """Confirm the final order with the customer."""
    thread_id = current_thread_id.get()
    if not thread_id:
        return f"Pedido confirmado: {order_summary}. Enviando a cocina."
    order = await order_manager.confirm_order(thread_id, order_summary)
    return f"Pedido confirmado: {order.summary}. Numero de orden: {order.id}."


async def check_order_status(order_id: str) -> str:
    """Check the current kitchen status for an existing order."""
    order = await order_manager.get_order(order_id)
    if order is None:
        return (
            f"No encontre la orden {order_id}. "
            "Verifica el numero e intentalo de nuevo."
        )

    status_text = {
        "nuevo": "nueva y pendiente de iniciar",
        "en_preparacion": "en preparacion",
        "listo": "lista para entregar",
    }[order.status]

    return (
        f"La orden {order.id} esta {status_text}. "
        f"Resumen: {order.summary}."
    )


system_prompt = """
Tu eres un asistente de un restaurante de sandwiches. Tu objetivo es tomar el pedido del cliente y confirmar el pedido.
Responde siempre en espanol.
No mezcles ingles salvo si el usuario te habla explicitamente en ingles.
Pronuncia numeros de orden, ingredientes y estados en espanol.
Se muy conciso y amigable.
Si el cliente pregunta por el estado de una orden y te comparte un numero de orden, usa la herramienta disponible para consultarla.

Toppings disponibles: lechuga, tomate, cebolla, pepinillos, mayonesa, mostaza.
Carnes disponibles: pavo, pollo, cerdo.
Quesos disponibles: cheddar, mozzarella, parmesano.

${CARTESIA_TTS_SYSTEM_PROMPT}
"""

agent = create_agent(
    model="openai:gpt-5.2",
    tools=[add_to_order, confirm_order, check_order_status],
    system_prompt=system_prompt,
    checkpointer=InMemorySaver(),
)


async def _stt_stream(
    audio_stream: AsyncIterator[bytes],
) -> AsyncIterator[VoiceAgentEvent]:
    """
    Transform stream: Audio (Bytes) -> Voice Events (VoiceAgentEvent)

    This function takes a stream of audio chunks and sends them to AssemblyAI for STT.

    It uses a producer-consumer pattern where:
    - Producer: A background task reads audio chunks from audio_stream and sends
      them to AssemblyAI via WebSocket. This runs concurrently with the consumer,
      allowing transcription to begin before all audio has arrived.
    - Consumer: The main coroutine receives transcription events from AssemblyAI
      and yields them downstream. Events include both partial results (stt_chunk)
      and final transcripts (stt_output).

    Args:
        audio_stream: Async iterator of PCM audio bytes (16-bit, mono, 16kHz)

    Yields:
        STT events (stt_chunk for partials, stt_output for final transcripts)
    """
    stt = AssemblyAISTT(sample_rate=16000)

    async def send_audio():
        """
        Background task that pumps audio chunks to AssemblyAI.

        This runs concurrently with the main coroutine, continuously reading
        audio chunks from the input stream and forwarding them to AssemblyAI.
        When the input stream ends, it signals completion by closing the
        WebSocket connection.
        """
        try:
            async for audio_chunk in audio_stream:
                await stt.send_audio(audio_chunk)
        finally:
            await stt.close()

    send_task = asyncio.create_task(send_audio())

    try:
        async for event in stt.receive_events():
            yield event
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            send_task.cancel()
            await send_task
        await stt.close()


async def _agent_stream(
    event_stream: AsyncIterator[VoiceAgentEvent],
) -> AsyncIterator[VoiceAgentEvent]:
    """
    Transform stream: Voice Events -> Voice Events (with Agent Responses)
    """
    thread_id = str(uuid4())

    async for event in event_stream:
        yield event

        if event.type == "stt_output":
            token = current_thread_id.set(thread_id)
            try:
                stream = agent.astream(
                    {"messages": [HumanMessage(content=event.transcript)]},
                    {"configurable": {"thread_id": thread_id}},
                    stream_mode="messages",
                )

                async for message, metadata in stream:
                    if isinstance(message, AIMessage):
                        yield AgentChunkEvent.create(message.text)
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for tool_call in message.tool_calls:
                                yield ToolCallEvent.create(
                                    id=tool_call.get("id", str(uuid4())),
                                    name=tool_call.get("name", "unknown"),
                                    args=tool_call.get("args", {}),
                                )

                    if isinstance(message, ToolMessage):
                        yield ToolResultEvent.create(
                            tool_call_id=getattr(message, "tool_call_id", ""),
                            name=getattr(message, "name", "unknown"),
                            result=str(message.content) if message.content else "",
                        )
            finally:
                current_thread_id.reset(token)

            yield AgentEndEvent.create()


async def _tts_stream(
    event_stream: AsyncIterator[VoiceAgentEvent],
) -> AsyncIterator[VoiceAgentEvent]:
    """
    Transform stream: Voice Events -> Voice Events (with Audio)
    """
    tts = CartesiaTTS()

    async def process_upstream() -> AsyncIterator[VoiceAgentEvent]:
        buffer: list[str] = []
        async for event in event_stream:
            yield event
            if event.type == "agent_chunk":
                buffer.append(event.text)
            if event.type == "agent_end":
                await tts.send_text("".join(buffer))
                buffer = []

    try:
        await tts.prepare()
        async for event in merge_async_iters(
            process_upstream(), tts.receive_events()
        ):
            yield event
    finally:
        await tts.close()


pipeline = (
    RunnableGenerator(_stt_stream)
    | RunnableGenerator(_agent_stream)
    | RunnableGenerator(_tts_stream)
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/kitchen")
async def kitchen_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def websocket_audio_stream() -> AsyncIterator[bytes]:
        try:
            while True:
                data = await websocket.receive_bytes()
                yield data
        except WebSocketDisconnect:
            return

    output_stream = pipeline.atransform(websocket_audio_stream())

    try:
        async for event in output_stream:
            await websocket.send_json(event_to_dict(event))
    except WebSocketDisconnect:
        pass


@app.websocket("/kitchen/ws")
async def kitchen_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue, snapshot = await order_manager.subscribe()

    await websocket.send_json({"type": "snapshot", "orders": snapshot})

    async def sender() -> None:
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    send_task = asyncio.create_task(sender())

    try:
        while True:
            payload = await websocket.receive_json()
            if payload.get("type") != "update_status":
                continue

            status = payload.get("status")
            order_id = payload.get("orderId")
            if status not in {"nuevo", "en_preparacion", "listo"}:
                continue
            if not isinstance(order_id, str) or not order_id.strip():
                continue

            validated_status = status
            await order_manager.update_status(
                order_id=order_id, status=validated_status
            )
    except WebSocketDisconnect:
        pass
    finally:
        send_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await send_task
        await order_manager.unsubscribe(queue)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    uvicorn.run("main:app", host=host, port=port, reload=reload)
