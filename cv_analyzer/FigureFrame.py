# https://matplotlib.org/stable/users/explain/event_handling.html
import tkinter as tk
import numpy as np

import matplotlib.pyplot as plt
import matplotlib.backends.backend_tkagg as plt_canvas
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator

import cmcrameri

import time
import threading
from . import helpers


class FigureFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)
        self.controller = controller

        # Farbschema
        helpers.set_scientific_colors_cycler()
        plt.rcParams.update({
            "font.size": 16.0,
            "axes.labelsize": 18,
            "legend.fontsize": 10,
            "figure.autolayout": False,
        })

        # Graph
        # self.fig = Figure(figsize=(4.72, 3.54))
        self.fig = Figure(figsize=(7.08, 5.31))
        self.ax = self.fig.add_subplot(1,1,1)
        self.ax_position = [0.14, 0.12, 0.82, 0.82]
        self.ax.set_position(self.ax_position)
        self.cb = None

        canvas = plt_canvas.FigureCanvasTkAgg(self.fig, self)
        canvas.get_tk_widget().pack(side="bottom", fill=tk.BOTH, expand=True)

        toolbar = plt_canvas.NavigationToolbar2Tk(canvas, self)
        toolbar.update()
        canvas._tkcanvas.pack(side="top", fill=tk.BOTH, expand=True)

        self.Clear()

    def Clear(self):
        if int(self.controller.Settings["ColorBar_Active"].get()) == 0:
            self.RemoveColorbar()
        elif int(self.controller.Settings["ColorBar_Active"].get()) == 1:
            self.AddColorbar()

        self.ax.clear()
        self.ax.grid(False)

        self.ax.xaxis.set_minor_locator(AutoMinorLocator(5))
        self.ax.yaxis.set_minor_locator(AutoMinorLocator(5))

        self.ax.set_xlabel(r"$E~/~{\rm V}$")
        # self.ax.set_xlabel(r"$E_{\rm vs~Ag|AgCl|KCl}~/~{\rm V}$", fontsize=12)
        self.ax.set_ylabel(r"$I~/~{\rm mA}$")

        self.fig.canvas.draw()

    def Redraw(self):
        self.Clear()
        ColorSchemeCoice = int(self.controller.Settings["ColorationScheme_Choice"].get())
        Legend_active = bool(self.controller.Settings["Legend_Active"].get())

        if ColorSchemeCoice == 3: # Nach Kurven-Namen bzw Dateinamen
            ColorIDs = []
            Colors = []
            for i in range(len(self.controller.Data)):
                if self.controller.Data[i].name not in Colors:
                    Colors.append(self.controller.Data[i].name)
                for n in range(len(Colors)):
                    if self.controller.Data[i].name == Colors[n]:
                        ColorID = n
                        break
                ColorIDs.append(ColorID)
        if ColorSchemeCoice == 4: # Nach Elektrode
            ColorIDs = []
            Colors = []
            for i in range(len(self.controller.Data)):
                if self.controller.Data[i].electrode not in Colors:
                    Colors.append(self.controller.Data[i].electrode)
                for n in range(len(Colors)):
                    if self.controller.Data[i].electrode == Colors[n]:
                        ColorID = n
                        break
                ColorIDs.append(ColorID)
        if ColorSchemeCoice == 5: # Nach Channel
            ColorIDs = []
            Colors = []
            for i in range(len(self.controller.Data)):
                if self.controller.Data[i].channel not in Colors:
                    Colors.append(self.controller.Data[i].channel)
                for n in range(len(Colors)):
                    if self.controller.Data[i].channel == Colors[n]:
                        ColorID = n
                        break
                ColorIDs.append(ColorID)
        if ColorSchemeCoice == 6: # nach CurveID
            Feature = np.array([], dtype=float)
            for i in range(len(self.controller.Data)):
                if ColorSchemeCoice == 6:
                    Feature = np.append(Feature, float(self.controller.Data[i].id))
        if ColorSchemeCoice >= 7:
            Feature = np.array([], dtype=float)
            for i in range(len(self.controller.Data)):
                if ColorSchemeCoice == 7:
                    Feature = np.append(Feature, float(self.controller.Data[i].feature_1))
                elif ColorSchemeCoice == 8:
                    Feature = np.append(Feature, float(self.controller.Data[i].feature_2))
                elif ColorSchemeCoice == 9:
                    Feature = np.append(Feature, float(self.controller.Data[i].feature_3))
                elif ColorSchemeCoice == 10:
                    Feature = np.append(Feature, float(self.controller.Data[i].feature_4))
                elif ColorSchemeCoice == 11:
                    Feature = np.append(Feature, float(self.controller.Data[i].feature_5))

        Legends_done = []
        if bool(self.controller.Settings["Reverse_Colors"].get()):
            Colormap = cmcrameri.cm.lipari_r
        else:
            Colormap = cmcrameri.cm.lipari
        for i in range(len(self.controller.Data)):
            if not self.controller.Data[i].active: continue
            if ColorSchemeCoice == 1: # alles Schwarz
                self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"] * 1000, "k")
            elif ColorSchemeCoice == 2:  # Farben nach Spannungsvorschub
                v_min, v_max = self.controller.get_v_minmax()
                if Legend_active and self.controller.Data[i].vRate not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=helpers.colormaps["vRate"]((self.controller.Data[i].vRate-v_min)/(v_max-v_min)), label=f"{self.controller.Data[i].vRate*1000:.0f} mV/s")
                    Legends_done.append(self.controller.Data[i].vRate)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=helpers.colormaps["vRate"]((self.controller.Data[i].vRate-v_min)/(v_max-v_min)))
            elif ColorSchemeCoice == 3: # Nach Kurven-Namen bzw Dateinamen
                if Legend_active and self.controller.Data[i].name not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)), label=f"{self.controller.Data[i].name}")
                    Legends_done.append(self.controller.Data[i].name)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)))
            elif ColorSchemeCoice == 4: # Nach Elektrode
                if Legend_active and self.controller.Data[i].electrode not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)), label=f"{self.controller.Data[i].electrode}")
                    Legends_done.append(self.controller.Data[i].electrode)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)))
            elif ColorSchemeCoice == 5: # Nach Channel
                if Legend_active and self.controller.Data[i].channel not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)), label=f"{self.controller.Data[i].channel}")
                    Legends_done.append(self.controller.Data[i].channel)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap(ColorIDs[i]/(np.max(ColorIDs)+1)))
            elif ColorSchemeCoice == 6: # Nach CurveID
                if Legend_active and self.controller.Data[i].id not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].id)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))
            elif ColorSchemeCoice == 7: # Nach Merkmal 1
                if Legend_active and self.controller.Data[i].feature_1 not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].feature_1)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))
            elif ColorSchemeCoice == 8: # Nach Merkmal 2
                if Legend_active and self.controller.Data[i].feature_2 not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].feature_2)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))
            elif ColorSchemeCoice == 9: # Nach Merkmal 3
                if Legend_active and self.controller.Data[i].feature_3 not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].feature_3)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))
            elif ColorSchemeCoice == 10: # Nach Merkmal 4
                if Legend_active and self.controller.Data[i].feature_4 not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].feature_4)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))
            elif ColorSchemeCoice == 11: # Nach Merkmal 5
                if Legend_active and self.controller.Data[i].feature_5 not in Legends_done:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())), label=f"{Feature[i]}")
                    Legends_done.append(self.controller.Data[i].feature_5)
                else:
                    self.ax.plot(self.controller.Data[i].working_data["E"], self.controller.Data[i].working_data["I"]*1000, color=Colormap((Feature[i] - Feature.min()) / (Feature.max() * 1.1 - Feature.min())))

            if self.controller.Data[i].calculated_data is not None:
                for n in range(len(self.controller.Data[i].calculated_data["E"])):
                    self.ax.plot(self.controller.Data[i].calculated_data["E"][n], self.controller.Data[i].calculated_data["I"][n]*1000, color="k", linestyle="--", alpha=0.2)

            if self.controller.Data[i].peak_results is not None:  # gefittete Peaks markieren
                for n in range(len(self.controller.Data[i].peak_results["Ep"])):
                    if self.controller.Data[i].peak_results["forward"][n]:
                        self.ax.plot(self.controller.Data[i].peak_results["Ep"][n], self.controller.Data[i].peak_results["Ip"][n]*1000, ".", color=helpers.scientific_colors["Green"])
                    else:
                        self.ax.plot(self.controller.Data[i].peak_results["Ep"][n], self.controller.Data[i].peak_results["Ip"][n]*1000, ".", color=helpers.scientific_colors["MedBlue"])
        if Legend_active:self.ax.legend(loc="best")
        self.fig.canvas.draw()

    def Plot(self, x, y, Formatcode='k'):
        self.ax.plot(x, y, Formatcode)
        self.fig.canvas.draw()

    def PlotVLine(self, x):
        self.ax.axvline(x=x, c='gray', linestyle='dotted')
        self.fig.canvas.draw()

    def AddColorbar(self):
        if self.cb is not None:
            self.RemoveColorbar()

        if int(self.controller.Settings["ColorationScheme_Choice"].get()) == 2:
            v_min, v_max = self.controller.get_v_minmax()

            sm = plt.cm.ScalarMappable(cmap=helpers.colormaps["vRate"])
            sm.set_array(np.linspace(v_min, v_max, 10))

            self.cb = self.fig.colorbar(sm, ticks=np.round(np.linspace(v_min, v_max, 5), 2))
            self.cb.set_label(r"$v~/~{\rm V~s^{-1}}$")

            self.ax.set_position([0.14, 0.12, 0.67, 0.82])
            self.cb.ax.set_position([0.83, 0.12, 0.05, 0.82])

    def RemoveColorbar(self):
        if self.cb is not None:
            self.cb.remove()
            self.cb = None
            self.ax.set_position(self.ax_position)


class Picker(object):
    def __init__(self, controller, color="k"):
        self.controller = controller
        self.active = False
        self.finished = False
        self.color = color

        # gespeicherte x-y-Daten
        self.xdata = []
        self.ydata = []

    def Activate(self):
        self.active = True

    def Deactivate(self):
        self.active = False


class xPointPicker(Picker):
    def __init__(self, controller, color="k"):
        super().__init__(controller, color)

        # Events
        self.CanvasClick = None
        self.CanvasHover = None

        self.lines = []

    def Activate(self):
        super().Activate()
        self.CanvasHover = self.controller.fig.canvas.mpl_connect("motion_notify_event", self.EventHover)
        self.CanvasClick = self.controller.fig.canvas.mpl_connect("button_press_event", self.EventClick)

    def Deactivate(self):
        super().Deactivate()
        self.controller.fig.canvas.mpl_disconnect(self.CanvasHover)
        self.CanvasHover = None
        self.controller.fig.canvas.mpl_disconnect(self.CanvasClick)
        self.CanvasClick = None

        for line in self.lines:
            line.remove()
        self.lines = []
        self.controller.fig.canvas.draw()

    def EventClick(self, event):
        # Klick außerhalb der Achsen: kein Punkt, Auswahl läuft weiter.
        if event.xdata is None or event.ydata is None:
            return
        self.xdata.append(event.xdata)
        self.ydata.append(event.ydata)
        self.finished = True
        self.Deactivate()

    def EventHover(self, event):
        # Außerhalb der Achsen liefert das Event None; set_xdata() verlangt seit
        # matplotlib 3.10 eine Sequenz statt eines Skalars.
        if event.xdata is None or event.ydata is None:
            return
        if len(self.lines) > 0:
            self.lines[0].set_xdata([event.xdata])
            self.controller.fig.canvas.draw()
        else:
            self.lines.append(self.controller.ax.axvline(event.xdata, color=self.color, linewidth=1, linestyle="-"))

class PointPicker(Picker):
    def __init__(self, controller, color="k"):
        super().__init__(controller, color)

        # Events
        self.CanvasClick = None
        self.CanvasHover = None

        self.lines = []

    def Activate(self):
        super().Activate()
        self.CanvasHover = self.controller.fig.canvas.mpl_connect("motion_notify_event", self.EventHover)
        self.CanvasClick = self.controller.fig.canvas.mpl_connect("button_press_event", self.EventClick)

    def Deactivate(self):
        super().Deactivate()
        self.controller.fig.canvas.mpl_disconnect(self.CanvasHover)
        self.CanvasHover = None
        self.controller.fig.canvas.mpl_disconnect(self.CanvasClick)
        self.CanvasClick = None

        for line in self.lines:
            line.remove()
        self.lines = []
        self.controller.fig.canvas.draw()

    def EventClick(self, event):
        # Klick außerhalb der Achsen: kein Punkt, Auswahl läuft weiter.
        if event.xdata is None or event.ydata is None:
            return
        self.xdata.append(event.xdata)
        self.ydata.append(event.ydata)
        self.finished = True
        self.Deactivate()

    def EventHover(self, event):
        # Außerhalb der Achsen liefert das Event None; set_xdata() verlangt seit
        # matplotlib 3.10 eine Sequenz statt eines Skalars.
        if event.xdata is None or event.ydata is None:
            return
        if len(self.lines) > 0:
            self.lines[0].set_xdata([event.xdata])
            self.lines[1].set_ydata([event.ydata])
            self.controller.fig.canvas.draw()
        else:
            self.lines.append(self.controller.ax.axvline(event.xdata, color=self.color, linewidth=1, linestyle="-"))
            self.lines.append(self.controller.ax.axhline(event.ydata, color=self.color, linewidth=1, linestyle="-"))

class RangePicker(Picker):
    def __init__(self, controller, color="k"):
        super().__init__(controller, color="k")

        # Events
        self.CanvasClick = None
        self.CanvasHover = None

        self.lines = []

    def Activate(self):
        super().Activate()
        self.CanvasHover = self.controller.fig.canvas.mpl_connect("motion_notify_event", self.EventHover)
        self.CanvasClick = self.controller.fig.canvas.mpl_connect("button_press_event", self.EventClick)

    def Deactivate(self):
        super().Deactivate()
        self.controller.fig.canvas.mpl_disconnect(self.CanvasHover)
        self.CanvasHover = None
        self.controller.fig.canvas.mpl_disconnect(self.CanvasClick)
        self.CanvasClick = None

        for line in self.lines:
            line.remove()
        self.lines = []
        self.controller.fig.canvas.draw()

    def EventClick(self, event):
        if len(self.lines) == 1:
            self.xdata = [event.xdata]
            self.ydata = [event.ydata]

            self.lines.append(self.controller.ax.axvline(self.xdata, color=self.color, linewidth=1, linestyle="-"))
            self.controller.fig.canvas.draw()
        elif len(self.lines) == 2:
            self.xdata.append(event.xdata)
            self.ydata.append(event.ydata)
            self.finished = True
            self.Deactivate()

    def EventHover(self, event):
        # Außerhalb der Achsen liefert das Event None; set_xdata() verlangt seit
        # matplotlib 3.10 eine Sequenz statt eines Skalars.
        if event.xdata is None or event.ydata is None:
            return
        if len(self.lines) == 0:
            self.lines.append(self.controller.ax.axvline(event.xdata, color=self.color, linewidth=1, linestyle="-"))
            self.controller.fig.canvas.draw()
        else:
            self.lines[-1].set_xdata([event.xdata])
            self.controller.fig.canvas.draw()

class RectanglePicker(Picker):
    def __init__(self, controller, color="k"):
        super().__init__(controller, color="k")

        # Events
        self.CanvasClick = None
        self.CanvasHover = None

        # Plot-Linien
        # 0: [[x1, x2], [y1, y1]]
        # 1: [[x1, x2], [y2, y2]]
        # 2: [[x1, x1], [y1, y2]]
        # 3: [[x2, x2], [y1, y2]]
        self.lines = []

    def Activate(self):
        super().Activate()
        self.CanvasClick = self.controller.fig.canvas.mpl_connect("button_press_event", self.EventClick)

    def Deactivate(self):
        super().Deactivate()
        self.controller.fig.canvas.mpl_disconnect(self.CanvasHover)
        self.CanvasHover = None
        self.controller.fig.canvas.mpl_disconnect(self.CanvasClick)
        self.CanvasClick = None

        for line in self.lines:
            line.remove()
        self.lines = []
        self.controller.fig.canvas.draw()

    def EventClick(self, event):
        if self.CanvasHover is None:
            self.CanvasHover = self.controller.fig.canvas.mpl_connect("motion_notify_event", self.EventHover)
            self.xdata = [event.xdata]
            self.ydata = [event.ydata]

            self.lines.append(self.controller.ax.plot([self.xdata, self.xdata], [self.ydata, self.ydata], color=self.color, linewidth=1, linestyle="-")[0])
            self.lines.append(self.controller.ax.plot([self.xdata, self.xdata], [self.ydata, self.ydata], color=self.color, linewidth=1, linestyle="-")[0])
            self.lines.append(self.controller.ax.plot([self.xdata, self.xdata], [self.ydata, self.ydata], color=self.color, linewidth=1, linestyle="-")[0])
            self.lines.append(self.controller.ax.plot([self.xdata, self.xdata], [self.ydata, self.ydata], color=self.color, linewidth=1, linestyle="-")[0])
            self.controller.fig.canvas.draw()
        else:
            self.xdata.append(event.xdata)
            self.ydata.append(event.ydata)
            self.finished = True
            self.Deactivate()

    def EventHover(self, event):
        self.lines[0].set_data([self.xdata[0], event.xdata], [self.ydata[0], self.ydata[0]])
        self.lines[1].set_data([self.xdata[0], event.xdata], [event.ydata, event.ydata])
        self.lines[2].set_data([self.xdata[0], self.xdata[0]], [self.ydata[0], event.ydata])
        self.lines[3].set_data([event.xdata, event.xdata], [self.ydata[0], event.ydata])
        self.controller.fig.canvas.draw()

class Pick_xPointEvent(threading.Thread):
    def __init__(self, controller, button, var1, DefaultText):
        super().__init__()
        self.controller = controller
        self.button = button
        self.var1 = var1
        self.DefaultText = DefaultText

    def run(self):
        while self.controller.Picker.active:
            time.sleep(0.01)

        if self.controller.Picker.finished:
            self.var1.set(round(self.controller.Picker.xdata[0], 3))
        else:
            return
        self.button.config(text=self.DefaultText)
        self.controller.Picker = None

class PickRangeEvent(threading.Thread):
    def __init__(self, controller, button, var1, var2, DefaultText):
        super().__init__()
        self.controller = controller
        self.button = button
        self.var1 = var1
        self.var2 = var2
        self.DefaultText = DefaultText

    def run(self):
        while self.controller.Picker.active:
            time.sleep(0.01)

        if self.controller.Picker.finished:
            if self.controller.Picker.xdata[0] < self.controller.Picker.xdata[1]:
                self.var1.set(round(self.controller.Picker.xdata[0], 3))
                self.var2.set(round(self.controller.Picker.xdata[1], 3))
            else:
                self.var1.set(round(self.controller.Picker.xdata[1], 3))
                self.var2.set(round(self.controller.Picker.xdata[0], 3))
        else:
            return
        self.button.config(text=self.DefaultText)
        self.controller.Picker = None