"""Dark, accessible desktop UI. No console windows are required."""
from __future__ import annotations

import json
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
from .icon_assets import SOURCE_PAGE, count_icons, has_icon, icon_file, import_zip
from .spellbook import Spellbook
from .voice_profile import VoiceProfile
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
        self.geometry("1080x765")
        self.minsize(890, 670)
        self.configure(fg_color=BASE)

        self.config_data = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        with DEFAULT_SPELLS.open("r", encoding="utf-8") as source:
            self.book = Spellbook(json.load(source))
        self.events = queue.Queue()
        self.proc = None
        self.wizard = None
        self._closed = False
        self._proc_generation = 0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=SIDE)
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
        button(s, "Тренировка заклинаний", self.open_wizard).pack(fill="x", padx=17, pady=5)
        button(s, "Импорт игровых иконок", self.import_icons).pack(fill="x", padx=17, pady=5)
        button(s, "Источник иконок", lambda: webbrowser.open(SOURCE_PAGE)).pack(fill="x", padx=17, pady=5)

        self.sidebar_stats = text(s, "", size=11, wraplength=210)
        self.sidebar_stats.pack(side="bottom", padx=24, pady=(0, 28), anchor="w")
        text(s, "HVC  /  v0.4", size=12, color=GOLD).pack(side="bottom", padx=24,
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

    def draw_home(self):
        self.clear_content()
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
        text(left, "Без облака, ожидания тишины и проверки личности.",
             size=12, wraplength=420).pack(anchor="w", pady=(9, 16))
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

    def set_status(self, value, color=GREEN):
        if hasattr(self,"state"):
            self.status_label.configure(text=value,text_color=color)

    def log(self, line):
        if not hasattr(self,"logbox"):
            return
        self.logbox.configure(state="normal")
        self.logbox.insert("end", line.rstrip()+"\n")
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
        if self.wizard and self.wizard.win.winfo_exists():
            self.wizard.win.lift()
            self.wizard.win.focus_set()
            return
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
        if self.wizard and self.wizard.win.winfo_exists():
            self.wizard.draw()
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
        self.counts = {}
        self.last_heard = ""
        self.busy = False
        self.model = None
        self.events = queue.Queue()
        self.win = ctk.CTkToplevel(app)
        self.win.title("Тренировка заклинаний — Hogwarts Voice Caster")
        self.win.geometry("1010x700")
        self.win.minsize(850,620)
        self.win.configure(fg_color=BASE)
        self.win.protocol("WM_DELETE_WINDOW", self.finish)

        root = ctk.CTkFrame(self.win, fg_color="transparent")
        root.pack(fill="both",expand=True,padx=25,pady=25)
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
        self.record=button(right,"ЗАПИСАТЬ ПРОИЗНОШЕНИЕ",self.record_click,primary=True)
        self.record.pack(fill="x",padx=pad,pady=(0,12))
        self.notice=text(right,"Три попытки по желанию. Сначала нажми кнопку.",
                         size=12,wraplength=360)
        self.notice.pack(anchor="w",padx=pad,pady=(0,12))
        self.heard=text(right,"РАСПОЗНАНО: —",size=13,color=TEXT,wraplength=360)
        self.heard.pack(anchor="w",padx=pad,pady=(4,12))
        self.accept=button(right,"ЗАПОМНИТЬ ЭТОТ ВАРИАНТ",self.accept_alias,height=38)
        self.accept.pack(fill="x",padx=pad,pady=(0,16))
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
        ru,phon=READINGS.get(spell,(spell,spell))
        self.ru.configure(text=ru)
        self.english.configure(text=spell)
        self.phonetic.configure(text=f"Английская транскрипция: {phon}")
        self.number.configure(text=f"ЗАКЛИНАНИЕ {self.index+1:02d} / {len(self.spells)}")
        self.progress.set((self.index+1)/len(self.spells))
        self.notice.configure(text=f"Попыток: {self.counts.get(spell,0)} / 3 · запись 2,8 сек.",
                              text_color=MUTED)
        self.heard.configure(text="РАСПОЗНАНО: —")
        self.last_heard=""
        self.accept.configure(state="disabled")
        self.record.configure(state="normal")

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

    def record_click(self):
        if self.busy:
            return
        self.busy=True
        self.record.configure(state="disabled")
        self.accept.configure(state="disabled")
        self.notice.configure(text="Инициализация микрофона...",text_color=GOLD)
        threading.Thread(target=self.worker,args=(self.spell,),daemon=True).start()

    def worker(self,spell):
        try:
            import numpy as np
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel
            if self.model is None:
                if not MODEL.is_dir():
                    raise FileNotFoundError("Модель Vosk не установлена. Запусти install.bat.")
                SetLogLevel(-1)
                self.model=Model(str(MODEL))
            self.events.put(("recording",spell,None))
            if sys.platform=="win32":
                import winsound
                winsound.Beep(660,75)
            audio=sd.rec(int(2.8*16000),samplerate=16000,channels=1,
                         dtype="float32",device=self.app.config_data.get("mic_device"))
            sd.wait()
            pcm=(np.clip(audio.flatten(),-1,1)*32767).astype("<i2").tobytes()
            grammar=json.dumps(self.app.book.grammar(),ensure_ascii=False)
            asr=KaldiRecognizer(self.model,16000,grammar)
            asr.AcceptWaveform(pcm)
            result=json.loads(asr.FinalResult()).get("text","").strip()
            self.events.put(("result",spell,result))
        except Exception as exc:
            self.events.put(("error",spell,str(exc)))

    def pump(self):
        if not self.win.winfo_exists():
            return
        try:
            while True:
                kind,spell,value=self.events.get_nowait()
                if kind=="recording":
                    self.notice.configure(text="● ЗАПИСЬ ИДЁТ — произнеси слово",text_color=GOLD)
                elif kind=="error":
                    self.busy=False
                    self.record.configure(state="normal")
                    self.notice.configure(text=f"Ошибка записи: {value}",text_color=RED)
                elif kind=="result":
                    self.busy=False
                    self.counts[spell]=self.counts.get(spell,0)+1
                    self.record.configure(state="normal")
                    self.notice.configure(text=f"Попыток: {self.counts[spell]} / 3",text_color=GREEN)
                    self.last_heard=value
                    self.heard.configure(text="РАСПОЗНАНО: "+(value or "не разобрано"))
                    self.accept.configure(state="normal" if value else "disabled")
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
            messagebox.showwarning("Нельзя сохранить",str(exc),parent=self.win)
        else:
            self.notice.configure(text="Вариант добавлен в личный словарь.",text_color=GREEN)
            self.accept.configure(state="disabled")

    def finish(self):
        if self.busy:
            messagebox.showinfo("Запись", "Дождись окончания записи.",parent=self.win)
            return
        self.win.destroy()
        self.app.wizard=None

def main():
    App().mainloop()
    return 0
