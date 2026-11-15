"""Fast PTT -> Russian GigaAM v2 -> incantation whitelist -> game IPC.

No DTW self-training, constrained Vosk guesses, cloud, or silence detection
in PTT mode. The recognizer is constructed once; inference is on one worker.
"""
from __future__ import annotations

import audioop
from concurrent.futures import ThreadPoolExecutor
import queue
import time

from .bridge import SpellBridge
from .ptt import PushToTalkCapture, key_code
from .ru_asr import RussianASR, load_spell_aliases, match_incantation, DEFAULT_ENABLED
from .vad import AdaptiveSpeechSegmenter
from .windows import KeyboardState, down, game_focused, foreground_process_name

def run(args, cfg):
    try:
        import sounddevice as sd
    except ImportError:
        print("[setup] Missing sounddevice. Run install.bat.", flush=True)
        return 2

    try:
        import sherpa_onnx
        print("[engine] Loading GigaAM v2 Russian neural model (CPU, offline)...",
              flush=True)
        neural = RussianASR(num_threads=int(cfg.get("asr_threads", 4)))
    except Exception as exc:
        print(f"[setup] Russian model error: {exc}", flush=True)
        print("[setup] Run the latest install.bat to install the neural engine.",
              flush=True)
        return 2

    spellbook = load_spell_aliases()
    allowed = cfg.get("enabled_spells", list(DEFAULT_ENABLED))
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) and item in spellbook for item in allowed
    ):
        print("[setup] Invalid enabled_spells in config.json", flush=True)
        return 2
    if not allowed:
        print("[setup] No enabled spells (safe mode).", flush=True)
    print("[engine] Russian GigaAM v2 ready. No voice samples needed.", flush=True)
    print(f"[allowed] {', '.join(allowed) or '(none)'}", flush=True)

    dry_run = bool(args.dry_run)
    ptt_mode = bool(cfg.get("push_to_talk", True))
    ptt_name = cfg.get("ptt_key", "F9")
    try:
        ptt_vk = key_code(ptt_name) if ptt_mode else None
    except ValueError as exc:
        print(f"[setup] {exc}", flush=True)
        return 2
    frames = int(16000 * int(cfg.get("block_ms", 20)) / 1000)
    focus_required = not dry_run and cfg.get("require_game_focus", True)
    recorder = PushToTalkCapture()
    segmenter = AdaptiveSpeechSegmenter(silence_ms=170, min_speech_ms=170)
    chunks = queue.Queue(maxsize=25)
    answers = queue.SimpleQueue()
    executor = ThreadPoolExecutor(max_workers=1)
    hotkeys = KeyboardState()
    bridge = None
    last_focused = None
    last_bridge_alive = None
    last_bridge_poll = float("-inf")
    last_focus_poll = float("-inf")
    last_audio_log = float("-inf")
    highest_rms = 0
    old_pressed = False
    pressed_at = 0.0
    generation = 0
    awaiting = False
    last_sent_at = float("-inf")
    last_sent_spell = ""

    def on_audio(data, frame_count, audio_time, status):
        try:
            chunks.put_nowait((time.monotonic(), bytes(data)))
        except queue.Full:
            try:
                chunks.get_nowait()
            except queue.Empty:
                return
            try:
                chunks.put_nowait((time.monotonic(), bytes(data)))
            except queue.Full:
                return

    def clear_audio():
        while True:
            try:
                chunks.get_nowait()
            except queue.Empty:
                break

    def start_decode(pcm: bytes, *, recorded_at: float, started_at: float):
        nonlocal awaiting
        if awaiting:
            print("[blocked] Previous spell is still being decoded; press again.",
                  flush=True)
            return
        awaiting = True
        current = generation
        task_start = time.monotonic()

        def decode():
            return neural.transcribe(pcm)

        future = executor.submit(decode)
        future.add_done_callback(
            lambda item, gen=current, t0=task_start,
                   recorded=recorded_at, begun=started_at:
                answers.put((gen, item, t0, recorded, begun))
        )

    try:
        mic = cfg.get("mic_device")
        print(f"[mic] {sd.query_devices(mic, 'input')['name']}", flush=True)
        if not dry_run:
            bridge = SpellBridge().connect()
        print(f"[mode] {'TEST - no casting' if dry_run else 'GAME - casts enabled spells'}",
              flush=True)
        print(f"[ptt] Hold {ptt_name}, speak ONE incantation and release."
              if ptt_mode else
              "[listen] Experimental automatic phrase boundaries",
              flush=True)
        print("[help] F8 toggles pause. Return to Hogwarts Legacy to cast in GAME mode.",
              flush=True)
        with sd.RawInputStream(
            samplerate=16000, blocksize=frames, channels=1, dtype="int16",
            device=mic, callback=on_audio
        ):
            while True:
                now = time.monotonic()
                if hotkeys.update():
                    print(f"[voice] {'ON' if hotkeys.active else 'PAUSED'}", flush=True)
                    recorder.reset()
                    segmenter.reset()
                    generation += 1
                    clear_audio()

                if bridge and now-last_bridge_poll > .15:
                    bridge.poll(now=now)
                    bridge.heartbeat()
                    good = bridge.alive(now=now)
                    last_bridge_poll = now
                    if last_bridge_alive is None or last_bridge_alive != good:
                        print("[mod] READY" if good else "[mod] NOT READY", flush=True)
                        last_bridge_alive = good

                if not focus_required:
                    foreground = True
                elif now-last_focus_poll > .12:
                    foreground = game_focused()
                    last_focus_poll = now
                enabled = hotkeys.active and foreground
                if enabled != last_focused:
                    last_focused = enabled
                    generation += 1
                    recorder.reset()
                    segmenter.reset()
                    clear_audio()
                    if enabled:
                        print("[focus] LISTENING (PTT)" if ptt_mode else
                              "[focus] LISTENING", flush=True)
                    else:
                        print(f"[focus] BLOCKED ({foreground_process_name() or 'unknown'})",
                              flush=True)

                if ptt_mode:
                    pressed = down(ptt_vk)
                    if enabled and pressed and not old_pressed:
                        recorder.press()
                        pressed_at = now
                        clear_audio()
                        print(f"[ptt] RECORDING ({ptt_name})", flush=True)
                    elif enabled and not pressed and old_pressed and recorder.held:
                        while True:
                            try:
                                captured, audio = chunks.get_nowait()
                            except queue.Empty:
                                break
                            if pressed_at <= captured <= now:
                                recorder.add(audio)
                        pcm, elapsed, state = recorder.release()
                        print(f"[ptt] RELEASED {elapsed:.0f}ms ({state})", flush=True)
                        if pcm:
                            start_decode(pcm, recorded_at=now, started_at=pressed_at)
                        else:
                            print("[blocked] Invalid hold length. Nothing cast.", flush=True)
                    elif not enabled and recorder.held:
                        recorder.reset()
                        print("[ptt] CANCELLED (focus lost or paused)", flush=True)
                    old_pressed = pressed

                while True:
                    try:
                        result_generation, future, submitted, released, started = answers.get_nowait()
                    except queue.Empty:
                        break
                    awaiting = False
                    if result_generation != generation or not enabled:
                        continue
                    try:
                        transcript = future.result()
                    except Exception as exc:
                        print(f"[asr] Decoding error: {exc}", flush=True)
                        continue
                    spell, reason = match_incantation(transcript, spellbook, allowed)
                    print(f"[heard] {transcript or '(silence)'}", flush=True)
                    elapsed_ms = (time.monotonic() - submitted) * 1000
                    print(f"[asr] GigaAM decoded in {elapsed_ms:.0f}ms; match={reason}",
                          flush=True)
                    if not spell:
                        print("[blocked] No permitted incantation. Nothing cast.", flush=True)
                        continue
                    if (spell == last_sent_spell and now - last_sent_at
                        < cfg.get("repeat_gap_ms", 450) / 1000):
                        print(f"[blocked] {spell}: repetition cooldown", flush=True)
                        continue
                    if focus_required and not game_focused():
                        print(f"[blocked] {spell}: game lost focus", flush=True)
                        continue
                    if dry_run:
                        ok, result = True, "TEST"
                    else:
                        ok, result = bridge.send(spell)
                    if ok:
                        last_sent_spell = spell
                        last_sent_at = now
                    print(f"[{result}] {spell} | release-to-dispatch="
                          f"{(time.monotonic()-released)*1000:.0f}ms; "
                          f"press-to-dispatch={(time.monotonic()-started)*1000:.0f}ms",
                          flush=True)

                try:
                    captured, audio = chunks.get(timeout=.025)
                except queue.Empty:
                    continue
                if not enabled:
                    continue
                if cfg.get("mic_diagnostics", True):
                    highest_rms = max(highest_rms, audioop.rms(audio, 2))
                    if captured-last_audio_log > 2.0:
                        print(f"[mic] RMS={highest_rms}", flush=True)
                        highest_rms = 0
                        last_audio_log = captured
                if ptt_mode:
                    if recorder.held and captured >= pressed_at:
                        recorder.add(audio)
                else:
                    phrase = segmenter.feed(audio)
                    if phrase:
                        duration = len(phrase) / 32000
                        print(f"[segment] {duration*1000:.0f}ms", flush=True)
                        start_decode(phrase, recorded_at=captured,
                                     started_at=captured-duration)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"[ERROR] Audio or game runtime: {exc}", flush=True)
        return 1
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        if bridge:
            bridge.close()
