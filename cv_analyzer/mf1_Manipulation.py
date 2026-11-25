import tkinter as tk
from tkinter import ttk


class ManipulationFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)
        tk.Label(self, text="Zyklusselektion", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Zyklen verwerfen:").pack(side="left", padx=5)
        E = tk.Entry(row, width=15, textvariable=controller.Settings["DelCyclus"])
        E.pack(side="left", padx=5)
        controller.HorizontalLine(self)

        tk.Label(self, text="Manipulationen", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        # Bereich Savitzky Golay
        tk.Checkbutton(self, text="Savitzky Golay Glättung", variable=controller.Settings["SavGol_Active"]).pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Spannungsfenster (V):").pack(side="left", padx=5)
        E = tk.Entry(row, width=4, textvariable=controller.Settings["SavGol_Width"])
        E.pack(side="left", padx=5)
        tk.Label(row, text="Polynom:", anchor='w').pack(side="left", padx=5)
        E = tk.Entry(row, width=4, textvariable=controller.Settings["SavGol_Polynom"])
        E.pack(side="left", padx=5)
        controller.HorizontalLine(self)

        # Interpolation
        tk.Checkbutton(self, text="Interpolation/Datenpunkte reduzieren", variable=controller.Settings["Interpolate_Active"]).pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Datenpunkte pro Zyklus:").pack(side="left", padx=5)
        E = tk.Entry(row, width=6, textvariable=controller.Settings["Interpolate_Points"])
        E.pack(side="left", padx=5)
        controller.HorizontalLine(self)

        # Korrekturen
        tk.Checkbutton(self, text="Korrekturformeln", variable=controller.Settings["Correction_Active"]).pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        tk.Label(row, text="Referenzpotential (V):").grid(row=0, column=0)
        E = tk.Entry(row, width=20, textvariable=controller.Settings["Correction_Eref"])
        E.grid(row=0, column=1)

        controller.HorizontalLine(self)

        tk.Checkbutton(self, text="E normieren (Min/Max)", variable=controller.Settings["Normalize_E_MinMax"]).pack(padx=5, pady=5)
        tk.Checkbutton(self, text="E normieren (Nulldurchgänge)", variable=controller.Settings["Normalize_E_ZeroCrossings"]).pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        ttk.Button(row, text="Neu berechnen", command=controller.Recalculate).pack(side="left", padx=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=10, side="bottom")
        ttk.Button(row, text="Zurück", state="disabled").pack(side="left", padx=5)
        ttk.Button(row, text="Weiter", command=lambda: controller.ShowFrame(1)).pack(side="left", padx=5)