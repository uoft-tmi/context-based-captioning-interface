export type StreamChunk = {
  chunk_index: number;
  capturedAtMs?: number;
} & ({ audio: Blob } | { audio_b64: string; mime: 'audio/wav' });
export interface StreamCallbacks {
  onReady?: (recordingLimitSeconds: number) => void;
  onCaption: (text: string, index: number, latencyMs: number) => void;
  onFinal: (text: string) => void;
  onWarning: (text: string) => void;
  onError: (error: Error) => void;
}
interface PendingChunk {
  started: number;
  resolve: () => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/** One ordered audio stream. Ready and final messages are explicit server acknowledgements. */
export class CaptionStream {
  private socket: WebSocket | null = null;
  private ready = false;
  private closed = false;
  private completed = false;
  private finalText = '';
  private pending = new Map<number, PendingChunk>();
  private nextChunkIndex = 0;
  private readyResolve?: () => void;
  private readyReject?: (error: Error) => void;
  private finalResolve?: (text: string) => void;
  private finalReject?: (error: Error) => void;
  private readyTimer?: ReturnType<typeof setTimeout>;
  private finalTimer?: ReturnType<typeof setTimeout>;
  private finishing?: Promise<string>;

  constructor(
    private callbacks: StreamCallbacks,
    private socketFactory: (url: string) => WebSocket = (url) => new WebSocket(url),
    private timeoutMs = 135_000,
    private chunkTimeoutMs = 30_000,
  ) {}

  get isActive(): boolean {
    return this.ready && !this.closed && !this.completed && !this.finishing;
  }

  connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.readyResolve = resolve;
      this.readyReject = reject;
      this.readyTimer = setTimeout(() => this.fail(new Error('Captioning service took too long to become ready.')), this.timeoutMs);
      try {
        const ws = this.socketFactory(url);
        this.socket = ws;
        ws.onmessage = (event) => this.receive(event.data);
        ws.onerror = () => this.fail(new Error('Unable to connect to the captioning service.'));
        ws.onclose = () => {
          if (!this.closed && !this.completed) this.fail(new Error('Captioning connection closed before the transcript was saved.'));
        };
      } catch {
        this.fail(new Error('Unable to open the captioning connection.'));
      }
    });
  }

  private receive(raw: unknown) {
    if (this.closed) return;
    let message;
    try {
      message = JSON.parse(String(raw));
      if (!message || typeof message !== 'object' || typeof message.type !== 'string') throw new Error('Invalid message');
    } catch {
      this.fail(new Error('Invalid response from the captioning service.'));
      return;
    }
    switch (message.type) {
      case 'ready':
        if (Number.isInteger(message.recording_limit_seconds) && message.recording_limit_seconds > 0) this.callbacks.onReady?.(message.recording_limit_seconds);
        this.ready = true;
        clearTimeout(this.readyTimer);
        this.readyResolve?.();
        break;
      case 'caption': {
        const pending = this.pending.get(message.chunk_index);
        if (!pending || typeof message.text !== 'string') {
          this.fail(new Error('Received an unexpected audio chunk response.'));
          return;
        }
        this.callbacks.onCaption(message.text, message.chunk_index, performance.now() - pending.started);
        this.acknowledge(message.chunk_index);
        break;
      }
      case 'warning':
        this.callbacks.onWarning(message.text);
        this.acknowledge(message.chunk_index);
        break;
      case 'final':
        if (message.transcript_saved !== true || typeof message.text !== 'string') {
          this.fail(new Error('The final transcript could not be saved.'));
          return;
        }
        this.completed = true;
        this.finalText = message.text;
        clearTimeout(this.readyTimer);
        clearTimeout(this.finalTimer);
        this.callbacks.onFinal(message.text);
        this.finalResolve?.(message.text);
        // Duration limits may finalize while an audio chunk is being sent.
        for (const index of this.pending.keys()) this.acknowledge(index);
        break;
      case 'error':
        this.fail(new Error(message.text || 'Captioning failed.'));
        break;
      default:
        this.fail(new Error('Unknown response from the captioning service.'));
    }
  }

  private acknowledge(index: number) {
    const pending = this.pending.get(index);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(index);
    pending.resolve();
  }

  sendChunk(chunk: StreamChunk): Promise<void> {
    if (!this.ready || this.closed || this.completed || this.finishing || this.socket?.readyState !== 1) {
      return Promise.reject(new Error('Captioning stream is not accepting audio.'));
    }
    // Binary frames rely on WebSocket ordering, so never allow skipped/duplicate sends.
    if (chunk.chunk_index !== this.nextChunkIndex) {
      return Promise.reject(new Error(`Expected audio chunk ${this.nextChunkIndex}.`));
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => this.fail(new Error('Timed out waiting for an audio chunk transcript.')), this.chunkTimeoutMs);
      this.pending.set(chunk.chunk_index, { started: chunk.capturedAtMs ?? performance.now(), resolve, reject, timer });
      try {
        if ('audio' in chunk) this.socket!.send(chunk.audio);
        else this.socket!.send(JSON.stringify({ type: 'audio_chunk', chunk_index: chunk.chunk_index, audio_b64: chunk.audio_b64, mime: chunk.mime }));
        this.nextChunkIndex += 1;
      }
      catch { this.fail(new Error('Unable to send audio.')); }
    });
  }

  finish(): Promise<string> {
    if (this.completed) return Promise.resolve(this.finalText);
    if (this.finishing) return this.finishing;
    if (!this.ready || this.closed || this.socket?.readyState !== 1) return Promise.reject(new Error('Captioning stream is not connected.'));
    this.finishing = new Promise((resolve, reject) => {
      this.finalResolve = resolve;
      this.finalReject = reject;
      this.finalTimer = setTimeout(() => this.fail(new Error('Timed out saving the final transcript.')), this.timeoutMs);
      try { this.socket!.send(JSON.stringify({ type: 'stop' })); }
      catch { this.fail(new Error('Unable to stop the captioning stream.')); }
    });
    return this.finishing;
  }

  private fail(error: Error) {
    if (this.closed || this.completed) return;
    this.close(error);
    this.callbacks.onError(error);
  }

  close(error = new Error('Captioning stream was closed.')) {
    this.closed = true;
    clearTimeout(this.readyTimer);
    clearTimeout(this.finalTimer);
    this.readyReject?.(error);
    this.finalReject?.(error);
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
    this.socket?.close();
  }
}
