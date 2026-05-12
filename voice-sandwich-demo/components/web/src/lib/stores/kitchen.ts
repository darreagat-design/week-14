import { writable } from "svelte/store";
import type { KitchenOrder, KitchenOrderStatus } from "../types";

export interface KitchenState {
  connected: boolean;
  status: "connecting" | "live" | "error" | "disconnected";
  orders: KitchenOrder[];
}

function sortOrders(orders: KitchenOrder[]): KitchenOrder[] {
  return [...orders].sort(
    (a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  );
}

function createKitchenStore() {
  const { subscribe, set, update } = writable<KitchenState>({
    connected: false,
    status: "connecting",
    orders: [],
  });

  return {
    subscribe,
    setConnecting() {
      update((state) => ({ ...state, connected: false, status: "connecting" }));
    },
    setError() {
      update((state) => ({ ...state, connected: false, status: "error" }));
    },
    disconnect() {
      update((state) => ({ ...state, connected: false, status: "disconnected" }));
    },
    setSnapshot(orders: KitchenOrder[]) {
      set({
        connected: true,
        status: "live",
        orders: sortOrders(orders),
      });
    },
    upsertOrder(order: KitchenOrder) {
      update((state) => {
        const existing = state.orders.findIndex((entry) => entry.id === order.id);
        const orders = [...state.orders];
        if (existing === -1) {
          orders.unshift(order);
        } else {
          orders[existing] = order;
        }
        return {
          connected: true,
          status: "live",
          orders: sortOrders(orders),
        };
      });
    },
    reset() {
      set({
        connected: false,
        status: "connecting",
        orders: [],
      });
    },
  };
}

export const kitchen = createKitchenStore();

export const kitchenStatusLabels: Record<KitchenOrderStatus, string> = {
  nuevo: "Nuevo",
  en_preparacion: "En preparación",
  listo: "Listo",
};
