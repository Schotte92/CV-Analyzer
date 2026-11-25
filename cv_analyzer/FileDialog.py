"""
Plattformübergreifende Datei-/Verzeichnis-Dialoge für Tkinter.

Unter Linux benutzt Tkinter einen alten Tk-Dialog ohne brauchbare Pfadeingabe.
Dieses Modul ruft dort – falls vorhanden – das native zenity (GNOME/GTK) oder
kdialog (KDE/Qt) auf und bietet damit ein modernes Interface samt Pfadeingabe
(in GTK mit Strg+L). Unter Windows/macOS sowie als Fallback wird der native
Tk-Dialog verwendet.

Drop-in-Ersatz:
    filedialog.askopenfilename   -> ask_open_filename
    filedialog.askopenfilenames  -> ask_open_filenames
    filedialog.asksaveasfilename -> ask_save_filename
    filedialog.askdirectory      -> ask_directory

Rückgabe wie bei Tkinter: einzelne Funktionen geben '' bei Abbruch zurück,
ask_open_filenames eine (ggf. leere) Liste.
"""

import os
import sys
import shutil
import subprocess
from tkinter import filedialog


# --------------------------------------------------------------------------- #
#  Öffentliche API
# --------------------------------------------------------------------------- #

def askopenfilename(title="Datei öffnen", filetypes=None, initialdir=None):
    """Eine Datei wählen. Rückgabe: Pfad oder '' (abgebrochen)."""
    filetypes = _default_types(filetypes)
    backend = _backend()
    if backend == "zenity":
        out = _run(_zenity_base(title) + _zenity_filters(filetypes)
                   + _zenity_filename(initialdir, None))
        return _first_line(out)
    if backend == "kdialog":
        out = _run(["kdialog", "--title", title, "--getopenfilename",
                    _start(initialdir), _kdialog_filter(filetypes)])
        return _first_line(out)
    return filedialog.askopenfilename(title=title, filetypes=filetypes,
                                      initialdir=initialdir) or ""


def askopenfilenames(title="Dateien öffnen", filetypes=None, initialdir=None):
    """Mehrere Dateien wählen. Rückgabe: Liste von Pfaden (leer = abgebrochen)."""
    filetypes = _default_types(filetypes)
    backend = _backend()
    if backend == "zenity":
        out = _run(_zenity_base(title) + ["--multiple", "--separator=\n"]
                   + _zenity_filters(filetypes)
                   + _zenity_filename(initialdir, None))
        return _lines(out)
    if backend == "kdialog":
        out = _run(["kdialog", "--title", title, "--getopenfilename",
                    _start(initialdir), _kdialog_filter(filetypes),
                    "--multiple", "--separate-output"])
        return _lines(out)
    return list(filedialog.askopenfilenames(title=title, filetypes=filetypes,
                                            initialdir=initialdir))


def asksavefilename(title="Speichern unter", filetypes=None, initialdir=None,
                      initialfile=None, defaultextension=None,
                      confirmoverwrite=True):
    """Speicherort wählen. Rückgabe: Pfad oder '' (abgebrochen)."""
    filetypes = _default_types(filetypes)
    backend = _backend()
    if backend == "zenity":
        cmd = _zenity_base(title) + ["--save"]
        if confirmoverwrite:
            # in neueren zenity-Versionen ohnehin Default (Flag dann ignoriert)
            cmd.append("--confirm-overwrite")
        cmd += _zenity_filters(filetypes) + _zenity_filename(initialdir,
                                                             initialfile)
        return _with_ext(_first_line(_run(cmd)), defaultextension)
    if backend == "kdialog":
        out = _run(["kdialog", "--title", title, "--getsavefilename",
                    _start(initialdir, initialfile),
                    _kdialog_filter(filetypes)])
        return _with_ext(_first_line(out), defaultextension)
    return filedialog.asksaveasfilename(
        title=title, filetypes=filetypes, initialdir=initialdir,
        initialfile=initialfile, defaultextension=defaultextension or "",
        confirmoverwrite=confirmoverwrite) or ""


def askdirectory(title="Verzeichnis wählen", initialdir=None, mustexist=True):
    """Verzeichnis wählen. Rückgabe: Pfad oder '' (abgebrochen)."""
    backend = _backend()
    if backend == "zenity":
        out = _run(_zenity_base(title) + ["--directory"]
                   + _zenity_filename(initialdir, None))
        return _first_line(out)
    if backend == "kdialog":
        out = _run(["kdialog", "--title", title, "--getexistingdirectory",
                    _start(initialdir)])
        return _first_line(out)
    return filedialog.askdirectory(title=title, initialdir=initialdir,
                                   mustexist=mustexist) or ""


# --------------------------------------------------------------------------- #
#  Interne Helfer
# --------------------------------------------------------------------------- #

def _backend():
    if sys.platform.startswith("linux"):
        if shutil.which("zenity"):
            return "zenity"
        if shutil.which("kdialog"):
            return "kdialog"
    return "tk"


def _default_types(filetypes):
    return filetypes or [("CSV-Datei", "*.csv"), ("Alle Dateien", "*.*")]


def _norm(pattern):
    """tkinter-Muster -> Glob-String; '*.*' -> '*'."""
    if isinstance(pattern, (list, tuple)):
        pattern = " ".join(pattern)
    return "*" if pattern in ("*.*", "") else pattern


def _start(initialdir, initialfile=None):
    base = initialdir or os.path.expanduser("~")
    return os.path.join(base, initialfile) if initialfile else base


def _run(cmd):
    """Dialog ausführen. Rückgabe: stdout oder None (abgebrochen)."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def _first_line(out):
    return out.strip() if out else ""


def _lines(out):
    return [p for p in out.strip().split("\n") if p] if out else []


def _with_ext(path, defaultextension):
    if path and defaultextension and not os.path.splitext(path)[1]:
        path += "." + defaultextension.lstrip(".")
    return path


# zenity-Bausteine -----------------------------------------------------------
def _zenity_base(title):
    return ["zenity", "--file-selection", f"--title={title}"]


def _zenity_filters(filetypes):
    return [f"--file-filter={name} | {_norm(p)}" for name, p in filetypes]


def _zenity_filename(initialdir, initialfile):
    if not (initialdir or initialfile):
        return []
    path = _start(initialdir, initialfile)
    if initialdir and not initialfile:
        path = path.rstrip("/") + "/"   # nur Verzeichnis -> mit Slash
    return [f"--filename={path}"]


# kdialog-Bausteine ----------------------------------------------------------
def _kdialog_filter(filetypes):
    return "\n".join(f"{_norm(p)}|{name}" for name, p in filetypes)


if __name__ == "__main__":
    print("open  :", ask_open_filename())
    print("opens :", ask_open_filenames())
    print("save  :", ask_save_filename(initialfile="daten.csv",
                                        defaultextension=".csv"))
    print("dir   :", ask_directory())