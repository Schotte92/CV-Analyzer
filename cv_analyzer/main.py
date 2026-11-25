import os
import io
import shutil
import joblib
import copy

import platform
import time
import pathlib
import queue
import multiprocessing
import tkinter as tk
from tkinter import messagebox

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal, cluster, spatial
import zipfile

import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from . import IO_Functions

from .FigureFrame import FigureFrame
from .mf1_Manipulation import ManipulationFrame
from .mf2_GraphSettings import GraphSettingsFrame
from .mf3_Integrate import IntegrationFrame
from .mf4_FitSettings import FitFrame
from .TableFrame import TableFrame
from .curve import Curve
from . import FileDialog

# pygmo ist auf Windows nicht per pip installierbar (keine Wheels, das sdist
# bringt kein setup.py mit). Fehlt das Paket, soll der Analyzer trotzdem
# starten — nur der Peakfit bleibt dann gesperrt, mit Hinweis statt Traceback.
try:
    import pygmo as pg

    PYGMO_IMPORTFEHLER = None
except ImportError as fehler:  # kein Wheel für diese Plattform / nicht installiert
    pg = None
    PYGMO_IMPORTFEHLER = fehler


def pygmo_verfuegbar():
    """True, wenn pygmo importierbar war. Sonst Hinweisfenster und False."""
    if pg is not None:
        return True

    if platform.system() == "Windows":
        installation = "conda install -c conda-forge pygmo"
    else:
        installation = "pip install pygmo"

    messagebox.showerror(
        "pygmo fehlt",
        "Der Peakfit braucht das Paket pygmo, das nicht installiert ist.\n\n"
        "Installieren mit:\n\n"
        "    {0}\n\n"
        "Unter Windows gibt es für pygmo keine pip-Wheels und das sdist lässt "
        "sich nicht bauen — dort geht es nur über conda-forge "
        "(z. B. Miniforge).\n\n"
        "Alle anderen Funktionen laufen auch ohne pygmo.".format(installation),
    )
    return False

from .version import __version__
from . import helpers
from . import projektdatei


def zyklus_status_setzen(Data, DelCyclus):
    """Setzt `active` aller Kurven anhand der Liste der zu verwerfenden Zyklen.

    `DelCyclus` ist der Text aus der Einstellung ("1,3"), nicht die Liste.
    Wieder aktiviert werden nur Kurven, die diese Funktion selbst verworfen hat
    (`zyklus_verworfen`). Vorher blieb ein Zyklus für immer inaktiv, sobald er
    einmal in der Liste stand — auch wenn man den Eintrag wieder löschte.
    """
    try:
        DelCyclus = np.array(np.flip(helpers.sort_aphanumeric(DelCyclus.split(","))), dtype=int)
    except ValueError:
        DelCyclus = np.array([], dtype=int)

    for i in range(len(Data)):
        c = Data[i]
        if c.cycle in DelCyclus:
            c.active = False
            c.zyklus_verworfen = True
        elif getattr(c, "zyklus_verworfen", False):
            c.active = True
            c.zyklus_verworfen = False
        elif c.active is None:
            c.active = True


def excel_blatt_schreiben(XLSXFile, df, SheetName):
    """Schreibt ein DataFrame als Blatt in eine Excel-Datei.

    Ein vorhandenes Blatt gleichen Namens wird ersetzt, alle anderen Blätter
    (samt ihrer Diagramme) bleiben erhalten.
    """
    if os.path.exists(XLSXFile):
        workbook = load_workbook(XLSXFile)
        if SheetName in workbook.sheetnames:
            if len(workbook.sheetnames) == 1:
                # Ein Arbeitsbuch ohne Blätter lässt sich nicht speichern —
                # die Datei wird deshalb neu angelegt.
                workbook.close()
                os.remove(XLSXFile)
            else:
                workbook.remove(workbook[SheetName])
                workbook.save(XLSXFile)
                workbook.close()

    with pd.ExcelWriter(XLSXFile, engine="openpyxl",
                        mode="a" if os.path.exists(XLSXFile) else "w") as writer:
        df.to_excel(writer, sheet_name=SheetName)


def kalibrier_zeilen(Data):
    """Baut die Tabelle für den Kalibrierungsexport: eine Zeile pro Kurve mit Peakfit.

    Früher wurde ein Spalten-Dict vorab mit den Peaks der ersten Kurve angelegt.
    Hatte eine andere Kurve mehr Peaks oder eine andere Richtung, verschoben sich
    die Werte oder der Export brach ab. Als Zeilenliste darf jede Kurve ihre
    eigenen Spalten mitbringen; fehlende bleiben beim DataFrame leer.
    """
    Zeilen = []
    for i in range(len(Data)):
        c = Data[i]
        if c.peak_results is None: continue

        Zeile = {
            "CurveID": c.id,
            "Name": c.name,
            "Elektrode": c.electrode,
            "Channel": c.channel,
            "Cycle": c.cycle,
            "v / V/s": c.vRate,
            "Merkmal 1": c.feature_1,
            "Merkmal 2": c.feature_2,
            "Merkmal 3": c.feature_3,
            "Merkmal 4": c.feature_4,
            "Merkmal 5": c.feature_5,
        }

        for n in range(len(c.peak_results["Ep"])):
            if c.peak_results["forward"][n] == True:
                Zeile["Ep%d_f / V" % n] = c.peak_results["Ep"][n]
                Zeile["Ip%d_f / A" % n] = c.peak_results["Ip"][n]
            else:
                Zeile["Ep%d_r / V" % n] = c.peak_results["Ep"][n]
                Zeile["Ip%d_r / A" % n] = c.peak_results["Ip"][n]

        Zeile["E0L / V"] = ""
        Zeile["E0R / V"] = ""
        if c.working_data is not None:
            Erev = c.working_data["E_rev"]
            zeros = helpers.FindZeroCrossings(c.working_data["I"][:Erev])
            if len(zeros) != 0:
                Zeile["E0L / V"] = c.working_data["E"][zeros[0]]
            zeros = helpers.FindZeroCrossings(c.working_data["I"][Erev:])
            if len(zeros) != 0:
                Zeile["E0R / V"] = c.working_data["E"][Erev+zeros[0]]

        Zeilen.append(Zeile)
    return Zeilen


def excel_bild_einfuegen(XLSXFile, SheetName, fig, zelle):
    """Hängt eine Abbildung an eine Zelle des Blattes.

    Das Bild geht über einen BytesIO direkt in die Arbeitsmappe. Früher wurde es
    als `<Ziel>.xlsx_graph.png` neben die Zieltabelle geschrieben und danach
    gelöscht — dabei wurde eine gleichnamige fremde Datei überschrieben und
    anschließend entfernt.
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    buffer.seek(0)

    workbook = load_workbook(XLSXFile)
    worksheet = workbook[SheetName]
    worksheet.add_image(Image(buffer), zelle)
    workbook.save(XLSXFile)
    workbook.close()

# GUI
class GUI(object):
    def __init__(self, master, client):
        self.master = master
        self.client = client

        tk.Tk.wm_title(self.master, "CV Analyzer [Version {0}, ©Schottenbauer 2026] - unbekanntes Projekt".format(__version__))
        # Icon liegt im Paket, damit der Aufruf nicht vom Arbeitsverzeichnis abhängt
        tk.Tk.iconphoto(self.master, False,
                        tk.PhotoImage(file=str(pathlib.Path(__file__).parent / "Icon.png")))

        self.MethodFrameList = ["Zyklen & Manipulationen", "Plot-Einstellungen", "Integration", "Kurvenfit"]
        self.SavePath = None

        # Datenmodell - Data:
        # - raw Data
        # - working Data (geglättet etc)
        # - Peak_results
        #
        # Datenmodell - Measurement:
        # - Name
        # - tn, En, In
        # - Position Umkehrpunkt
        # - Vorschubspannung
        # - Zeitschritte zwischen den Datenpunkten
        self.CurveTableDefault = {"CurveID": [], "Name": [], "Active": [], "Electrode": [], "Channel": [], "Cycle": [], "v / V/s": [], "Merkmal 1": [], "Merkmal 2": [], "Merkmal 3": [], "Merkmal 4": [], "Merkmal 5": []}
        self.PeakTableDefault = {"forward": [], "E1 / V": [], "E2 / V": [], "σ / V": [], "τ / V": []}
        self.ResultTableDefault = {"CurveID": [], "forward": [], "Ep / V": [], "σ / V": [], "τ / s": [], "Ip / A": [], "Ip_F / A": [], "Ip_C / A": [], "Qp / C": []}
        self.Data = []
        self.Settings = {
            # Allgemein
            "ActiveMethodFrame": tk.StringVar(value=self.MethodFrameList[0]),
            # Manipulationen
            "DelCyclus": tk.StringVar(value="1"),
            "SavGol_Active": tk.IntVar(value=0), "SavGol_Width": tk.DoubleVar(value=0.1), "SavGol_Polynom": tk.IntVar(value=3),
            "Interpolate_Active": tk.IntVar(value=0), "Interpolate_Points": tk.IntVar(value=500),
            "Correction_Active": tk.IntVar(value=0), "Correction_Eref": tk.StringVar(value=""),
            "Normalize_E_MinMax": tk.IntVar(value=0), "Normalize_E_ZeroCrossings": tk.IntVar(value=0),
            # GraphSettings
            "ColorationScheme_Choice": tk.IntVar(value=1), "ColorBar_Active": tk.IntVar(value=0), "Legend_Active": tk.IntVar(value=0), "Reverse_Colors": tk.IntVar(value=0),
            # Integration
            "Integrate_ERangeStart": tk.DoubleVar(value=0.0), "Integrate_ERangeEnd": tk.DoubleVar(value=0.0),
            "Integrate_Edl": tk.DoubleVar(value=0.0),
            # FitSetings
            # Muss schon hier belegt sein: SettingsDump (unten) merkt sich diesen
            # Stand, und "Einstellungen resetten" stellt ihn wieder her. Mit ""
            # kam danach eine leere Peakform in den Fit (KeyError in Shapes).
            "Fit_PeakShape": tk.StringVar(value="Gauß-Peak"),
            "Fit_ERangeStart_Forward": tk.DoubleVar(value=0.0), "Fit_ERangeEnd_Forward": tk.DoubleVar(value=0.0),
            "Fit_ERangeStart_Reverse": tk.DoubleVar(value=0.0), "Fit_ERangeEnd_Reverse": tk.DoubleVar(value=0.0),
            "Fit_wd0": tk.IntVar(value=0), "Fit_wd1": tk.IntVar(value=1), "Fit_wd2": tk.IntVar(value=1),
            "Fit_Generations": tk.IntVar(value=200),
            "Fit_Workers": tk.IntVar(value=multiprocessing.cpu_count()),
            "CurveID_Iterator": tk.IntVar(value=0),
        }
        self.SettingsDump = {}
        for name in self.Settings:
            self.SettingsDump.update({name: self.Settings[name].get()})
        self.GUI_Elements = {
            "mf3_Button_StartFit": None,
            "mf3_Button_StopFit": None,
            "mf3_Label_ProgressBar": None,
            "mf3_ProgressBar": None,
        }

        # Keybinds
        self.master.bind("<Control-s>", self.Key_Save)
        self.master.bind("<Control-o>", self.Key_Open)

        menubar = tk.Menu(self.master)
        menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Datei", menu=menu)
        menu.add_command(label="Neu", command=self.Menu_New)
        menu.add_command(label="Neu + Einstellungen resetten", command=self.Menu_NewAndReset)
        menu.add_separator()
        menu.add_command(label="Speichern", command=self.Menu_Save)
        menu.add_command(label="Speichern unter...", command=self.Menu_SaveAs)
        menu.add_command(label="Öffnen...", command=self.Menu_Open)
        menu.add_separator()
        menu.add_command(label="Beenden", command=self.client.end_application)

        menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Import", menu=menu)
        menu.add_command(label="PalmSens CSV-Dateien...", command=self.Menu_ImportPalmSensCSV)
        menu.add_command(label="PalmSens Excel-Dateien...", command=self.Menu_ImportPalmSensExcel)
        menu.add_separator()
        menu.add_command(label="Raspberry Pi ZIP-Datei...", command=self.Menu_ImportRaspbiZIP)
        menu.add_command(label="Numpy npz-Dateien...", command=self.Menu_ImportNPZ)
        menu.add_command(label="SRS-Dateien...", command=self.Menu_ImportSRS)
        # menu.add_command(label="Import Solartron...")
        menu.add_separator()
        menu.add_command(label="SRS-Ordner zu Dateien", command=self.Menu_ReorderSRS)
        # menu.add_separator()
        # menu.add_command(label="Exportieren...")

        menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Export", menu=menu)
        menu.add_command(label="Peak-Fit-Results to Excel", command=self.Menu_ExportPeaks_to_Excel)
        menu.add_command(label="Cumsum-Q-Results to Excel", command=self.Menu_Export_CumsumQ_to_Excel)
        menu.add_command(label="IfI-Results to Excel", command=self.Menu_Export_IFI_to_Excel)
        menu.add_command(label="Peaks for Calibration to Excel", command=self.Menu_Export_Peaks_for_Calibration_to_Excel)
        menu.add_separator()
        menu.add_command(label="Plot: Kummulative Peakladung je Kurve", command=self.Menu_CumsumQ_Plot)
        menu.add_command(label="Plot: Anteil Faradaystrom an Gesamtstrom", command=self.Menu_IFI_Plot)

        menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Einstellungen", menu=menu)
        menu.add_command(label="Reset", command=self.Menu_ResetSettings)
        menu.add_separator()
        menu.add_command(label="Einstellungen speichern...", command=self.Menu_ExportSettings)
        menu.add_command(label="Einstellungen laden...", command=self.Menu_ImportSettings)

        self.master.config(menu=menubar)

        # Hauptframe
        MainFrame = tk.Frame(self.master)
        MainFrame.pack(fill="both", expand=True)
        MainFrame.grid_rowconfigure(0)
        MainFrame.grid_rowconfigure(1, weight=1)
        MainFrame.grid_columnconfigure(0, weight=1)

        self.method_frames = []

        row = tk.Frame(MainFrame)
        opt = tk.OptionMenu(row, self.Settings["ActiveMethodFrame"], *self.MethodFrameList, command=self.ShowFrame)
        opt.config(width=38)
        opt.pack()
        self.HorizontalLine(row)
        row.grid(row=0, column=0, sticky="nsew")

        for i, F in enumerate([ManipulationFrame, GraphSettingsFrame, IntegrationFrame, FitFrame]):
            frame = F(MainFrame, self)
            self.method_frames.append(frame)
            frame.grid(row=1, column=0, sticky="nsew")

        self.Graph = FigureFrame(MainFrame, self)
        self.Graph.grid(row=0, column=1, rowspan=2, sticky="nsew")

        col = tk.Frame(MainFrame)

        self.CurveTable = TableFrame(col, self)
        self.CurveTable.grid(row=0, column=0, sticky="nsew")
        self.CurveTable.SetValues(self.CurveTableDefault)

        self.PeakTable = TableFrame(col, self)
        self.PeakTable.grid(row=1, column=0, sticky="nsew")
        self.PeakTable.SetValues(self.PeakTableDefault)

        self.ResultTable = TableFrame(col, self)
        self.ResultTable.grid(row=2, column=0, sticky="nsew")
        self.ResultTable.SetValues(self.ResultTableDefault)

        col.grid(row=0, column=2, rowspan=2, sticky="nsew")

        self.ShowFrame()

    # -----------------------------------------------------------------------------------------------
    # Berechungs- und Zeichenfunktionen
    # -----------------------------------------------------------------------------------------------
    def Recalculate(self):
        self.UpdateCurveData()
        zyklus_status_setzen(self.Data, self.Settings["DelCyclus"].get())

        for i in range(len(self.Data)):
            if not self.Data[i].active:
                self.Data[i].working_data = None
                self.Data[i].calculated_data = None
                self.Data[i].peak_results = None
                continue
            self.Data[i].working_data = copy.deepcopy(self.Data[i].raw_data)

            if self.Settings["SavGol_Active"].get() == 1:
                SavGolWindow = float(self.Settings["SavGol_Width"].get())
                SavGolWindow = int(SavGolWindow / (self.Data[i].vRate * self.Data[i].working_data["dt"]))
                if SavGolWindow % 2 == 0: SavGolWindow += 1

                rev = self.Data[i].working_data["E_rev"]
                t = self.Data[i].working_data["t"][:rev]
                E = signal.savgol_filter(self.Data[i].working_data["E"][:rev], window_length=SavGolWindow, polyorder=int(self.Settings["SavGol_Polynom"].get()))
                I = signal.savgol_filter(self.Data[i].working_data["I"][:rev], window_length=SavGolWindow, polyorder=int(self.Settings["SavGol_Polynom"].get()))

                t = np.append(t, self.Data[i].working_data["t"][rev:])
                E = np.append(E, signal.savgol_filter(self.Data[i].working_data["E"][rev:], window_length=SavGolWindow, polyorder=int(self.Settings["SavGol_Polynom"].get())))
                I = np.append(I, signal.savgol_filter(self.Data[i].working_data["I"][rev:], window_length=SavGolWindow, polyorder=int(self.Settings["SavGol_Polynom"].get())))

                self.Data[i].working_data["E"] = E
                self.Data[i].working_data["I"] = I
            if self.Settings["Interpolate_Active"].get() == 1:
                # Einmal interpolieren genügt — die alte Schleife lief über alle
                # Messpunkte und rechnete jedes Mal dieselbe Interpolation erneut.
                t_alt = self.Data[i].working_data["t"]
                t_new = np.linspace(np.min(t_alt), np.max(t_alt), int(self.Settings["Interpolate_Points"].get()))
                E_neu = np.interp(t_new, t_alt, self.Data[i].working_data["E"])
                I_neu = np.interp(t_new, t_alt, self.Data[i].working_data["I"])
                self.Data[i].working_data["E"] = E_neu
                self.Data[i].working_data["I"] = I_neu
                self.Data[i].working_data["t"] = t_new
                self.Data[i].working_data["E_rev"] = np.argmax(E_neu)
                self.Data[i].working_data["dt"] = t_new[1]-t_new[0]

            if self.Settings["Correction_Active"].get() == 1:
                if self.Settings["Correction_Eref"].get() != "":
                    self.Data[i].working_data["E"] -= float(self.Settings["Correction_Eref"].get())

            # Normalisierung
            if self.Settings["Normalize_E_ZeroCrossings"].get() == 1:
                E_Manipulation = 1
            elif self.Settings["Normalize_E_MinMax"].get() == 1:
                E_Manipulation = 2
            else:
                E_Manipulation = 0

            if self.Data[i].peak_results is not None:
                if "E_Manipulation" not in self.Data[i].peak_results.keys():
                    # Wenn nicht vorhanden, gehe davon aus, dass nicht normiert etc wurde (Schlimmstenfalls ist ein neuer Peakfit nötig)
                    self.Data[i].peak_results["E_Manipulation"] = 0
                if E_Manipulation != self.Data[i].peak_results["E_Manipulation"]:
                    # Vorherige Manipulationen rückgängig machen...
                    if self.Data[i].peak_results["E_Manipulation"] == 1:
                        E1 = self.Data[i].working_data["E"][helpers.FindZeroCrossings(self.Data[i].working_data["I"][:self.Data[i].working_data["E_rev"]])[0]]
                        E2 = self.Data[i].working_data["E"][self.Data[i].working_data["E_rev"] + helpers.FindZeroCrossings(self.Data[i].working_data["I"][self.Data[i].working_data["E_rev"]:])[0]]
                        for n in range(len(self.Data[i].peak_results["Ep"])):
                            self.Data[i].peak_results["Ep"][n] = self.Data[i].peak_results["Ep"][n]*(E2-E1) + E1
                            self.Data[i].peak_results["σ"][n] = self.Data[i].peak_results["σ"][n]*(E2-E1)
                            self.Data[i].calculated_data["E"][n] = self.Data[i].calculated_data["E"][n]*(E2-E1) + E1
                    elif self.Data[i].peak_results["E_Manipulation"] == 2:
                        E1 = np.min(self.Data[i].working_data["E"])
                        E2 = np.max(self.Data[i].working_data["E"])
                        for n in range(len(self.Data[i].peak_results["Ep"])):
                            self.Data[i].peak_results["Ep"][n] = self.Data[i].peak_results["Ep"][n]*(E2-E1) + E1
                            self.Data[i].peak_results["σ"][n] = self.Data[i].peak_results["σ"][n]*(E2-E1)
                            self.Data[i].calculated_data["E"][n] = self.Data[i].calculated_data["E"][n]*(E2-E1) + E1
                    self.Data[i].peak_results["E_Manipulation"] = 0

            if E_Manipulation == 1: # Zero-Crossings
                E1 = self.Data[i].working_data["E"][helpers.FindZeroCrossings(self.Data[i].working_data["I"][:self.Data[i].working_data["E_rev"]])[0]]
                E2 = self.Data[i].working_data["E"][self.Data[i].working_data["E_rev"] + helpers.FindZeroCrossings(self.Data[i].working_data["I"][self.Data[i].working_data["E_rev"]:])[0]]
                self.Data[i].working_data["E"] = (self.Data[i].working_data["E"] - E1) / (np.max(E2 - E1))
                if self.Data[i].peak_results is not None:
                    if E_Manipulation != self.Data[i].peak_results["E_Manipulation"]:
                        for n in range(len(self.Data[i].peak_results["Ep"])):
                            self.Data[i].peak_results["Ep"][n] = (self.Data[i].peak_results["Ep"][n]-E1)/(np.max(E2 - E1))
                            self.Data[i].peak_results["σ"][n] = self.Data[i].peak_results["σ"][n] / (np.max(E2 - E1))
                            self.Data[i].calculated_data["E"][n] = (self.Data[i].calculated_data["E"][n]-E1)/(np.max(E2 - E1))
                        self.Data[i].peak_results["E_Manipulation"] = E_Manipulation
            elif E_Manipulation == 2: # MinMax
                E1 = np.min(self.Data[i].working_data["E"])
                E2 = np.max(self.Data[i].working_data["E"])
                self.Data[i].working_data["E"] = (self.Data[i].working_data["E"] - E1) / (np.max(E2 - E1))
                if self.Data[i].peak_results is not None:
                    if E_Manipulation != self.Data[i].peak_results["E_Manipulation"]:
                        for n in range(len(self.Data[i].peak_results["Ep"])):
                            self.Data[i].peak_results["Ep"][n] = (self.Data[i].peak_results["Ep"][n]-E1)/(np.max(E2 - E1))
                            self.Data[i].peak_results["σ"][n] = self.Data[i].peak_results["σ"][n] / (np.max(E2 - E1))
                            self.Data[i].calculated_data["E"][n] = (self.Data[i].calculated_data["E"][n]-E1)/(np.max(E2 - E1))
                        self.Data[i].peak_results["E_Manipulation"] = E_Manipulation
        self.UpdateResultTable()
        self.SetCurveTable()
        self.Redraw()

    def get_v_minmax(self):
        v_min = None
        v_max = None
        for i in range(len(self.Data)):
            if v_min is None:
                v_min = self.Data[i].vRate
            else:
                if v_min > self.Data[i].vRate:
                    v_min = self.Data[i].vRate

            if v_max is None:
                v_max = self.Data[i].vRate
            else:
                if v_max < self.Data[i].vRate:
                    v_max = self.Data[i].vRate
        if v_min is None: v_min = 0.0
        if v_max is None: v_max = 1.0
        return v_min, v_max

    def Redraw(self):
        # Kein UpdateCurveData hier: das würde den Tabellenstand (der beim letzten
        # SetCurveTable geschrieben wurde) über die frisch berechneten Daten
        # legen — z. B. eine von DelCyclus verworfene Kurve wieder aktivieren.
        # Die Tabelle wird an einer Stelle gelesen: am Anfang von Recalculate.
        self.Graph.Redraw()

    def Calc_CumsumQ(self):
        self.UpdateCurveData()

        ID = np.array([], dtype=int)
        x = np.array([], dtype=float)
        y1 = np.array([], dtype=float)
        y2 = np.array([], dtype=float)
        for i in range(len(self.Data)):
            if self.Data[i].peak_results is not None:
                y1_temp = 0
                y2_temp = 0
                for n in range(len(self.Data[i].peak_results["Ep"])):
                    if bool(self.Data[i].peak_results["forward"][n]):
                        y1_temp += self.Data[i].peak_results["Qp"][n]
                    else:
                        y2_temp += self.Data[i].peak_results["Qp"][n]

                ID = np.append(ID, self.Data[i].id)
                if y1_temp == 0.0:
                    y1 = np.append(y1, np.nan)
                else:
                    y1 = np.append(y1, float(y1_temp))
                if y2_temp == 0.0:
                    y2 = np.append(y2, np.nan)
                else:
                    y2 = np.append(y2, float(y2_temp))

                ColorSchemeCoice = int(self.Settings["ColorationScheme_Choice"].get())
                if ColorSchemeCoice >= 6:
                    if ColorSchemeCoice == 6: x = np.append(x, float(self.Data[i].feature_1))
                    elif ColorSchemeCoice == 7: x = np.append(x, float(self.Data[i].feature_2))
                    elif ColorSchemeCoice == 8: x = np.append(x, float(self.Data[i].feature_3))
                    elif ColorSchemeCoice == 9: x = np.append(x, float(self.Data[i].feature_4))
                    elif ColorSchemeCoice == 10: x = np.append(x, float(self.Data[i].feature_5))
                else:
                    x = np.append(x, float(self.Data[i].channel))

        return {"CurveID": ID, "x": x, "y1": y1, "y2": y2}

    def Calc_IFI(self):
        self.UpdateCurveData()

        ID = np.array([], dtype=int)
        x = np.array([], dtype=float)
        y1 = np.array([], dtype=float)
        y2 = np.array([], dtype=float)
        for i in range(len(self.Data)):
            if self.Data[i].peak_results is not None:
                ID = np.append(ID, self.Data[i].id)
                ColorSchemeCoice = int(self.Settings["ColorationScheme_Choice"].get())
                if ColorSchemeCoice >= 6:
                    if ColorSchemeCoice == 6: x = np.append(x, float(self.Data[i].feature_1))
                    elif ColorSchemeCoice == 7: x = np.append(x, float(self.Data[i].feature_2))
                    elif ColorSchemeCoice == 8: x = np.append(x, float(self.Data[i].feature_3))
                    elif ColorSchemeCoice == 9: x = np.append(x, float(self.Data[i].feature_4))
                    elif ColorSchemeCoice == 10: x = np.append(x, float(self.Data[i].feature_5))
                else:
                    x = np.append(x, float(self.Data[i].channel))

                Estart_Forward = self.Settings["Fit_ERangeStart_Forward"].get()
                Eend_Forward = self.Settings["Fit_ERangeEnd_Forward"].get()
                if Eend_Forward - Estart_Forward != 0:
                    if Eend_Forward - Estart_Forward < 0:
                        tmp = Estart_Forward
                        Estart_Forward = Eend_Forward
                        Eend_Forward = tmp
                    Erev = self.Data[i].working_data["E_rev"]
                    start = helpers.GetNearest(self.Data[i].working_data["E"][:Erev], Estart_Forward)
                    end = helpers.GetNearest(self.Data[i].working_data["E"][:Erev], Eend_Forward)
                    I = self.Data[i].working_data["I"][start:end]
                    Icalc = np.zeros_like(I)
                    for n in range(len(self.Data[i].peak_results["Ep"])):
                        if bool(self.Data[i].peak_results["forward"][n]):
                            Icalc += self.Data[i].calculated_data["I"][n]
                    ind = np.argmax(Icalc)
                    y1 = np.append(y1, Icalc[ind]/I[ind])
                else: y1 = np.append(y1, np.nan)

                Estart_Reverse = self.Settings["Fit_ERangeStart_Reverse"].get()
                Eend_Reverse = self.Settings["Fit_ERangeEnd_Reverse"].get()
                if Eend_Reverse - Estart_Reverse != 0:
                    if Eend_Reverse - Estart_Reverse > 0:
                        tmp = Estart_Reverse
                        Estart_Reverse = Eend_Reverse
                        Eend_Reverse = tmp
                    Erev = self.Data[i].working_data["E_rev"]
                    start = Erev + helpers.GetNearest(self.Data[i].working_data["E"][Erev:], Estart_Reverse)
                    end = Erev + helpers.GetNearest(self.Data[i].working_data["E"][Erev:], Eend_Reverse)
                    I = self.Data[i].working_data["I"][start:end]
                    Icalc = np.zeros_like(I)
                    for n in range(len(self.Data[i].peak_results["Ep"])):
                        if not bool(self.Data[i].peak_results["forward"][n]):
                            Icalc += self.Data[i].calculated_data["I"][n]
                    ind = np.argmin(Icalc)
                    y2 = np.append(y2, Icalc[ind]/I[ind])
                else: y2 = np.append(y2, np.nan)

        return {"CurveID": ID, "x": x, "y1": y1, "y2": y2}

    # -----------------------------------------------------------------------------------------------
    # Tabellen- und Fit-Funktionen
    # -----------------------------------------------------------------------------------------------
    def SetCurveTable(self):
        # Schreibt nur Data -> Tabelle. Das frühere UpdateCurveData am Anfang
        # las den alten Tabellenstand zurück in die Daten und hat beim Öffnen
        # eines Projekts die frisch geladenen Kurven mit den Werten des vorigen
        # Projekts überschrieben (gleiche CurveID).
        df = copy.deepcopy(self.CurveTableDefault)
        for i in range(len(self.Data)):
            df["CurveID"].append(self.Data[i].id)
            df["Name"].append(self.Data[i].name)
            df["Active"].append(self.Data[i].active)
            df["Electrode"].append(self.Data[i].electrode)
            df["Channel"].append(self.Data[i].channel)
            df["Cycle"].append(self.Data[i].cycle)
            df["v / V/s"].append(self.Data[i].vRate)
            df["Merkmal 1"].append(self.Data[i].feature_1)
            df["Merkmal 2"].append(self.Data[i].feature_2)
            df["Merkmal 3"].append(self.Data[i].feature_3)
            df["Merkmal 4"].append(self.Data[i].feature_4)
            df["Merkmal 5"].append(self.Data[i].feature_5)
        self.CurveTable.SetValues(df)

    def UpdateCurveData(self):
        TableValues = self.CurveTable.GetValues()

        def ganzzahl(wert):
            """Die Tabelle führt Zahlen als float (wegen der NaN-Füllung) —
            Zyklus und Channel sind aber ganze Zahlen."""
            if isinstance(wert, (int, np.integer)):
                return int(wert)
            if isinstance(wert, float) and float(wert).is_integer():
                return int(wert)
            return wert

        for i in range(len(TableValues[0])):
            if not np.isnan(TableValues[0][i]):
                for n in range(len(self.Data)):
                    if TableValues[0][i] == self.Data[n].id:
                        self.Data[n].name = TableValues[1][i]
                        # Einen Kurve, die die Zyklusauswahl (DelCyclus) verworfen
                        # hat, darf die Tabelle nicht wieder aktivieren: sie steht
                        # dort noch mit dem alten "True", und Recalculate würde sie
                        # mit working_data = None zeichnen wollen (TypeError in
                        # FigureFrame.Redraw). Aktiv/inaktiv entscheidet hier die
                        # Auswahl, nicht das alte Tabellenstandbild.
                        if not getattr(self.Data[n], "zyklus_verworfen", False):
                            self.Data[n].active = TableValues[2][i]
                        self.Data[n].electrode = TableValues[3][i]
                        self.Data[n].channel = ganzzahl(TableValues[4][i])
                        self.Data[n].cycle = ganzzahl(TableValues[5][i])
                        self.Data[n].vRate = TableValues[6][i]
                        self.Data[n].feature_1 = TableValues[7][i]
                        self.Data[n].feature_2 = TableValues[8][i]
                        self.Data[n].feature_3 = TableValues[9][i]
                        self.Data[n].feature_4 = TableValues[10][i]
                        self.Data[n].feature_5 = TableValues[11][i]
                        break

    def UpdateResultTable(self, df=None):
        if df is None:
            df = {"CurveID": [], "forward": [], "Ep / V": [], "σ / V": [], "τ / s": [], "Ip / A": [], "Ip_F / A": [], "Ip_C / A": [], "Qp / C": []}
        else:
            df = copy.deepcopy(df)
        for i in range(len(self.Data)):
            if self.Data[i].peak_results is not None:
                for n in range(len(self.Data[i].peak_results["Ep"])):
                    df["CurveID"].append(self.Data[i].id)
                    df["forward"].append(self.Data[i].peak_results["forward"][n])
                    df["Ep / V"].append(self.Data[i].peak_results["Ep"][n])
                    df["σ / V"].append(self.Data[i].peak_results["σ"][n])
                    df["τ / s"].append(self.Data[i].peak_results["τ"][n])
                    df["Ip / A"].append(self.Data[i].peak_results["Ip"][n])
                    df["Ip_F / A"].append(self.Data[i].peak_results["Ip_F"][n])
                    df["Ip_C / A"].append(self.Data[i].peak_results["Ip_C"][n])
                    df["Qp / C"].append(self.Data[i].peak_results["Qp"][n])
        self.ResultTable.SetValues(df)

    def Integrate(self):
        Estart = self.Settings["Integrate_ERangeStart"].get()
        Eend = self.Settings["Integrate_ERangeEnd"].get()
        Edl = self.Settings["Integrate_Edl"].get()

        results = {"Name": [], "Elektrode": [], "Channel": [], "forward": [], "Cycle": [], "v / V/s": [], "Qges / C": [], "Qdl / C": [], "Qf / C": [], "Idl / A": []}

        for i in range(len(self.Data)):
            if not self.Data[i].active: continue

            # Forward
            Erev = self.Data[i].working_data["E_rev"]
            t = self.Data[i].working_data["t"]
            E = self.Data[i].working_data["E"]
            I = self.Data[i].working_data["I"]
            vRate = self.Data[i].vRate

            start = helpers.GetNearest(E[:Erev], Estart)
            end = helpers.GetNearest(E[:Erev], Eend)
            dl = helpers.GetNearest(E[:Erev], Edl)

            if start > end:
                tmp = start
                start = end
                end = tmp

            Qges = abs(helpers.trapez(I[start:end], t[start:end]))
            Qdl = abs(I[dl] * (t[end] - t[start]))
            Qf = Qges - Qdl

            results["Name"].append(self.Data[i].name)
            results["Elektrode"].append(self.Data[i].electrode)
            results["Channel"].append(self.Data[i].channel)
            results["Cycle"].append(self.Data[i].cycle)
            results["forward"].append(True)
            results["v / V/s"].append(vRate)
            results["Qges / C"].append(Qges)
            results["Qdl / C"].append(Qdl)
            results["Qf / C"].append(Qf)
            results["Idl / A"].append(I[dl])

            # Reverse
            start = Erev + helpers.GetNearest(E[Erev:], Estart)
            end = Erev + helpers.GetNearest(E[Erev:], Eend)
            dl = Erev + helpers.GetNearest(E[Erev:], Edl)

            if start > end:
                tmp = start
                start = end
                end = tmp

            Qges = abs(helpers.trapez(I[start:end], t[start:end]))
            Qdl = abs(I[dl] * (t[end] - t[start]))
            Qf = Qges - Qdl

            results["Name"].append(self.Data[i].name)
            results["Elektrode"].append(self.Data[i].electrode)
            results["Channel"].append(self.Data[i].channel)
            results["Cycle"].append(self.Data[i].cycle)
            results["forward"].append(False)
            results["v / V/s"].append(vRate)
            results["Qges / C"].append(Qges)
            results["Qdl / C"].append(Qdl)
            results["Qf / C"].append(Qf)
            results["Idl / A"].append(I[dl])
        self.ResultTable.SetValues(results)

    def GetPeakCandidates(self):
        Values = self.PeakTable.GetValues()

        ind = []
        for i in range(len(Values[1])):
            if (type(Values[1][i]) is float or type(Values[1][i]) is int):
                if not np.isnan(Values[1][i]):
                    ind.append(i)

        return {
            "forward": list(Values[0][ind]),
            "E1 / V": list(Values[1][ind]),
            "E2 / V": list(Values[2][ind]),
            "σ / V": list(Values[3][ind]),
            "τ / V": list(Values[4][ind]),
        }

    def SearchPeaks(self):
        PeakWidth = float(self.Settings["SavGol_Width"].get()) # in E
        Estart_f = self.Settings["Fit_ERangeStart_Forward"].get()
        Eend_f = self.Settings["Fit_ERangeEnd_Forward"].get()
        Estart_r = self.Settings["Fit_ERangeStart_Reverse"].get()
        Eend_r = self.Settings["Fit_ERangeEnd_Reverse"].get()

        if Estart_f != Eend_f:
            PeakCandidates = []
            for i in range(len(self.Data)):
                if self.Data[i].active:
                    E = self.Data[i].working_data["E"][:self.Data[i].working_data["E_rev"]]
                    start = helpers.GetNearest(E, Estart_f)
                    end = helpers.GetNearest(E, Eend_f)
                    E = self.Data[i].working_data["E"][start:end]
                    I = self.Data[i].working_data["I"][start:end]

                    # Peaksuche
                    p, pp = signal.find_peaks(I, width=PeakWidth/self.Data[i].working_data["dE"])
                    PeakCandidates = np.append(PeakCandidates, E[p])

            if len(PeakCandidates) > 0:
                dist = spatial.distance.pdist(PeakCandidates.reshape(-1, 1), metric="euclidean")
                Z = cluster.hierarchy.linkage(dist, method="ward")
                clusters = cluster.hierarchy.fcluster(Z, t=2*PeakWidth, criterion="distance")

                for c in np.unique(clusters):
                    p = np.mean(PeakCandidates[np.argwhere(clusters == c).flatten()])
                    E1 = p-PeakWidth/2
                    E2 = p+PeakWidth/2
                    if E1 < Estart_f: E1 = Estart_f
                    if E2 > Eend_f: E2 = Eend_f
                    self.AddPeakCandidate([E1,E2], forward=True)

        if Estart_r != Eend_r:
            PeakCandidates = []
            for i in range(len(self.Data)):
                if self.Data[i].active:
                    E = self.Data[i].working_data["E"][self.Data[i].working_data["E_rev"]:]
                    start = self.Data[i].working_data["E_rev"] + helpers.GetNearest(E, Estart_r)
                    end = self.Data[i].working_data["E_rev"] + helpers.GetNearest(E, Eend_r)
                    if start > end:
                        tmp = start
                        start = end
                        end = tmp
                    E = self.Data[i].working_data["E"][start:end]
                    I = -1*self.Data[i].working_data["I"][start:end]

                    # Peaksuche
                    p, pp = signal.find_peaks(I, width=PeakWidth / self.Data[i].working_data["dE"])
                    PeakCandidates = np.append(PeakCandidates, E[p])

            if len(PeakCandidates) > 0:
                dist = spatial.distance.pdist(PeakCandidates.reshape(-1, 1), metric="euclidean")
                Z = cluster.hierarchy.linkage(dist, method="ward")
                clusters = cluster.hierarchy.fcluster(Z, t=2 * PeakWidth, criterion="distance")

                for c in np.unique(clusters):
                    p = np.mean(PeakCandidates[np.argwhere(clusters == c).flatten()])
                    E1 = p-PeakWidth/2
                    E2 = p+PeakWidth/2
                    if E1 < Estart_r: E1 = Estart_r
                    if E2 > Eend_r: E2 = Eend_r
                    self.AddPeakCandidate([E1,E2], forward=False)

    def AddPeakCandidate(self, xdata, forward):
        peak_candidates = self.GetPeakCandidates()

        E1 = xdata[0]
        E2 = xdata[1]

        if forward:
            Estart = self.Settings["Fit_ERangeStart_Forward"].get()
            Eend = self.Settings["Fit_ERangeEnd_Forward"].get()
        else:
            Estart = self.Settings["Fit_ERangeStart_Reverse"].get()
            Eend = self.Settings["Fit_ERangeEnd_Reverse"].get()

        if E1 < Estart or E1 > Eend or E2 < Estart or E2 > Eend:
            tk.messagebox.showerror("Ungültige Eingabe", "Die Grenzpotentiale zwischen denen der Peak liegt, müssen innerhalb des Fit-Bereichs sein!")
            return
        if E1 >= E2:
            tk.messagebox.showerror("Ungültige Eingabe", "E1 muss kleiner als E2 sein!")
            return

        if E2 - E1 > 0:
            s = E2 - E1
            t = E2 - E1
        else:
            s = 0.1
            t = 0.1

        if len(peak_candidates["forward"]) == 1:
            if peak_candidates["forward"][0] == "":
                peak_candidates["forward"] = [forward]
                peak_candidates["E1 / V"] = [E1]
                peak_candidates["E2 / V"] = [E2]
                peak_candidates["σ / V"] = [s]
                peak_candidates["τ / V"] = [t]

                self.PeakTable.SetValues(peak_candidates)
                return

        peak_candidates["forward"].append(forward)
        peak_candidates["E1 / V"].append(E1)
        peak_candidates["E2 / V"].append(E2)
        peak_candidates["σ / V"].append(s)
        peak_candidates["τ / V"].append(t)

        self.PeakTable.SetValues(peak_candidates)

    def StartFit(self):
        # Ohne pygmo gibt es keinen Optimierer — dann erst gar nicht starten,
        # statt die Worker an einem AttributeError auf pg.problem scheitern zu lassen.
        if not pygmo_verfuegbar():
            return

        self.GUI_Elements["mf3_Button_StartFit"]["state"] = "disabled"
        self.GUI_Elements["mf3_Button_StopFit"]["state"] = "normal"

        # Alte Results löschen
        for i in range(len(self.Data)):
            self.Data[i].peak_results = None
            self.Data[i].calculated_data = None
        self.ResultTable.SetValues(self.ResultTableDefault)

        # Bereiche laden
        Estart_Forward = self.Settings["Fit_ERangeStart_Forward"].get()
        Eend_Forward = self.Settings["Fit_ERangeEnd_Forward"].get()

        Estart_Reverse = self.Settings["Fit_ERangeStart_Reverse"].get()
        Eend_Reverse = self.Settings["Fit_ERangeEnd_Reverse"].get()

        # PeakKandidaten laden
        peak_candidates = self.GetPeakCandidates()
        forward = np.array(peak_candidates["forward"], dtype=bool)
        E1 = np.array(peak_candidates["E1 / V"], dtype=float)
        E2 = np.array(peak_candidates["E2 / V"], dtype=float)
        sigma = np.array(peak_candidates["σ / V"], dtype=float)
        tau = np.array(peak_candidates["τ / V"], dtype=float)

        # Peakform
        PeakShape = self.Settings["Fit_PeakShape"].get()
        if PeakShape == "Gauß-Peak":
            PeakShape = "gaussian"
        elif PeakShape == "Exp. mod. Gauß-Peak":
            PeakShape = "exp_gaussian"
        if PeakShape not in ("gaussian", "exp_gaussian"):
            # Kann nur durch eine alte Einstellungsdatei oder ein Reset mit leerem
            # Wert passieren. Ohne diese Prüfung bricht der Fit später im Worker
            # mit KeyError in helpers.Shapes ab, während die Oberfläche "Fit läuft"
            # anzeigt.
            self.GUI_Elements["mf3_Button_StartFit"]["state"] = "normal"
            self.GUI_Elements["mf3_Button_StopFit"]["state"] = "disabled"
            messagebox.showerror(
                "Peakform fehlt",
                "Es ist keine gültige Peakform eingestellt ('{0}').\n\n"
                "Bitte unter Kurvenfit eine Peak-Form wählen.".format(PeakShape))
            return

        # Ableitungen
        wd0 = self.Settings["Fit_wd0"].get()
        wd1 = self.Settings["Fit_wd1"].get()
        wd2 = self.Settings["Fit_wd2"].get()

        # Generationen
        generations = self.Settings["Fit_Generations"].get()

        # SavGolWindow
        SavGolWindow_E = self.Settings["SavGol_Width"].get()

        # Schleife: Task definieren
        ntasks = 0
        for i in range(len(self.Data)):
            if not self.Data[i].active: continue
            # Forward
            if Eend_Forward - Estart_Forward != 0:
                if Eend_Forward - Estart_Forward < 0:
                    tmp = Estart_Forward
                    Estart_Forward = Eend_Forward
                    Eend_Forward = tmp

                Erev = self.Data[i].working_data["E_rev"]
                t = self.Data[i].working_data["t"][:Erev]
                E = self.Data[i].working_data["E"][:Erev]
                I = self.Data[i].working_data["I"][:Erev]
                vRate = self.Data[i].vRate

                start = helpers.GetNearest(E, Estart_Forward)
                end = helpers.GetNearest(E, Eend_Forward)
                peak_ind = np.argwhere(forward == True)
                if len(peak_ind) != 0:
                    peak_ind = peak_ind.T[0]

                    fit_task = [
                        "curve_fit", # Task-Identifier
                        [
                            i,
                            True, # Forward
                            t[start:end], E[start:end], I[start:end], vRate, # Kurvendaten
                            PeakShape, E1[peak_ind], E2[peak_ind], sigma[peak_ind], tau[peak_ind], # Peakdaten
                            SavGolWindow_E, wd0, wd1, wd2, generations# Fit-Parameter
                        ],
                    ]
                    self.client.queue_tasks.put(fit_task)
                    ntasks += 1

            # Reverse
            if Eend_Reverse - Estart_Reverse != 0:
                if Eend_Reverse - Estart_Reverse > 0:
                    tmp = Estart_Reverse
                    Estart_Reverse = Eend_Reverse
                    Eend_Reverse = tmp

                Erev = self.Data[i].working_data["E_rev"]
                t = self.Data[i].working_data["t"][Erev:]
                E = self.Data[i].working_data["E"][Erev:]
                I = self.Data[i].working_data["I"][Erev:]
                vRate = self.Data[i].vRate

                start = helpers.GetNearest(E, Estart_Reverse)
                end = helpers.GetNearest(E, Eend_Reverse)
                peak_ind = np.argwhere(forward == False)
                if len(peak_ind) != 0:
                    peak_ind = peak_ind.T[0]

                    fit_task = [
                        "curve_fit",  # Task-Identifier
                        [
                            i,
                            False, # Reverse
                            t[start:end], E[start:end], I[start:end], vRate,  # Kurvendaten
                            PeakShape, E1[peak_ind], E2[peak_ind], sigma[peak_ind], tau[peak_ind],  # Peakdaten
                            SavGolWindow_E, wd0, wd1, wd2, generations  # Fit-Parameter
                        ],
                    ]
                    self.client.queue_tasks.put(fit_task)
                    ntasks += 1

        self.client.opened_tasks = ntasks
        self.client.closed_tasks = 0

        # Ohne Aufträge gäbe es unten eine Division durch 0 und die Oberfläche
        # bliebe in der "Fit läuft"-Stellung hängen.
        if ntasks == 0:
            self.client.opened_tasks = 0
            self.GUI_Elements["mf3_ProgressBar"]["value"] = 0
            self.GUI_Elements["mf3_Label_ProgressBar"].set("Kein Fitprozess aktiv...")
            self.GUI_Elements["mf3_Button_StartFit"]["state"] = "normal"
            self.GUI_Elements["mf3_Button_StopFit"]["state"] = "disabled"
            messagebox.showwarning(
                "Kein Fit möglich",
                "Es gibt keinen Fit-Auftrag: entweder ist keine Kurve aktiv oder\n"
                "es fehlen Peak-Kandidaten bzw. ein Fit-Bereich.")
            return

        # WorkerProzesse (neu) starten
        self.client.spawn_workers(self.Settings["Fit_Workers"].get())

        self.GUI_Elements["mf3_ProgressBar"]["value"] = 100*self.client.closed_tasks/self.client.opened_tasks
        self.GUI_Elements["mf3_Label_ProgressBar"].set("Fit läuft: {0}/{1}".format(self.client.closed_tasks, self.client.opened_tasks))

    def StopFit(self):
        self.client.abort_all_tasks()

        self.client.opened_tasks = 0
        self.client.closed_tasks = 0
        for i in range(len(self.Data)):
            self.Data[i].peak_results = None

        self.GUI_Elements["mf3_ProgressBar"]["value"] = 0
        self.GUI_Elements["mf3_Label_ProgressBar"].set("Kein Fitprozess aktiv...")

        self.GUI_Elements["mf3_Button_StartFit"]["state"] = "normal"
        self.GUI_Elements["mf3_Button_StopFit"]["state"] = "disabled"

    def ProcessFitResult(self, result):
        self.client.closed_tasks += 1

        E_Ref = 0.0
        if self.Settings["Correction_Active"].get() == 1:
            if self.Settings["Correction_Eref"].get() != "":
                E_Ref = float(self.Settings["Correction_Eref"].get())

        if self.Settings["Normalize_E_ZeroCrossings"].get() == 1:
            E_Manipulation = 1
        elif self.Settings["Normalize_E_MinMax"].get() == 1:
            E_Manipulation = 2
        else:
            E_Manipulation = 0

        for peak in result:
            if self.Data[peak[0]].peak_results is None:
                self.Data[peak[0]].peak_results = {"forward": [peak[1]], "Ep": [peak[3]], "σ": [peak[4]], "τ": [peak[5]], "Ip": [peak[6]], "Ip_F": [peak[7]], "Ip_C": [peak[8]], "Qp": [peak[9]], "E_Manipulation": E_Manipulation, "E_Ref": E_Ref}
            else:
                self.Data[peak[0]].peak_results["forward"].append(peak[1])
                self.Data[peak[0]].peak_results["Ep"].append(peak[3])
                self.Data[peak[0]].peak_results["σ"].append(peak[4])
                self.Data[peak[0]].peak_results["τ"].append(peak[5])
                self.Data[peak[0]].peak_results["Ip"].append(peak[6])
                self.Data[peak[0]].peak_results["Ip_F"].append(peak[7])
                self.Data[peak[0]].peak_results["Ip_C"].append(peak[8])
                self.Data[peak[0]].peak_results["Qp"].append(peak[9])

            if self.Data[peak[0]].calculated_data is None:
                self.Data[peak[0]].calculated_data = {"t": [peak[10]], "E": [peak[11]], "I": [peak[12]]}
            else:
                self.Data[peak[0]].calculated_data["t"].append(peak[10])
                self.Data[peak[0]].calculated_data["E"].append(peak[11])
                self.Data[peak[0]].calculated_data["I"].append(peak[12])

        self.UpdateResultTable()
        self.Redraw()

        if self.client.closed_tasks >= self.client.opened_tasks: # Fertig?
            self.GUI_Elements["mf3_ProgressBar"]["value"] = 100
            self.GUI_Elements["mf3_Label_ProgressBar"].set("Kein Fitprozess aktiv...")
            self.client.abort_all_tasks() # nur für den Fall

            self.client.opened_tasks = 0
            self.client.closed_tasks = 0

            self.GUI_Elements["mf3_Button_StartFit"]["state"] = "normal"
            self.GUI_Elements["mf3_Button_StopFit"]["state"] = "disabled"
        else:
            self.GUI_Elements["mf3_ProgressBar"]["value"] = 100*self.client.closed_tasks/self.client.opened_tasks
            self.GUI_Elements["mf3_Label_ProgressBar"].set("Fit läuft: {0}/{1}".format(self.client.closed_tasks, self.client.opened_tasks))

    # -----------------------------------------------------------------------------------------------
    # Menübar-Funktionen
    # -----------------------------------------------------------------------------------------------
    def Menu_New(self):
        self.SavePath = None
        self.Data = []
        self.Settings["CurveID_Iterator"].set(0)
        self.CurveTable.SetValues(self.CurveTableDefault)
        self.PeakTable.SetValues(self.PeakTableDefault)
        self.ResultTable.SetValues(self.ResultTableDefault)
        self.Graph.Clear()
        tk.Tk.wm_title(self.master, "CV Analyzer [Version {0}, ©Schottenbauer 2026] - neues Projekt".format(__version__))

    def Menu_NewAndReset(self):
        self.Menu_New()
        self.Menu_ResetSettings()

    def Menu_ImportPalmSensCSV(self):
        Files = FileDialog.askopenfilenames(filetypes=[("CSV-Datei", "*.csv")])

        if len(Files) == 0: return
        for File in Files:
            Data = IO_Functions.Import_PalmSensCSV(File)
            if Data is None: continue
            for i in range(len(Data["Channels"])):
                c = Curve()
                c.id = self.Settings["CurveID_Iterator"].get()
                self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)

                c.name = File.split("/")[-1]
                c.electrode = ""
                c.channel = Data["Channels"][i]
                c.cycle = Data["Cycles"][i]
                c.vRate = Data["vRate"]
                c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                self.Data.append(c)
        self.Recalculate()
        self.SetCurveTable()

    def Menu_ImportPalmSensExcel(self):
        Files = FileDialog.askopenfilenames(filetypes=[("Excel-Datei", "*.xlsx")])

        if len(Files) == 0: return
        for File in Files:
            Data = IO_Functions.Import_PalmSensExcel(File)
            if Data is None: continue
            for i in range(len(Data["Channels"])):
                c = Curve()
                c.id = self.Settings["CurveID_Iterator"].get()
                self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                c.name = File.split("/")[-1]
                c.electrode = ""
                c.channel = Data["Channels"][i]
                c.cycle = Data["Cycles"][i]
                c.vRate = Data["vRate"]
                c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                self.Data.append(c)
        self.Recalculate()
        self.SetCurveTable()

    def Menu_ImportRaspbiZIP(self):
        File = FileDialog.askopenfilename(filetypes=[("ZIP-Datei", "*.zip")])
        if File == "": return
        vRate = tk.simpledialog.askstring("Spannungsvorschub", "Welcher Spannungsvorschub soll importiert werden?\n(all = alle, mehrere mit Komma trennen)")
        if vRate is None: return   # Dialog abgebrochen

        if "all" in vRate:
            ZF = zipfile.ZipFile(File, mode="r")
            for v in ZF.filelist:
                try:
                    v = helpers.getBetween(v.filename, "CV-", "Vps")
                    if v is None:
                        continue
                    else:
                        v = float(v)
                    Data = IO_Functions.Import_RaspiZIP(File, v)
                    if Data is None: continue
                    for i in range(len(Data["Channels"])):
                        c = Curve()
                        c.id = self.Settings["CurveID_Iterator"].get()
                        self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                        c.name = File.split("/")[-1]
                        c.electrode = ""
                        c.channel = Data["Channels"][i]
                        c.cycle = Data["Cycles"][i]
                        c.vRate = Data["vRate"]
                        c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                        self.Data.append(c)
                except ValueError:
                    tk.messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
                    return
        elif "," in vRate:
            for v in vRate.split(","):
                try:
                    v = float(v)
                    Data = IO_Functions.Import_RaspiZIP(File, v)
                    if Data is None: continue
                    for i in range(len(Data["Channels"])):
                        c = Curve()
                        c.id = self.Settings["CurveID_Iterator"].get()
                        self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                        c.name = File.split("/")[-1]
                        c.electrode = ""
                        c.channel = Data["Channels"][i]
                        c.cycle = Data["Cycles"][i]
                        c.vRate = Data["vRate"]
                        c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                        self.Data.append(c)
                except ValueError:
                    tk.messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
                    return
        else:
            try:
                vRate = float(vRate)
                Data = IO_Functions.Import_RaspiZIP(File, vRate)
                if Data is None: return
                for i in range(len(Data["Channels"])):
                    c = Curve()
                    c.id = self.Settings["CurveID_Iterator"].get()
                    self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                    c.name = File.split("/")[-1]
                    c.electrode = ""
                    c.channel = Data["Channels"][i]
                    c.cycle = Data["Cycles"][i]
                    c.vRate = Data["vRate"]
                    c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                    self.Data.append(c)
            except ValueError:
                tk.messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
                return
        self.Recalculate()
        self.SetCurveTable()

    def Menu_ImportNPZ(self):
        Files = FileDialog.askopenfilenames(filetypes=[("NPZ-Datei", "*.npz")])

        if len(Files) == 0: return
        for File in Files:
            Data = IO_Functions.Import_npzFile(File)
            if Data is None: continue
            for i in range(len(Data["Channels"])):
                c = Curve()
                c.id = self.Settings["CurveID_Iterator"].get()
                self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                c.name = File.split("/")[-1]
                c.electrode = ""
                c.channel = Data["Channels"][i]
                c.cycle = Data["Cycles"][i]
                c.vRate = Data["vRate"]
                c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                self.Data.append(c)
        self.Recalculate()
        self.SetCurveTable()

    def Menu_ImportSRS(self):
        Files = FileDialog.askopenfilenames(filetypes=[("Textdatei", "*.txt")])

        if len(Files) == 0: return
        for File in Files:
            Data = IO_Functions.Import_SRS(File)
            if Data is None: continue
            for i in range(len(Data["Channels"])):
                c = Curve()
                c.id = self.Settings["CurveID_Iterator"].get()
                self.Settings["CurveID_Iterator"].set(self.Settings["CurveID_Iterator"].get() + 1)
                c.name = File.split("/")[-1]
                c.electrode = ""
                c.channel = Data["Channels"][i]
                c.cycle = Data["Cycles"][i]
                c.vRate = Data["vRate"]
                c.raw_data = {"t": Data["tn"][i], "E": Data["En"][i], "I": Data["In"][i], "E_rev": Data["En_rev"][i], "dt": Data["dt"], "dE": Data["dE"]}
                self.Data.append(c)
        self.Recalculate()
        self.SetCurveTable()

    def Menu_Save(self):
        if self.SavePath is None or self.SavePath == "":
            self.Menu_SaveAs()
            # Abbrechen im Dialog: nichts speichern und nicht mit leerem Pfad
            # in joblib.dump laufen.
            if self.SavePath is None or self.SavePath == "":
                return

        Settings = {}
        for name in self.Settings:
            Settings.update({name: self.Settings[name].get()})
        peak_candidates = self.GetPeakCandidates()
        self.UpdateCurveData()

        joblib.dump({"Data": self.Data, "Settings": Settings, "PeakCandidates": peak_candidates}, self.SavePath, compress=9)

    def Menu_SaveAs(self):
        self.SavePath = FileDialog.asksavefilename(filetypes=[("CV-Projektdatei", "*.cvproj")])
        if self.SavePath == "": return
        tk.Tk.wm_title(self.master, "CV Analyzer [Version {0}, ©Schottenbauer 2025] - {1}".format(__version__, self.SavePath.split("/")[-1]))

        if self.SavePath.split(".")[-1] != "cvproj":
            self.SavePath = self.SavePath + ".cvproj"

        self.Menu_Save()

    def Menu_Open(self):
        Path = FileDialog.askopenfilename(filetypes=[("CV-Projektdatei", "*.cvproj")])
        if Path == "": return
        self.OpenFile(Path)

    def OpenFile(self, Path):
        """Öffnet eine Projektdatei. Getrennt von der Dateiauswahl, damit der
        Ablauf ohne Dialog prüfbar ist."""
        try:
            Proj = projektdatei.laden(Path)   # verträgt auch Dateien aus der Zeit vor dem Paket
        except projektdatei.UnsicheresObjekt as fehler:
            messagebox.showerror(
                "Projektdatei abgewiesen",
                "Die Datei wurde nicht geöffnet, weil sie etwas anderes enthält als "
                "CV-Analyzer-Daten:\n\n{0}".format(fehler))
            return
        except Exception as fehler:
            messagebox.showerror(
                "Projektdatei nicht lesbar",
                "Die Datei konnte nicht gelesen werden:\n\n{0}".format(fehler))
            return

        # Sehr alte Dateien können ein anderes Datenmodell enthalten. Lieber eine
        # verständliche Meldung als ein Traceback mitten im Aufbau der Tabellen.
        if not isinstance(Proj.get("Data"), list) or \
                not all(hasattr(c, "raw_data") for c in Proj["Data"]):
            messagebox.showwarning(
                "Projektdatei nicht lesbar",
                "Diese Projektdatei stammt aus einer älteren Version des CV-Analyzers\n"
                "und benutzt ein anderes Datenformat.\n\n"
                "Die Messdaten lassen sich weiterhin über den Import neu einlesen.")
            return

        self.SavePath = Path
        tk.Tk.wm_title(self.master, "CV Analyzer [Version {0}, ©Schottenbauer 2025] - {1}".format(__version__, self.SavePath.split("/")[-1]))

        self.Data = Proj["Data"]
        for name in Proj["Settings"]:
            # Ältere Projektdateien können Einstellungen enthalten, die es
            # inzwischen nicht mehr gibt — die werden übersprungen.
            if name in self.Settings:
                self.Settings[name].set(Proj["Settings"][name])
        self.SetCurveTable()
        self.PeakTable.SetValues(Proj["PeakCandidates"])
        self.UpdateResultTable(self.ResultTableDefault)

        self.Redraw()
        self.ShowFrame()

    def Menu_ExportSettings(self):
        Path = FileDialog.asksavefilename(filetypes=[("CV-Einstellungen", "*.cvsettings")])
        if Path == "": return
        if Path.split(".")[-1] != "cvsettings":
            Path = Path + ".cvsettings"

        Settings = {}
        for name in self.Settings:
            Settings.update({name: self.Settings[name].get()})
        peak_candidates = self.GetPeakCandidates()
        joblib.dump({"Settings": Settings, "PeakCandidates": peak_candidates}, Path, compress=9)

    def Menu_ImportSettings(self):
        Path = FileDialog.askopenfilename(filetypes=[("CV-Einstellungen", "*.cvsettings"), ("CV-Projektdatei", "*.cvproj")])
        if Path == "": return

        try:
            Import = projektdatei.laden(Path)   # prüft die Datei, statt sie blind zu entpickeln
        except projektdatei.UnsicheresObjekt as fehler:
            messagebox.showerror("Datei abgewiesen", str(fehler))
            return
        except Exception as fehler:
            messagebox.showerror("Einstellungen nicht lesbar",
                                 "Die Datei konnte nicht gelesen werden:\n\n{0}".format(fehler))
            return

        for name in Import["Settings"]:
            # Ältere Einstellungsdateien können Schlüssel enthalten, die es
            # inzwischen nicht mehr gibt — die werden übersprungen.
            if name in self.Settings:
                self.Settings[name].set(Import["Settings"][name])
        self.PeakTable.SetValues(Import["PeakCandidates"])

        self.Recalculate()
        self.ShowFrame()

    def Menu_ResetSettings(self):
        for name in self.SettingsDump:
            self.Settings[name].set(self.SettingsDump[name])
        self.PeakTable.SetValues(self.PeakTableDefault)
        self.ResultTable.SetValues(self.ResultTableDefault)

        self.Recalculate()
        self.ShowFrame()

    def Menu_ReorderSRS(self):
        Path = FileDialog.askdirectory()
        if Path == "": return
        if Path[-1] != "/": Path += "/"

        for Folder in os.listdir(Path):
            if os.path.isdir(Path+Folder):
                shutil.move(Path+Folder+"/EC.txt", Path+Folder+".txt")
                shutil.rmtree(Path+Folder)

    # -----------------------------------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------------------------------
    def Menu_ExportPeaks_to_Excel(self):
        self.UpdateCurveData()

        df = {
            "CurveID": [],
            "Name": [],
            "Elektrode": [],
            "Channel": [],
            "Cycle": [],
            "v / V/s": [],
            "Merkmal 1": [],
            "Merkmal 2": [],
            "Merkmal 3": [],
            "Merkmal 4": [],
            "Merkmal 5": [],
            "forward": [],
            "Ep / V": [],
            "σ / V": [],
            "τ / s": [],
            "Ip / A": [],
            "Ip_F / A": [],
            "Ip_C / A": [],
            "Qp / C": [],
            "E0L / V": [],
            "E0R / V": [],
        }
        for i in range(len(self.Data)):
            if self.Data[i].peak_results is not None:
                for n in range(len(self.Data[i].peak_results["Ep"])):
                    df["CurveID"].append(self.Data[i].id)
                    df["Name"].append(self.Data[i].name)
                    df["Elektrode"].append(self.Data[i].electrode)
                    df["Channel"].append(self.Data[i].channel)
                    df["Cycle"].append(self.Data[i].cycle)
                    df["v / V/s"].append(self.Data[i].vRate)
                    df["Merkmal 1"].append(self.Data[i].feature_1)
                    df["Merkmal 2"].append(self.Data[i].feature_2)
                    df["Merkmal 3"].append(self.Data[i].feature_3)
                    df["Merkmal 4"].append(self.Data[i].feature_4)
                    df["Merkmal 5"].append(self.Data[i].feature_5)
                    df["forward"].append(self.Data[i].peak_results["forward"][n])
                    df["Ep / V"].append(self.Data[i].peak_results["Ep"][n])
                    df["σ / V"].append(self.Data[i].peak_results["σ"][n])
                    df["τ / s"].append(self.Data[i].peak_results["τ"][n])
                    df["Ip / A"].append(self.Data[i].peak_results["Ip"][n])
                    df["Ip_F / A"].append(self.Data[i].peak_results["Ip_F"][n])
                    df["Ip_C / A"].append(self.Data[i].peak_results["Ip_C"][n])
                    df["Qp / C"].append(self.Data[i].peak_results["Qp"][n])

                    zeros = helpers.FindZeroCrossings(self.Data[i].working_data["I"][:self.Data[i].working_data["E_rev"]])
                    if len(zeros) != 0:
                        df["E0L / V"].append(self.Data[i].working_data["E"][zeros[0]])
                    else:
                        df["E0L / V"].append("")
                    zeros = helpers.FindZeroCrossings(self.Data[i].working_data["I"][self.Data[i].working_data["E_rev"]:])
                    if len(zeros) != 0:
                        df["E0R / V"].append(self.Data[i].working_data["E"][self.Data[i].working_data["E_rev"]+zeros[0]])
                    else:
                        df["E0R / V"].append("")
            else:
                df["CurveID"].append(self.Data[i].id)
                df["Name"].append(self.Data[i].name)
                df["Elektrode"].append(self.Data[i].electrode)
                df["Channel"].append(self.Data[i].channel)
                df["Cycle"].append(self.Data[i].cycle)
                df["v / V/s"].append(self.Data[i].vRate)
                df["Merkmal 1"].append(self.Data[i].feature_1)
                df["Merkmal 2"].append(self.Data[i].feature_2)
                df["Merkmal 3"].append(self.Data[i].feature_3)
                df["Merkmal 4"].append(self.Data[i].feature_4)
                df["Merkmal 5"].append(self.Data[i].feature_5)
                df["forward"].append("")
                df["Ep / V"].append("")
                df["σ / V"].append("")
                df["τ / s"].append("")
                df["Ip / A"].append("")
                df["Ip_F / A"].append("")
                df["Ip_C / A"].append("")
                df["Qp / C"].append("")

                if self.Data[i].working_data is not None:
                    df["E0L / V"].append(self.Data[i].working_data["E"][helpers.FindZeroCrossings(self.Data[i].working_data["I"][:self.Data[i].working_data["E_rev"]])[0]])
                    df["E0R / V"].append(self.Data[i].working_data["E"][self.Data[i].working_data["E_rev"]+helpers.FindZeroCrossings(self.Data[i].working_data["I"][self.Data[i].working_data["E_rev"]:])[0]])
                else:
                    df["E0L / V"].append("")
                    df["E0R / V"].append("")

        XLSXFile = FileDialog.asksavefilename(filetypes=[("Excel-Datei", "*.xlsx")])
        if XLSXFile == "": return
        if not XLSXFile.endswith(".xlsx"): XLSXFile += ".xlsx"
        df = pd.DataFrame(df)
        SheetName = "Peak-Fit-Results"

        excel_blatt_schreiben(XLSXFile, df, SheetName)
        excel_bild_einfuegen(XLSXFile, SheetName, self.Graph.fig, "W1")

    def Menu_Export_CumsumQ_to_Excel(self):
        data = self.Calc_CumsumQ()

        df = {
            "CurveID": [],
            "Name": [],
            "Elektrode": [],
            "Channel": [],
            "Cycle": [],
            "v / V/s": [],
            "Merkmal 1": [],
            "Merkmal 2": [],
            "Merkmal 3": [],
            "Merkmal 4": [],
            "Merkmal 5": [],
            "Qf / C": [],
            "Qr / C": [],
        }
        for i in range(len(data["CurveID"])):
            nDataset = None
            for n in range(len(self.Data)):
                if self.Data[n].id == data["CurveID"][i]:
                    nDataset = n
            df["CurveID"].append(self.Data[nDataset].id)
            df["Name"].append(self.Data[nDataset].name)
            df["Elektrode"].append(self.Data[nDataset].electrode)
            df["Channel"].append(self.Data[nDataset].channel)
            df["Cycle"].append(self.Data[nDataset].cycle)
            df["v / V/s"].append(self.Data[nDataset].vRate)
            df["Merkmal 1"].append(self.Data[nDataset].feature_1)
            df["Merkmal 2"].append(self.Data[nDataset].feature_2)
            df["Merkmal 3"].append(self.Data[nDataset].feature_3)
            df["Merkmal 4"].append(self.Data[nDataset].feature_4)
            df["Merkmal 5"].append(self.Data[nDataset].feature_5)
            df["Qf / C"].append(data["y1"][i])
            df["Qr / C"].append(data["y2"][i])

        XLSXFile = FileDialog.asksavefilename(filetypes=[("Excel-Datei", "*.xlsx")])
        if XLSXFile == "": return
        if not XLSXFile.endswith(".xlsx"): XLSXFile += ".xlsx"
        df = pd.DataFrame(df)
        SheetName = "Cumsum-Q"

        excel_blatt_schreiben(XLSXFile, df, SheetName)

        # Plot
        fig = plt.figure("Cumsum Q Plot", tight_layout=True)
        ax = fig.add_subplot(111)
        label = tk.simpledialog.askstring("x-Label", "Welche Achsenbeschriftung soll die x-Achse haben?")
        if label: ax.set_xlabel(label)
        ax.set_ylabel(r"$Q_{\rm P}~/~{\rm mC}$")
        ax.plot(data["x"], 1e3*data["y1"], ".", color=helpers.scientific_colors["Green"])
        ax.plot(data["x"], 1e3*data["y2"], ".", color=helpers.scientific_colors["MedBlue"])

        excel_bild_einfuegen(XLSXFile, SheetName, fig, "O1")
        fig.clf()

    def Menu_Export_IFI_to_Excel(self):
        data = self.Calc_IFI()

        df = {
            "CurveID": [],
            "Name": [],
            "Elektrode": [],
            "Channel": [],
            "Cycle": [],
            "v / V/s": [],
            "Merkmal 1": [],
            "Merkmal 2": [],
            "Merkmal 3": [],
            "Merkmal 4": [],
            "Merkmal 5": [],
            "If/I-f": [],
            "If/I-r": [],
        }
        for i in range(len(data["CurveID"])):
            nDataset = None
            for n in range(len(self.Data)):
                if self.Data[n].id == data["CurveID"][i]:
                    nDataset = n
            df["CurveID"].append(self.Data[nDataset].id)
            df["Name"].append(self.Data[nDataset].name)
            df["Elektrode"].append(self.Data[nDataset].electrode)
            df["Channel"].append(self.Data[nDataset].channel)
            df["Cycle"].append(self.Data[nDataset].cycle)
            df["v / V/s"].append(self.Data[nDataset].vRate)
            df["Merkmal 1"].append(self.Data[nDataset].feature_1)
            df["Merkmal 2"].append(self.Data[nDataset].feature_2)
            df["Merkmal 3"].append(self.Data[nDataset].feature_3)
            df["Merkmal 4"].append(self.Data[nDataset].feature_4)
            df["Merkmal 5"].append(self.Data[nDataset].feature_5)
            df["If/I-f"].append(data["y1"][i])
            df["If/I-r"].append(data["y2"][i])

        XLSXFile = FileDialog.asksavefilename(filetypes=[("Excel-Datei", "*.xlsx")])
        if XLSXFile == "": return
        if not XLSXFile.endswith(".xlsx"): XLSXFile += ".xlsx"
        df = pd.DataFrame(df)
        SheetName = "IfI"

        excel_blatt_schreiben(XLSXFile, df, SheetName)

        # Plot
        fig = plt.figure("IF_I-Verhältnis", tight_layout=True)
        ax = fig.add_subplot(111)
        label = tk.simpledialog.askstring("x-Label", "Welche Achsenbeschriftung soll die x-Achse haben?")
        if label: ax.set_xlabel(label)
        # Diagramm und Tabelle zeigen dasselbe dimensionslose Verhältnis. Der
        # frühere Faktor 1000 stammte aus der Stromachse (mA) und hat hier nichts
        # zu suchen.
        ax.set_ylabel(r"$\frac{I_{\rm F}}{I}~/~{\rm -}$")
        ax.plot(data["x"], data["y1"], ".", color=helpers.scientific_colors["Green"])
        ax.plot(data["x"], data["y2"], ".", color=helpers.scientific_colors["MedBlue"])

        excel_bild_einfuegen(XLSXFile, SheetName, fig, "O1")
        fig.clf()

    def Menu_Export_Peaks_for_Calibration_to_Excel(self):
        self.UpdateCurveData()

        Zeilen = kalibrier_zeilen(self.Data)

        XLSXFile = FileDialog.asksavefilename(filetypes=[("Excel-Datei", "*.xlsx")])
        if XLSXFile == "": return
        if not XLSXFile.endswith(".xlsx"): XLSXFile += ".xlsx"
        df = pd.DataFrame(Zeilen)   # fehlende Peaks einer Kurve bleiben leer
        SheetName = "Calibration Peaks"

        excel_blatt_schreiben(XLSXFile, df, SheetName)

    def Menu_CumsumQ_Plot(self):
        data = self.Calc_CumsumQ()

        fig = plt.figure("Cumsum Q Plot", tight_layout=True)
        ax = fig.add_subplot(111)

        label = tk.simpledialog.askstring("x-Label", "Welche Achsenbeschriftung soll die x-Achse haben?")
        if label: ax.set_xlabel(label)
        ax.set_ylabel(r"$Q_{\rm P}~/~{\rm mC}$")

        ax.plot(data["x"], 1e3*data["y1"], ".", color=helpers.scientific_colors["Green"])
        ax.plot(data["x"], 1e3*data["y2"], ".", color=helpers.scientific_colors["MedBlue"])

        filename = FileDialog.asksavefilename(filetypes=[("PNG-Datei", "*.png")])
        if filename == "":
            fig.clf()
            return
        if not filename.endswith(".png"): filename += ".png"
        fig.savefig(filename, format="png")
        fig.clf()

    def Menu_IFI_Plot(self):
        self.UpdateCurveData()

        data = self.Calc_IFI()

        fig = plt.figure("IF_I-Verhältnis", tight_layout=True)
        ax = fig.add_subplot(111)

        label = tk.simpledialog.askstring("x-Label", "Welche Achsenbeschriftung soll die x-Achse haben?")
        if label: ax.set_xlabel(label)
        ax.set_ylabel(r"$\frac{I_{\rm F}}{I}~/~{\rm -}$")

        ax.plot(data["x"], data["y1"], ".", color=helpers.scientific_colors["Green"])
        ax.plot(data["x"], data["y2"], ".", color=helpers.scientific_colors["MedBlue"])

        filename = FileDialog.asksavefilename(filetypes=[("PNG-Datei", "*.png")])
        if filename == "":
            fig.clf()
            return
        if not filename.endswith(".png"): filename += ".png"
        fig.savefig(filename, format="png")
        fig.clf()

    # -----------------------------------------------------------------------------------------------
    # Shortcuts
    # -----------------------------------------------------------------------------------------------
    def Key_Save(self, *args):
        self.Menu_Save()

    def Key_Open(self, *args):
        self.Menu_Open()

    # -----------------------------------------------------------------------------------------------
    # GUI-Funtionen
    # -----------------------------------------------------------------------------------------------
    def ShowFrame(self, Frame=None):
        if type(Frame) is int:
            self.method_frames[Frame].tkraise()
            self.Settings["ActiveMethodFrame"].set(self.MethodFrameList[Frame])
        else:
            for i in range(len(self.MethodFrameList)):
                if self.MethodFrameList[i] == self.Settings["ActiveMethodFrame"].get():
                    self.method_frames[i].tkraise()

    def HorizontalLine(self, pFrame):
        return tk.Frame(pFrame, padx=5, pady=5, height=1, bg="gray").pack(fill="x")

    def ChangeState(self, *Elements):
        for E in Elements:
            if E["state"] == "disabled":
                E["state"] = "normal"
            else:
                E["state"] = "disabled"



class ThreadedClient(object):
    def __init__(self, master):
        self.master = master

        # Jedes Result ist eine Liste der Form: result: [Typ (z.B. Kurvenfit), args (Parameter und Werte als Liste/Array)]
        # Jeder Task ist eine Liste der Form: task: [Typ (z.B. Kurvenfit), Funktion (Python Funktion die ausgeführt werden soll), args (Parameter und Werte als Liste/Array)]
        self.queue_results = multiprocessing.Queue()
        self.queue_tasks = multiprocessing.Queue()

        self.max_workers = 2
        self.active_workers = 0
        self.opened_tasks = 0
        self.closed_tasks = 0

        self.gui = GUI(self.master, self)

        # Set up the thread to do asynchronous I/O
        # More threads can also be created and used, if necessary
        self.running = True
        self.workers = []

        # Start the periodic call in the GUI to check the queue
        self.periodic_call()

    def periodic_call(self):
        """ Check every 200 ms if there is something new in the queue. """
        self.master.after(200, self.periodic_call)

        worker_running = False
        i = len(self.workers)-1
        while i > 0:
            if not self.workers[i].is_alive():
                self.workers[i].close()
                del self.workers[i]
            else:
                worker_running = True
            i -= 1
        if not worker_running: self.workers = []

        while self.queue_results.qsize():
            try:
                result = self.queue_results.get_nowait()
                if type(result) is list:
                    if result[0] == "curve_fit_result":
                        self.gui.ProcessFitResult(result[1])
            except queue.Empty:
                pass

        if not self.running:
            # This is the brutal stop of the system.  You may want to do
            # some cleanup before actually shutting it down.
            import sys
            sys.exit(1)

    def spawn_workers(self, n):
        if len(self.workers) > 0: self.abort_all_tasks()

        for i in range(n):
            worker = multiprocessing.Process(target=curve_fit_worker, args=(self.queue_tasks, self.queue_results))
            self.workers.append(worker)
        for i in range(len(self.workers)):
            self.workers[i].start()

    def abort_all_tasks(self):
        # Prozesse schließen
        for i in range(len(self.workers)):
            self.workers[i].terminate()
        time.sleep(0.1)
        for i in range(len(self.workers)):
            self.workers[i].close()
        self.workers = []

        # Queue leeren
        empty = False
        while not empty:
            try:
                self.queue_tasks.get_nowait()
            except queue.Empty:
                empty = True
        # Queue leeren
        empty = False
        while not empty:
            try:
                self.queue_results.get_nowait()
            except queue.Empty:
                empty = True

        # Counter zurücksetzen
        self.opened_tasks = 0
        self.closed_tasks = 0

    def end_application(self):
        self.abort_all_tasks()
        self.running = False

def curve_fit_worker(TaskQueue, ResultQueue):
    while True:
        try:
            msg = TaskQueue.get_nowait()
        except queue.Empty:
            return
        if msg[0] == "curve_fit":
            parameters = msg[1]

            # Variablen übersichtlich definieren
            CurveID = parameters[0]
            forward = parameters[1]
            t = parameters[2]
            E = parameters[3]
            I = parameters[4]
            vRate = parameters[5]
            PeakShape = parameters[6]
            E1 = parameters[7]
            E2 = parameters[8]
            sigma = parameters[9]
            tau = parameters[10]
            SavGolWindow = parameters[11]
            wd0 = parameters[12]
            wd1 = parameters[13]
            wd2 = parameters[14]
            generations = parameters[15]

            # SavGolWindow in Punkten berechnen
            dt = np.mean(np.gradient(t))
            dE = np.mean(np.gradient(E))
            SavGolWindow = int(SavGolWindow/abs(dE))
            if SavGolWindow % 2 == 0.0: SavGolWindow += 1

            # Peak-Shapes
            PeakShapes = []
            for i in range(len(E1)):
                PeakShapes.append(PeakShape)

            # Fit-Objekt
            if forward:
                sign = 1
            else:
                sign = -1

            # Gewichtungen
            if wd0 != 0: wd0 = np.ones_like(I)/np.std(sign*I, ddof=1)
            # if wd0 != 0: wd0 = 1/helpers.Moving_Std(sign*I, SavGolWindow)
            else: wd0 = np.zeros_like(I)
            if wd1 != 0: wd1 = np.ones_like(I)/np.std(signal.savgol_filter(sign*I, window_length=SavGolWindow, polyorder=3, deriv=1), ddof=1)
            # if wd1 != 0: wd1 = 1/helpers.Moving_Std(signal.savgol_filter(sign*I, window_length=SavGolWindow, polyorder=3, deriv=1), SavGolWindow)
            else: wd1 = np.zeros_like(I)
            if wd2 != 0: wd2 = np.ones_like(I)/np.std(signal.savgol_filter(sign*I, window_length=SavGolWindow, polyorder=3, deriv=2), ddof=1)
            # if wd2 != 0: wd2 = 1/helpers.Moving_Std(signal.savgol_filter(sign*I, window_length=SavGolWindow, polyorder=3, deriv=2), SavGolWindow)
            else: wd2 = np.zeros_like(I)

            FitObj = helpers.FitOptimizer(sign*I, SavGolWindow, PeakShapes, d0w=wd0, d1w=wd1, d2w=wd2)

            # Bounds anpassen
            it = 0
            for i in range(len(PeakShapes)):
                p1 = float(helpers.GetNearest(E, E1[i]))
                p2 = float(helpers.GetNearest(E, E2[i]))
                if p1 > p2:
                    tmp = p1
                    p1 = p2
                    p2 = tmp

                FitObj.bounds_min[it] = p1
                FitObj.bounds_max[it] = p2
                it += 1

                FitObj.bounds_min[it] = 1.0
                FitObj.bounds_max[it] = sigma[i]/abs(dE)
                it += 1

                if PeakShapes[i] == "exp_gaussian":
                    FitObj.bounds_min[it] = 1e-10
                    FitObj.bounds_max[it] = tau[i]/abs(dE)
                    it += 1

            # Pygmo Algorithmus
            # StartFit stellt nur dann Tasks ein, wenn pygmo importierbar war.
            assert pg is not None, "pygmo fehlt — StartFit hätte keine Tasks einstellen dürfen"
            problem = pg.problem(FitObj)
            algorithm = pg.algorithm(pg.pso(gen=generations))
            individuals = 20 * problem.get_nx()
            population = pg.population(problem, size=individuals)

            # Kurvenfit
            population = algorithm.evolve(population)
            y_calc, params, areas = FitObj.CalcResults(population.champion_x)

            # Ergebnisse auswerten
            results = ["curve_fit_result", []]
            it = 0
            for i in range(len(PeakShapes)):
                if PeakShapes[i] == "gaussian":
                    center = params[it]
                    pmax = int(round(center, 0))
                    it += 1

                    sigma = params[it]
                    it += 1

                    results[1].append([
                        CurveID, forward, vRate,
                        center*dE+E[0], # Ep
                        sigma*abs(dE), # sigma
                        0.0, # tau
                        I[pmax], # Ip
                        sign * areas[i] / (sigma * np.sqrt(2 * np.pi)), # Ip_F
                        I[pmax] - sign * areas[i] / (sigma * np.sqrt(2 * np.pi)), # Ip_C
                        areas[i]*dt, # Qp
                        t,
                        E,
                        sign * areas[i] * helpers.Shapes[FitObj.PeakShapes[i]][0](FitObj.X, params=[center, sigma, tau], derivs=False),
                    ])
                elif PeakShapes[i] == "exp_gaussian":
                    center = params[it]
                    it += 1
                    sigma = params[it]
                    it += 1
                    tau = params[it]
                    it += 1

                    y_p = helpers.Shapes[PeakShapes[i]][0](FitObj.X, params=[center, sigma, tau], derivs=False)
                    pmax = np.argmax(y_p)

                    results[1].append([
                        CurveID, forward, vRate,
                        E[pmax], # Ep
                        sigma*abs(dE), # sigma
                        tau*abs(dt), # tau
                        I[pmax], # Ip
                        sign * areas[i] / (sigma * np.sqrt(2 * np.pi)) * np.exp(-(center - pmax) ** 2 / (2 * sigma ** 2)), # Ip_F
                        I[pmax] - sign * areas[i] / (sigma * np.sqrt(2 * np.pi)) * np.exp(-(center - pmax) ** 2 / (2 * sigma ** 2)), # Ip_C
                        areas[i]*dt, # Qp
                        t,
                        E,
                        sign * areas[i] * helpers.Shapes[FitObj.PeakShapes[i]][0](FitObj.X, params=[center, sigma, tau], derivs=False),
                    ])
                else:
                    continue

            # Ergebnisse übergeben
            ResultQueue.put(results)
        else:
            raise ValueError("Unknown Task!")

def run():
    root = tk.Tk()
    client = ThreadedClient(root)
    root.mainloop()