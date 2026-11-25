import tkinter as tk

import pandas as pd
import pandastable
import numpy as np

import copy


class TableFrame(tk.Frame):
    def __init__(self, parent, controller):
        tk.Frame.__init__(self, parent)

        # Tabelle
        self.Table = pandastable.Table(self, showtoolbar=False, showstatusbar=False, width=400, height=155) # 2 Tabellen: 237, 3 Tabellen: 155
        self.Table.model.df = pd.DataFrame({"val": [""]})
        self.Table.show()

    def SetValues(self, ModelDict):
        if type(ModelDict) == dict:
            ModelDict = copy.deepcopy(ModelDict)
            for ind in ModelDict:
                for n in range(len(ModelDict[ind]), 20):
                    ModelDict[ind].append(np.nan)

            df = pd.DataFrame(ModelDict)
            self.Table.model.df = df
            self.Table.redraw()

    def GetValues(self):
        return np.transpose(self.Table.model.df.values)