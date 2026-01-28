import os, tempfile, inspect

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from mdr_gtk.app import MDRApp

dbp = os.path.join(tempfile.gettempdir(), "mdr_strict_clean.sqlite")

# Robust: prüfe __init__ Signatur (nicht die Klasse selbst)
sig = inspect.signature(MDRApp.__init__)
kwargs = {}
if "db_path" in sig.parameters:
    kwargs["db_path"] = dbp
if "use_adwaita" in sig.parameters:
    kwargs["use_adwaita"] = False

app = MDRApp(**kwargs)

app.register(None)
app.activate()

for w in list(app.get_windows()):
    w.close()

app.quit()

# GTK4: Event-Pump via GLib MainContext
ctx = GLib.MainContext.default()
while ctx.pending():
    ctx.iteration(False)

print("GUI strict-clean OK")
