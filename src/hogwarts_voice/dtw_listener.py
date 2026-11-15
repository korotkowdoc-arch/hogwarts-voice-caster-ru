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
from .template_voice import SpeechSegmenter
from .windows import KeyboardState, VK_F9, down, game_focused, foreground_process_name

def run(args, cfg):
    import sounddevice as sd

    bank = DTWBank.load()
    trained = bank.trained_spells()
    if not trained:
        print("[setup] НЕТ ОБУЧЕННЫХ ЗАКЛИНАНИЙ. "
              "Открой «Тренировка заклинаний» и запиши хотя бы одно слово 3 раза.",
              flush=True)
        print("[setup] Старая база Vosk несовместима с новым акустическим движком. "
              "Для безопасности её образцы не переносятся.", flush=True)
        return 2
    if cfg.get("speaker_verification", False):
        print("[setup] Отдельная идентификация говорящего не включена в быстрый "
              "акустический режим; отключи speaker_verification для продолжения.",
              flush=True)
        return 2

    print("[engine] LOCAL ACOUSTIC DTW — no Vosk guesses, no cloud", flush=True)
    print(f"[engine] Trained commands: {', '.join(sorted(trained))}", flush=True)
    print("[engine] Уверенные совпадения отправляются; неизвестные звуки блокируются.",
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
    segmenter = SpeechSegmenter(silence_ms=100, min_ms=180)
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
        print(f"[mode] {'TEST — no game casting' if dry_run else 'GAME'}", flush=True)
        print("[help] F8 = pause. Game mode: return to Hogwarts Legacy after Start.",
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
                enabled = hotkeys.active and focus_ok and (
                    not cfg.get("push_to_talk", False) or down(VK_F9)
                )
                if enabled != prev_enabled:
                    tag += 1
                    segmenter.reset()
                    while not chunks.empty():
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            break
                    prev_enabled = enabled
                    if enabled:
                        print("[focus] LISTENING", flush=True)
                    else:
                        print(f"[focus] BLOCKED ({foreground_process_name() or 'inactive'})",
                              flush=True)

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
                        print(f"[blocked] Нет уверенного заклинания: {reason} "
                              f"(score={score:.3f}). Ничего не отправлено.",
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
                    print(f"[{reason}] {selected} | score={score:.3f} | "
                          f"last-audio-to-dispatch={max(0,(dispatch-captured)*1000):.1f}ms, "
                          f"speech-onset-to-dispatch~={max(0,(dispatch-started)*1000):.0f}ms",
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

                phrase = segmenter.feed(chunk)
                if phrase is None:
                    continue
                if waiting >= 2:
                    print("[asr] busy, dropped a spoken phrase to avoid latency", flush=True)
                    continue
                waiting += 1
                task_tag = tag
                duration = len(phrase) / 32000
                # Approximation: includes pre-roll and tail silence.
                began = captured - duration
                started_at = time.monotonic()

                def analyze(pcm=phrase):
                    ranking = bank.rank(pcm)
                    if not ranking:
                        return None, 0.0, "empty model", [], 0.0
                    top_spell, best = ranking[0]
                    runner = ranking[1][1] if len(ranking)>1 else -1.0
                    if best < threshold:
                        chosen, reason = None, "low similarity"
                    elif best-runner < margin:
                        chosen, reason = None, "ambiguous"
                    else:
                        chosen, reason = top_spell, "matched"
                    return chosen, float(best), reason, ranking, (
                        time.monotonic() - started_at
                    ) * 1000

                task = executor.submit(analyze)
                task.add_done_callback(
                    lambda fut, session=task_tag, onset=began, recorded=captured:
                        results.put((session, fut, onset, recorded))
                )
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
