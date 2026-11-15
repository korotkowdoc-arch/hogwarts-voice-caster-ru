"""Local low-latency voice control for Hogwarts Legacy.

Default: direct Vosk partial -> SpellCaster shared memory, without voice ID.
Speaker identity verification can be explicitly enabled but costs latency.
"""
from __future__ import annotations

import argparse
import audioop
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
from .game_commands import to_game_command
from .latency import AudioDelayMeter
from .template_voice import PronunciationBank, SpeechSegmenter
from .recognition_policy import route_spells
from .model_storage import installed_model_path, model_layout_ok, migrate_legacy
from .spellbook import Spellbook
from .stream import StreamGate
from .windows import KeyboardState, VK_F9, down, game_focused, foreground_process_name

ROOT = Path(__file__).resolve().parents[2]
MODEL = installed_model_path(ROOT)
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
        try:
            game_name = to_game_command(args.send)
        except ValueError as exc:
            print(f"Invalid game command: {exc}", file=sys.stderr)
            return 2
        bridge = SpellBridge().connect()
        try:
            deadline = time.monotonic() + 2
            while not bridge.alive() and time.monotonic() < deadline:
                time.sleep(.08)
                bridge.poll()
            ok, reason = bridge.send(game_name)
            print(f"{args.send} -> {game_name}: {reason} (IPC only, not confirmed cast)")
            return 0 if ok else 1
        finally:
            bridge.close()

    # Default acoustic engine never asks Vosk to guess a word.
    try:
        selected_cfg = load_config(args.config)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Config error: {exc}", flush=True)
        return 2
    engine = selected_cfg.get("recognition_engine", "gigaam_ru")
    if engine == "gigaam_ru" and (args.dry_run or args.listen):
        from .ru_asr_listener import run as run_neural
        return run_neural(args, selected_cfg)
    if engine == "acoustic_dtw" and (args.dry_run or args.listen):
        from .dtw_listener import run as run_acoustic
        return run_acoustic(args, selected_cfg)

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
        if args.model == MODEL and not model_layout_ok(MODEL):
            migrate_legacy(ROOT, MODEL)
        if not model_layout_ok(args.model):
            raise FileNotFoundError(f"Model not found or incomplete: {args.model}. Run install.bat again.")
    except (ImportError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 2

    # Instantiate the model ONCE; no cloud round trip, no per-command loading.
    SetLogLevel(-1)
    print("Loading Russian offline model...", flush=True)
    try:
        model = Model(str(args.model))
    except Exception as exc:
        print(f"[MODEL ERROR] Vosk cannot load the model at: {args.model}", file=sys.stderr, flush=True)
        print(f"Details: {exc}. Run the updated install.bat to verify and repair the model.", file=sys.stderr, flush=True)
        if sys.platform == "win32" and not str(args.model).isascii():
            print("The model path contains non-English characters, unsupported by some Windows Vosk builds.", file=sys.stderr, flush=True)
        return 2
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
    bank = PronunciationBank.load()
    trained_spells = bank.trained_spells()
    # Listening without samples is unchanged. With samples, hold dubious Vosk
    # guesses until the live acoustic matcher has examined that phrase.
    segmenter = SpeechSegmenter(silence_ms=100) if trained_spells else None
    pending_vosk = []
    allow_fallback = bool(cfg.get("allow_untrained_vosk_fallback", False))
    print(f"Pronunciation templates: {len(trained_spells)} trained spell(s)", flush=True)
    if trained_spells:
        print("[policy] Strict learned spells only" if not allow_fallback else
              "[policy] WARNING: untrained Vosk fallback enabled; false spells possible",
              flush=True)
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
    show_partials = cfg.get("show_partials", True)
    mic_diagnostics = cfg.get("mic_diagnostics", True)
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
    if not args.dry_run:
        print("[help] Return to Hogwarts Legacy after pressing Start; "
              "the program window does NOT count as active game.", flush=True)
        print("[help] Use Check microphone to test while this window is active.", flush=True)
    if cfg.get("push_to_talk", False):
        print("Hold F9 to speak.", flush=True)

    focus_ok = False
    last_focus_checked = float("-inf")
    was_enabled = None
    last_heartbeat = float("-inf")
    last_partial = ""
    last_display = float("-inf")
    last_microphone_log = float("-inf")
    microphone_peak = 0
    last_mod_ready = None

    def emit(spells, *, capture_at, speech_onset, score=None):
        for spell in spells:
            before = time.monotonic()
            if args.dry_run:
                ok, reason = True, "TEST"
            else:
                # Do not trust a cached focus check at the moment of casting.
                if cfg.get("require_game_focus", True) and not game_focused():
                    print(f"[BLOCKED] {spell}: game not in foreground; "
                          f"active process = {foreground_process_name() or '(unknown)'}", flush=True)
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
                    pending_vosk.clear()
                    if segmenter:
                        segmenter.reset()
                    session += 1

                if bridge and now - last_heartbeat >= 0.16:
                    bridge.poll(now=now)
                    bridge.heartbeat()
                    last_heartbeat = now
                    mod_ready = bridge.alive(now=now)
                    if mod_ready != last_mod_ready:
                        print("[mod] READY: Hogwarts Legacy SpellCaster connected"
                              if mod_ready else
                              "[mod] NOT READY: waiting for game's UE4SS SpellCaster",
                              flush=True)
                        last_mod_ready = mod_ready

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
                    pending_vosk.clear()
                    if segmenter:
                        segmenter.reset()
                    session += 1
                    while True:
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            break
                    was_enabled = enabled
                    if enabled:
                        print("[focus] LISTENING: voice commands enabled", flush=True)
                    elif not hotkeys.active:
                        print("[focus] PAUSED: F8 pressed", flush=True)
                    elif cfg.get("push_to_talk", False) and not down(VK_F9):
                        print("[focus] WAITING: hold F9 to speak", flush=True)
                    elif not focus_ok:
                        name = foreground_process_name() or "(unknown process)"
                        print(f"[focus] BLOCKED: foreground is {name}; "
                              "switch to the game or disable focus restriction in app settings.",
                              flush=True)
                    else:
                        print("[focus] INACTIVE: waiting for game", flush=True)

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

                if mic_diagnostics:
                    rms = audioop.rms(chunk, 2)
                    microphone_peak = max(microphone_peak, rms)
                    if captured_at - last_microphone_log >= 1.5:
                        print(f"[mic] input active, peak RMS={microphone_peak} "
                              f"({'signal' if microphone_peak >= 400 else 'very quiet / silence'})",
                              flush=True)
                        microphone_peak = 0
                        last_microphone_log = captured_at

                onset = meter.observe(chunk, captured_at)
                completed_phrase = segmenter.feed(chunk) if segmenter else None
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
                if heard and (verbose or show_partials) and (
                    (heard != last_partial and decoded_at - last_display >= 0.18)
                    or decoded_at - last_display > 1.6
                ):
                    print(f"[heard] {heard}", flush=True)
                    last_partial = heard
                    last_display = decoded_at

                if spells:
                    if verifier:
                        pending.extend(spells)
                    elif segmenter:
                        pending_vosk.extend(spells)
                        if show_partials:
                            print(f"[candidate] {', '.join(spells)}: waiting for trained audio check",
                                  flush=True)
                    else:
                        emit(spells, capture_at=captured_at, speech_onset=onset)

                if completed_phrase is not None and not verifier:
                    try:
                        selected, score, reason = bank.match(
                            completed_phrase,
                            threshold=float(cfg.get("template_threshold", 0.78)),
                            margin=float(cfg.get("template_margin", 0.055))
                        )
                    except ValueError as exc:
                        selected, score, reason = None, 0.0, str(exc)
                    approved = route_spells(
                        trained_spells=trained_spells,
                        acoustic_spell=selected,
                        vosk_candidates=pending_vosk,
                        allow_untrained_fallback=allow_fallback,
                    )
                    if selected:
                        print(f"[trained] {selected}: similarity={score:.3f}", flush=True)
                    else:
                        if verbose or args.dry_run or mic_diagnostics:
                            print(f"[trained] No confident match: {reason} ({score:.3f})",
                                  flush=True)
                        if mic_diagnostics or args.dry_run:
                            try:
                                ranking = bank.rank(completed_phrase)[:3]
                                print("[rank] " + (", ".join(
                                    f"{spell}={value:.3f}" for spell, value in ranking)
                                    or "no recorded templates"), flush=True)
                            except ValueError:
                                pass
                        if pending_vosk and not approved:
                            print("[blocked] Vosk guessed "
                                  + ", ".join(pending_vosk)
                                  + "; acoustic recognition did not confirm the spell.",
                                  flush=True)
                    if approved:
                        emit(approved, capture_at=captured_at, speech_onset=onset)
                    pending_vosk.clear()

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
                    if not segmenter:
                        pending_vosk.clear()
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
