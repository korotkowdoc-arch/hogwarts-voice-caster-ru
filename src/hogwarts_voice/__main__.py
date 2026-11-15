"""Low-latency continuous Russian speech listener for Hogwarts Legacy.

Windows usage:
  python -m hogwarts_voice --list-mics
  python -m hogwarts_voice --dry-run
  python -m hogwarts_voice
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import sys
import time
from typing import Any

from .bridge import SpellBridge
from .spellbook import Spellbook
from .stream import StreamGate
from .windows import KeyboardState, VK_F9, down, game_focused

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "vosk-model-small-ru-0.22"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_SPELLS = ROOT / "spells.json"


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        cfg = json.load(file)
    if cfg["samplerate"] != 16000:
        raise ValueError("Use 16000 Hz: the Vosk model expects 16 kHz")
    if not 1 <= cfg["stable_partial_updates"] <= 8:
        raise ValueError("stable_partial_updates must be 1..8")
    return cfg


def args_parser():
    parser = argparse.ArgumentParser(description="Hogwarts Legacy: Russian offline voice spells")
    parser.add_argument("--list-mics", action="store_true", help="List microphone IDs")
    parser.add_argument("--dry-run", action="store_true", help="Recognize but don't send to game")
    parser.add_argument("--send", metavar="GAME_SPELL", help="Send one game spell, e.g. Lumos")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--spells", type=Path, default=DEFAULT_SPELLS)
    parser.add_argument("--model", type=Path, default=MODEL)
    return parser


def main():
    args = args_parser().parse_args()
    if os.name != "nt" and not args.dry_run and not args.list_mics:
        print("Only Windows is supported for in-game spell casting.", file=sys.stderr)
        return 2

    if args.send:
        bridge = SpellBridge().connect()
        try:
            deadline = time.monotonic() + 2.0
            while not bridge.alive() and time.monotonic() < deadline:
                time.sleep(0.1)
                bridge.poll()
            ok, reason = bridge.send(args.send)
            print(f"{args.send}: {reason}")
            return 0 if ok else 1
        finally:
            bridge.close()

    try:
        import sounddevice as sd
    except ImportError:
        print("Audio dependencies not installed; run install.bat", file=sys.stderr)
        return 2

    if args.list_mics:
        print(sd.query_devices())
        return 0

    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError:
        print("Vosk missing; run install.bat", file=sys.stderr)
        return 2

    try:
        cfg = load_config(args.config)
        with args.spells.open("r", encoding="utf-8") as file:
            spellbook = Spellbook(json.load(file))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if not args.model.is_dir():
        print(f"Model missing: {args.model}\nRun install.bat or python download_model.py", file=sys.stderr)
        return 2

    SetLogLevel(-1)
    print("Loading Russian offline model...", flush=True)
    model = Model(str(args.model))
    mode = cfg.get("grammar_mode", "constrained")
    if mode == "constrained":
        grammar = json.dumps(spellbook.grammar(), ensure_ascii=False)
        recognizer = KaldiRecognizer(model, cfg["samplerate"], grammar)
    elif mode == "free":
        recognizer = KaldiRecognizer(model, cfg["samplerate"])
    else:
        raise ValueError("grammar_mode must be constrained or free")

    gate = StreamGate(spellbook, cfg["stable_partial_updates"],
                      cfg["min_gap_ms"], cfg["repeat_gap_ms"])
    hotkeys = KeyboardState()
    bridge = None if args.dry_run else SpellBridge().connect()
    audio = queue.Queue(maxsize=6)
    frames = int(cfg["block_ms"] * cfg["samplerate"] / 1000)
    if frames < 160:
        raise ValueError("block_ms too low; use >=10")

    def on_audio(indata, count, timing, status):
        # Keep real-time callback cheap; never decode in callback.
        if status and cfg.get("verbose"):
            print(f"[audio] {status}", flush=True)
        chunk = bytes(indata)
        try:
            audio.put_nowait(chunk)
        except queue.Full:
            try:
                audio.get_nowait()
            except queue.Empty:
                pass
            try:
                audio.put_nowait(chunk)
            except queue.Full:
                pass

    device = cfg["mic_device"]
    mic_name = sd.query_devices(device, "input")["name"]
    print(f"\nMic: {mic_name}")
    print(f"Mode: {'voice test (no cast)' if args.dry_run else 'direct game casting / UE4SS'}")
    print(f"Audio blocks: {cfg['block_ms']} ms, stable partials: {cfg['stable_partial_updates']}")
    print("F8: enable/disable recognition | Ctrl+C: exit")
    if cfg["push_to_talk"]:
        print("F9: hold to speak")
    if cfg["require_game_focus"] and not args.dry_run:
        print("Commands only while Hogwarts Legacy has window focus.")
    print("Recognized words and commands are displayed below.\n", flush=True)

    last_hb_tick = 0.0
    last_focus = None
    last_partial = ""
    last_display = 0.0

    try:
        with sd.RawInputStream(samplerate=cfg["samplerate"],
                               blocksize=frames, channels=1, dtype="int16",
                               device=device, callback=on_audio):
            while True:
                now = time.monotonic()
                if hotkeys.update():
                    print(f"\n[voice] {'ON' if hotkeys.active else 'PAUSED'}", flush=True)
                    gate.reset_segment()
                    recognizer.Reset()

                if bridge and now - last_hb_tick >= 0.16:
                    bridge.poll(now=now)
                    bridge.heartbeat()
                    last_hb_tick = now

                focus_ok = args.dry_run or not cfg["require_game_focus"] or game_focused()
                enabled = hotkeys.active and focus_ok and (
                    not cfg["push_to_talk"] or down(VK_F9)
                )
                if enabled != last_focus:
                    gate.reset_segment()
                    recognizer.Reset()
                    while True:
                        try:
                            audio.get_nowait()
                        except queue.Empty:
                            break
                    last_focus = enabled
                    if cfg.get("verbose"):
                        print(f"[voice] {'listening' if enabled else 'muted'}", flush=True)

                try:
                    chunk = audio.get(timeout=0.04)
                except queue.Empty:
                    continue
                if not enabled:
                    continue

                is_final = recognizer.AcceptWaveform(chunk)
                if is_final:
                    transcript = json.loads(recognizer.Result()).get("text", "")
                else:
                    transcript = json.loads(recognizer.PartialResult()).get("partial", "")
                transcript = transcript.strip()

                if transcript and (transcript != last_partial or now - last_display > 1):
                    if cfg.get("verbose"):
                        print(f"[heard] {transcript}", flush=True)
                    last_display = now
                    last_partial = transcript

                detected = gate.feed(transcript, final=is_final, now=now)
                for spell in detected:
                    if args.dry_run:
                        print(f"{spell} [TEST]", flush=True)
                    elif bridge:
                        ok, reason = bridge.send(spell, now=now)
                        print(f"{spell} [{'OK' if ok else reason}]", flush=True)
                if is_final:
                    last_partial = ""

    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Audio device/runtime error: {e}", file=sys.stderr)
        print("Try another mic_device or enable microphone permissions.", file=sys.stderr)
        return 1
    finally:
        if bridge:
            bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
