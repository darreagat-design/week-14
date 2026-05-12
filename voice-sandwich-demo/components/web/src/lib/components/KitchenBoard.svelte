<script lang="ts">
  import { kitchen, kitchenStatusLabels } from "../stores";
  import { formatTime } from "../utils";
  import type { KitchenOrderStatus } from "../types";

  interface Props {
    onUpdateStatus: (orderId: string, status: KitchenOrderStatus) => void;
  }

  let { onUpdateStatus }: Props = $props();

  const statusTone: Record<KitchenOrderStatus, string> = {
    nuevo: "bg-amber-100 text-amber-800 border-amber-200",
    en_preparacion: "bg-sky-100 text-sky-800 border-sky-200",
    listo: "bg-emerald-100 text-emerald-800 border-emerald-200",
  };

  const statusButtons: KitchenOrderStatus[] = [
    "nuevo",
    "en_preparacion",
    "listo",
  ];
</script>

<div class="min-h-screen bg-[radial-gradient(circle_at_top,_#fff7ed,_#f8fafc_45%,_#e2e8f0)] text-slate-900">
  <div class="max-w-6xl mx-auto px-6 py-8">
    <div class="flex flex-col gap-5 md:flex-row md:items-end md:justify-between mb-8">
      <div>
        <div class="text-xs font-semibold uppercase tracking-[0.35em] text-orange-500 mb-3">
          Kitchen Display
        </div>
        <h1 class="text-4xl font-semibold tracking-tight">Pedidos en tiempo real</h1>
        <p class="mt-3 text-sm text-slate-600 max-w-2xl">
          Cada pedido confirmado desde la experiencia de voz aparece aquí al instante y puede avanzar por cocina sin recargar la página.
        </p>
      </div>

      <div class="rounded-2xl border border-white/70 bg-white/75 backdrop-blur px-4 py-3 shadow-sm">
        <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-1">Estado</div>
        <div class="flex items-center gap-3">
          <span
            class={`h-2.5 w-2.5 rounded-full ${
              $kitchen.connected
                ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.55)]"
                : $kitchen.status === "error"
                  ? "bg-rose-500"
                  : "bg-slate-400"
            }`}
          ></span>
          <span class="text-sm font-medium text-slate-700">
            {$kitchen.status === "live"
              ? "Conectado"
              : $kitchen.status === "connecting"
                ? "Conectando..."
                : $kitchen.status === "error"
                  ? "Error de conexión"
                  : "Desconectado"}
          </span>
        </div>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-3 mb-8">
      <div class="rounded-2xl bg-white/80 border border-white/70 shadow-sm p-5">
        <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-2">Nuevos</div>
        <div class="text-3xl font-semibold">{$kitchen.orders.filter((order) => order.status === "nuevo").length}</div>
      </div>
      <div class="rounded-2xl bg-white/80 border border-white/70 shadow-sm p-5">
        <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-2">Preparando</div>
        <div class="text-3xl font-semibold">{$kitchen.orders.filter((order) => order.status === "en_preparacion").length}</div>
      </div>
      <div class="rounded-2xl bg-white/80 border border-white/70 shadow-sm p-5">
        <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-2">Listos</div>
        <div class="text-3xl font-semibold">{$kitchen.orders.filter((order) => order.status === "listo").length}</div>
      </div>
    </div>

    {#if $kitchen.orders.length === 0}
      <div class="rounded-[28px] border border-dashed border-slate-300 bg-white/70 px-8 py-16 text-center shadow-sm">
        <div class="text-sm uppercase tracking-[0.3em] text-slate-400 mb-3">Esperando pedidos</div>
        <p class="text-slate-600 max-w-xl mx-auto">
          Confirma un pedido desde la interfaz principal y aparecerá automáticamente aquí.
        </p>
      </div>
    {:else}
      <div class="grid gap-5 lg:grid-cols-2">
        {#each $kitchen.orders as order (order.id)}
          <article class="rounded-[28px] border border-white/80 bg-white/85 p-6 shadow-[0_18px_45px_rgba(15,23,42,0.08)] backdrop-blur">
            <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <div class="text-xs uppercase tracking-[0.3em] text-slate-400 mb-2">
                  {order.id}
                </div>
                <h2 class="text-2xl font-semibold tracking-tight text-slate-900">
                  {order.summary}
                </h2>
                <div class="mt-2 text-sm text-slate-500">
                  {formatTime(new Date(order.createdAt))}
                </div>
              </div>

              <span class={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] ${statusTone[order.status]}`}>
                {kitchenStatusLabels[order.status]}
              </span>
            </div>

            <div class="mt-6">
              <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-3">Items</div>
              <ul class="space-y-2">
                {#each order.items as item}
                  <li class="flex items-center justify-between rounded-2xl bg-slate-100/80 px-4 py-3">
                    <span class="font-medium text-slate-700">{item.item}</span>
                    <span class="text-sm text-slate-500">{item.quantity}x</span>
                  </li>
                {/each}
              </ul>
            </div>

            <div class="mt-6">
              <div class="text-xs uppercase tracking-[0.25em] text-slate-400 mb-3">Actualizar estado</div>
              <div class="flex flex-wrap gap-2">
                {#each statusButtons as status}
                  <button
                    onclick={() => onUpdateStatus(order.id, status)}
                    class={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                      order.status === status
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {kitchenStatusLabels[status]}
                  </button>
                {/each}
              </div>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>
</div>
