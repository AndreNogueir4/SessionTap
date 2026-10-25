// Batches capture events so the native port is not flooded.

import type { NativeBridge } from "./native";
import type { CaptureEvent } from "./types";

const FLUSH_MS = 1000;
const MAX_BATCH = 200;
const MAX_BATCH_CHARS = 4 * 1024 * 1024; // a full HTML page usually travels alone
const MAX_QUEUED = 2000; // drop oldest beyond this (daemon offline for a long time)

function size(event: CaptureEvent): number {
  if (event.type !== "exchange") return 1024;
  return 2048 + (event.request_body?.length ?? 0) + (event.response_body?.length ?? 0);
}

export class EventQueue {
  private events: CaptureEvent[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  sent = 0;

  constructor(private bridge: NativeBridge) {}

  push(event: CaptureEvent): void {
    this.events.push(event);
    if (this.events.length > MAX_QUEUED) this.events.splice(0, this.events.length - MAX_QUEUED);
    if (this.events.length >= MAX_BATCH) void this.flush();
    else this.timer ??= setTimeout(() => void this.flush(), FLUSH_MS);
  }

  private batchLength(): number {
    let chars = 0;
    for (let i = 0; i < Math.min(this.events.length, MAX_BATCH); i++) {
      chars += size(this.events[i]!);
      if (chars > MAX_BATCH_CHARS) return Math.max(1, i);
    }
    return Math.min(this.events.length, MAX_BATCH);
  }

  async flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    while (this.events.length) {
      const batch = this.events.splice(0, this.batchLength());
      const result = await this.bridge.ingest(batch);
      if (result === "retry") {
        // Keep them for the next attempt; the daemon may just be starting.
        this.events.unshift(...batch);
        this.timer = setTimeout(() => void this.flush(), 5000);
        return;
      }
      if (result === "ok") this.sent += batch.length;
      else console.warn("SessionTap: daemon rejected a batch of", batch.length, "events");
    }
  }
}
