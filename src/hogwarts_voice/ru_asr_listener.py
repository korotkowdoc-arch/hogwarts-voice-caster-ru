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
from .ru_asr import (
    RussianASR, RussianTransducerASR,
    load_spell_aliases, match_incantation, DEFAULT_ENABLED
)
from .early_decode import EarlyDecode
from .vad import AdaptiveSpeechSegmenter
from .windows import KeyboardState, down, game_focused, foreground_process_name
from .voice_presets import DEFAULT_STYLE, validate_style, STYLE_LABELS
from .game_commands import to_game_command
from .game_interactions import ACTION_IDS, interact_with_lock, validate_interact_key
from .game_feedback import ModLogMonitor, find_log
from .windows import foreground_process_path

def run(args, cfg):
    try:
        import sounddevice as sd
    except ImportError:
        print("[setup] Missing sounddevice. Run install.bat.", flush=True)
        return 2

    try:
        import sherpa_onnx
        backend = cfg.get("asr_backend", "ctc")
        if backend not in ("ctc", "transducer"):
            raise ValueError(f"Invalid asr_backend: {backend}")
        engine_class = RussianTransducerASR if backend == "transducer" else RussianASR
        print(f"[engine] Loading GigaAM v2 Russian {backend.upper()} model "
              "(CPU, offline)...", flush=True)
        neural = engine_class(num_threads=int(cfg.get("asr_threads", 4)))
    except Exception as exc:
        print(f"[setup] Russian model error: {exc}", flush=True)
        print("[setup] Run the latest install.bat to install the neural engine.",
              flush=True)
        return 2

    spellbook = load_spell_aliases()
    try:
        voice_style = validate_style(cfg.get("voice_style", DEFAULT_STYLE))
    except ValueError as exc:
        print(f"[setup] {exc}", flush=True)
        return 2
    game_allowed = cfg.get("enabled_spells", list(DEFAULT_ENABLED))
    if not isinstance(game_allowed, list) or not all(
        isinstance(item, str) and item in spellbook for item in game_allowed
    ):
        print("[setup] Invalid enabled_spells in config.json", flush=True)
        return 2
    # A microphone TEST never sends commands. Allow testing the entire spell
    # dictionary, even spells that have not been enabled for real gameplay.
    dry_run = bool(args.dry_run)
    allowed = list(spellbook) if dry_run else game_allowed
    print("[engine] Russian GigaAM v2 ready. No voice samples needed.", flush=True)
    print(f"[style] {STYLE_LABELS[voice_style]}", flush=True)
    if dry_run:
        print(f"[allowed] TEST: all {len(allowed)} known incantations; "
              "none are sent to the game.", flush=True)
    else:
        print(f"[allowed] GAME: {', '.join(allowed) or '(none)'}", flush=True)
        if not allowed:
            print("[setup] No spells enabled: voice casts are disabled.", flush=True)

    ptt_mode = bool(cfg.get("push_to_talk", True))
    ptt_name = cfg.get("ptt_key", "F9")
    try:
        ptt_vk = key_code(ptt_name) if ptt_mode else None
    except ValueError as exc:
        print(f"[setup] {exc}", flush=True)
        return 2
    # Existing installs saved fast=20ms before v1.2; promote this to
    # 10ms automatically without forcing config.json replacement.
    configured_block = int(cfg.get("block_ms", 20))
    block_ms = (10 if cfg.get("performance_mode", "fast") == "fast"
                and configured_block == 20 else configured_block)
    frames = int(16000 * block_ms / 1000)
    try:
        interact_key = validate_interact_key(cfg.get("interaction_key", "F"))
    except ValueError as exc:
        print(f"[setup] {exc}", flush=True)
        return 2
    focus_required = not dry_run and cfg.get("require_game_focus", True)
    recorder = PushToTalkCapture()
    early_enabled = bool(cfg.get("early_decode", True)) and ptt_mode
    early = EarlyDecode()
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
    mod_feedback = None
    last_log_search = float("-inf")

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

    def decode_task(pcm):
        t0 = time.monotonic()
        transcript = neural.transcribe(pcm)
        return transcript, (time.monotonic() - t0) * 1000

    def start_decode(pcm: bytes, *, recorded_at: float, started_at: float,
                     preview_future=None):
        nonlocal awaiting
        if awaiting:
            print("[blocked] Previous spell is still being decoded; press again.",
                  flush=True)
            return
        awaiting = True
        current = generation
        task_start = time.monotonic()
        reuse = preview_future is not None
        future = preview_future if reuse else executor.submit(decode_task, pcm)
        future.add_done_callback(
            lambda item, gen=current, t0=task_start,
                   recorded=recorded_at, begun=started_at, early=reuse:
                answers.put((gen, item, t0, recorded, begun, early))
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
        print(f"[perf] mic block={block_ms}ms, CPU threads="
              f"{cfg.get('asr_threads', 4)}; "
              f"speculative={'on' if early_enabled else 'off'}; "
              f"model stays loaded", flush=True)
        print(f"[actions] Alohomora interacts with nearby lock using {interact_key}. "
              "A lock minigame may still appear.", flush=True)
        with sd.RawInputStream(
            samplerate=16000, blocksize=frames, channels=1, dtype="int16",
            device=mic, callback=on_audio
        ):
            while True:
                now = time.monotonic()
                if hotkeys.update():
                    print(f"[voice] {'ON' if hotkeys.active else 'PAUSED'}", flush=True)
                    recorder.reset()
                    early.reset()
                    segmenter.reset()
                    generation += 1
                    clear_audio()

                # Only the game's own UE4SS.log may positively confirm casts.
                # Discover it lazily when Hogwarts Legacy is foreground; no
                # user folder selection required for most Steam/Epic installs.
                if bridge and game_focused() and mod_feedback is None and now-last_log_search > 3:
                    last_log_search = now
                    log = find_log(cfg.get("game_folder"), foreground_process_path())
                    if log:
                        mod_feedback = ModLogMonitor(log)
                        mod_feedback.begin()
                        print(f"[game-log] Monitoring: {log}", flush=True)
                if mod_feedback is not None:
                    for event in mod_feedback.poll(now=now):
                        print(f"[game:{event.state}] {event.spell} | "
                              f"{event.detail}; elapsed={event.latency_ms}ms",
                              flush=True)

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
                    early.reset()
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
                        early.reset()
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
                            reused = early.release_future(pcm) if early_enabled else None
                            start_decode(pcm, recorded_at=now, started_at=pressed_at,
                                         preview_future=reused)
                        else:
                            early.reset()
                            print("[blocked] Invalid hold length. Nothing cast.", flush=True)
                    elif not enabled and recorder.held:
                        recorder.reset()
                        early.reset()
                        print("[ptt] CANCELLED (focus lost or paused)", flush=True)
                    old_pressed = pressed

                while True:
                    try:
                        result_generation, future, submitted, released, started, used_preview = answers.get_nowait()
                    except queue.Empty:
                        break
                    awaiting = False
                    if result_generation != generation or not enabled:
                        continue
                    try:
                        transcript, inference_ms = future.result()
                    except Exception as exc:
                        print(f"[asr] Decoding error: {exc}", flush=True)
                        continue
                    spell, reason = match_incantation(
                        transcript, spellbook, allowed, style=voice_style
                    )
                    print(f"[heard] {transcript or '(silence)'}", flush=True)
                    elapsed_ms = (time.monotonic() - released) * 1000
                    print(f"[asr] GigaAM {backend} inference={inference_ms:.0f}ms; "
                          f"release-to-text={elapsed_ms:.0f}ms; match={reason}",
                          flush=True)
                    print(f"[latency] inference={inference_ms:.0f}ms "
                          f"after-release={elapsed_ms:.0f}ms "
                          f"speculative={'yes' if used_preview else 'no'}",
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
                    if spell in ACTION_IDS:
                        game_command = f"interact:{interact_key}"
                        if dry_run:
                            ok, result = True, "TEST"
                        else:
                            ok, result = interact_with_lock(key=interact_key)
                        if ok:
                            last_sent_spell, last_sent_at = spell, now
                        print(f"[{result}] {spell} -> {game_command} | "
                              f"release-to-action="
                              f"{(time.monotonic()-released)*1000:.0f}ms",
                              flush=True)
                        if ok and not dry_run:
                            print("[action] Interaction key pressed. Only a nearby "
                                  "locked door/chest can start Alohomora; "
                                  "the puzzle is not bypassed.", flush=True)
                        continue
                    try:
                        game_command = to_game_command(spell)
                    except ValueError as exc:
                        print(f"[blocked] {exc}; nothing sent.", flush=True)
                        continue
                    if dry_run:
                        ok, result = True, "TEST"
                    else:
                        ok, result = bridge.send(game_command)
                    if ok:
                        last_sent_spell = spell
                        last_sent_at = now
                        if mod_feedback is not None and not dry_run:
                            mod_feedback.record_sent(spell, game_command, now=now)
                    print(f"[{result}] {spell} -> {game_command} | release-to-dispatch="
                          f"{(time.monotonic()-released)*1000:.0f}ms; "
                          f"press-to-dispatch={(time.monotonic()-started)*1000:.0f}ms",
                          flush=True)
                    if ok and not dry_run:
                        if mod_feedback is not None:
                            print("[ipc] Command queued; awaiting UE4SS log result.",
                                  flush=True)
                        else:
                            print("[ipc] Command queued; UE4SS.log not found. "
                                  "Actual cast is UNVERIFIED.",flush=True)

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
                        if early_enabled and not awaiting and not recorder.overlong:
                            def submit_preview(snapshot):
                                print("[perf] Speech ended while Mouse PTT still held; "
                                      "started early decode.", flush=True)
                                return executor.submit(decode_task, snapshot)
                            early.feed(
                                audio, snapshot=lambda: b"".join(recorder.frames),
                                submit=submit_preview,
                            )
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
