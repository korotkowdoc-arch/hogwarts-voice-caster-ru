"""Dark, accessible desktop UI. No console windows are required."""
from __future__ import annotations

import json
from collections import deque
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import webbrowser

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox
from .spell_meta import READINGS, palette_of
from .voice_presets import DEFAULT_STYLE, STYLE_LABELS, visible_name
from .icon_assets import SOURCE_PAGE, count_icons, has_icon, icon_file, import_zip
from .spellbook import Spellbook
from .voice_profile import VoiceProfile
from .dtw_voice import DTWBank as PronunciationBank
from .training_capture import capture_one_hold
from .__main__ import ROOT, MODEL, DEFAULT_CONFIG, DEFAULT_SPELLS

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BASE = "#0b111b"
SIDE = "#101825"
PANEL = "#172231"
RAISED = "#1c2a3b"
BORDER = "#2c3a4e"
TEXT = "#ecf0f7"
MUTED = "#a2b0c3"
GOLD = "#d7bd86"
GOLD_HOVER = "#f4dca8"
GREEN = "#99dab8"
RED = "#eea9a2"
DARK_GOLD = "#28271f"
FONT = "Segoe UI"
DISPLAY = "Georgia"

def heading(master, value, size=24, *, color=TEXT, weight="normal"):
    return ctk.CTkLabel(master, text=value, text_color=color,
                        font=ctk.CTkFont(family=DISPLAY, size=size, weight=weight))

def text(master, value, size=13, *, color=MUTED, weight="normal",
         justify="left", wraplength=None):
    opts = {}
    if wraplength is not None:
        opts["wraplength"] = wraplength
    return ctk.CTkLabel(master, text=value, text_color=color, justify=justify,
                        font=ctk.CTkFont(family=FONT, size=size, weight=weight), **opts)

def button(master, label, command, *, primary=False, width=None, height=46):
    props = dict(
        text=label, command=command, height=height, corner_radius=10,
        font=ctk.CTkFont(family=FONT, size=14, weight="bold" if primary else "normal"),
        fg_color=GOLD if primary else RAISED,
        hover_color=GOLD_HOVER if primary else "#304057",
        text_color=BASE if primary else TEXT,
        border_width=0 if primary else 1,
        border_color=BORDER,
    )
    if width is not None:
        props["width"] = width
    return ctk.CTkButton(master, **props)

def picture(master, spell: str, *, size=192):
    """Only actual, explicitly imported game art is rendered as an icon."""
    if not has_icon(spell):
        wrapper = ctk.CTkFrame(master, corner_radius=14, fg_color="#111a29",
                               border_color=BORDER, border_width=1)
        heading(wrapper, "Иконка не загружена", size=18, color=MUTED).pack(pady=(size//3, 10))
        text(wrapper, "Импортируй оригинальный набор\nиз меню приложения",
             size=12, justify="center").pack()
        return wrapper
    wrapper = ctk.CTkFrame(master, corner_radius=14, fg_color="#111a29",
                           border_color=BORDER, border_width=1)
    with Image.open(icon_file(spell)) as opened:
        image = ctk.CTkImage(light_image=opened.copy(), dark_image=opened.copy(),
                             size=(size, size))
    ctk.CTkLabel(wrapper, text="", image=image).pack(expand=True, fill="both", padx=14, pady=14)
    return wrapper

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Hogwarts Voice Caster — RU")
        self.geometry("1100x730")
        self.minsize(1000, 640)
        self.configure(fg_color=BASE)

        self.config_data = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        with DEFAULT_SPELLS.open("r", encoding="utf-8") as source:
            self.book = Spellbook(json.load(source))
        self.events = queue.Queue()
        self.proc = None
        self.wizard = None
        self._active_page = "home"
        self._log_history = deque(maxlen=200)
        self._closed = False
        self._proc_generation = 0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=SIDE)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=BASE)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)

        self.draw_sidebar()
        self.draw_home()
        self.after(110, self.pump)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def draw_sidebar(self):
        s = self.sidebar
        heading(s, "HOGWARTS", size=25, color=GOLD).pack(anchor="w", padx=27, pady=(35, 0))
        heading(s, "VOICE CASTER", size=19).pack(anchor="w", padx=27, pady=(0, 5))
        text(s, "МАГИЯ БЕЗ КЛАВИШ", size=10).pack(anchor="w", padx=28, pady=(0, 38))
        ctk.CTkFrame(s, height=1, fg_color=BORDER).pack(fill="x", padx=23, pady=(0, 20))

        button(s, "Главная", self.draw_home).pack(fill="x", padx=17, pady=5)
        button(s, "Атлас заклинаний", self.open_wizard).pack(fill="x", padx=17, pady=5)
        button(s, "Доступные заклинания", self.draw_spell_settings).pack(
            fill="x", padx=17, pady=5)
        button(s, "Импорт игровых иконок", self.import_icons).pack(fill="x", padx=17, pady=5)
        button(s, "Источник иконок", lambda: webbrowser.open(SOURCE_PAGE)).pack(fill="x", padx=17, pady=5)

        self.sidebar_stats = text(s, "", size=11, wraplength=210)
        self.sidebar_stats.pack(side="bottom", padx=24, pady=(0, 28), anchor="w")
        text(s, "HVC  /  v1.1", size=12, color=GOLD).pack(side="bottom", padx=24,
                                                         pady=(0, 8), anchor="w")
        self.update_icon_count()

    def update_icon_count(self):
        if hasattr(self, "sidebar_stats"):
            self.sidebar_stats.configure(
                text=f"Иконки заклинаний: {count_icons()} из 26\n"
                     "Файлы изображений хранятся локально.\n"
                     "Распознавание работает без интернета."
            )

    def clear_content(self):
        for item in self.content.winfo_children():
            item.destroy()

    def save_config(self):
        DEFAULT_CONFIG.write_text(
            json.dumps(self.config_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )

    def draw_spell_settings(self):
        """Select which incantations may actually cast in the game.

        Microphone TEST mode always checks all dictionary words. These toggles
        only authorize actual game commands, never modify the ASR model.
        """
        if self.wizard is not None and self.wizard.win.winfo_exists():
            if self.wizard.busy:
                self.wizard.notice.configure(
                    text="Дождись окончания записи перед переходом.",
                    text_color=GOLD,
                )
                return
            self.wizard = None
        self.clear_content()
        self._active_page = "spells"
        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, padx=28, pady=23)
        text(wrapper, "НАСТРОЙКА ГОЛОСОВЫХ КОМАНД", size=11,
             color=GOLD, weight="bold").pack(anchor="w", pady=(0,6))
        heading(wrapper, "Какие заклинания разрешены?", size=28).pack(anchor="w")
        text(wrapper,
             "Выбери книжное или оригинальное произношение. "
             "В проверке микрофона доступны все команды; "
             "ниже выбирается, что можно применять в игре.",
             size=12, wraplength=750).pack(anchor="w", pady=(10,12))
        style_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        style_row.pack(fill="x", pady=(0,13))
        text(style_row, "ПРОИЗНОШЕНИЕ", size=11, color=GOLD,
             weight="bold").pack(side="left", padx=(0,14))
        self.voice_style_menu = ctk.CTkOptionMenu(
            style_row, values=list(STYLE_LABELS.values()),
            command=self.set_voice_style,
            fg_color=RAISED, button_color="#2b4055",
            button_hover_color="#3d5670",
            text_color=TEXT, height=39,
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.voice_style_menu.pack(side="left", padx=(0,10))
        self.voice_style_menu.set(STYLE_LABELS.get(
            self.config_data.get("voice_style", DEFAULT_STYLE),
            STYLE_LABELS[DEFAULT_STYLE]))
        self.enabled_count = text(wrapper, "", size=12, color=GREEN)
        self.enabled_count.pack(anchor="w", pady=(0,12))

        scroll = ctk.CTkScrollableFrame(
            wrapper, fg_color=PANEL, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        scroll.pack(fill="both", expand=True, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)
        enabled = set(self.config_data.get("enabled_spells", ["Lumos", "Accio"]))
        style = self.config_data.get("voice_style", DEFAULT_STYLE)
        self.spell_vars = {}
        self.spell_controls = {}
        for index, spell in enumerate(self.book.entries):
            reading = visible_name(spell, style)
            variable = ctk.BooleanVar(value=spell in enabled)
            self.spell_vars[spell] = variable
            control = ctk.CTkCheckBox(
                scroll, text=f"{reading}  —  {spell}", variable=variable,
                command=self.update_enabled_spells,
                fg_color=GOLD, hover_color=GOLD_HOVER,
                text_color=TEXT, checkmark_color=BASE,
                font=ctk.CTkFont(family=FONT, size=12),
            )
            control.grid(row=index // 2, column=index % 2, sticky="w",
                         padx=18, pady=10)
            self.spell_controls[spell] = control

        actions = ctk.CTkFrame(wrapper, fg_color="transparent")
        actions.pack(fill="x", pady=(0,6))
        button(actions, "Разрешить все", lambda: self.set_all_spells(True),
               height=38, width=150).pack(side="left", padx=(0,8))
        button(actions, "Запретить все", lambda: self.set_all_spells(False),
               height=38, width=150).pack(side="left")
        button(actions, "Вернуться на главную", self.draw_home,
               height=38, width=190).pack(side="right")
        self.update_spell_count()

    def set_voice_style(self, label):
        style = next((key for key, name in STYLE_LABELS.items()
                      if name == label), None)
        if style is None:
            return
        self.config_data["voice_style"] = style
        self.save_config()
        for spell, control in self.spell_controls.items():
            control.configure(text=f"{visible_name(spell, style)}  —  {spell}")
        self.log(f"[style] {STYLE_LABELS[style]}. Для применения "
                 "останови и снова запусти распознавание.")

    def update_spell_count(self):
        selected = [spell for spell, state in self.spell_vars.items()
                    if state.get()]
        self.enabled_count.configure(
            text=f"Разрешено в игре: {len(selected)} из {len(self.spell_vars)}"
        )

    def update_enabled_spells(self):
        selected = [spell for spell in self.book.entries
                    if self.spell_vars[spell].get()]
        self.config_data["enabled_spells"] = selected
        self.save_config()
        self.update_spell_count()
        self.log(f"[config] В игре разрешено заклинаний: {len(selected)}. "
                 "Перезапусти прослушивание для применения изменений.")

    def set_all_spells(self, allow):
        for state in self.spell_vars.values():
            state.set(allow)
        self.update_enabled_spells()

    def draw_home(self):
        # The training wizard is an embedded page, not a top-level dialog.
        if self.wizard is not None and self.wizard.win.winfo_exists():
            if self.wizard.busy:
                self.wizard.notice.configure(
                    text="Сейчас идёт запись. Дождись её окончания перед переходом.",
                    text_color=GOLD,
                )
                return
            self.wizard = None
        self.clear_content()
        self._active_page = "home"
        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=35, pady=28)

        text(body, "ПАНЕЛЬ УПРАВЛЕНИЯ", size=11, color=GOLD,
             weight="bold").pack(anchor="w", pady=(0, 5))
        heading(body, "Твой голос — твоя магия", size=32).pack(anchor="w")
        text(body, "Быстрое локальное распознавание. Минимум настроек, без лишних окон.",
             size=13).pack(anchor="w", pady=(8, 25))

        hero = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=18,
                            border_width=1, border_color=BORDER)
        hero.pack(fill="x", pady=(0, 17))
        hero.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, padx=(24, 16), pady=23, sticky="w")
        self.status_label = text(left, "● ГОТОВО К ЗАПУСКУ", size=11,
                          color=GREEN, weight="bold")
        self.status_label.pack(anchor="w", pady=(0, 14))
        heading(left, "Произнёс. Применил.", size=27).pack(anchor="w")
        text(left, "Произношение: " + STYLE_LABELS.get(
            self.config_data.get("voice_style", DEFAULT_STYLE),
            STYLE_LABELS[DEFAULT_STYLE]),
            size=12, wraplength=420, color=GOLD).pack(anchor="w", pady=(6,0))
        text(left, "Без облака, ожидания тишины и проверки личности.",
             size=12, wraplength=420).pack(anchor="w", pady=(5,14))
        self.primary = button(left, "НАЧАТЬ КОЛДОВАТЬ", lambda: self.start(False),
                              primary=True, width=270, height=51)
        self.primary.pack(anchor="w")
        thumb = ctk.CTkFrame(hero, width=176, height=176, corner_radius=15,
                             fg_color="#101b2c")
        thumb.grid(row=0, column=1, padx=(0, 22), pady=20)
        thumb.grid_propagate(False)
        self.home_art = picture(thumb, "Lumos", size=118)
        self.home_art.pack(fill="both", expand=True, padx=4, pady=4)

        settings = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16,
                                border_width=1, border_color=BORDER)
        settings.pack(fill="x", pady=(0, 16))
        settings.grid_columnconfigure(0,weight=1)
        settings.grid_columnconfigure(1,weight=1)
        text(settings, "УСТРОЙСТВО ВВОДА", size=10, color=GOLD,
             weight="bold").grid(row=0, column=0, padx=(20,14), pady=(18,6), sticky="w")
        text(settings, "РЕЖИМ РАСПОЗНАВАНИЯ", size=10, color=GOLD,
             weight="bold").grid(row=0, column=1, padx=(14,20), pady=(18,6), sticky="w")
        self.mic_options = [(None, "По умолчанию")]
        try:
            import sounddevice as sd
            for n, device in enumerate(sd.query_devices()):
                if device["max_input_channels"] > 0:
                    self.mic_options.append((n, f"{n} — {device['name'][:38]}"))
        except Exception:
            pass
        self.mic_names = [value for _,value in self.mic_options]
        selected_device = self.config_data.get("mic_device")
        current_mic = next((v for n,v in self.mic_options if n == selected_device), self.mic_names[0])
        self.mic_menu = ctk.CTkOptionMenu(
            settings, values=self.mic_names, command=self.set_mic,
            fg_color=RAISED, button_color="#2b4055", button_hover_color="#3d5670",
            text_color=TEXT, height=39, font=ctk.CTkFont(family=FONT,size=12)
        )
        self.mic_menu.grid(row=1,column=0,padx=(20,14),pady=(0,18),sticky="ew")
        self.mic_menu.set(current_mic)
        modes = ["Максимальная скорость", "Сбалансированный"]
        self.speed_menu = ctk.CTkOptionMenu(
            settings, values=modes, command=self.set_speed,
            fg_color=RAISED, button_color="#2b4055", button_hover_color="#3d5670",
            text_color=TEXT, height=39, font=ctk.CTkFont(family=FONT,size=12)
        )
        self.speed_menu.grid(row=1,column=1,padx=(14,20),pady=(0,18),sticky="ew")
        self.speed_menu.set(modes[1] if self.config_data.get("performance_mode") == "balanced" else modes[0])

        text(settings, "РЕЖИМ АКТИВАЦИИ", size=10, color=GOLD,
             weight="bold").grid(row=2, column=0, padx=(20,14), pady=(0,6), sticky="w")
        text(settings, "КНОПКА ЗАПИСИ", size=10, color=GOLD,
             weight="bold").grid(row=2, column=1, padx=(14,20), pady=(0,6), sticky="w")
        modes_ptt = ["Удерживать кнопку (1 заклинание)", "Свободное прослушивание"]
        self.activation_menu = ctk.CTkOptionMenu(
            settings, values=modes_ptt, command=self.set_activation_mode,
            fg_color=RAISED, button_color="#2b4055", button_hover_color="#3d5670",
            text_color=TEXT, height=39, font=ctk.CTkFont(family=FONT, size=12),
        )
        self.activation_menu.grid(row=3, column=0, padx=(20,14),
                                  pady=(0,14), sticky="ew")
        self.activation_menu.set(modes_ptt[0] if self.config_data.get(
            "push_to_talk", True) else modes_ptt[1])
        self.ptt_key_menu = ctk.CTkOptionMenu(
            settings, values=["F9", "F10", "F11", "Mouse4", "Mouse5"],
            command=self.set_ptt_key, fg_color=RAISED,
            button_color="#2b4055", button_hover_color="#3d5670",
            text_color=TEXT, height=39,
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.ptt_key_menu.grid(row=3, column=1, padx=(14,20),
                               pady=(0,14), sticky="ew")
        self.ptt_key_menu.set(self.config_data.get("ptt_key", "F9"))
        if not self.config_data.get("push_to_talk", True):
            self.ptt_key_menu.configure(state="disabled")

        self.focus_only = ctk.CTkSwitch(
            settings,
            text="Слушать только при активном окне игры",
            command=self.change_focus_setting,
            fg_color="#455269", progress_color=GOLD, button_color=TEXT,
            text_color=MUTED,
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.focus_only.grid(row=4, column=0, columnspan=2,
                             padx=20, pady=(0, 15), sticky="w")
        if self.config_data.get("require_game_focus", True):
            self.focus_only.select()
        else:
            self.focus_only.deselect()

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 15))
        actions.grid_columnconfigure(0,weight=1)
        actions.grid_columnconfigure(1,weight=1)
        button(actions, "ПРОВЕРИТЬ МИКРОФОН", lambda: self.start(True),
               height=43).grid(row=0,column=0,sticky="ew",padx=(0,8))
        button(actions, "ОСТАНОВИТЬ", self.stop, height=43).grid(
            row=0,column=1,sticky="ew",padx=(8,0))

        journal = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16,
                               border_width=1, border_color=BORDER)
        journal.pack(fill="both", expand=True)
        text(journal, "ЖУРНАЛ РАСПОЗНАВАНИЯ", size=11,
             color=GOLD, weight="bold").pack(anchor="w", padx=20, pady=(16,8))
        self.logbox = ctk.CTkTextbox(
            journal, fg_color="#111a26", corner_radius=9,
            text_color="#cfdae8", border_width=0,
            font=ctk.CTkFont(family="Consolas",size=11), wrap="word")
        self.logbox.pack(fill="both", expand=True, padx=16, pady=(0,15))
        self.logbox.insert("end", "Здесь появятся распознанные заклинания и замеры задержки.\n")
        for line in self._log_history:
            self.logbox.insert("end", line + "\n")
        self.logbox.configure(state="disabled")
        if self.proc and self.proc.poll() is None:
            self.set_status("● РАСПОЗНАВАНИЕ АКТИВНО", GOLD)

    def set_mic(self, name):
        for index, title in self.mic_options:
            if title == name:
                self.config_data["mic_device"] = index
                self.save_config()
                self.log("Микрофон изменён. Перезапусти распознавание.")
                return

    def set_speed(self, name):
        fast = name == "Максимальная скорость"
        self.config_data["performance_mode"] = "fast" if fast else "balanced"
        self.config_data["block_ms"] = 20 if fast else 32
        self.config_data["stable_partial_updates"] = 1 if fast else 2
        self.save_config()
        self.log("Режим изменён. При следующем запуске он вступит в силу.")

    def set_activation_mode(self, name):
        ptt = name == "Удерживать кнопку (1 заклинание)"
        self.config_data["push_to_talk"] = ptt
        self.ptt_key_menu.configure(state="normal" if ptt else "disabled")
        self.save_config()
        self.log("Режим обновлён: " + (
            "кнопка удерживается для записи одного заклинания."
            if ptt else "свободное прослушивание (экспериментальное)."
        ))
        self.log("Останови и заново запусти распознавание для применения.")

    def set_ptt_key(self, key):
        self.config_data["ptt_key"] = key
        self.save_config()
        self.log(f"Кнопка записи: {key}. Настройка вступит в силу после перезапуска распознавания.")

    def change_focus_setting(self):
        self.config_data["require_game_focus"] = bool(self.focus_only.get())
        self.save_config()
        self.log("Настройка активного окна изменена. Останови и запусти "
                 "распознавание заново, чтобы применить её.")

    def set_status(self, value, color=GREEN):
        # Main-page widgets do not exist while viewing the training section.
        if (self._active_page == "home" and hasattr(self, "status_label")
                and self.status_label.winfo_exists()):
            self.status_label.configure(text=value, text_color=color)

    def log(self, line):
        # Keep worker output while the user is practising incantations;
        # it will reappear when navigating back to the main page.
        line = line.rstrip()
        self._log_history.append(line)
        if (self._active_page != "home" or not hasattr(self, "logbox")
                or not self.logbox.winfo_exists()):
            return
        self.logbox.configure(state="normal")
        self.logbox.insert("end", line + "\n")
        self.logbox.see("end")
        if int(self.logbox.index("end-1c").split(".")[0]) > 260:
            self.logbox.delete("1.0", "40.0")
        self.logbox.configure(state="disabled")

    def start(self, dry_run=False):
        if self.proc and self.proc.poll() is None:
            self.log("Распознавание уже запущено. Нажми «Остановить», чтобы перезапустить.")
            return
        # The GUI runs under pythonw.exe, but worker stdout must be captured.
        pythonexe = Path(sys.executable).with_name("python.exe")
        if not pythonexe.is_file():
            pythonexe = Path(sys.executable)
        argv = [str(pythonexe), "-u", "-m", "hogwarts_voice",
                "--dry-run" if dry_run else "--listen"]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["PYTHONIOENCODING"] = "utf-8"  # Avoid mojibake in the in-app log on Russian Windows.
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = subprocess.Popen(
                argv, cwd=str(ROOT), env=env, creationflags=flags,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, encoding="utf-8", errors="replace"
            )
        except OSError as exc:
            self.set_status("● ОШИБКА ЗАПУСКА", RED)
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.proc = proc
        self._proc_generation += 1
        generation = self._proc_generation
        self.set_status("● ПРОВЕРКА МИКРОФОНА" if dry_run else "● РАСПОЗНАВАНИЕ АКТИВНО", GOLD)
        self.log("Запуск проверки микрофона..." if dry_run else "Запуск игрового распознавания...")
        if self.config_data.get("recognition_engine", "gigaam_ru") == "gigaam_ru":
            self.log("[engine] Русская нейросеть GigaAM v2. Обучение голосу не требуется.")
            self.log("[style] " + STYLE_LABELS.get(
                self.config_data.get("voice_style", DEFAULT_STYLE),
                STYLE_LABELS[DEFAULT_STYLE]))
            if dry_run:
                self.log("[engine] Проверка распознаёт все заклинания, но ничего не применяет.")
            else:
                selected = self.config_data.get("enabled_spells", ["Lumos", "Accio"])
                self.log(f"[engine] Для игры разрешено заклинаний: {len(selected)}.")
        if self.config_data.get("push_to_talk", True):
            self.log(f"[ptt] Зажми {self.config_data.get('ptt_key','F9')}, "
                     "произнеси ОДНО заклинание и отпусти кнопку.")
            self.log("[ptt] До отпускания кнопки ничего не применяется.")
        if dry_run:
            self.log("[help] Проверка микрофона работает и при открытом окне программы.")
        elif self.config_data.get("require_game_focus", True):
            self.log("[help] Вернись в Hogwarts Legacy после нажатия «Начать колдовать». "
                     "Пока это окно активно, голос игнорируется.")
        else:
            self.log("[help] Режим без проверки активного окна: команды могут отправляться, "
                     "даже когда игра свёрнута.")
        def reader():
            try:
                for line in proc.stdout:
                    self.events.put(("log", generation, line))
            except (OSError, ValueError) as exc:
                self.events.put(("log", generation, str(exc)))
            code = proc.wait()
            self.events.put(("exit", generation, code))
        threading.Thread(target=reader, daemon=True).start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.log("Останавливаем распознавание...")
        self.proc = None
        self._proc_generation += 1
        self.set_status("● ГОТОВО К ЗАПУСКУ", GREEN)

    def pump(self):
        if self._closed:
            return
        try:
            while True:
                kind, generation, value = self.events.get_nowait()
                if generation != self._proc_generation:
                    continue
                if kind == "log":
                    self.log(str(value))
                    if "[sent]" in str(value) or "[TEST]" in str(value):
                        self.set_status("● ЗАКЛИНАНИЕ РАСПОЗНАНО", GREEN)
                    elif "[focus] BLOCKED" in str(value):
                        self.set_status("● ОКНО ИГРЫ НЕ АКТИВНО", RED)
                    elif "[focus] LISTENING" in str(value):
                        self.set_status("● МИКРОФОН СЛУШАЕТ", GOLD)
                    elif "[mod] NOT READY" in str(value):
                        self.set_status("● ИГРОВОЙ МОД НЕ ОТВЕЧАЕТ", RED)
                    elif "[mod] READY" in str(value):
                        self.set_status("● ИГРОВОЙ МОД ПОДКЛЮЧЕН", GREEN)
                    elif "Audio/runtime error" in str(value) or "Startup error" in str(value):
                        self.set_status("● ПРОВЕРЬ МИКРОФОН", RED)
                elif kind == "exit":
                    self.proc = None
                    self.set_status("● ГОТОВО К ЗАПУСКУ" if value == 0
                                    else "● РАСПОЗНАВАНИЕ ОСТАНОВЛЕНО", GREEN if value == 0 else RED)
                    self.log(f"Работа завершена (код {value}).")
        except queue.Empty:
            pass
        self.after(125, self.pump)

    def open_wizard(self):
        if self.wizard is not None and self.wizard.win.winfo_exists():
            return  # Already on this page — never create a separate window.
        self.clear_content()
        self._active_page = "training"
        self.wizard = Wizard(self)

    def import_icons(self):
        chosen = filedialog.askopenfilename(
            parent=self, title="Выбери ZIP с игровыми иконками Hogwarts Legacy",
            filetypes=[("ZIP-архив", "*.zip"), ("Все файлы", "*.*")])
        if not chosen:
            return
        try:
            found = import_zip(Path(chosen))
        except Exception as exc:
            messagebox.showerror("Не удалось открыть иконки", str(exc),parent=self)
            return
        if not found:
            messagebox.showwarning(
                "Иконки не найдены",
                "В ZIP не обнаружены оригинальные файлы UI_T_accio.png и другие иконки заклинаний.\n"
                "Нужен набор «Spells» из The Spriters Resource.",parent=self)
            return
        self.update_icon_count()
        self.log(f"Импортировано игровых иконок: {len(found)}.")
        if self.wizard is not None and self.wizard.win.winfo_exists():
            self.wizard.draw()
        else:
            self.draw_home()
        messagebox.showinfo("Готово",f"Загружено {len(found)} иконок.\n"
                            "Они останутся на этом ПК и будут доступны офлайн.",
                            parent=self)

    def close(self):
        self._closed = True
        self.stop()
        self.destroy()

class Wizard:
    def __init__(self, app: App):
        self.app = app
        self.spells = list(app.book.entries)
        self.index = 0
        self.bank = PronunciationBank.load()
        self.last_heard = ""
        self.busy = False
        self.model = None
        self.events = queue.Queue()
        # Render inside the existing app content area (one Windows taskbar item).
        self.win = ctk.CTkFrame(app.content, fg_color=BASE, corner_radius=0)
        self.win.pack(fill="both", expand=True)
        root = ctk.CTkScrollableFrame(self.win, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=17, pady=16)
        root.grid_columnconfigure(0,weight=1,uniform="wiz")
        root.grid_columnconfigure(1,weight=1,uniform="wiz")
        root.grid_rowconfigure(1,weight=1)
        text(root,"АТЛАС ЗАКЛИНАНИЙ  /  НАСТРОЙКА ПРОИЗНОШЕНИЯ",size=11,
             color=GOLD,weight="bold").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,15))

        self.left = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=19,
                                 border_width=1, border_color=BORDER)
        self.left.grid(row=1,column=0,sticky="nsew",padx=(0,9))
        self.category = text(self.left,"",size=11,color=GOLD,weight="bold")
        self.category.pack(anchor="w",padx=25,pady=(24,14))
        self.icon_container = ctk.CTkFrame(self.left,fg_color="transparent")
        self.icon_container.pack(expand=True,fill="both",padx=35,pady=(0,20))
        self.number = text(self.left,"",size=11,color=MUTED)
        self.number.pack(pady=(0,24))

        right = ctk.CTkFrame(root,fg_color=PANEL,corner_radius=19,
                             border_width=1,border_color=BORDER)
        right.grid(row=1,column=1,sticky="nsew",padx=(9,0))
        pad=24
        text(right,"ПРОИЗНЕСИ ЗАКЛИНАНИЕ",size=11,color=GOLD,
             weight="bold").pack(anchor="w",padx=pad,pady=(25,14))
        self.ru=heading(right,"",size=29)
        self.ru.pack(anchor="w",padx=pad)
        self.english=text(right,"",size=17,color=GOLD)
        self.english.pack(anchor="w",padx=pad,pady=(5,8))
        self.phonetic=text(right,"",size=12,wraplength=360)
        self.phonetic.pack(anchor="w",padx=pad,pady=(0,20))
        self.progress=ctk.CTkProgressBar(right,progress_color=GOLD,
                                         fg_color="#2a3548",height=6)
        self.progress.pack(fill="x",padx=pad,pady=(3,20))
        self.record=button(right,"ОБУЧИТЬ ПРОИЗНОШЕНИЕ",self.record_click,primary=True)
        self.record.pack(fill="x",padx=pad,pady=(0,12))
        self.reset_samples=button(right,"СБРОСИТЬ ОБРАЗЦЫ ЭТОГО ЗАКЛИНАНИЯ",
                                  self.clear_samples,height=36)
        self.reset_samples.pack(fill="x",padx=pad,pady=(0,12))
        self.notice=text(right,"Нажми кнопку, затем зажми F9, произнеси заклинание и отпусти F9.",
                         size=12,wraplength=360)
        self.notice.pack(anchor="w",padx=pad,pady=(0,12))
        self.heard=text(right,"РАСПОЗНАНО: —",size=13,color=TEXT,wraplength=360)
        self.heard.pack(anchor="w",padx=pad,pady=(4,12))
        self.accept=button(right,"ЗАПОМНИТЬ ЭТОТ ВАРИАНТ",self.accept_alias,height=38)
        # Old Vosk text-alias control is hidden in acoustic mode.
        self.accept.pack_forget()
        self.accept.configure(state="disabled")

        nav=ctk.CTkFrame(right,fg_color="transparent")
        nav.pack(side="bottom",fill="x",padx=pad,pady=(0,24))
        button(nav,"НАЗАД",self.prev,width=117,height=40).pack(side="left")
        button(nav,"ДАЛЕЕ",self.next,width=117,height=40).pack(side="right")
        self.next_btn=nav.winfo_children()[-1]
        button(right,"ЗАВЕРШИТЬ",self.finish,height=34).pack(
            side="bottom",fill="x",padx=pad,pady=(0,12))

        self.draw()
        self.win.after(120,self.pump)

    @property
    def spell(self):
        return self.spells[self.index]

    def draw(self):
        spell=self.spell
        accent,background,category=palette_of(spell)
        self.category.configure(text=category,text_color=accent)
        for child in self.icon_container.winfo_children():
            child.destroy()
        area=ctk.CTkFrame(self.icon_container,fg_color=background,corner_radius=18,
                          border_width=1,border_color=accent)
        area.pack(fill="both",expand=True)
        self.icon_widget=picture(area,spell,size=212)
        self.icon_widget.pack(fill="both",expand=True,padx=30,pady=30)
        _,phon=READINGS.get(spell,(spell,spell))
        self.ru.configure(text=visible_name(
            spell, self.app.config_data.get("voice_style", DEFAULT_STYLE)))
        self.english.configure(text=spell)
        self.phonetic.configure(text=f"Английская транскрипция: {phon}")
        self.number.configure(text=f"ЗАКЛИНАНИЕ {self.index+1:02d} / {len(self.spells)}")
        self.progress.set((self.index+1)/len(self.spells))
        self.notice.configure(text=f"Образцов: {self.bank.count(spell)} / 3 · "
                                     f"удерживай {self.app.config_data.get('ptt_key', 'F9')} для одного слова.",
                              text_color=GREEN if self.bank.trained(spell) else MUTED)
        self.heard.configure(text="Режим: сравнение звучания (без Vosk)")
        self.last_heard=""
        self.accept.configure(state="disabled")
        self.record.configure(state="normal")
        if self.app.config_data.get("recognition_engine", "gigaam_ru") == "gigaam_ru":
            self.record.configure(state="disabled")
            self.reset_samples.configure(state="disabled")
            self.notice.configure(
                text="Новая русская нейросеть GigaAM распознаёт слова без обучения. "
                     "Здесь можно посмотреть написание и произношение заклинания.",
                text_color=GREEN
            )
            self.heard.configure(text="Проверка произношения — через главное меню.")

    def prev(self):
        if not self.busy and self.index:
            self.index-=1
            self.draw()

    def next(self):
        if self.busy:
            return
        if self.index+1>=len(self.spells):
            self.finish()
            return
        self.index+=1
        self.draw()

    def clear_samples(self):
        if self.busy:
            return
        spell = self.spell
        if not self.bank.count(spell):
            self.notice.configure(text="Образцов для удаления нет.", text_color=MUTED)
            return
        if not messagebox.askyesno(
            "Удаление примеров",
            f"Удалить все записи произношения для {spell}? Остальные заклинания сохранятся.",
            parent=self.app
        ):
            return
        self.bank.clear(spell)
        self.bank.save()
        self.draw()
        self.notice.configure(text="Образцы очищены. Запиши три новых произнесения.",
                              text_color=GOLD)

    def record_click(self):
        if self.busy:
            return
        self.busy=True
        self.record.configure(state="disabled")
        self.accept.configure(state="disabled")
        self.notice.configure(text="Подключение микрофона. Готовься зажать кнопку...",text_color=GOLD)
        threading.Thread(target=self.worker,args=(self.spell,),daemon=True).start()

    def worker(self,spell):
        try:
            # Identical PCM16 sampling and physical key hold as game PTT.
            # No fixed recording window or silence endpoint.
            key = self.app.config_data.get("ptt_key", "F9")
            pcm = capture_one_hold(
                device=self.app.config_data.get("mic_device"),
                key=key,
                state_callback=lambda message: self.events.put(
                    ("recording", spell, message)
                ),
            )
            count = self.bank.add(spell, pcm)
            self.bank.save()
            quality = self.bank.quality(spell)
            self.events.put(("result", spell, (quality, count)))
        except Exception as exc:
            self.events.put(("error",spell,str(exc)))

    def pump(self):
        if not self.win.winfo_exists():
            return
        try:
            while True:
                kind,spell,value=self.events.get_nowait()
                if kind=="recording":
                    self.notice.configure(text=value or "Нажми кнопку для записи",text_color=GOLD)
                elif kind=="error":
                    self.busy=False
                    self.record.configure(state="normal")
                    self.notice.configure(text=f"Ошибка записи: {value}",text_color=RED)
                elif kind=="result":
                    self.busy=False
                    quality, count = value
                    self.record.configure(state="normal")
                    ready = self.bank.trained(spell)
                    self.notice.configure(
                        text=(f"Образцов: {min(count,3)} / 3 · "
                              + ("Готово к проверке ✓" if ready else "запиши ещё")),
                        text_color=GREEN if ready else GOLD
                    )
                    if quality is not None and quality < .75:
                        self.notice.configure(
                            text="Записи сильно различаются. Лучше сбросить и записать заново.",
                            text_color=RED,
                        )
                    self.heard.configure(
                        text=("Согласованность примеров: " + f"{quality:.3f}"
                              + " (это не точность распознавания)" if quality is not None
                              else "Образец записан в игровом формате PTT")
                    )
                    self.accept.configure(state="disabled")
        except queue.Empty:
            pass
        self.win.after(120,self.pump)

    def accept_alias(self):
        if not self.last_heard:
            return
        profile=VoiceProfile.load()
        try:
            profile.add_alias(self.spell,self.last_heard,self.app.book)
            profile.save()
        except ValueError as exc:
            messagebox.showwarning("Нельзя сохранить",str(exc),parent=self.app)
        else:
            self.notice.configure(text="Вариант добавлен в личный словарь.",text_color=GREEN)
            self.accept.configure(state="disabled")

    def finish(self):
        if self.busy:
            messagebox.showinfo("Запись", "Дождись окончания записи.",parent=self.win)
            return
        self.app.draw_home()

def main():
    App().mainloop()
    return 0
