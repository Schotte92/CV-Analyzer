import tkinter as tk
from tkinter import ttk

import time
import threading

from . import FigureFrame
from . import helpers

class FitFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)

        self.Picker = None

        controller.HorizontalLine(self)
        tk.Label(self, text="Kurvenfit-Bereich", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        self.Button_RangeForward = ttk.Button(row, text="Bereich (aufwärts)", command=lambda: self.Switch_Range_Picker_Forward(controller)) # Command
        self.Button_RangeForward.pack(side="left", padx=0)
        tk.Label(row, text="E-start:", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Fit_ERangeStart_Forward"]).pack(side="left", padx=0)
        tk.Label(row, text="V, E-end:", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Fit_ERangeEnd_Forward"]).pack(side="left", padx=0)
        tk.Label(row, text="V", anchor='w').pack(side="left", padx=0)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        self.Button_RangeReverse = ttk.Button(row, text="Bereich (abwärts) ", command=lambda: self.Switch_Range_Picker_Reverse(controller)) # Command
        self.Button_RangeReverse.pack(side="left", padx=0)
        tk.Label(row, text="E-start:", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Fit_ERangeStart_Reverse"]).pack(side="left", padx=0)
        tk.Label(row, text="V, E-end:", anchor='w').pack(side="left", padx=0)
        tk.Entry(row, width=6, textvariable=controller.Settings["Fit_ERangeEnd_Reverse"]).pack(side="left", padx=0)
        tk.Label(row, text="V", anchor='w').pack(side="left", padx=0)

        controller.HorizontalLine(self)
        tk.Label(self, text="Peaks einfügen", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        self.PeakShapeList = ["Gauß-Peak", "Exp. mod. Gauß-Peak"]
        controller.Settings["Fit_PeakShape"].set(self.PeakShapeList[0])

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Peak-Form:").pack(side="left", padx=5)
        opt = tk.OptionMenu(row, controller.Settings["Fit_PeakShape"], *self.PeakShapeList)
        opt.config(width=20)
        opt.pack()

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        self.Button_SearchPeaks = ttk.Button(row, text="Peaksuche", command=controller.SearchPeaks) # Command
        self.Button_SearchPeaks.pack(side="left", padx=5)
        self.Button_AddPeak_Forward = ttk.Button(row, text="+Peak (aufwärts)", command=lambda: self.Switch_AddPeak_Picker_Forward(controller)) # Command
        self.Button_AddPeak_Forward.pack(side="left", padx=5)
        self.Button_AddPeak_Reverse = ttk.Button(row, text="+Peak (abwärts) ", command=lambda: self.Switch_AddPeak_Picker_Reverse(controller)) # Command
        self.Button_AddPeak_Reverse.pack(side="left", padx=5)

        controller.HorizontalLine(self)
        tk.Label(self, text="Gewichtung Ableitungen", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Checkbutton(self, text="Funktion", variable=controller.Settings["Fit_wd0"]).pack(padx=5, pady=0)
        tk.Checkbutton(self, text="1. Ableitung", variable=controller.Settings["Fit_wd1"]).pack(padx=5, pady=0)
        tk.Checkbutton(self, text="2. Ableitung", variable=controller.Settings["Fit_wd2"]).pack(padx=5, pady=0)

        controller.HorizontalLine(self)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Prozesse", anchor='w').pack(side="left", padx=5)
        tk.Entry(row, width=5, textvariable=controller.Settings["Fit_Workers"]).pack(side="left", padx=5)
        controller.GUI_Elements["mf3_Button_StartFit"] = ttk.Button(row, text="Start Fit", command=controller.StartFit)
        controller.GUI_Elements["mf3_Button_StartFit"].pack(side="left", padx=5)
        controller.GUI_Elements["mf3_Button_StopFit"] = ttk.Button(row, text="Stop Fit", command=controller.StopFit, state="disabled")
        controller.GUI_Elements["mf3_Button_StopFit"].pack(side="left", padx=5)

        # Progressbar
        row = tk.Frame(self)
        controller.GUI_Elements["mf3_Label_ProgressBar"] = tk.StringVar(value="Kein Fitprozess aktiv...")
        controller.GUI_Elements["mf3_ProgressBar"] = tk.ttk.Progressbar(row, length=250, mode="determinate")
        controller.GUI_Elements["mf3_ProgressBar"].pack(padx=10, pady=0)
        tk.Label(row, textvariable=controller.GUI_Elements["mf3_Label_ProgressBar"], anchor="w", font=("Arial", 12)).pack(padx=10, pady=0)
        row.pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=10, side="bottom")
        ttk.Button(row, text="Zurück", command=lambda: controller.ShowFrame(2)).pack(side="left", padx=5)
        ttk.Button(row, text="Weiter", state="disabled").pack(side="left", padx=5)

    def Switch_Range_Picker_Forward(self, controller):
        if self.Picker is None:
            self.Button_RangeForward.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.RangePicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = FigureFrame.PickRangeEvent(self, self.Button_RangeForward, controller.Settings["Fit_ERangeStart_Forward"], controller.Settings["Fit_ERangeEnd_Forward"], "Bereich (aufwärts)")
            self.PickerEvent.start()
        else:
            self.Button_RangeForward.config(text="Bereich (aufwärts)")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None

    def Switch_Range_Picker_Reverse(self, controller):
        if self.Picker is None:
            self.Button_RangeReverse.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.RangePicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = FigureFrame.PickRangeEvent(self, self.Button_RangeReverse, controller.Settings["Fit_ERangeStart_Reverse"], controller.Settings["Fit_ERangeEnd_Reverse"], "Bereich (abwärts)")
            self.PickerEvent.start()
        else:
            self.Button_RangeReverse.config(text="Bereich (abwärts)")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None

    def Switch_AddPeak_Picker_Forward(self, controller):
        if self.Picker is None:
            self.Button_AddPeak_Forward.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.RangePicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = PickPeakRangeEvent(self, self.Button_AddPeak_Forward, controller.AddPeakCandidate, True, "+Peak (aufwärts)")
            self.PickerEvent.start()
        else:
            self.Button_AddPeak_Forward.config(text="+Peak (aufwärts)")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None

    def Switch_AddPeak_Picker_Reverse(self, controller):
        if self.Picker is None:
            self.Button_AddPeak_Reverse.config(text="Auswahl stoppen")
            self.Picker = FigureFrame.RangePicker(controller.Graph)
            self.Picker.Activate()
            self.PickerEvent = PickPeakRangeEvent(self, self.Button_AddPeak_Reverse, controller.AddPeakCandidate, False, "+Peak (abwärts)")
            self.PickerEvent.start()
        else:
            self.Button_AddPeak_Reverse.config(text="+Peak (abwärts)")
            self.Picker.Deactivate()
            self.Picker = None
            self.PickerEvent = None


class PickPointEvent(threading.Thread):
    def __init__(self, controller, button, AddPeakFunction, forward, DefaultText):
        super().__init__()
        self.controller = controller
        self.button = button
        self.AddPeakFunction = AddPeakFunction
        self.forward = forward
        self.DefaultText = DefaultText

    def run(self):
        while self.controller.Picker.active:
            time.sleep(0.01)

        if self.controller.Picker.finished:
            self.AddPeakFunction(round(self.controller.Picker.xdata[0], 3), self.forward)
        else:
            return
        self.button.config(text=self.DefaultText)
        self.controller.Picker = None

class PickPeakRangeEvent(threading.Thread):
    def __init__(self, controller, button, AddPeakFunction, forward, DefaultText):
        super().__init__()
        self.controller = controller
        self.button = button
        self.AddPeakFunction = AddPeakFunction
        self.forward = forward
        self.DefaultText = DefaultText

    def run(self):
        while self.controller.Picker.active:
            time.sleep(0.01)

        if self.controller.Picker.finished:
            self.AddPeakFunction(self.controller.Picker.xdata, self.forward)
        else:
            return
        self.button.config(text=self.DefaultText)
        self.controller.Picker = None