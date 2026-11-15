"""Windows desktop regression test for Tkinter method shadowing.

Run after installing UI dependencies, with PYTHONPATH=src.
"""
from hogwarts_voice.ui import App, Wizard

app = App()
try:
    app.update_idletasks()
    app.update()
    assert callable(app.state), "App.state() was overwritten by a widget"
    assert app.state() in {"normal", "zoomed", "iconic", "withdrawn"}
    app.set_status("Smoke test")
    app.draw_home()
    app.update()
    assert callable(app.state), "Main view has overwritten Tk state()"
    wizard = Wizard(app)
    app.wizard = wizard
    wizard.win.update_idletasks()
    wizard.win.update()
    wizard.next()
    wizard.win.update()
    wizard.prev()
    wizard.win.update()
    wizard.finish()
    app.update()
    assert callable(app.state), "Wizard has overwritten Tk state()"
    print("[OK] Desktop main window, refresh, wizard and navigation")
finally:
    app.destroy()
