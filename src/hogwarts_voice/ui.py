"""Tkinter wizard: original spell sigils, pronunciation, mic enrollment and app launch.

No microphone recordings are persisted: only speaker vectors and manually
confirmed text aliases in LOCALAPPDATA. All heavy work happens in a thread.
"""
from __future__ import annotations

import json
from math import cos, pi, sin
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .voice_profile import VoiceProfile, profile_path
from .spellbook import Spellbook
from .__main__ import ROOT, MODEL, DEFAULT_CONFIG, DEFAULT_SPELLS

INK = "#e9eef8"
MUTED = "#abb9d2"
BG = "#0c1322"
SURFACE = "#142039"
ACCENT = "#9cc7ff"
PINK = "#f0b5db"
DARK = "#192941"

# UI wording is independent of the ASR grammar; actual recognition aliases
# are kept in the editable spells.json file / local confirmed custom aliases.
READINGS = {
    "Accio": ("Акцио", "AK-ee-oh"), "Levioso": ("Левиосо", "leh-vee-OH-soh"),
    "Depulso": ("Депульсо", "deh-PUL-soh"), "Descendo": ("Десцендо", "deh-SEN-doh"),
    "Flipendo": ("Флипендо", "flih-PEN-doh"), "Glacius": ("Глациус", "GLAY-see-us"),
    "ArrestoMomentum": ("Арресто Моментум", "ah-RES-toh moh-MEN-tum"),
    "Incendio": ("Инсендио", "in-SEN-dee-oh"), "Confringo": ("Конфринго", "kon-FRING-goh"),
    "Diffindo": ("Диффиндо", "dih-FIN-doh"), "Bombarda": ("Бомбарда", "bom-BAR-dah"),
    "Stupefy": ("Ступефай", "STOO-puh-fy"),
    "Expelliarmus": ("Экспеллиармус", "eks-pel-ee-AR-mus"),
    "Protego": ("Протего", "proh-TAY-goh"), "Oppugno": ("Оппуньо", "oh-PUG-noh"),
    "Lumos": ("Люмос", "LOO-mos"), "Nox": ("Нокс", "NOKS"),
    "Reparo": ("Репаро", "reh-PAR-oh"), "Revelio": ("Ревелио", "reh-VEH-lee-oh"),
    "Disillusionment": ("Дезиллюминация", "dis-ill-OO-zhun"),
    "Wingardium": ("Вингардиум Левиоса", "win-GAR-dee-um lev-ee-OH-sah"),
    "Transformation": ("Трансформация", "trans-for-MAY-shun"),
    "Vanishment": ("Эванеско", "ev-ah-NES-koh"),
    "Crucio": ("Круцио", "KROO-see-oh"),
    "Imperius": ("Империо", "im-PEH-ree-oh"),
    "AvadaKedavra": ("Авада Кедавра", "ah-VAH-dah keh-DAH-vrah"),
    "Finisher": ("Древняя магия", "ancient magic"),
    "AppareVestigium": ("Путь к цели", "show objective path"),
}

def label(parent, text, *, size=12, color=INK, weight="normal", **options):
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                    font=("Segoe UI", size, weight), **options)

def sigil(canvas: tk.Canvas, name: str):
    """Procedurally draw an original, repeatable sigil for every spell.

    These are original decorative illustrations, not copyrighted game icons.
    """
    canvas.delete("all")
    w, h = 320, 190
    canvas.configure(width=w, height=h, bg=SURFACE, highlightthickness=0)
    cx, cy = 160, 92
    val = sum((i + 1) * ord(ch) for i, ch in enumerate(name))
    palette = ["#8ddbf1", "#c9a2ff", "#ffbb86", "#99e5bc", "#f3b6de"]
    color = palette[val % len(palette)]
    canvas.create_oval(84, 16, 236, 168, outline="#2e4668", width=1)
    canvas.create_oval(102, 34, 218, 150, outline=color, width=2)
    canvas.create_oval(122, 54, 198, 130, outline="#59718f", width=1)
    sides = 7 + val % 5
    for n in range(sides):
        a = 2 * pi * n / sides - pi / 2
        r1 = 56
        r2 = 70 + ((val // (n + 1)) % 9)
        canvas.create_line(cx + r1*cos(a), cy + r1*sin(a),
                           cx + r2*cos(a), cy + r2*sin(a), fill=color, width=2)
        canvas.create_oval(cx + (r2+2)*cos(a)-2, cy + (r2+2)*sin(a)-2,
                           cx + (r2+2)*cos(a)+2, cy + (r2+2)*sin(a)+2,
                           fill=color, outline="")
    points = []
    for n in range(10):
        radius = 32 if n % 2 == 0 else 14
        theta = 2 * pi * n / 10 - pi / 2
        points.extend((cx + radius*cos(theta), cy + radius*sin(theta)))
    canvas.create_polygon(*points, fill=color, outline="#ffffff", width=1)
    # Inner glyph is spell-specific and legible at small sizes.
    canvas.create_text(cx, cy, text=name[0].upper(), fill=BG,
                       font=("Segoe UI Semibold", 18, "bold"))

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hogwarts Voice Caster · RU")
        self.root.geometry("620x670")
        self.root.minsize(550, 590)
        self.root.configure(bg=BG)
        self.proc = None
        self.wizard = None
        self.config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        with DEFAULT_SPELLS.open(encoding="utf-8") as f:
            self.book = Spellbook(json.load(f))
        self.profile = VoiceProfile.load()
        self.titlebar()
        self.main()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        # Voice enrollment is optional: nothing delays the first game launch.

    def titlebar(self):
        frame = tk.Frame(self.root, bg=BG, pady=22)
        frame.pack(fill="x")
        label(frame, "HOGWARTS VOICE CASTER", size=22, weight="bold").pack()
        label(frame, "Твои заклинания. Минимум ожидания.", color=MUTED).pack(pady=(6, 0))

    def main(self):
        panel = tk.Frame(self.root, bg=SURFACE, padx=24, pady=22)
        panel.pack(fill="both", expand=True, padx=28, pady=(5, 20))
        self.status = label(panel, "", size=12, color=PINK, justify="left", wraplength=460)
        self.status.pack(anchor="w", pady=(0, 14))
        label(panel, "Готово без обучения. Сначала проверь микрофон,\n"
                     "затем запускай быстрые голосовые заклинания.",
              color=MUTED, justify="left").pack(anchor="w", pady=(0, 8))
        self.add_microphone_picker(panel)
        self.add_speed_picker(panel)
        actions = tk.Frame(panel, bg=SURFACE)
        actions.pack(fill="x", pady=5)
        self.play = tk.Button(actions, text="▶  Начать колдовать", font=("Segoe UI", 13, "bold"),
                              command=lambda: self.launch(False), bg="#9cc7ff", fg=BG,
                              activebackground="#d4e5ff", relief="flat", padx=14, pady=9)
        self.play.pack(fill="x", pady=(0, 8))
        tk.Button(actions, text="🎤  Настроить произношение (по желанию)",
                  command=self.open_wizard, bg=DARK, fg=INK, relief="flat",
                  font=("Segoe UI", 11), pady=9).pack(fill="x", pady=4)
        tk.Button(actions, text="Проверить распознавание без игры", command=lambda: self.launch(True),
                  bg=DARK, fg=INK, relief="flat", font=("Segoe UI", 11), pady=9).pack(fill="x", pady=4)
        tk.Button(actions, text="Остановить", command=self.stop,
                  bg=DARK, fg=MUTED, relief="flat", font=("Segoe UI", 11), pady=7).pack(fill="x", pady=4)
        label(panel, "F8 — пауза · Без интернета · Нужен UE4SS-мод SpellCaster",
              color=MUTED, size=9).pack(anchor="w", pady=(16, 0))
        self.refresh()

    def add_microphone_picker(self, panel):
        frame = tk.Frame(panel, bg=SURFACE)
        frame.pack(fill="x", pady=(0, 8))
        label(frame, "Микрофон:", color=MUTED, size=10).pack(side="left", padx=(0, 10))
        self.mic_choices = [(None, "По умолчанию")]
        try:
            import sounddevice as sd
            for number, device in enumerate(sd.query_devices()):
                if device.get("max_input_channels", 0) > 0:
                    self.mic_choices.append((number, f"{number}: {device['name']}"))
        except Exception:
            pass
        names = [value for _, value in self.mic_choices]
        stored = self.config.get("mic_device")
        current = next((i for i, (idx, _) in enumerate(self.mic_choices) if idx == stored), 0)
        self.mic_index = tk.StringVar(value=names[current])
        selector = ttk.Combobox(frame, state="readonly", values=names, textvariable=self.mic_index)
        selector.pack(side="left", fill="x", expand=True)
        selector.bind("<<ComboboxSelected>>", self.change_mic)

    def change_mic(self, _event=None):
        label_text = self.mic_index.get()
        for index, name in self.mic_choices:
            if label_text == name:
                self.config["mic_device"] = index
                DEFAULT_CONFIG.write_text(json.dumps(self.config, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
                break

    def add_speed_picker(self, panel):
        frame = tk.Frame(panel, bg=SURFACE)
        frame.pack(fill="x", pady=(0, 7))
        label(frame, "Режим:", color=MUTED, size=10).pack(side="left", padx=(0, 23))
        values = ["Максимальная скорость", "Сбалансированный"]
        selected = values[1] if self.config.get("performance_mode") == "balanced" else values[0]
        self.speed_choice = tk.StringVar(value=selected)
        selector = ttk.Combobox(frame, state="readonly", values=values,
                                textvariable=self.speed_choice)
        selector.pack(fill="x", expand=True)
        selector.bind("<<ComboboxSelected>>", self.change_speed)
        label(panel, "Быстрый режим реагирует на первое распознавание, но может ошибаться.",
              size=9, color=MUTED).pack(anchor="w", pady=(0, 6))

    def change_speed(self, _event=None):
        fast = self.speed_choice.get() == "Максимальная скорость"
        self.config["performance_mode"] = "fast" if fast else "balanced"
        self.config["block_ms"] = 20 if fast else 32
        self.config["stable_partial_updates"] = 1 if fast else 2
        DEFAULT_CONFIG.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.refresh()

    def refresh(self):
        self.profile = VoiceProfile.load()
        if self.config.get("speaker_verification", False):
            ready = self.profile.ready()
            self.status.configure(
                text=("● Проверка голоса включена" if ready
                      else "● Проверка голоса требует обучения. Отключи её в config.json."),
                fg="#a7edcc" if ready else PINK)
            self.play.configure(state="normal" if ready else "disabled")
        else:
            self.status.configure(text="● Быстрый режим · Проверка личности отключена",
                                  fg="#a7edcc")
            self.play.configure(state="normal")

    def launch(self, test=False):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Уже запущено", "Распознавание уже работает.")
            return
        if not test and self.config.get("speaker_verification", False) and not self.profile.ready():
            self.open_wizard()
            return
        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        cmd = [sys.executable, "-m", "hogwarts_voice", "--dry-run" if test else "--listen"]
        try:
            self.proc = subprocess.Popen(cmd, cwd=str(ROOT), creationflags=flags)
        except OSError as exc:
            messagebox.showerror("Не удалось запустить", str(exc))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None

    def open_wizard(self):
        if self.wizard and self.wizard.win.winfo_exists():
            self.wizard.win.lift()
            self.wizard.win.focus_set()
            return
        self.wizard = Wizard(self)

    def close(self):
        self.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

class Wizard:
    def __init__(self, app: App):
        self.app = app
        self.book = app.book
        self.profile = VoiceProfile.load()
        self.spells = list(self.book.entries)
        self.practice = {}
        self.index = 0
        self.last_guess = ""
        self.busy = False
        self.encoder = None
        self.model = None
        self.events: queue.Queue = queue.Queue()

        win = tk.Toplevel(app.root)
        self.win = win
        win.title("Тренировка произношения · Заклинания")
        win.geometry("650x730")
        win.minsize(540, 640)
        win.configure(bg=BG)
        win.transient(app.root)
        win.grab_set()

        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=27, pady=16)
        self.progress = label(frame, "", size=11, color=MUTED)
        self.progress.pack(pady=(4, 6))
        label(frame, "ПРОИЗНЕСИ ЗАКЛИНАНИЕ", size=18, weight="bold").pack(pady=5)
        self.picture = tk.Canvas(frame, width=320, height=190, bg=SURFACE, highlightthickness=0)
        self.picture.pack(pady=(8, 8))
        self.name_ru = label(frame, "", size=23, weight="bold")
        self.name_ru.pack(pady=(5, 1))
        self.name_en = label(frame, "", size=13, color=ACCENT)
        self.name_en.pack()
        self.phonetic = label(frame, "", size=11, color=MUTED)
        self.phonetic.pack(pady=(3, 15))
        self.count_label = label(frame, "", size=11, color=ACCENT)
        self.count_label.pack(pady=3)
        self.record = tk.Button(frame, text="🎤  Произнести (3 секунды)",
                                command=self.record_click, bg="#9cc7ff", fg=BG,
                                font=("Segoe UI", 12, "bold"), relief="flat",
                                padx=12, pady=12)
        self.record.pack(fill="x", pady=(6, 11))
        self.notice = label(frame, "Запиши 3 произнесения в спокойной обстановке.",
                            color=MUTED, wraplength=530)
        self.notice.pack(pady=4)
        self.guess_label = label(frame, "Распознавание произношения: —", size=10, color=MUTED)
        self.guess_label.pack(pady=(7, 4))
        self.alias = tk.Button(frame, text="Запомнить услышанный вариант",
                               command=self.confirm_alias, bg=DARK, fg=INK,
                               relief="flat", state="disabled", pady=7)
        self.alias.pack(fill="x", pady=4)
        navigation = tk.Frame(frame, bg=BG)
        navigation.pack(fill="x", pady=(15, 6))
        self.back = tk.Button(navigation, text="← Назад", command=self.prev, bg=DARK,
                              fg=INK, relief="flat", padx=18, pady=9)
        self.back.pack(side="left")
        self.skip = tk.Button(navigation, text="Пропустить →", command=self.next,
                              bg=DARK, fg=INK, relief="flat", padx=18, pady=9)
        self.skip.pack(side="right")
        tk.Button(frame, text="Завершить настройку", command=self.finish,
                  bg=BG, fg=MUTED, relief="flat", pady=8).pack(pady=4)
        label(frame, "Записи остаются в памяти только во время распознавания.\n"
                     "Сохраняются лишь подтверждённые тобой варианты произношения.",
              size=9, color=MUTED, justify="center").pack(side="bottom")
        self.draw()
        win.after(120, self.poll)

    @property
    def spell(self):
        return self.spells[self.index]

    def draw(self):
        spell = self.spell
        sigil(self.picture, spell)
        ru, phon = READINGS.get(spell, (spell, spell))
        self.name_ru.configure(text=ru)
        self.name_en.configure(text=spell)
        self.phonetic.configure(text=f"English pronunciation: {phon}")
        self.progress.configure(text=f"Заклинание {self.index + 1} из {len(self.spells)}")
        self.count_label.configure(text=f"Попыток: {min(self.practice.get(spell, 0), 3)} / 3")
        self.notice.configure(text="Нажми на микрофон, дождись сигнала и произнеси заклинание.")
        self.last_guess = ""
        self.guess_label.configure(text="Распознавание произношения: —")
        self.alias.configure(state="disabled")
        self.back.configure(state="normal" if self.index else "disabled")
        self.skip.configure(text="Далее →" if self.practice.get(spell, 0) >= 3 else "Пропустить →")
        self.record.configure(state="normal")

    def prev(self):
        if self.busy or self.index == 0:
            return
        self.index -= 1
        self.draw()

    def next(self):
        if self.busy:
            return
        if self.index + 1 == len(self.spells):
            self.finish()
            return
        self.index += 1
        self.draw()

    def record_click(self):
        if self.busy:
            return
        self.busy = True
        self.record.configure(state="disabled")
        self.back.configure(state="disabled")
        self.skip.configure(state="disabled")
        self.alias.configure(state="disabled")
        self.notice.configure(text="Подготовка микрофона…", fg=ACCENT)
        spell = self.spell
        threading.Thread(target=self.worker, args=(spell,), daemon=True).start()

    def worker(self, spell: str):
        try:
            import numpy as np
            import sounddevice as sd
            # Calibration uses Vosk alone. Speaker identity model is optional.
            if self.model is None and MODEL.is_dir():
                from vosk import Model
                self.model = Model(str(MODEL))
            self.events.put(("recording", spell, None))
            if sys.platform == "win32":
                import winsound
                winsound.Beep(740, 95)
            wav = sd.rec(int(2.8 * 16000), samplerate=16000,
                         channels=1, dtype="float32",
                         device=self.app.config.get("mic_device"))
            sd.wait()
            mono = wav.flatten().copy()
            embedding = None
            if self.app.config.get("speaker_verification", False):
                from .speaker import SpeakerEncoder
                if self.encoder is None:
                    self.encoder = SpeakerEncoder()
                embedding = self.encoder.encode_float(mono)
            heard = ""
            if self.model:
                from vosk import KaldiRecognizer
                rec = KaldiRecognizer(self.model, 16000)
                pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes()
                rec.AcceptWaveform(pcm)
                heard = json.loads(rec.FinalResult()).get("text", "").strip()
            self.events.put(("result", spell, (embedding, heard)))
        except Exception as exc:
            self.events.put(("error", spell, str(exc)))

    def poll(self):
        try:
            while True:
                kind, spell, result = self.events.get_nowait()
                if kind == "recording":
                    self.notice.configure(text="● Идёт запись — произнеси заклинание сейчас.", fg=ACCENT)
                elif kind == "error":
                    self.busy = False
                    self.notice.configure(text=f"Запись не удалась: {result}", fg=PINK)
                    self.record.configure(state="normal")
                    self.skip.configure(state="normal")
                    self.back.configure(state="normal" if self.index else "disabled")
                elif kind == "result":
                    embedding, heard = result
                    if embedding is not None:
                        self.profile.add_take(spell, embedding)
                        self.profile.save()
                    self.practice[spell] = self.practice.get(spell, 0) + 1
                    self.busy = False
                    self.notice.configure(text="Попытка записана ✓", fg="#a7edcc")
                    self.count_label.configure(text=f"Попыток: {min(self.practice[spell], 3)} / 3")
                    self.guess_label.configure(text=f"Распознано: {heard or '(не разобрано)'}")
                    self.last_guess = heard
                    self.alias.configure(state="normal" if heard else "disabled")
                    self.record.configure(state="normal")
                    self.skip.configure(state="normal")
                    self.back.configure(state="normal" if self.index else "disabled")
                    if self.practice.get(spell, 0) >= 3 and self.index + 1 < len(self.spells):
                        # Give a moment to inspect ASR result and explicitly accept an alias.
                        self.notice.configure(text="3/3 готово. Нажми «Далее» или запомни вариант.", fg="#a7edcc")
                    self.app.refresh()
        except queue.Empty:
            pass
        if self.win.winfo_exists():
            self.win.after(120, self.poll)

    def confirm_alias(self):
        if not self.last_guess:
            return
        try:
            self.profile.add_alias(self.spell, self.last_guess, self.book)
            self.profile.save()
        except ValueError as exc:
            messagebox.showwarning("Вариант не принят", str(exc), parent=self.win)
        else:
            self.alias.configure(state="disabled")
            self.notice.configure(text="Произношение добавлено в личный словарь.", fg="#a7edcc")

    def finish(self):
        if self.busy:
            messagebox.showinfo("Запись", "Сначала заверши текущую запись.", parent=self.win)
            return
        # Pronunciation practice is optional. No enrollment gate in fast mode.
        self.win.destroy()
        self.app.wizard = None
        self.app.refresh()

def main():
    App().run()
    return 0
