#!/usr/bin/env python3
"""A Wyoming TTS server for k2-fsa/OmniVoice."""

import argparse
import asyncio
import json
import logging
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncTcpServer
from wyoming.tts import Synthesize, SynthesizeChunk, SynthesizeStart, SynthesizeStop, SynthesizeStopped

VERSION = "1.0.0"
LOG = logging.getLogger("wyoming_omnivoice")
MAX_TEXT = 10000
MAX_FRAME = 65536
MAX_CONNECTIONS = 16
READ_TIMEOUT = 300


def pop_piece(text, target, final=False):
    """Return a bounded piece and remainder, retaining incomplete streamed words."""
    text = re.sub(r"\s+", " ", text).lstrip()
    if not text:
        return "", ""
    sentence = re.search(r'[.!?](?:["\')\]]*)(?=\s|$)', text[:target + 1])
    if sentence:
        cut = sentence.end()
    elif len(text) <= target:
        return (text.strip(), "") if final else ("", text)
    else:
        prefix = text[:target + 1]
        cut = max(prefix.rfind(", "), prefix.rfind("; "), prefix.rfind(": "))
        cut = cut + 1 if cut >= target // 2 else prefix.rfind(" ")
        if cut <= 0:
            # Unbroken tokens must not bypass the inference size limit.
            cut = target
    return text[:cut].strip(), text[cut:].lstrip()


class Engine:
    def __init__(self, args):
        # Keep discovery tests and health probes independent of the ML runtime.
        import numpy as np
        import torch
        from omnivoice.models.omnivoice import OmniVoice

        self.np, self.args = np, args
        LOG.info("Loading model %s on %s", args.model, args.device)
        self.model = OmniVoice.from_pretrained(
            args.model, device_map=args.device,
            dtype=torch.float16 if args.device == "cuda" else torch.float32,
        )
        self.rate = self.model.sampling_rate
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnivoice")
        self.lock = asyncio.Lock()
        LOG.info("Model ready: %d Hz", self.rate)

    def generate(self, text):
        a = self.args
        audio = self.model.generate(
            text=text, language=a.language, ref_audio=a.voice_ref or None,
            ref_text=a.ref_text or None, instruct=a.instruct or None,
            duration=None, num_step=a.num_step, guidance_scale=a.guidance_scale,
            speed=a.speed, t_shift=a.t_shift, denoise=True, postprocess_output=True,
            layer_penalty_factor=5.0, position_temperature=5.0, class_temperature=0.0,
        )[0]
        audio = self.np.clip(self.np.asarray(audio).squeeze(), -1.0, 1.0)
        return (audio * 32767.0).astype("<i2").tobytes()

    async def synthesize(self, text):
        async with self.lock:
            job = asyncio.get_running_loop().run_in_executor(self.executor, self.generate, text)
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                # Cancelling an asyncio task cannot stop a running CUDA operation.
                # Keep the lock until inference actually finishes.
                try:
                    await asyncio.shield(job)
                finally:
                    raise

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


async def read_event(reader):
    """Read Wyoming JSON/data frames with bounds before allocating their bodies."""
    line = await reader.readline()
    if not line:
        return None
    if len(line) > MAX_FRAME:
        raise ValueError("Header too large")
    header = json.loads(line)
    if not isinstance(header, dict) or not isinstance(header.get("type"), str):
        raise ValueError("Invalid event header")
    length = header.get("data_length", 0)
    payload = header.get("payload_length", 0)
    if type(length) is not int or not 0 <= length <= MAX_FRAME or payload != 0:
        raise ValueError("Unsupported frame size or payload")
    data = header.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Invalid event data")
    if length:
        extra = json.loads(await reader.readexactly(length))
        if not isinstance(extra, dict):
            raise ValueError("Invalid event data")
        data.update(extra)
    return Event(type=header["type"], data=data)


class Handler(AsyncEventHandler):
    def __init__(self, reader, writer, engine, args):
        super().__init__(reader, writer)
        self.engine, self.args = engine, args
        self.reset()

    def reset(self):
        self.streaming = False
        self.buffer = ""
        self.count = 0
        self.pieces = 0
        self.audio_started = False

    async def run(self):
        try:
            while True:
                event = await asyncio.wait_for(read_event(self.reader), READ_TIMEOUT)
                if event is None or not await self.handle_event(event):
                    break
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass
        except Exception as err:
            # Neither generated text, reference transcripts nor library exception
            # messages (which may contain input) belong in routine logs.
            LOG.warning("Request failed: %s", type(err).__name__)
            try:
                await self.write_event(Event(type="error", data={
                    "code": "synthesis-failed", "text": "Invalid request or synthesis failed",
                }))
            except ConnectionError:
                pass
        finally:
            self.reset()
            self.writer.close()

    def check_text(self, text):
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        self.count += len(text)
        if self.count > MAX_TEXT:
            raise ValueError("Request text too long")

    async def send_pcm(self, pcm):
        for offset in range(0, len(pcm), 8192):
            await self.write_event(AudioChunk(
                rate=self.engine.rate, width=2, channels=1, audio=pcm[offset:offset + 8192],
            ).event())

    async def piece(self, text):
        if not self.audio_started:
            await self.write_event(AudioStart(rate=self.engine.rate, width=2, channels=1).event())
            self.audio_started = True
        if self.pieces:
            await self.send_pcm(bytes(int(self.engine.rate * self.args.silence) * 2))
        pcm = await self.engine.synthesize(text)
        await self.send_pcm(pcm)
        self.pieces += 1

    async def flush(self, final=False):
        while self.buffer:
            target = (self.args.first_stream_chars if self.pieces == 0 else self.args.stream_chars) if self.streaming else self.args.full_text_chars
            piece, self.buffer = pop_piece(self.buffer, target, final)
            if not piece:
                break
            await self.piece(piece)

    async def finish(self):
        if not self.audio_started:
            await self.write_event(AudioStart(rate=self.engine.rate, width=2, channels=1).event())
        await self.write_event(AudioStop().event())
        if self.streaming:
            await self.write_event(SynthesizeStopped().event())
        self.reset()

    async def handle_event(self, event):
        if Describe.is_type(event.type):
            attribution = Attribution(name="k2-fsa OmniVoice", url="https://github.com/k2-fsa/OmniVoice")
            await self.write_event(Info(tts=[TtsProgram(
                name="omnivoice", description="OmniVoice TTS", version=VERSION,
                attribution=attribution, installed=True, supports_synthesize_streaming=True,
                voices=[TtsVoice(name="omnivoice", description="Configured OmniVoice voice",
                    version=VERSION, attribution=attribution, installed=True,
                    languages=[self.args.language_code])],
            )]).event())
        elif SynthesizeStart.is_type(event.type):
            if self.streaming:
                raise ValueError("Stream already started")
            SynthesizeStart.from_event(event)
            self.reset()
            self.streaming = True
        elif SynthesizeChunk.is_type(event.type):
            if not self.streaming:
                raise ValueError("Stream not started")
            text = SynthesizeChunk.from_event(event).text
            self.check_text(text)
            self.buffer += text
            await self.flush()
        elif SynthesizeStop.is_type(event.type):
            if not self.streaming:
                raise ValueError("Stream not started")
            await self.flush(final=True)
            await self.finish()
        elif Synthesize.is_type(event.type):
            text = Synthesize.from_event(event).text
            if self.streaming:
                # Wyoming clients also send the complete text for compatibility.
                if not isinstance(text, str) or len(text) > MAX_TEXT:
                    raise ValueError("Invalid compatibility text")
                return True
            self.reset()
            self.check_text(text)
            self.buffer = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
            await self.flush(final=True)
            await self.finish()
        return True


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=VERSION)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=10200)
    for name, env, default in [
        ("model", "MODEL", "k2-fsa/OmniVoice"), ("device", "DEVICE", "cpu"),
        ("voice-ref", "REF_AUDIO", ""), ("ref-text", "REF_TEXT", ""),
        ("instruct", "INSTRUCT", ""), ("language", "LANGUAGE", "English"),
        ("language-code", "LANGUAGE_CODE", "en"),
    ]:
        p.add_argument("--" + name, default=os.environ.get("OMNIVOICE_" + env, default))
    for name, env, default, typ, low, high in [
        ("num-step", "NUM_STEP", 32, int, 1, 100),
        ("guidance-scale", "GUIDANCE_SCALE", 2.0, float, 0, 10),
        ("speed", "SPEED", 1.0, float, 0.25, 4),
        ("t-shift", "T_SHIFT", 0.1, float, 0, 1),
        ("silence", "INTER_CHUNK_SILENCE", 0.15, float, 0, 2),
        ("full-text-chars", "FULL_TEXT_CHARS", 100, int, 20, 500),
        ("first-stream-chars", "FIRST_STREAM_CHARS", 100, int, 20, 500),
        ("stream-chars", "STREAM_CHARS", 100, int, 20, 500),
    ]:
        def bounded(value, typ=typ, low=low, high=high):
            result = typ(value)
            if not math.isfinite(result) or not low <= result <= high:
                raise argparse.ArgumentTypeError(f"Expected {low} through {high}")
            return result
        p.add_argument("--" + name, type=bounded, default=str(os.environ.get("OMNIVOICE_" + env, default)))
    a = p.parse_args(argv)
    if a.device not in ("cpu", "cuda"):
        p.error("--device must be cpu or cuda")
    if not 1 <= a.port <= 65535:
        p.error("--port must be between 1 and 65535")
    if a.voice_ref and not os.path.isfile(a.voice_ref):
        p.error("Reference audio file does not exist")
    if bool(a.voice_ref) != bool(a.ref_text):
        p.error("Reference audio and its transcript must be supplied together")
    return a


async def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = Engine(args)
    server = AsyncTcpServer(args.host, args.port)
    active = set()

    class LimitedHandler(Handler):
        async def run(self):
            if len(active) >= MAX_CONNECTIONS:
                self.writer.close()
                return
            active.add(self)
            try:
                await super().run()
            finally:
                active.discard(self)

    try:
        await server.run(lambda r, w: LimitedHandler(r, w, engine, args))
    finally:
        await server.stop()
        engine.close()


if __name__ == "__main__":
    asyncio.run(main())
