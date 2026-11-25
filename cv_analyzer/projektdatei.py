"""Projektdateien (`.cvproj`) laden — auch solche aus der Zeit vor der Paketstruktur.

Die Dateien sind mit `joblib` gepickelt und enthalten `Curve`-Objekte. Pickle
schreibt den Modulnamen mit, unter dem die Klasse damals definiert war: früher
`curve`, seit der Umstellung auf ein Paket `cv_analyzer.curve`. Ohne Gegenmaßnahme
scheitert das Öffnen alter Dateien mit `ModuleNotFoundError: No module named 'curve'`.

Deshalb werden vor dem Laden die historischen Modulnamen als Alias in
`sys.modules` eingetragen. Der Unpickler importiert dann `curve` und bekommt das
heutige Modul — die Klasse ist dieselbe, die Objekte bleiben also gültig.

Sicherheit
----------
Pickle kann beim Laden beliebigen Code ausführen: eine manipulierte Datei könnte
`os.system(...)` oder Ähnliches auslösen, bevor irgendetwas zu sehen ist. Deshalb
läuft das Einlesen über `SichererUnpickler`, der nur die Module und Klassennamen
durchlässt, die in einer Projektdatei wirklich vorkommen können (`ERLAUBTE_MODULE`,
`ERLAUBTE_BUILTINS`). Alles andere bricht mit `UnsicheresObjekt` ab, ohne dass das
Objekt angelegt wird — der Code in der Datei kommt so nie zur Ausführung.

Das Dateiformat selbst bleibt unverändert (joblib, komprimiert); Schreiben geht
weiter über `joblib.dump`, damit alte Analyzer-Versionen die Dateien noch lesen.

Verträglichkeit
---------------
Hier wird bewusst **keine** private joblib-Funktion benutzt. `_validate_fileobject_and_memmap`
gab es in joblib 1.2/1.3 nicht (Import brach beim Start ab), und die Signatur von
`NumpyUnpickler` hat sich zwischen 1.3 und 1.6 geändert. Das Entpacken macht
deshalb `_entpacken()` selbst — joblib schreibt den Kompressor-Stream direkt, das
Format ist von 1.2 bis 1.6 byte-identisch (geprüft: zlib `78 da`, unkomprimiert
`80 04`).
"""

import importlib
import inspect
import io
import sys
import bz2
import gzip
import lzma
import zlib

from joblib.numpy_pickle import NumpyUnpickler

# Hat diese joblib-Version den Parameter schon? 1.2/1.3: nein, 1.6: ja (ohne Default).
_UNPICKLER_MIT_BYTEORDER = "ensure_native_byte_order" in inspect.signature(NumpyUnpickler.__init__).parameters

# Modulname in alten Projektdateien -> heutiger Pfad im Paket
HISTORISCHE_MODULE = {
    "curve": "cv_analyzer.curve",
    "helpers": "cv_analyzer.helpers",
    "IO_Functions": "cv_analyzer.IO_Functions",
    "FileDialog": "cv_analyzer.FileDialog",
    "FigureFrame": "cv_analyzer.FigureFrame",
    "TableFrame": "cv_analyzer.TableFrame",
    "mf1_Manipulation": "cv_analyzer.mf1_Manipulation",
    "mf2_GraphSettings": "cv_analyzer.mf2_GraphSettings",
    "mf3_Integrate": "cv_analyzer.mf3_Integrate",
    "mf4_FitSettings": "cv_analyzer.mf4_FitSettings",
    "version": "cv_analyzer.version",
}

# Module, deren Klassen in einer Projektdatei vorkommen dürfen. Alles andere
# (os, subprocess, socket, shutil, ...) wird abgewiesen, bevor es entsteht.
ERLAUBTE_MODULE = (
    "cv_analyzer",
    "numpy",
    "joblib.numpy_pickle",   # NumpyArrayWrapper für die Arrays in der Datei
    "collections",
    "copyreg",
    "_codecs",
    "datetime",
) + tuple(HISTORISCHE_MODULE)

# builtins nur mit diesen Namen — eval, exec, open, getattr und Konsorten fehlen
# absichtlich, genau über sie läuft der Missbrauch.
ERLAUBTE_BUILTINS = frozenset((
    "bool", "bytearray", "bytes", "complex", "dict", "float", "frozenset",
    "int", "list", "range", "set", "slice", "str", "tuple",
))


class UnsicheresObjekt(Exception):
    """Die Datei enthält ein Objekt, das in einer Projektdatei nichts zu suchen hat."""


# Namen, die auch aus einem erlaubten Modul nicht kommen dürfen. Über sie ließe
# sich der Filter umgehen, z. B. numpy.ctypeslib.load_library (lädt eine fremde
# Bibliothek und führt damit deren Initialisierungscode aus).
VERBOTENE_NAMEN = frozenset((
    "load", "load_library", "loadtxt", "fromfile", "memmap",
    "system", "popen", "spawn", "spawnl", "spawnv", "fork", "execv", "execve",
    "eval", "exec", "compile", "open", "__import__", "import_module",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
))


def _erlaubt(module, name):
    """Darf dieses Modul/Attribut aus einer Datei geladen werden?"""
    if name in VERBOTENE_NAMEN:
        return False
    if module in ("builtins", "__builtin__"):
        return name in ERLAUBTE_BUILTINS
    for erlaubt in ERLAUBTE_MODULE:
        if module == erlaubt or module.startswith(erlaubt + "."):
            return True
    return False


class SichererUnpickler(NumpyUnpickler):
    """Unpickler, der nur die zum Datenmodell gehörenden Klassen zulässt."""

    def find_class(self, module, name):
        if not _erlaubt(module, name):
            raise UnsicheresObjekt(
                "Die Datei will '{0}.{1}' laden. Das gehört nicht zu einer "
                "Projektdatei des CV-Analyzers.".format(module, name))
        return super().find_class(module, name)


def historische_module_verfuegbar_machen():
    """Trägt die alten Modulnamen auf die heutigen Module in sys.modules ein."""
    eingetragen = []
    for alt, neu in HISTORISCHE_MODULE.items():
        if alt in sys.modules:
            continue
        try:
            sys.modules[alt] = importlib.import_module(neu)
            eingetragen.append(alt)
        except ImportError:
            # Modul gibt es nicht mehr — dann kann auch keine alte Datei
            # darauf verweisen, also ignorieren.
            continue
    return eingetragen


def _entpacken(roh):
    """Macht aus dem Dateiinhalt den Pickle-Stream.

    joblib legt keinen Container um den Kompressor-Strom: komprimiert beginnt die
    Datei mit den Bytes des Kompressors, unkomprimiert mit dem Pickle-Protocol-Byte
    0x80. Erkannt wird deshalb an den ersten Bytes; die Präfixe sind seit joblib
    1.2 unverändert (zlib `78 da`/`78 5e`, gzip `1f 8b`, bz2 `BZh`, xz `fd 37 7a`).
    """
    if len(roh) >= 2 and roh[0] == 0x78 and ((roh[0] << 8) | roh[1]) % 31 == 0:
        return zlib.decompress(roh)          # zlib — das schreibt joblib.dump(compress=<int>)
    if roh[:2] == b"\x1f\x8b":
        return gzip.decompress(roh)
    if roh[:3] == b"BZh":
        return bz2.decompress(roh)
    if roh[:6] == b"\xfd7zXZ\x00" or roh[:1] == b"\x5d":
        return lzma.decompress(roh)
    if roh[:1] == b"\x80":
        return roh          # unkomprimiert (compress=0/False)
    raise UnsicheresObjekt(
        "Die Datei hat ein unbekanntes Format und wird nicht geöffnet. "
        "(Kein CV-Analyzer-Projekt, keine Einstellungsdatei.)")


def _unpickler(pfad, strom):
    """SichererUnpickler mit den Argumenten, die diese joblib-Version kennt."""
    if _UNPICKLER_MIT_BYTEORDER:      # joblib >= 1.6
        return SichererUnpickler(pfad, strom, ensure_native_byte_order=True, mmap_mode=None)
    return SichererUnpickler(pfad, strom, mmap_mode=None)   # joblib 1.2 – 1.3


def laden(pfad):
    """Lädt eine Projekt- oder Einstellungsdatei, unabhängig von ihrem Alter.

    Manipulierte Dateien werden abgewiesen (`UnsicheresObjekt`), statt beim
    Entpickeln Code auszuführen.
    """
    historische_module_verfuegbar_machen()

    with open(pfad, "rb") as datei:
        strom = io.BytesIO(_entpacken(datei.read()))
    return _unpickler(pfad, strom).load()
