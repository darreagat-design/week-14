// AudioWorklet code for PCM capture
const workletCode = `
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.targetSampleRate = 16000;
    this.resampleRatio = sampleRate / this.targetSampleRate;
    this.resampleIndex = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0];

    for (let i = 0; i < channelData.length; i++) {
      this.resampleIndex += 1;
      if (this.resampleIndex >= this.resampleRatio) {
        this.resampleIndex -= this.resampleRatio;
        let sample = channelData[i];
        sample = Math.max(-1, Math.min(1, sample));
        const int16 = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        this.buffer.push(int16);
      }
    }

    const CHUNK_SIZE = 1600;
    while (this.buffer.length >= CHUNK_SIZE) {
      const chunk = this.buffer.splice(0, CHUNK_SIZE);
      const int16Array = new Int16Array(chunk);
      this.port.postMessage(int16Array.buffer, [int16Array.buffer]);
    }

    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
`;

export interface AudioCapture {
  start: (
    onChunk: (chunk: ArrayBuffer) => void
  ) => Promise<{ inputSampleRate: number; targetSampleRate: number }>;
  stop: () => void;
}

export function createAudioCapture(): AudioCapture {
  let audioContext: AudioContext | null = null;
  let workletNode: AudioWorkletNode | null = null;
  let mediaStream: MediaStream | null = null;
  let sourceNode: MediaStreamAudioSourceNode | null = null;
  let silentGainNode: GainNode | null = null;

  async function start(
    onChunk: (chunk: ArrayBuffer) => void
  ): Promise<{ inputSampleRate: number; targetSampleRate: number }> {
    // Create AudioContext if needed
    if (!audioContext) {
      audioContext = new AudioContext();
      const blob = new Blob([workletCode], { type: "application/javascript" });
      const workletUrl = URL.createObjectURL(blob);
      await audioContext.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);
    }

    // Resume if suspended
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }

    // Get microphone access
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // Create worklet node and connect
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioContext, "pcm-processor");
    silentGainNode = audioContext.createGain();
    silentGainNode.gain.value = 0;

    workletNode.port.onmessage = (event) => {
      onChunk(event.data);
    };

    // Keep the graph connected to a live output so the worklet continues
    // processing microphone frames across browsers, without audible playback.
    sourceNode.connect(workletNode);
    workletNode.connect(silentGainNode);
    silentGainNode.connect(audioContext.destination);

    return {
      inputSampleRate: audioContext.sampleRate,
      targetSampleRate: 16000,
    };
  }

  function stop(): void {
    if (workletNode) {
      workletNode.disconnect();
      workletNode = null;
    }

    if (sourceNode) {
      sourceNode.disconnect();
      sourceNode = null;
    }

    if (silentGainNode) {
      silentGainNode.disconnect();
      silentGainNode = null;
    }

    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }
  }

  return { start, stop };
}
