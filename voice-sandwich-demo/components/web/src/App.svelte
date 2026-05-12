<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { Header, Controls, PipelineCard, ActivityFeed, Console } from './lib/components';
  import KitchenBoard from './lib/components/KitchenBoard.svelte';
  import { createVoiceSession } from './lib/websocket';
  import { createKitchenSession } from './lib/kitchen';

  const voiceSession = createVoiceSession();
  const kitchenSession = createKitchenSession();
  const isKitchenRoute = window.location.pathname === '/kitchen';

  onMount(() => {
    if (isKitchenRoute) {
      kitchenSession.connect();
    }
  });

  onDestroy(() => {
    if (isKitchenRoute) {
      kitchenSession.disconnect();
    }
  });
</script>

{#if isKitchenRoute}
  <KitchenBoard onUpdateStatus={(orderId, status) => kitchenSession.updateStatus(orderId, status)} />
{:else}
  <div class="max-w-3xl mx-auto">
    <Header />
    <Controls onStart={() => voiceSession.start()} onStop={() => voiceSession.stop()} />
    <PipelineCard />
    <ActivityFeed />
    <Console />
  </div>
{/if}

