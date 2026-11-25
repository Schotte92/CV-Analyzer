import tkinter as tk
from tkinter import ttk


class GraphSettingsFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)
        tk.Label(self, text="Farbgebung", font=("Arial", 14), anchor='w').pack(padx=5, pady=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=0)
        for txt, val in [("Schwarz",1), ("nach Spannungsvorschub",2), ("nach Namen",3), ("nach Elektrode",4), ("nach Channel",5), ("nach CurveID",6), ("Merkmal 1",7), ("Merkmal 2",8), ("Merkmal 3",9), ("Merkmal 4",10), ("Merkmal 5",11)]:
            row = tk.Frame(self)
            row.pack(padx=5, pady=0)
            tk.Radiobutton(row, text=txt, padx=20, variable=controller.Settings["ColorationScheme_Choice"], value=val).pack(side="left", padx=5)

        tk.Checkbutton(self, text="Farbbalken", variable=controller.Settings["ColorBar_Active"]).pack(padx=5, pady=5)
        tk.Checkbutton(self, text="Legende", variable=controller.Settings["Legend_Active"]).pack(padx=5, pady=5)
        tk.Checkbutton(self, text="Farben umkehren", variable=controller.Settings["Reverse_Colors"]).pack(padx=5, pady=5)

        controller.HorizontalLine(self)

        row = tk.Frame(self)
        row.pack(padx=5, pady=5)
        ttk.Button(row, text="Neu zeichnen", command=controller.Redraw).pack(side="left", padx=5)

        row = tk.Frame(self)
        row.pack(padx=5, pady=10, side="bottom")
        ttk.Button(row, text="Zurück", command=lambda: controller.ShowFrame(0)).pack(side="left", padx=5)
        ttk.Button(row, text="Weiter", command=lambda: controller.ShowFrame(2)).pack(side="left", padx=5)