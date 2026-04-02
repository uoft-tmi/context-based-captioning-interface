class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channels = input.map((channelData) => {
      const copied = new Float32Array(channelData.length);
      copied.set(channelData);
      return copied;
    });

    this.port.postMessage(
      channels,
      channels.map((channel) => channel.buffer),
    );
    return true;
  }
}

registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
