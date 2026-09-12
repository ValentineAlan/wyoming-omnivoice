import asyncio
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from types import SimpleNamespace

from wyoming.event import Event
from wyoming_omnivoice import Engine, Handler, MAX_TEXT, parse_args, pop_piece, read_event


class TextTests(unittest.TestCase):
    def test_long_words_and_final_flush_are_bounded(self):
        for text in ["x" * 800, "Hello, this is a sentence. " * 100, "one two three"]:
            rest, pieces = text, []
            while rest:
                piece, rest = pop_piece(rest, 35, final=True)
                self.assertLessEqual(len(piece), 35)
                pieces.append(piece)
            self.assertEqual("".join(text.split()), "".join("".join(pieces).split()))

    def test_partial_stream_waits(self):
        self.assertEqual(pop_piece("incomplete", 35), ("", "incomplete"))

    def test_invalid_configuration(self):
        for args in [["--speed", "nan"], ["--num-step", "0"], ["--stream-chars", "10000"], ["--device", "rocm"]]:
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(args)


class FakeEngine:
    rate = 24000
    def __init__(self):
        self.texts = []
    async def synthesize(self, text):
        self.texts.append(text)
        return b"\x01\x00" * 100


class RecordingHandler(Handler):
    def __init__(self):
        super().__init__(None, None, FakeEngine(), parse_args([]))
        self.events = []
    async def write_event(self, event):
        self.events.append(event)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_and_empty_request_framing(self):
        h = RecordingHandler()
        for text in ["Hello world.", ""]:
            h.events.clear()
            await h.handle_event(Event(type="synthesize", data={"text": text}))
            self.assertEqual(h.events[0].type, "audio-start")
            self.assertEqual(h.events[-1].type, "audio-stop")
            self.assertFalse(h.audio_started)

    async def test_stream_compatibility_is_not_spoken_twice(self):
        h = RecordingHandler()
        await h.handle_event(Event(type="synthesize-start"))
        await h.handle_event(Event(type="synthesize-chunk", data={"text": "Hello "}))
        await h.handle_event(Event(type="synthesize-chunk", data={"text": "world."}))
        await h.handle_event(Event(type="synthesize", data={"text": "Hello world."}))
        await h.handle_event(Event(type="synthesize-stop"))
        self.assertEqual(h.engine.texts, ["Hello world."])
        self.assertEqual([e.type for e in h.events][-2:], ["audio-stop", "synthesize-stopped"])
        self.assertFalse(h.streaming)

    async def test_discovery_advertises_configured_language(self):
        h = RecordingHandler()
        h.args.language_code = "fr"
        await h.handle_event(Event(type="describe"))
        self.assertEqual(h.events[0].data["tts"][0]["voices"][0]["languages"], ["fr"])

    async def test_cumulative_stream_limit(self):
        h = RecordingHandler()
        await h.handle_event(Event(type="synthesize-start"))
        h.count = MAX_TEXT
        with self.assertRaises(ValueError):
            await h.handle_event(Event(type="synthesize-chunk", data={"text": "x"}))
        self.assertEqual(h.engine.texts, [])

    async def test_nested_or_unstarted_stream_rejected(self):
        h = RecordingHandler()
        with self.assertRaises(ValueError):
            await h.handle_event(Event(type="synthesize-chunk", data={"text": "x"}))
        await h.handle_event(Event(type="synthesize-start"))
        with self.assertRaises(ValueError):
            await h.handle_event(Event(type="synthesize-start"))

    async def test_frame_lengths_checked_before_reading_body(self):
        for header in [dict(type="synthesize", data_length=9999999), dict(type="synthesize", data_length=-1), dict(type="synthesize", payload_length=1)]:
            reader = asyncio.StreamReader()
            reader.feed_data(json.dumps(header).encode() + b"\n")
            with self.assertRaises(ValueError):
                await read_event(reader)

    async def test_separate_json_data_supported(self):
        data = b'{"text":"hello"}'
        reader = asyncio.StreamReader()
        reader.feed_data(json.dumps(dict(type="synthesize", data_length=len(data))).encode() + b"\n" + data)
        event = await read_event(reader)
        self.assertEqual(event.data["text"], "hello")

    async def test_cancellation_keeps_inference_serial(self):
        engine = Engine.__new__(Engine)
        engine.lock = asyncio.Lock()
        engine.executor = ThreadPoolExecutor(max_workers=1)
        started, release = threading.Event(), threading.Event()
        calls = []
        def generate(text):
            calls.append(text)
            if text == "first":
                started.set()
                release.wait(5)
            return b"pcm"
        engine.generate = generate
        first = asyncio.create_task(engine.synthesize("first"))
        try:
            await asyncio.to_thread(started.wait, 2)
            first.cancel()
            second = asyncio.create_task(engine.synthesize("second"))
            await asyncio.sleep(0.02)
            self.assertEqual(calls, ["first"])
            self.assertTrue(engine.lock.locked())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual(await second, b"pcm")
        finally:
            release.set()
            engine.close()


if __name__ == "__main__":
    unittest.main()
