// Browser microphone -> Amazon Transcribe streaming (presigned WebSocket) -> transcript callbacks.
import { api } from "./api";
import { audioEvent, decodeMessage } from "./eventstream";

export type VoiceHandlers = {
  onPartial: (text: string) => void;
  onFinal: (text: string) => void;
  onLevel?: (level: number) => void;
  onError: (message: string) => void;
  onEnd: () => void;
};

const TARGET_RATE = 16000;

function downsample(input: Float32Array, rate: number): Int16Array {
  const ratio = rate / TARGET_RATE;
  const length = Math.floor(input.length / ratio);
  const out = new Int16Array(length);
  let pos = 0;
  for (let i = 0; i < length; i++) {
    const next = Math.floor((i + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (; pos < next && pos < input.length; pos++) {
      sum += input[pos];
      count++;
    }
    const s = Math.max(-1, Math.min(1, count ? sum / count : 0));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

export class VoiceSession {
  private ws?: WebSocket;
  private ctx?: AudioContext;
  private stream?: MediaStream;
  private node?: ScriptProcessorNode;
  private stopTimer?: number;
  private silenceSince = 0;
  private finals: string[] = [];
  private closed = false;

  constructor(private h: VoiceHandlers, private opts: { language?: string; autoStopMs?: number } = {}) {}

  async start() {
    const session = await api<{ url: string; max_seconds: number }>("/api/voice/session", { body: { language: this.opts.language || "en-IN" } });
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    this.ctx = new AudioContext();
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    this.ws = new WebSocket(session.url);
    this.ws.binaryType = "arraybuffer";
    this.ws.onmessage = (ev) => this.onMessage(new Uint8Array(ev.data as ArrayBuffer));
    this.ws.onerror = () => this.fail("Voice connection failed. You can keep typing.");
    this.ws.onclose = () => this.finish();
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("Voice service timed out")), 8000);
      this.ws!.onopen = () => {
        clearTimeout(t);
        resolve();
      };
    });
    const rate = this.ctx.sampleRate;
    this.node.onaudioprocess = (e) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      const data = e.inputBuffer.getChannelData(0);
      let peak = 0;
      for (let i = 0; i < data.length; i += 16) peak = Math.max(peak, Math.abs(data[i]));
      this.h.onLevel?.(peak);
      const now = performance.now();
      if (peak > 0.04) this.silenceSince = now;
      else if (this.finals.length && this.silenceSince && now - this.silenceSince > (this.opts.autoStopMs ?? 1800)) this.stop();
      const pcm = downsample(data, rate);
      this.ws.send(audioEvent(new Uint8Array(pcm.buffer)));
    };
    source.connect(this.node);
    this.node.connect(this.ctx.destination);
    this.silenceSince = performance.now();
    this.stopTimer = window.setTimeout(() => this.stop(), session.max_seconds * 1000);
  }

  private onMessage(buf: Uint8Array) {
    try {
      const msg = decodeMessage(buf);
      const body = JSON.parse(new TextDecoder().decode(msg.payload));
      if (msg.headers[":message-type"] !== "event") {
        this.fail(body.Message || "Transcription error");
        return;
      }
      for (const r of body.Transcript?.Results || []) {
        const text = r.Alternatives?.[0]?.Transcript || "";
        if (!text) continue;
        if (r.IsPartial) this.h.onPartial([...this.finals, text].join(" "));
        else {
          this.finals.push(text);
          this.h.onPartial(this.finals.join(" "));
        }
      }
    } catch {
      /* ignore malformed frames */
    }
  }

  stop() {
    if (this.closed) return;
    try {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(audioEvent(new Uint8Array(0))); // end-of-stream
    } catch {
      /* noop */
    }
    setTimeout(() => this.finish(), 700);
  }

  private fail(message: string) {
    if (this.closed) return;
    this.h.onError(message);
    this.finish(true);
  }

  private finish(errored = false) {
    if (this.closed) return;
    this.closed = true;
    clearTimeout(this.stopTimer);
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close().catch(() => {});
    try {
      this.ws?.close();
    } catch {
      /* noop */
    }
    const text = this.finals.join(" ").trim();
    if (!errored && text) this.h.onFinal(text);
    this.h.onEnd();
  }
}

let currentAudio: HTMLAudioElement | null = null;

export async function speak(text: string, onStart?: () => void, onEnd?: () => void) {
  stopSpeaking();
  const res = await api<{ audio_base64: string; content_type: string }>("/api/speak", { body: { text } });
  const audio = new Audio(`data:${res.content_type};base64,${res.audio_base64}`);
  currentAudio = audio;
  audio.onplay = () => onStart?.();
  audio.onended = () => onEnd?.();
  audio.onpause = () => onEnd?.();
  await audio.play().catch(() => onEnd?.());
}

export function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
}
