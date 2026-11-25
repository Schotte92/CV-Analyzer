import tkinter as tk
from tkinter import ttk

import time
import threading

from . import FigureFrame

class IntegrationFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)

        self.Picker = None

        controller.HorizontalLine(self)
        tk.Label(self, text="Integrationsbereich", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        self.Button_Range = ttk.Button(row, text="Integrationsbereich", command=lambda: self.Switch_Range_Picker(controller))
        self.Button_Range.pack(side="left", padx=0)
        tk.Label(row, text="E-start (V):", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Integrate_ERangeStart"]).pack(side="left", padx=0)
        tk.Label(row, text="E-end (V):", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Integrate_ERangeEnd"]).pack(side="left", padx=0)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        self.Button_DLPoint = ttk.Button(row, text="Doppelschichtpunkt", command=lambda: self.Switch_DLPoint_Picker(controller))
        self.Button_DLPoint.pack(side="left", padx=0)
        tk.Label(row, text="E-start (V):", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Integrate_Edl"]).pack(side="left", padx=0)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        ttk.Button(row, text="Berechnen", command=controller.Integrate).pack(side="left", padx=0)

        controller.HorizontalLine(self)

        row = tk.Frame(self)
        row.pack(padx=5, pady=10, side="bottom")
        ttk.Button(row, text="Zurück", command=lambda: controller.ShowFrame(1)).pack(side="left", padx=5)
        ttk.Button(row, text="Weiter", command=lambda: controller.ShowFrame(3)).pack(side="left", padx=5)

    def Switch_Range_Picker(self, controller):
        if self.Picker is None:
            self.Button_Range.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.RangePicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = FigureFrame.PickRangeEvent(self, self.Button_Range, controller.Settings["Integrate_ERangeStart"], controller.Settings["Integrate_ERangeEnd"], "Integrationsbereich")
            self.PickerEvent.start()
        else:
            self.Button_Range.config(text="Integrationsbereich")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None

    def Switch_DLPoint_Picker(self, controller):
        if self.Picker is None:
            self.Button_DLPoint.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.xPointPicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = FigureFrame.Pick_xPointEvent(self, self.Button_DLPoint, controller.Settings["Integrate_Edl"], "Doppelschichtpunkt")
            self.PickerEvent.start()
        else:
            self.Button_DLPoint.config(text="Doppelschichtpunkt")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None