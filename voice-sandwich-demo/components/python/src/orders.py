import asyncio
import contextlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

KitchenOrderStatus = Literal["nuevo", "en_preparacion", "listo"]


@dataclass
class OrderItem:
    item: str
    quantity: int

    def to_dict(self) -> dict:
        return {
            "item": self.item,
            "quantity": self.quantity,
            "label": f"{self.quantity} x {self.item}",
        }


@dataclass
class KitchenOrder:
    id: str
    created_at: str
    status: KitchenOrderStatus
    summary: str
    items: list[OrderItem]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "createdAt": self.created_at,
            "status": self.status,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class ConfirmationState:
    draft_version: int
    fingerprint: tuple[tuple[tuple[str, int], ...], str]
    order: KitchenOrder


class OrderManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._drafts: dict[str, list[OrderItem]] = defaultdict(list)
        self._draft_versions: dict[str, int] = defaultdict(int)
        self._orders: list[KitchenOrder] = []
        self._listeners: set[asyncio.Queue[dict]] = set()
        self._last_confirmed_by_session: dict[str, ConfirmationState] = {}

    def _normalize_summary(self, order_summary: str) -> str:
        summary = " ".join(order_summary.strip().lower().split())
        return summary or "pedido confirmado"

    def _normalize_order_id(self, order_id: str) -> str:
        return " ".join(order_id.strip().upper().split())

    def _fingerprint(
        self, items: list[OrderItem], order_summary: str
    ) -> tuple[tuple[tuple[str, int], ...], str]:
        normalized_items = tuple(
            sorted(
                (
                    (" ".join(item.item.strip().lower().split()) or "item", item.quantity)
                    for item in items
                ),
                key=lambda entry: (entry[0], entry[1]),
            )
        )
        return normalized_items, self._normalize_summary(order_summary)

    async def add_item(self, session_id: str, item: str, quantity: int) -> str:
        async with self._lock:
            self._drafts[session_id].append(OrderItem(item=item, quantity=quantity))
            self._draft_versions[session_id] += 1
        return f"Added {quantity} x {item} to the order."

    async def confirm_order(self, session_id: str, order_summary: str) -> KitchenOrder:
        async with self._lock:
            draft_items = list(self._drafts.get(session_id, []))
            draft_version = self._draft_versions.get(session_id, 0)
            if draft_items:
                fingerprint = self._fingerprint(draft_items, order_summary)
                last_confirmation = self._last_confirmed_by_session.get(session_id)
                if (
                    last_confirmation
                    and last_confirmation.draft_version == draft_version
                    and last_confirmation.fingerprint == fingerprint
                ):
                    self._drafts.pop(session_id, None)
                    return last_confirmation.order

                items = draft_items
                self._drafts.pop(session_id, None)
            else:
                last_confirmation = self._last_confirmed_by_session.get(session_id)
                if last_confirmation:
                    return last_confirmation.order

                items = [
                    OrderItem(
                        item=order_summary.strip() or "Pedido confirmado",
                        quantity=1,
                    )
                ]
                fingerprint = self._fingerprint(items, order_summary)

            order = KitchenOrder(
                id=f"ORD-{uuid4().hex[:8].upper()}",
                created_at=datetime.now().isoformat(),
                status="nuevo",
                summary=order_summary.strip() or "Pedido confirmado",
                items=items,
            )
            self._orders.insert(0, order)
            self._last_confirmed_by_session[session_id] = ConfirmationState(
                draft_version=draft_version,
                fingerprint=fingerprint,
                order=order,
            )
            listeners = list(self._listeners)

        await self._broadcast(
            listeners,
            {
                "type": "order_created",
                "order": order.to_dict(),
            },
        )
        return order

    async def list_orders(self) -> list[dict]:
        async with self._lock:
            return [order.to_dict() for order in self._orders]

    async def update_status(
        self, order_id: str, status: KitchenOrderStatus
    ) -> KitchenOrder | None:
        async with self._lock:
            normalized_order_id = self._normalize_order_id(order_id)
            order = next(
                (
                    order
                    for order in self._orders
                    if self._normalize_order_id(order.id) == normalized_order_id
                ),
                None,
            )
            if order is None:
                return None
            order.status = status
            listeners = list(self._listeners)

        await self._broadcast(
            listeners,
            {
                "type": "order_updated",
                "order": order.to_dict(),
            },
        )
        return order

    async def get_order(self, order_id: str) -> KitchenOrder | None:
        async with self._lock:
            normalized_order_id = self._normalize_order_id(order_id)
            return next(
                (
                    order
                    for order in self._orders
                    if self._normalize_order_id(order.id) == normalized_order_id
                ),
                None,
            )

    async def subscribe(self) -> tuple[asyncio.Queue[dict], list[dict]]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        async with self._lock:
            self._listeners.add(queue)
            snapshot = [order.to_dict() for order in self._orders]
        return queue, snapshot

    async def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        async with self._lock:
            self._listeners.discard(queue)

    async def _broadcast(self, listeners: list[asyncio.Queue[dict]], message: dict) -> None:
        for listener in listeners:
            with contextlib.suppress(asyncio.QueueFull):
                listener.put_nowait(message)
