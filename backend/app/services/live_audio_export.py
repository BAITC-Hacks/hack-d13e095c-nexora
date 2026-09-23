import array
import sys
import wave
from pathlib import Path


def mix_recording(chunks: list[tuple[str, float]], output: Path):
    """Mix known participant tracks, preserving their shared room clock, with bounded RAM."""
    origin = min(start for _, start in chunks)
    raw = output.with_suffix(".pcm")
    try:
        with raw.open("w+b") as mixed:
            for filename, start in chunks:
                with wave.open(filename, "rb") as source:
                    pcm = source.readframes(source.getnframes())
                offset = max(0, round((start - origin) * 16000)) * 2
                mixed.seek(0, 2)
                if mixed.tell() < offset + len(pcm):
                    mixed.truncate(offset + len(pcm))
                mixed.seek(offset)
                before, incoming = array.array("h"), array.array("h")
                before.frombytes(mixed.read(len(pcm)))
                incoming.frombytes(pcm)
                if sys.byteorder != "little":
                    before.byteswap()
                    incoming.byteswap()
                for i, value in enumerate(incoming):
                    before[i] = max(-32768, min(32767, before[i] + value))
                if sys.byteorder != "little":
                    before.byteswap()
                mixed.seek(offset)
                mixed.write(before.tobytes())
            mixed.seek(0)
            with wave.open(str(output), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                while part := mixed.read(1024 * 1024):
                    wav.writeframesraw(part)
    finally:
        raw.unlink(missing_ok=True)
