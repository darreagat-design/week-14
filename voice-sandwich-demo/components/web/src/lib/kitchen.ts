import { kitchen } from "./stores";
import type { KitchenOrderStatus, KitchenServerMessage } from "./types";

export interface KitchenSession {
  connect: () => void;
  disconnect: () => void;
  updateStatus: (orderId: string, status: KitchenOrderStatus) => void;
}

export function createKitchenSession(): KitchenSession {
  let ws: WebSocket | null = null;

  function handleMessage(message: KitchenServerMessage): void {
    if (message.type === "snapshot") {
      kitchen.setSnapshot(message.orders);
      return;
    }
    kitchen.upsertOrder(message.order);
  }

  function connect(): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return;
    }

    kitchen.setConnecting();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/kitchen/ws`);

    ws.onmessage = (event) => {
      const payload: KitchenServerMessage = JSON.parse(event.data);
      handleMessage(payload);
    };

    ws.onerror = () => {
      kitchen.setError();
    };

    ws.onclose = () => {
      kitchen.disconnect();
      ws = null;
    };
  }

  function updateStatus(orderId: string, status: KitchenOrderStatus): void {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    ws.send(
      JSON.stringify({
        type: "update_status",
        orderId,
        status,
      })
    );
  }

  function disconnect(): void {
    if (ws) {
      ws.close();
      ws = null;
    }
  }

  return {
    connect,
    disconnect,
    updateStatus,
  };
}
