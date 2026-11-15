"""Real Windows desktop test: one app window, wizard embedded as a page."""
from hogwarts_voice.ui import App

app = App()
try:
    app.update_idletasks()
    app.update()
    assert callable(app.state), "App.state() was overwritten by a widget"
    assert app.state() in {"normal", "zoomed", "iconic", "withdrawn"}
    app.set_status("Smoke test")
    app.draw_spell_settings()
    app.update()
    assert app._active_page == "spells"
    assert app.voice_style_menu is not None
    app.set_voice_style("Росмэн / книжный стиль")
    assert app.config_data["voice_style"] == "rosmen"
    assert "Остолбеней" in app.spell_controls["Stupefy"].cget("text")
    app.set_voice_style("Оригинальные формулы")
    assert app.config_data["voice_style"] == "original"
    assert "Ступефай" in app.spell_controls["Stupefy"].cget("text")
    app.set_voice_style("Росмэн / книжный стиль")
    assert len(app.spell_vars) >= 25
    app.spell_vars["Depulso"].set(True)
    app.update_enabled_spells()
    assert "Depulso" in app.config_data["enabled_spells"]
    app.set_all_spells(False)
    assert app.config_data["enabled_spells"] == []
    app.set_all_spells(True)
    assert len(app.config_data["enabled_spells"]) == len(app.spell_vars)
    # Tests should never leave a modified Git working tree behind.
    app.config_data["enabled_spells"] = ["Lumos", "Accio"]
    app.config_data["voice_style"] = "rosmen"
    app.save_config()
    app.draw_home()
    app.update()
    assert app.activation_menu is not None
    assert app.ptt_key_menu is not None
    assert app.activation_menu.get() in (
        "Удерживать кнопку (1 заклинание)", "Свободное прослушивание"
    )

    # Opening training should never spawn a second taskbar window.
    app.open_wizard()
    app.update()
    assert app._active_page == "training"
    assert app.wizard is not None
    wizard = app.wizard
    assert callable(wizard.record_click)
    if app.config_data.get("recognition_engine") == "gigaam_ru":
        assert wizard.record.cget("state") == "disabled"
    assert wizard.win.winfo_toplevel() is app
    assert len(app.winfo_children()) == 2, "Unexpected root-level window"
    wizard.next()
    wizard.win.update()
    wizard.prev()
    wizard.win.update()

    # Worker logs arriving while training must not crash on destroyed homepage.
    app.log("[TEST] Accio")
    app.set_status("Testing")
    wizard.finish()
    app.update()
    assert app._active_page == "home"
    assert app.wizard is None
    assert "[TEST] Accio" in app.logbox.get("1.0", "end")

    # Sidebar navigation both ways must also keep a single main window.
    app.open_wizard()
    app.update()
    app.draw_home()
    app.update()
    assert app.wizard is None
    assert app._active_page == "home"
    assert callable(app.state)
    print("[OK] Embedded training page; navigation; logs; no extra window")
finally:
    app.destroy()
