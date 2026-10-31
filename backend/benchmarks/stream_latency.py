"""Concurrent WebSocket load test. Uses real authentication unless the test app overrides it."""
import argparse
import asyncio
import base64
import json
import math
import time
import wave
from uuid import uuid4
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import connect


def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("No latency samples collected")
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)]


def check_budget(report: dict, p95_ms: float) -> None:
    if report["failures"] or report["samples"] != report["expected_samples"]:
        raise AssertionError(f"Incomplete load run: {report}")
    if report["p95_ms"] > p95_ms:
        raise AssertionError(f"p95 {report['p95_ms']:.2f} ms exceeds {p95_ms:.2f} ms budget")


async def run_load(base_url: str, tokens: list[str], audio: bytes, *, chunks: int = 10,
                   interval_ms: float = 2500, timeout_seconds: float = 135) -> dict:
    if not tokens or chunks < 1 or interval_ms < 0:
        raise ValueError("Provide at least one session/chunk and a non-negative interval")
    barrier = asyncio.Barrier(len(tokens))
    encoded_audio = base64.b64encode(audio).decode()
    latencies: list[float] = []
    finalizations: list[float] = []
    errors: list[str] = []
    parsed = urlsplit(base_url.rstrip('/'))
    ws_base = urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, parsed.path, '', ''))

    async def worker(token: str):
        session_id = None
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as http:
                response = await http.post(f"{base_url}/api/sessions", headers=headers, json={"mode": "baseline", "name": f"Benchmark {uuid4().hex}"})
                if response.status_code != 200:
                    raise RuntimeError(f"Session creation returned HTTP {response.status_code}")
                session_id = response.json()["id"]
                from urllib.parse import urlencode
                url = f"{ws_base}/ws/sessions/{session_id}/stream?{urlencode({'access_token': token})}"
                async with connect(url, open_timeout=timeout_seconds, max_size=2**20) as ws:
                    async with asyncio.timeout(timeout_seconds):
                        ready = json.loads(await ws.recv())
                        if ready.get("type") != "ready":
                            raise RuntimeError("Stream did not acknowledge readiness")
                    await asyncio.wait_for(barrier.wait(), timeout_seconds)
                    sent_at: dict[int, float] = {}
                    stop_sent_at = 0.0

                    async def send_audio():
                        nonlocal stop_sent_at
                        origin = time.perf_counter()
                        for index in range(chunks):
                            await asyncio.sleep(max(0, origin + index * interval_ms / 1000 - time.perf_counter()))
                            sent_at[index] = time.perf_counter()
                            await ws.send(json.dumps({"type": "audio_chunk", "chunk_index": index, "audio_b64": encoded_audio, "mime": "audio/wav"}))
                        stop_sent_at = time.perf_counter()
                        await ws.send(json.dumps({"type": "stop"}))

                    async def receive_captions():
                        next_index = 0
                        while True:
                            message = json.loads(await ws.recv())
                            if message.get("type") == "caption":
                                index = message["chunk_index"]
                                if index != next_index or index not in sent_at:
                                    raise RuntimeError("Missing, duplicate or out-of-order chunk acknowledgement")
                                latencies.append((time.perf_counter() - sent_at[index]) * 1000)
                                next_index += 1
                            elif message.get("type") == "final":
                                if next_index != chunks or not message.get("transcript_saved"):
                                    raise RuntimeError("Incomplete or unsaved transcript")
                                finalizations.append((time.perf_counter() - stop_sent_at) * 1000)
                                return
                            else:
                                raise RuntimeError(f"Unexpected stream message: {message.get('type')}")

                    async with asyncio.timeout(timeout_seconds + chunks * interval_ms / 1000):
                        async with asyncio.TaskGroup() as group:
                            group.create_task(send_audio())
                            group.create_task(receive_captions())
        except Exception as exc:
            # Never include socket URLs or credentials in reports.
            errors.append(type(exc).__name__)
            await barrier.abort()
        finally:
            if session_id:
                try:
                    async with httpx.AsyncClient(timeout=10) as http:
                        await http.post(f"{base_url}/api/sessions/{session_id}/end", headers=headers)
                except Exception:
                    pass

    started = time.perf_counter()
    await asyncio.gather(*(worker(token) for token in tokens))
    return {
        "sessions": len(tokens), "chunks_per_session": chunks, "interval_ms": interval_ms,
        "samples": len(latencies), "expected_samples": len(tokens) * chunks,
        "failures": len(errors), "error_types": errors,
        "p50_ms": round(percentile(latencies, 0.5), 2) if latencies else None,
        "p95_ms": round(percentile(latencies, 0.95), 2) if latencies else None,
        "p99_ms": round(percentile(latencies, 0.99), 2) if latencies else None,
        "max_ms": round(max(latencies), 2) if latencies else None,
        "finalization_p95_ms": round(percentile(finalizations, 0.95), 2) if finalizations else None,
        "duration_seconds": round(time.perf_counter() - started, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--tokens-file', type=Path, required=True, help='JSON array of access tokens, one per distinct test user')
    parser.add_argument('--audio', type=Path, required=True, help='16 kHz mono PCM16 WAV chunk')
    parser.add_argument('--sessions', type=int, default=20)
    parser.add_argument('--chunks', type=int, default=10)
    parser.add_argument('--interval-ms', type=float, default=2500)
    parser.add_argument('--p95-ms', type=float, required=True)
    parser.add_argument('--output', type=Path, help='Optional JSON report path')
    args = parser.parse_args()
    tokens = json.loads(args.tokens_file.read_text())
    if not isinstance(tokens, list) or args.sessions < 1 or len(tokens) < args.sessions or any(not isinstance(token, str) or not token for token in tokens):
        parser.error('tokens-file must contain at least --sessions nonempty access tokens')
    if args.p95_ms <= 0:
        parser.error('--p95-ms must be positive')
    with wave.open(str(args.audio)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            parser.error('audio must be 16 kHz, mono, PCM16 WAV')
    report = asyncio.run(run_load(args.base_url.rstrip('/'), tokens[:args.sessions], args.audio.read_bytes(), chunks=args.chunks, interval_ms=args.interval_ms))
    report['p95_budget_ms'] = args.p95_ms
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        check_budget(report, args.p95_ms)
    except AssertionError as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
