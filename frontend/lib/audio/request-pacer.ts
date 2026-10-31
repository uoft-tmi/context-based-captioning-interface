/** Keep delayed audio from bursting requests after a provider recovers. */
export class AudioRequestPacer {
  private nextAllowedAt = 0;

  constructor(
    private readonly intervalMs: number,
    private readonly now: () => number = () => performance.now(),
    private readonly sleep: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  ) {
    if (!Number.isFinite(intervalMs) || intervalMs < 0) throw new Error('Request interval must be non-negative.');
  }

  async wait(): Promise<void> {
    while (this.nextAllowedAt > this.now()) {
      await this.sleep(this.nextAllowedAt - this.now());
    }
  }

  markSent(): void {
    this.nextAllowedAt = this.now() + this.intervalMs;
  }
}
