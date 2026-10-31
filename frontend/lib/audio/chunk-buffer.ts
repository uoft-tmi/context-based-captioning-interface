export interface CapturedSegment {
  samples: Float32Array;
  capturedAtMs: number;
}

/** Preserve every sample while allowing a shorter first caption interval. */
export class AudioChunkBuffer {
  private queue: Float32Array[] = [];
  private count = 0;
  private startedAtMs: number | null = null;
  private target: number;
  private readonly steadyTarget: number;

  constructor(private readonly sampleRate: number, chunkMs: number, initialChunkMs = chunkMs) {
    if (![sampleRate, chunkMs, initialChunkMs].every((value) => Number.isFinite(value) && value > 0)) {
      throw new Error('Audio sample rate and chunk durations must be positive.');
    }
    this.steadyTarget = Math.max(1, Math.round(sampleRate * chunkMs / 1000));
    this.target = Math.max(1, Math.round(sampleRate * initialChunkMs / 1000));
  }

  push(samples: Float32Array, receivedAtMs: number): CapturedSegment[] {
    if (samples.length === 0) return [];
    // Approximate the first sample's capture time, rather than the send time.
    this.startedAtMs ??= receivedAtMs - samples.length / this.sampleRate * 1000;
    this.queue.push(samples);
    this.count += samples.length;
    const ready: CapturedSegment[] = [];
    while (this.count >= this.target) {
      ready.push(this.consume(this.target));
      this.target = this.steadyTarget;
    }
    return ready;
  }

  flush(): CapturedSegment | null {
    return this.count ? this.consume(this.count) : null;
  }

  private consume(count: number): CapturedSegment {
    const capturedAtMs = this.startedAtMs!;
    const samples = new Float32Array(count);
    let offset = 0;
    while (offset < count) {
      const head = this.queue[0];
      const take = Math.min(head.length, count - offset);
      samples.set(head.subarray(0, take), offset);
      offset += take;
      if (take === head.length) this.queue.shift();
      else this.queue[0] = head.subarray(take);
    }
    this.count -= count;
    this.startedAtMs = capturedAtMs + count / this.sampleRate * 1000;
    return { samples, capturedAtMs };
  }
}
