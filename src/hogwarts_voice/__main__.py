"""Local low-latency voice control for Hogwarts Legacy.

Default: direct Vosk partial -> SpellCaster shared memory, without voice ID.
Speaker identity verification can be explicitly enabled but costs latency.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import queue
import sys
import time
from typing import Any

from .bridge import SpellBridge
from .latency import AudioDelayMeter
from .spellbook import Spellbook
from .stream import StreamGate
from .windows import KeyboardState, VK_F9, down, game_focused

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "vosk-model-small-ru-0.22"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_SPELLS = ROOT / "spells.json"

def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("samplerate") != 16000:
        raise ValueError("Use a 16000 Hz Vosk model")
    if not 10 <= cfg.get("block_ms", 20) <= 80:
        raise ValueError("block_ms must be 10..80")
    if not 1 <= cfg.get("stable_partial_updates", 1) <= 8:
        raise ValueError("stable_partial_updates must be 1..8")
    if not 0 <= cfg.get("repeat_gap_ms", 450) <= 5000:
        raise ValueError("repeat_gap_ms must be 0..5000")
    return cfg

def args_parser():
    parser = argparse.ArgumentParser(description="Hogwarts Voice Caster RU")
    parser.add_argument("--gui", action="store_true", help="Open main window")
    parser.add_argument("--listen", action="store_true", help="Run spell listener")
    parser.add_argument("--dry-run", action="store_true", help="Recognize but never cast")
    parser.add_argument("--list-mics", action="store_true", help="List audio input devices")
    parser.add_argument("--send", metavar="GAME_SPELL", help="Test direct IPC, bypass microphone")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--spells", type=Path, default=DEFAULT_SPELLS)
    parser.add_argument("--model", type=Path, default=MODEL)
    return parser

def main():
    if len(sys.argv) == 1 or "--gui" in sys.argv[1:]:
        from .ui import main as show_ui
        return show_ui()

    args = args_parser().parse_args()
    if os.name != "nt" and not args.dry_run and not args.list_mics:
        print("Game integration is supported on Windows only.", file=sys.stderr)
        return 2

    if args.send:
        bridge = SpellBridge().connect()
        try:
            deadline = time.monotonic() + 2
            while not bridge.alive() and time.monotonic() < deadline:
                time.sleep(.08)
                bridge.poll()
            ok, reason = bridge.send(args.send)
            print(f"{args.send}: {reason}")
            return 0 if ok else 1
        finally:
            bridge.close()

    try:
        import sounddevice as sd
    except ImportError:
        print("Run install.bat to install audio libraries.", file=sys.stderr)
        return 2
    if args.list_mics:
        print(sd.query_devices())
        return 0
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
        from .voice_profile import VoiceProfile
        cfg = load_config(args.config)
        profile = VoiceProfile.load()
        with args.spells.open("r", encoding="utf-8") as f:
            spellbook = profile.merged_book(Spellbook(json.load(f)))
        if not args.model.is_dir():
            raise FileNotFoundError(f"Model not found: {args.model}. Run install.bat")
    except (ImportError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 2

    # Instantiate the model ONCE; no cloud round trip, no per-command loading.
    SetLogLevel(-1)
    print("Loading Russian offline model...", flush=True)
    model = Model(str(args.model))
    grammar_mode = cfg.get("grammar_mode", "constrained")
    if grammar_mode == "constrained":
        recognizer = KaldiRecognizer(model, 16000, json.dumps(spellbook.grammar(), ensure_ascii=False))
    elif grammar_mode == "free":
        recognizer = KaldiRecognizer(model, 16000)
    else:
        raise ValueError("grammar_mode must be constrained or free")

    gate = StreamGate(
        spellbook, cfg.get("stable_partial_updates", 1),
        cfg.get("min_gap_ms", 0), cfg.get("repeat_gap_ms", 450)
    )
    verify_speaker = bool(cfg.get("speaker_verification", False))
    verifier = None
    worker = None
    if verify_speaker:
        if not profile.ready():
            print("Voice identification enabled, but no trained profile. "
                  "Open the pronunciation wizard or disable the option.", file=sys.stderr)
            return 2
        try:
            from .speaker import SpeakerVerifier
            verifier = SpeakerVerifier(profile, cfg.get("speaker_threshold", 0.68))
            worker = ThreadPoolExecutor(max_workers=1)
        except Exception as exc:
            print(f"Speaker verification unavailable: {exc}", file=sys.stderr)
            return 2

    bridge = None if args.dry_run else SpellBridge().connect()
    chunks = queue.Queue(maxsize=6)
    results = queue.SimpleQueue()
    hotkeys = KeyboardState()
    history = deque(maxlen=120)
    pending = []
    session = 0
    waiting_tasks = 0
    block_ms = cfg.get("block_ms", 20)
    meter = AudioDelayMeter()
    frames = round(block_ms * 16000 / 1000)
    verbose = cfg.get("verbose", False)
    debug_latency = cfg.get("debug_latency", True)

    def callback(indata, count, time_info, status):
        if status and verbose:
            print(f"[audio] {status}", flush=True)
        # Timestamp at capture callback; if decoding stalls, drop oldest audio.
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
        mic_name = sd.query_devices(cfg.get("mic_device"), "input")["name"]
    except Exception as exc:
        print(f"Microphone unavailable: {exc}", file=sys.stderr)
        if bridge:
            bridge.close()
        if worker:
            worker.shutdown(wait=False, cancel_futures=True)
        return 2

    print(f"Microphone: {mic_name}")
    print(f"Mode: {'TEST' if args.dry_run else 'GAME'}, "
          f"audio blocks: {block_ms} ms, partial stability: {cfg.get('stable_partial_updates', 1)}")
    print(f"Voice ID: {'ON (slower)' if verify_speaker else 'OFF (fast path)'}")
    print("F8: pause | Ctrl+C: stop", flush=True)
    if cfg.get("push_to_talk", False):
        print("Hold F9 to speak.", flush=True)

    focus_ok = False
    last_focus_checked = float("-inf")
    was_enabled = None
    last_heartbeat = float("-inf")
    last_partial = ""
    last_display = float("-inf")

    def emit(spells, *, capture_at, speech_onset, score=None):
        for spell in spells:
            before = time.monotonic()
            if args.dry_run:
                ok, reason = True, "TEST"
            else:
                # Do not trust a cached focus check at the moment of casting.
                if cfg.get("require_game_focus", True) and not game_focused():
                    continue
                ok, reason = bridge.send(spell, now=before)
            after = time.monotonic()
            if debug_latency:
                capture_delay = max(0.0, 1000 * (after - capture_at))
                phrase_delay = None if speech_onset is None else max(0.0, 1000 * (after - speech_onset))
                extra = f"onset-to-dispatch~{phrase_delay:.0f}ms" if phrase_delay is not None else "no onset"
                print(f"[{reason}] {spell} | last-audio-to-dispatch={capture_delay:.1f}ms, {extra}", flush=True)
            else:
                print(f"[{reason}] {spell}", flush=True)

    try:
        with sd.RawInputStream(samplerate=16000, blocksize=frames,
                               channels=1, dtype="int16",
                               device=cfg.get("mic_device"), callback=callback):
            while True:
                now = time.monotonic()
                if hotkeys.update():
                    print(f"[voice] {'ON' if hotkeys.active else 'PAUSED'}", flush=True)
                    recognizer.Reset()
                    gate.reset_segment()
                    meter.reset()
                    history.clear()
                    pending.clear()
                    session += 1

                if bridge and now - last_heartbeat >= 0.16:
                    bridge.poll(now=now)
                    bridge.heartbeat()
                    last_heartbeat = now

                # Avoid querying Windows process path for each ~20ms audio block.
                if args.dry_run or not cfg.get("require_game_focus", True):
                    focus_ok = True
                elif now - last_focus_checked >= 0.12:
                    focus_ok = game_focused()
                    last_focus_checked = now
                enabled = hotkeys.active and focus_ok and (
                    not cfg.get("push_to_talk", False) or down(VK_F9)
                )
                if enabled != was_enabled:
                    gate.reset_segment()
                    recognizer.Reset()
                    meter.reset()
                    history.clear()
                    pending.clear()
                    session += 1
                    while True:
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            break
                    was_enabled = enabled
                    if verbose:
                        print(f"[voice] {'listening' if enabled else 'inactive'}", flush=True)

                # Async verification only when opt-in. Fast mode has no queue or
                # machine-learning speaker comparison between ASR and casting.
                if verifier:
                    while not results.empty():
                        spells, future, ticket, captured, onset = results.get_nowait()
                        waiting_tasks = max(0, waiting_tasks - 1)
                        try:
                            accepted, score = future.result()
                        except Exception as exc:
                            print(f"[speaker] blocked: {exc}", flush=True)
                            continue
                        if ticket != session or not enabled:
                            continue
                        if accepted:
                            emit(spells, capture_at=captured, speech_onset=onset, score=score)
                        elif verbose:
                            print(f"[speaker] blocked: score={score:.3f}", flush=True)

                try:
                    chunk, captured_at = chunks.get(timeout=0.025)
                except queue.Empty:
                    continue
                if not enabled:
                    continue

                onset = meter.observe(chunk, captured_at)
                if verifier:
                    history.append(chunk)

                is_final = recognizer.AcceptWaveform(chunk)
                if is_final:
                    heard = json.loads(recognizer.Result()).get("text", "").strip()
                else:
                    heard = json.loads(recognizer.PartialResult()).get("partial", "").strip()
                decoded_at = time.monotonic()

                # Live partials: don't wait for trailing silence.
                spells = gate.feed(heard, final=is_final, now=decoded_at)
                if heard and verbose and (heard != last_partial or decoded_at - last_display > 1):
                    print(f"[heard] {heard}", flush=True)
                    last_partial = heard
                    last_display = decoded_at

                if spells:
                    if verifier:
                        pending.extend(spells)
                    else:
                        emit(spells, capture_at=captured_at, speech_onset=onset)

                if verifier and pending:
                    wav = b"".join(history)
                    if len(wav) >= int(16000 * 2 * 0.75) or is_final:
                        spells_to_check = tuple(pending)
                        pending.clear()
                        if len(wav) < int(16000 * 2 * 0.55):
                            if verbose:
                                print("[speaker] too short to verify, skipped", flush=True)
                        elif waiting_tasks < 3:
                            ticket = session
                            future = worker.submit(verifier.verify_pcm, wav)
                            future.add_done_callback(
                                lambda f, sp=spells_to_check, t=ticket, c=captured_at, o=onset:
                                    results.put((sp, f, t, c, o))
                            )
                            waiting_tasks += 1
                        elif verbose:
                            print("[speaker] busy, dropped", flush=True)

                if is_final:
                    history.clear()
                    pending.clear()
                    last_partial = ""
                    meter.reset()

    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as exc:
        print(f"Audio/runtime error: {exc}", file=sys.stderr)
        return 1
    finally:
        if worker:
            worker.shutdown(wait=False, cancel_futures=True)
        if bridge:
            bridge.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
