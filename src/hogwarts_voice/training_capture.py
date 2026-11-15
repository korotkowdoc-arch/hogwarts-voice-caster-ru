"""Record a pronunciation sample with the EXACT same PCM16 / hold-to-record
protocol used by the game's PTT voice listener. No fixed 2.8-second window,
no Vosk and no silence-based start/end guessing.
"""
from __future__ import annotations

import queue
import time
from collections.abc import Callable

from .ptt import PushToTalkCapture, key_code
from .windows import down

class TrainingTimeout(ValueError):
    pass

def capture_one_hold(*, device=None, key="F9", wait_seconds=25.0,
                     state_callback: Callable[[str], None] | None = None,
                     key_is_down: Callable[[int], bool] | None = None,
                     stream_factory=None,
                     clock=None, sleep=None):
    """Listen once from physical key-down until key-up.

    Designed for background worker thread (never call on Tk main thread).
    Optional injected clock, keyboard and stream permit deterministic tests.
    Returns int16 PCM bytes, 16 kHz mono. Does not save raw audio.
    """
    if key_is_down is None:
        key_is_down = down
    if clock is None:
        clock = time.monotonic
    if sleep is None:
        sleep = time.sleep
    if stream_factory is None:
        import sounddevice as sd
        stream_factory = sd.RawInputStream
    vk = key_code(key)
    recorder = PushToTalkCapture()
    chunks = queue.Queue(maxsize=24)

    def notify(message):
        if state_callback:
            state_callback(message)

    def callback(indata, frames, time_info, status):
        item = (clock(), bytes(indata))
        try:
            chunks.put_nowait(item)
        except queue.Full:
            try:
                chunks.get_nowait()
                chunks.put_nowait(item)
            except queue.Empty:
                pass

    def drain(started, until):
        while True:
            try:
                recorded_at, pcm = chunks.get_nowait()
            except queue.Empty:
                break
            if started <= recorded_at <= until:
                recorder.add(pcm)

    with stream_factory(samplerate=16000, blocksize=320, channels=1,
                        dtype="int16", device=device, callback=callback):
        notify(f"Зажми {key}, произнеси слово и отпусти клавишу")
        # If the key is already down when opening, wait for release first.
        was_down = bool(key_is_down(vk))
        start_at = None
        deadline = clock() + wait_seconds
        while clock() < deadline:
            now = clock()
            is_down = bool(key_is_down(vk))
            if is_down and not was_down:
                recorder.press()
                start_at = now
                while not chunks.empty():
                    try:
                        chunks.get_nowait()
                    except queue.Empty:
                        break
                notify(f"● ЗАПИСЬ ИДЁТ — отпусти {key} после слова")
            elif not is_down and was_down and recorder.held:
                drain(start_at, now)
                pcm, ms, reason = recorder.release()
                if pcm is None:
                    if reason == "too short":
                        raise ValueError(
                            f"Запись слишком короткая ({ms:.0f} мс). "
                            "Зажми клавишу до начала слова."
                        )
                    raise ValueError(
                        f"Запись слишком длинная ({ms:.0f} мс). "
                        "Произнеси только одно заклинание."
                    )
                notify(f"Образец записан: {ms:.0f} мс")
                return pcm
            if recorder.held and start_at is not None:
                drain(start_at, now)
            was_down = is_down
            sleep(.01)

    raise TrainingTimeout(f"Не дождались нажатия и отпускания {key}. Повтори запись.")
