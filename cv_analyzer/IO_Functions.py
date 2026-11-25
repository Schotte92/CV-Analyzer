import os
import numpy as np
import pandas as pd
from scipy import signal

import io
import zipfile

from tkinter import simpledialog, messagebox
from . import helpers


def Get_vRate_from_FileName(FileName):
    multiplier = 1e-3
    pos = helpers.find_str(FileName, "mVps")
    if pos is None:
        multiplier = 1
        pos = helpers.find_str(FileName, "Vps")
        if pos is None:
            return None

    try:
        i = pos-1
        while FileName[i-1].isdigit() or FileName[i-1] == ".": i-=1
        vRate = multiplier * float(FileName[i:pos])
    except:
        return None
    return vRate

def Import_PalmSensCSV(File):
    vRate = Get_vRate_from_FileName(File)
    if vRate is None:
        vRate = simpledialog.askstring("Spannungsvorschub", "Bitte den Spannungsvorschub in V/s eingeben:")
        if vRate is None:  # Dialog abgebrochen
            return None
        try:
            vRate = float(vRate)
        except (ValueError, TypeError):
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
            return
    if vRate < 0:
        messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
        return

    data = np.genfromtxt(File, delimiter=",", skip_header=6, skip_footer=1, encoding="utf-16").T
    # Elektrodenbenennung
    f = open(File, "r", encoding="utf-16")
    description = f.readline()
    description = f.readline()
    description = f.readline()
    description = f.readline().split(",")
    f.close()

    Channels = []
    for i in np.arange(0, data.shape[0], 2):
        if "CH" in description[i]:
            Channel = int(helpers.getBetween(description[i], "CH", ":"))
        else:
            Channel = 1
        Channels.append(Channel)

    ActiveChannel = simpledialog.askstring("Channel", "Bitte Channel ein der importiert werden soll\n(all = alle, mehrere mit Komma trennen):")
    if ActiveChannel is None:  # Dialog abgebrochen
        return None
    if "all" in ActiveChannel:
        ActiveChannel = np.array([-1], dtype=float)
    elif "," in ActiveChannel:
        try:
            ActiveChannel = np.array(ActiveChannel.split(","), dtype=float)
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return
    else:
        try:
            ActiveChannel = np.array([ActiveChannel], dtype=float)
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return
        if ActiveChannel not in Channels:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return

    Results = {"Channels": np.array([], dtype=int), "Cycles": np.array([], dtype=int), "tn": [], "En": [], "In": [], "En_rev": [], "vRate": vRate, "dt": None, "dE": None}
    for i in range(len(description)):
        if description[i] == "": continue
        if "CH" in description[i]:
            Channel = int(helpers.getBetween(description[i], "CH", ":"))
        else:
            Channel = 1
        if -1 not in ActiveChannel and Channel not in ActiveChannel:
            continue

        Cycle = int(description[i][helpers.find_str(description[i], "Scan ") + 5:])
        ind = ~np.isnan(data[i])
        if np.intersect1d(np.argwhere(Results["Channels"] == Channel).flatten(), np.argwhere(Results["Cycles"] == Cycle).flatten()).size == 0:
            Results["Channels"] = np.append(Results["Channels"], Channel)
            Results["Cycles"] = np.append(Results["Cycles"], Cycle)
            Results["En"].append(data[i][ind])
            Results["En_rev"].append(np.argmax(Results["En"][-1]))

            if Results["dE"] is None: Results["dE"] = np.median(np.append(np.gradient(Results["En"][-1][:Results["En_rev"][-1]]), -1 * np.gradient(Results["En"][-1][Results["En_rev"][-1]:])))
            if Results["dt"] is None: Results["dt"] = Results["dE"] / Results["vRate"]

            Results["tn"].append(np.arange(0, Results["dt"] * len(Results["En"][-1]), Results["dt"]))
            Results["In"].append(None)
            # Evtl für später
            # Results["ECEn"].append(None)
            # Results["EWEn"].append(None)
        iResult = np.intersect1d(np.argwhere(Results["Channels"] == Channel).flatten(), np.argwhere(Results["Cycles"] == Cycle).flatten())[0]

        if "CV i vs E" in description[i]:
            DataType = "In"
        # Evtl für später
        # elif "CV Cell potential" in description[i]:
        #     DataType = "ECEn"
        # elif "CV Measured WE potential" in description[i]:
        #     DataType = "EWEn"
        else:
            continue

        if DataType == "In":
            Results[DataType][iResult] = 1e-6 * data[i + 1][ind]
        # Evtl für später
        # else:
        #     Results[DataType][iResult] = data[i + 1][ind]

    return Results

def Import_PalmSensExcel(File):
    vRate = Get_vRate_from_FileName(File)
    if vRate is None:
        vRate = simpledialog.askstring("Spannungsvorschub", "Bitte den Spannungsvorschub in V/s eingeben:")
        if vRate is None:  # Dialog abgebrochen
            return None
        try:
            vRate = float(vRate)
        except (ValueError, TypeError):
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
            return
    if vRate < 0:
        messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Float-Zahl >0 eingeben.")
        return

    pd_data = pd.read_excel(File)

    Channels = []
    for description in pd_data.columns:
        if "CH" in description:
            Channel = int(helpers.getBetween(description, "CH", ":"))
            Channels.append(Channel)

    ActiveChannel = simpledialog.askstring("Channel", "Bitte Channel ein der importiert werden soll\n(all = alle, mehrere mit Komma trennen):")
    if ActiveChannel is None:  # Dialog abgebrochen
        return None
    if "all" in ActiveChannel:
        ActiveChannel = np.array([-1], dtype=float)
    elif "," in ActiveChannel:
        try:
            ActiveChannel = np.array(ActiveChannel.split(","), dtype=float)
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return
    else:
        try:
            ActiveChannel = np.array([ActiveChannel], dtype=float)
        except ValueError:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return
        if ActiveChannel not in Channels:
            messagebox.showerror("Ungültige Eingabe", "Bitte eine gültige Integer-Zahl oder 'all' eingeben.")
            return

    Channels = []
    Cycles = []
    tn = []
    En = []
    In = []
    En_rev = []

    for i in np.arange(0, len(pd_data.columns), 2):
        if "CH" in pd_data.columns[i]:
            Channel = int(helpers.getBetween(pd_data.columns[i], "CH", ":"))
        else:
            continue
        if -1 not in ActiveChannel and Channel not in ActiveChannel:
            continue
        Cycle = int(pd_data.columns[i][helpers.find_str(pd_data.columns[i], "Scan ") + 5:])

        Channels.append(Channel)
        Cycles.append(Cycle)
        ind = np.argwhere(~np.isnan(pd_data.iloc[1:,i].to_numpy(dtype=float))).T[0]
        En.append(pd_data.iloc[1:,i].to_numpy(dtype=float)[ind])
        In.append(1e-6 * pd_data.iloc[1:,i+1].to_numpy(dtype=float)[ind])
        En_rev.append(np.argmax(En[-1]))
        dE = np.mean(np.append(np.gradient(En[-1][:En_rev[-1]]), -1 * np.gradient(En[-1][En_rev[-1]:])))
        dt = dE / vRate
        tn.append(np.arange(0, dt * len(En[-1]), dt))

    return {"Channels": Channels, "Cycles": Cycles, "tn": tn, "En": En, "In": In, "En_rev": En_rev, "vRate": vRate, "dt": dt, "dE": dE}

def Import_RaspiZIP(File, vRate):
    ZF = zipfile.ZipFile(File, mode="r")
    try:
        data = np.genfromtxt(io.BytesIO(ZF.read("CV-{0:.3f}Vps.txt".format(vRate))), delimiter="\t", skip_header=5, dtype=float).T
    except:
        messagebox.showerror("Fehler", "Die Daten konnten nicht für diesen Spannungsvorschub konnten nicht geladen werden!")
        return

    return SplitCycles(data[0], data[1], data[2], vRate)

def Import_npzFile(File):
    data = np.load(File)
    return SplitCycles(data["t"], data["E"], data["I"], data["v"]/1000)

def Import_Solartron(File):
    vRate = None

    File = open(File, "r", encoding="ISO-8859-1")
    for line in File:
        line = line.split(":")
        if line[0] == "=VoltageFeed" and len(line) >= 2:
            vRate = float((line[1].strip("\n")).replace(",", "."))
            break
    if vRate is None: return None

    En_rev = []
    tn = []
    En = []
    In = []

    return {"tn": tn, "En": En, "In": In, "En_rev": En_rev, "vRate": vRate}


def Import_SRS(File):
    if os.path.isfile(File) == False:
        return None

    Data = pd.read_csv(File, sep=" ", decimal=",", header=7, skipinitialspace=True)
    t = np.array(Data["T(usec)"].values)/1000000
    E = np.array(Data["E(V)"].values)
    I = -1 * np.array(Data["I(mA)"].values)/1000
    vRate = False

    File = open(File, "r")
    for line in File:
        line = line.split(" ")
        if line[0] == "VRate" and len(line) > 2:
            vRate = int(line[1]) / 1000
            break
    if vRate is None: return None

    return SplitCycles(t, E, I, vRate)

def SplitCycles(t, E, I, vRate):
    start = np.argmin(I[:20])
    t = t[start:]
    E = E[start:]
    I = I[start:]

    dt = t[1] - t[0]
    steps_per_cycle = int(round(((np.max(E) - np.min(E)) / vRate) / dt * 2, 0))

    E_start = np.append(steps_per_cycle * np.arange(int(round(len(t) / steps_per_cycle, 0))), len(t) - 1)

    Channels = []
    Cycles = []
    En_rev = []
    tn = []
    En = []
    In = []

    for i in range(0, len(E_start)-1):
        Channels.append(1)
        Cycles.append(i+1)
        if len(t[E_start[i]:E_start[i + 1]]) != steps_per_cycle:
            t_new = np.linspace(np.min(t[E_start[i]:E_start[i + 1]]), np.max(t[E_start[i]:E_start[i + 1]]), steps_per_cycle)
            En.append(np.interp(t_new, t[E_start[i]:E_start[i + 1]], E[E_start[i]:E_start[i + 1]]))
            In.append(np.interp(t_new, t[E_start[i]:E_start[i + 1]], I[E_start[i]:E_start[i + 1]]))
            tn.append(t_new)
        else:
            tn.append(t[E_start[i]:E_start[i + 1]])
            En.append(E[E_start[i]:E_start[i + 1]])
            In.append(I[E_start[i]:E_start[i + 1]])
        En_rev.append(np.argmax(En[i]))

    return {"Channels": Channels, "Cycles": Cycles, "tn": tn, "En": En, "In": In, "En_rev": En_rev, "vRate": vRate, "dt": dt, "dE": dt*vRate}

def ReassignCycles(data):
    t = np.array([], dtype=float)
    E = np.array([], dtype=float)
    I = np.array([], dtype=float)

    t0 = 0
    for n in range(len(data["En"])):
        t = np.append(t, data["tn"][n]+t0)
        E = np.append(E, data["En"][n])
        I = np.append(I, data["In"][n])
        t0 = np.max(t)
    data["tn"] = []
    data["En"] = []
    data["In"] = []
    data["En_rev"] = []

    E_start = np.append([0], signal.argrelmin(E))
    if len(E_start) < len(data["Cycles"])+1:
        E_start = np.append(E_start, len(E)-1)

    for n in range(len(E_start)-1):
        data["tn"].append(t[E_start[n]:E_start[n+1]])
        data["En"].append(E[E_start[n]:E_start[n+1]])
        data["In"].append(I[E_start[n]:E_start[n+1]])
        data["En_rev"].append(np.argmax(data["En"][-1]))

    return data