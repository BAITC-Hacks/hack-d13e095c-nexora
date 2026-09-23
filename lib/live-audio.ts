import { ApiError, conferenceApi, type RoomSession } from "./conference-api";

type PendingAudio = {
  id: string;
  roomId: string;
  owner: string;
  start: number;
  version: number;
  blob: Blob;
};
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open("protocol-live-audio", 1);
    r.onupgradeneeded = () =>
      r.result.createObjectStore("pending", { keyPath: "id" });
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function storage(
  action: "put" | "delete" | "getAll",
  value?: PendingAudio | string,
): Promise<PendingAudio[]> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(
      "pending",
      action === "getAll" ? "readonly" : "readwrite",
    );
    const s = tx.objectStore("pending");
    const r =
      action === "getAll"
        ? s.getAll()
        : action === "put"
          ? s.put(value)
          : s.delete(value as string);
    tx.oncomplete = () => {
      db.close();
      resolve(action === "getAll" ? (r.result as PendingAudio[]) : []);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}
export class AudioUploadQueue {
  private items: PendingAudio[] = [];
  private running = false;
  private closed = false;
  private retry: ReturnType<typeof setTimeout> | undefined;
  constructor(
    private session: RoomSession,
    private changed: (count: number, error?: string) => void,
  ) {}
  async restore() {
    const restored = (await storage("getAll")).filter(
      (x) => x.roomId === this.session.id && x.owner === this.session.token,
    );
    this.items = [
      ...new Map([...restored, ...this.items].map((x) => [x.id, x])).values(),
    ].sort((a, b) => a.start - b.start);
    this.changed(this.items.length);
    void this.pump();
  }
  async add(blob: Blob, start: number, version: number) {
    const item = {
      id: crypto.randomUUID(),
      roomId: this.session.id,
      owner: this.session.token,
      start,
      version,
      blob,
    };
    await storage("put", item);
    this.items.push(item);
    this.changed(this.items.length);
    void this.pump();
  }
  private async pump() {
    if (this.running || this.closed) return;
    this.running = true;
    try {
      while (this.items.length && !this.closed) {
        const item = this.items[0];
        await conferenceApi(
          `/${this.session.id}/audio?sequence=${item.id}&start=${item.start.toFixed(3)}&version=${item.version}`,
          this.session.token,
          {
            method: "POST",
            headers: { "Content-Type": "audio/wav" },
            body: item.blob,
          },
        );
        await storage("delete", item.id);
        this.items.shift();
        this.changed(this.items.length);
      }
    } catch (error) {
      this.changed(
        this.items.length,
        error instanceof ApiError
          ? error.message
          : "Не удалось отправить аудио. Фрагменты сохранены на устройстве; повторим отправку.",
      );
      if (!this.closed) this.retry = setTimeout(() => void this.pump(), 5000);
    } finally {
      this.running = false;
    }
  }
  close() {
    this.closed = true;
    clearTimeout(this.retry);
  }
}
export function encodeWave(samples: Float32Array, rate: number): Blob {
  const ratio = rate / 16000,
    count = Math.floor(samples.length / ratio),
    data = new ArrayBuffer(44 + count * 2),
    view = new DataView(data);
  const text = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++)
      view.setUint8(offset + i, s.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + count * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) {
    const from = Math.floor(i * ratio),
      to = Math.max(from + 1, Math.floor((i + 1) * ratio));
    let value = 0;
    for (let j = from; j < to && j < samples.length; j++) value += samples[j];
    value = Math.max(-1, Math.min(1, value / (to - from)));
    view.setInt16(44 + i * 2, value < 0 ? value * 32768 : value * 32767, true);
  }
  return new Blob([data], { type: "audio/wav" });
}
export class LiveCapture {
  private node: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private elapsed = 0;
  private flushDone: (() => void) | null = null;
  private stopped = false;
  private stopping: Promise<void> | null = null;
  private writes = Promise.resolve();
  constructor(
    private context: AudioContext,
    private stream: MediaStream,
    private start: number,
    private version: number,
    private queue: AudioUploadQueue,
    private error: (s: string) => void,
  ) {}
  async begin() {
    await this.context.audioWorklet.addModule("/conference-recorder.js");
    if (this.stopped) return;
    if (this.context.state !== "running") await this.context.resume();
    this.node = new AudioWorkletNode(this.context, "conference-recorder");
    this.source = this.context.createMediaStreamSource(this.stream);
    this.node.port.onmessage = ({ data }) => {
      if (data.flushed) {
        this.flushDone?.();
        return;
      }
      const samples = data.samples as Float32Array,
        offset = this.start + this.elapsed;
      this.elapsed += samples.length / this.context.sampleRate;
      const power = samples.reduce((sum, v) => sum + v * v, 0) / samples.length;
      // Suppress only near-digital silence; VAD remains the ASR model's responsibility.
      if (power < 0.0000001) return;
      const blob = encodeWave(samples, this.context.sampleRate);
      this.writes = this.writes
        .then(() => this.queue.add(blob, offset, this.version))
        .catch(() =>
          this.error(
            "Не удалось сохранить аудиофрагмент. Освободите место и проверьте доступ к хранилищу браузера.",
          ),
        );
    };
    this.source.connect(this.node);
    this.node.connect(this.context.destination);
  }
  stop(): Promise<void> {
    return (this.stopping ??= this.flush());
  }
  private async flush() {
    this.stopped = true;
    if (!this.node) return;
    this.source?.disconnect();
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, 1000);
      this.flushDone = () => {
        clearTimeout(timer);
        resolve();
      };
      this.node!.port.postMessage("flush");
    });
    this.node.disconnect();
    await this.writes;
    this.node.port.close();
    this.node = null;
  }
}
