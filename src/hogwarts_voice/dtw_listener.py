"""Live fast local spell spotting. No Vosk, Whisper, network, or speech text.

20ms chunks -> voice activity -> ~100ms tail silence -> DTW acoustic match
-> SpellCaster shared memory. Untrained/ambiguous audio is discarded.
"""
from __future__ import annotations

import audioop
from concurrent.futures import ThreadPoolExecutor
import os
import queue
import sys
import time

from .bridge import SpellBridge
from .dtw_voice import DTWBank, MIN_SCORE, MIN_MARGIN
from .vad import AdaptiveSpeechSegmenter
from .ptt import PushToTalkCapture, key_code
from .windows import KeyboardState, VK_F9, down, game_focused, foreground_process_name

def run(args, cfg):
    import sounddevice as sd

    bank = DTWBank.load()
    trained = bank.trained_spells()
    if not trained:
        print("[setup] NO TRAINED SPELLS. Open Spell Training and record "
              "a spell 3 times before testing.", flush=True)
        print("[setup] Old Vosk templates are incompatible with the new engine. "
              "Please record new samples.", flush=True)
        return 2
    if cfg.get("speaker_verification", False):
        print("[setup] Speaker ID is unavailable in the fast DTW mode. "
              "Disable speaker_verification to continue.", flush=True)
        return 2

    print("[engine] LOCAL ACOUSTIC DTW: no Vosk guesses, no cloud", flush=True)
    print(f"[engine] Trained commands: {', '.join(sorted(trained))}", flush=True)
    print("[engine] Only confident acoustic matches are sent; unknown sounds are blocked.",
          flush=True)
    threshold = float(cfg.get("dtw_threshold", MIN_SCORE))
    margin = float(cfg.get("dtw_margin", MIN_MARGIN))
    if not .5 <= threshold <= .99 or not 0 <= margin <= .3:
        print("[ERROR] dtw_threshold must be 0.50..0.99; dtw_margin 0..0.30",
              flush=True)
        return 2
    chunks = queue.Queue(maxsize=12)
    results = queue.SimpleQueue()
    executor = ThreadPoolExecutor(max_workers=1)
    waiting = 0
    tag = 0
    hotkeys = KeyboardState()
    bridge = None
    last_mod_ready = None
    block_ms = cfg.get("block_ms", 20)
    frames = round(block_ms * 16000 / 1000)
    ptt_mode = bool(cfg.get("push_to_talk", True))
    try:
        ptt_name = cfg.get("ptt_key", "F9")
        ptt_vk = key_code(ptt_name) if ptt_mode else None
    except ValueError as exc:
        print(f"[setup] {exc}", flush=True)
        return 2
    recorder = PushToTalkCapture()
    segmenter = AdaptiveSpeechSegmenter(silence_ms=170, min_speech_ms=170)
    ptt_was_pressed = False
    ptt_pressed_at = 0.0
    mic = cfg.get("mic_device")
    dry_run = bool(args.dry_run)
    require_focus = bool(cfg.get("require_game_focus", True))
    focus_ok = False
    prev_enabled = None
    last_focus_check = float("-inf")
    last_heartbeat = float("-inf")
    last_mic_report = float("-inf")
    max_mic_rms = 0
    last_spell = None
    last_spell_at = float("-inf")

    def submit_phrase(phrase, *, released, began):
        # A held-key recording bypasses both VAD and silence endpointing.
        # One submission per release, with the same strict acoustic checks.
        nonlocal waiting
        if waiting >= 2:
            print("[asr] busy; cannot queue another phrase", flush=True)
            return
        waiting += 1
        task_tag = tag
        started_at = time.monotonic()

        def analyze(pcm=phrase):
            ranking = bank.rank(pcm)
            if not ranking:
                return None, 0.0, "empty model", [], 0.0
            top_spell, best = ranking[0]
            runner = ranking[1][1] if len(ranking) > 1 else -1.0
            if best < threshold:
                chosen, reason = None, "low similarity"
            elif best - runner < margin:
                chosen, reason = None, "ambiguous"
            else:
                chosen, reason = top_spell, "matched"
            return chosen, float(best), reason, ranking, (
                time.monotonic() - started_at
            ) * 1000

        task = executor.submit(analyze)
        task.add_done_callback(
            lambda fut, session=task_tag, onset=began, recorded=released:
                results.put((session, fut, onset, recorded))
        )

    def callback(indata, count, timing, status):
        if status and cfg.get("verbose", False):
            print(f"[audio] {status}", flush=True)
        item = (bytes(indata), time.monotonic())
        try:
            chunks.put_nowait(item)
        except queue.Full:
            try:
                chunks.get_nowait()
                chunks.put_nowait(item)
            except queue.Empty:
                pass

    try:
        print(f"[mic] Device: {sd.query_devices(mic, 'input')['name']}", flush=True)
        if not dry_run:
            bridge = SpellBridge().connect()
        print(f"[mode] {'TEST - no game casting' if dry_run else 'GAME'}", flush=True)
        print("[help] F8 = pause. Game mode: return to Hogwarts Legacy after Start.",
              flush=True)
        if ptt_mode:
            print(f"[ptt] Hold {ptt_name}, speak ONE incantation, release {ptt_name} to cast.",
                  flush=True)
            print("[ptt] Detection by silence is OFF. Nothing casts while the key is held.",
                  flush=True)
        else:
            print("[listen] Continuous listening with adaptive VAD (experimental).",
                  flush=True)
        with sd.RawInputStream(
            samplerate=16000, blocksize=frames, channels=1, dtype="int16",
            device=mic, callback=callback
        ):
            while True:
                now = time.monotonic()
                if hotkeys.update():
                    print(f"[voice] {'ON' if hotkeys.active else 'PAUSED'}", flush=True)
                    segmenter.reset()
                    recorder.reset()
                    tag += 1

                if bridge and now - last_heartbeat >= .15:
                    bridge.poll(now=now)
                    bridge.heartbeat()
                    last_heartbeat = now
                    ready = bridge.alive(now=now)
                    if ready != last_mod_ready:
                        print("[mod] READY" if ready else "[mod] NOT READY: game component not responding",
                              flush=True)
                        last_mod_ready = ready

                if dry_run or not require_focus:
                    focus_ok = True
                elif now - last_focus_check >= .12:
                    focus_ok = game_focused()
                    last_focus_check = now
                # PTT does NOT alter the listener's enabled state: releasing
                # the key must not invalidate the asynchronous matching result.
                enabled = hotkeys.active and focus_ok
                if enabled != prev_enabled:
                    tag += 1
                    segmenter.reset()
                    recorder.reset()
                    while not chunks.empty():
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            break
                    prev_enabled = enabled
                    if enabled:
                        print("[focus] LISTENING" +
                              (f" — hold {ptt_name} to record" if ptt_mode else ""),
                              flush=True)
                    else:
                        print(f"[focus] BLOCKED ({foreground_process_name() or 'inactive'})",
                              flush=True)

                # Poll the physical key even while focus is blocked, so a
                # re-focused game cannot record halfway through an old hold.
                if ptt_mode:
                    pressed = down(ptt_vk)
                    if enabled and pressed and not ptt_was_pressed:
                        recorder.press()
                        ptt_pressed_at = now
                        # Discard audio from before the actual key press.
                        while not chunks.empty():
                            try:
                                chunks.get_nowait()
                            except queue.Empty:
                                break
                        print(f"[ptt] RECORDING ({ptt_name} held)", flush=True)
                    elif enabled and not pressed and ptt_was_pressed and recorder.held:
                        # Process audio already captured up to key-up before
                        # closing the utterance. No VAD or silence wait.
                        while True:
                            try:
                                buffered, captured = chunks.get_nowait()
                            except queue.Empty:
                                break
                            if ptt_pressed_at <= captured <= now:
                                recorder.add(buffered)
                        phrase, duration_ms, reason = recorder.release()
                        print(f"[ptt] RELEASED: {duration_ms:.0f}ms ({reason})", flush=True)
                        if phrase is not None:
                            submit_phrase(phrase, released=now, began=ptt_pressed_at)
                        else:
                            print("[blocked] PTT phrase too short or too long; nothing sent.",
                                  flush=True)
                    elif not enabled and recorder.held:
                        recorder.reset()
                        print("[ptt] CANCELLED: lost game focus or paused", flush=True)
                    ptt_was_pressed = pressed

                while not results.empty():
                    task_tag, future, started, captured = results.get_nowait()
                    waiting = max(0, waiting-1)
                    try:
                        selected, score, reason, rankings, elapsed_ms = future.result()
                    except Exception as err:
                        print(f"[asr] ERROR: {err}", flush=True)
                        continue
                    if task_tag != tag or not enabled:
                        continue
                    top = ", ".join(f"{name}={value:.3f}" for name,value in rankings[:3])
                    print(f"[rank] {top} (DTW {elapsed_ms:.1f}ms)", flush=True)
                    if selected is None:
                        print(f"[blocked] No reliable spell: {reason} "
                              f"(score={score:.3f}). Nothing sent.",
                              flush=True)
                        continue
                    if selected == last_spell and now - last_spell_at < (
                        cfg.get("repeat_gap_ms",450) / 1000
                    ):
                        print(f"[throttle] {selected} (too soon)", flush=True)
                        continue
                    if not dry_run and require_focus and not game_focused():
                        print(f"[blocked] {selected}: Hogwarts Legacy is not foreground",
                              flush=True)
                        continue
                    if dry_run:
                        ok, reason = True, "TEST"
                    else:
                        ok, reason = bridge.send(selected)
                    dispatch = time.monotonic()
                    last_spell = selected
                    last_spell_at = dispatch
                    first_metric = "release-to-dispatch" if ptt_mode else "last-audio-to-dispatch"
                    second_metric = "press-to-dispatch" if ptt_mode else "speech-onset-to-dispatch~"
                    print(f"[{reason}] {selected} | score={score:.3f} | "
                          f"{first_metric}={max(0,(dispatch-captured)*1000):.1f}ms, "
                          f"{second_metric}={max(0,(dispatch-started)*1000):.0f}ms",
                          flush=True)

                try:
                    chunk, captured = chunks.get(timeout=.035)
                except queue.Empty:
                    continue
                if not enabled:
                    continue
                if cfg.get("mic_diagnostics", True):
                    max_mic_rms = max(max_mic_rms, audioop.rms(chunk, 2))
                    if captured - last_mic_report > 1.6:
                        print(f"[mic] RMS={max_mic_rms}", flush=True)
                        max_mic_rms = 0
                        last_mic_report = captured

                if ptt_mode:
                    if recorder.held and captured >= ptt_pressed_at:
                        recorder.add(chunk)
                    continue

                phrase = segmenter.feed(chunk)
                if phrase is None:
                    continue
                duration = len(phrase) / 32000
                if cfg.get("mic_diagnostics", True):
                    print(f"[segment] complete utterance: {duration*1000:.0f}ms", flush=True)
                # Approximation in free-listening mode: includes pre-roll and tail silence.
                submit_phrase(phrase, released=captured, began=captured-duration)
    except KeyboardInterrupt:
        print("[stop] stopped", flush=True)
        return 0
    except Exception as exc:
        print(f"[ERROR] Audio/device/runtime error: {exc}", flush=True)
        return 1
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        if bridge:
            bridge.close()
