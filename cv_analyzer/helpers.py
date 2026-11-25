"""
Numerische Hilfsfunktionen für den CV-Analyzer.

Enthalten:
    find_str, getBetween              Stringsuche in Messdatei-Headern
    sort_aphanumeric                  natürliche Sortierung von Zyklusnamen
    GetNearest, FindZeroCrossings     Peak- und Nulldurchgangssuche
    Moving_Std                        gleitende Standardabweichung
    Weighted_Mulitilinear_Regression  gewichtete Regression (Peakfit)
    Gauss, Lorentz, Voigt, ExpGauss   Peakformen
    Shapes, FitOptimizer              Peakfit-Problem für pygmo
    scientific_colors, colormaps      Farbschema für Plots
    trapez                            Trapezregel, unabhängig von der numpy-Version
"""

import re

import cmcrameri.cm
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal, special

# numpy 2.0 hat np.trapz entfernt (dort heißt die Funktion np.trapezoid),
# numpy 1.x kennt nur np.trapz. Hier einmal festlegen, damit der Analyzer mit
# beiden Versionen integriert. Sonst bricht die Ladungsberechnung bei einer
# frischen Installation ab.
if hasattr(np, "trapezoid"):
    trapez = np.trapezoid
else:
    trapez = np.trapz

plt.rcParams.update({
    "font.size": 14.0,
    "axes.labelsize": 16,
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "figure.figsize": (4.72, 3.54),
    "figure.autolayout": True,
    "errorbar.capsize": 3,
})



def find_str(str, search_str, direction=1, start_index=None):
    """
    Sucht nach einem String in einem anderen String.

    :param str: String IN dem gesucht wird
    :param search_str: String NACH dem gesucht wird
    :param direction: Suchrichtung: 1 oder -1, von vorne nach hinten oder von hinten nach vorne
    :param start_index: Position an dem die Suche startet
    :return: Position des gesuchten Strings ODER None
    """

    if direction == 1:
        if start_index is None:
            index = 0
        else:
            index = start_index

        while index + len(search_str) <= len(str):
            if str[index:index + len(search_str)] == search_str:
                return index
            index = index + direction
    elif direction == -1:
        if start_index is None:
            index = len(str) - len(search_str)
        else:
            index = start_index

        while index >= 0:
            if str[index:index + len(search_str)] == search_str:
                return index
            index = index + direction
    else:
        raise ValueError("Direction must be 1 or -1")
    return None



def getBetween(str, start, end):
    """
    Liefert einen String zwischen zwei Zeichen zurück

    :param str: String in dem gesucht wird
    :param start: Anfangszeichen
    :param end: Endzeichen
    :return: String zwischen den Zeichen
    """

    ps = find_str(str, start)
    if ps is None:
        return None
    else:
        ps += len(start)

    pe = ps + find_str(str[ps:], end)
    if pe is None:
        return None

    return str[ps:pe]



def sort_aphanumeric(data):
    """
    Alphanumerische Sortierung eines Arrays

    :param data: Array das sortiert werden soll
    :return: Sortiertes Array
    """

    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ]
    return sorted(data, key=alphanum_key)



def GetNearest(x, value, pos=0):
    """
    Sucht den nächstgelegenen Wert in einem Array

    :param x: Werte / Array
    :param value: Gesuchter Wert
    :param pos: 0 = Global nächster Wert, positiv = nächster positiver Wert, negativ = nächster negativer Wert
    :return: Position in Array (int)
    """
    x = np.array(x) - value
    if pos < 0:
        try:
            result = np.where(x == np.max(x[np.where(x < 0)]))
        except ValueError:
            return None
        if len(result) != 0:
            return result[0][0]
        else:
            return None
    elif pos > 0:
        try:
            result = np.where(x == np.min(x[np.where(x > 0)]))
        except ValueError:
            return None
        if len(result) != 0:
            return result[0][0]
        else:
            return None
    else:
        return np.argmin(np.abs(x))



def FindZeroCrossings(x):
    """
    Nullstellensuche
    Findet Nullstellen in einem Array. Auch anwendbar wenn die Nullstelle zwischen zwei erfassten Werten liegen sollte.

    :param x: Werte / Array
    :return: Position aller Nullstellen
    """
    return np.array(np.where(np.diff(np.signbit(x)))[0], dtype=int)



def Moving_Std(x, window_size, ddof=1):
    """
    Berechnet die gleitende Standardabweichung eines Arrays

    :param x: Array mit Werten
    :param w: Fenster-Größe
    :param ddof: 1 = Stichprobenstandardabweichung
    :return: Gleitende Standardabweichung (Numpy Array)
    """
    result = np.zeros_like(x, dtype=float)
    for i in range(len(x)):
        start = max(0, i - window_size//2)
        end = min(len(x), i + window_size//2 + 1)
        window = x[start:end]
        result[i] = np.std(window, ddof=ddof)
    return result



def Weighted_Mulitilinear_Regression(x, y, sqrt_w=None, constant_term=False, coeff_signs=0, const_coeff_sign=False):
    if np.ndim(x) == 1:
        x = np.array([x], dtype=float).T
    if np.ndim(y) == 1:
        y = np.array([y], dtype=float).T
    y = y.copy().ravel()

    if sqrt_w is None:
        sqrt_w = np.ones_like(y)
    else:
        sqrt_w = sqrt_w.ravel()

    # --------------------------------------------------------------------------------------------------------------------------------
    # Step 1: Performing the weighted least squares multiple linear regression
    # Falls ein Achsenabschnitt benötigt wird
    if constant_term == True:
        x = np.concatenate((np.ones((x.shape[0], 1)), x), axis = 1)

    # Multiplikation der Gewichtungsfaktoren
    xw = x * sqrt_w[::, None]
    yw = y * sqrt_w

    # symmetric square matrix
    mat_xw = np.dot(np.transpose(xw), xw)

    # Wenn Kollinearitäten vorhanden: verdwende die Moore-Penrose-Pseudoinverse
    collin_check_coeff = np.abs(np.corrcoef(mat_xw, rowvar = False))
    if np.ndim == 1:
        np.fill_diagonal(collin_check_coeff, 0)
    if np.all(collin_check_coeff < 0.995):
        invert_mat_xw = np.linalg.inv(mat_xw)
    else:
        invert_mat_xw = np.linalg.pinv(mat_xw, hermitian = True)

    coeffs = np.dot(invert_mat_xw, np.dot(np.transpose(xw), yw)) # Regressionskoeffizienten

    # Regressionskoeffizienten Nachbehandlung: nur positive oder negative Werte? etc.
    if coeff_signs == 1:
        zero_vect = np.zeros_like(coeffs)
        if constant_term == True and const_coeff_sign == False:
            zero_vect[0] = coeffs[0].copy()
        coeffs = np.maximum(coeffs, zero_vect)
    elif coeff_signs == -1:
        zero_vect = np.zeros_like(coeffs)
        if constant_term == True and const_coeff_sign == False:
            zero_vect[0] = coeffs[0].copy()
        coeffs = np.minimum(coeffs, zero_vect)

    # --------------------------------------------------------------------------------------------------------------------------------
    # Step 2: Calculation of the coefficient of determination (the wR²-value)
    w2 = sqrt_w**2
    yw2 = y * w2
    avg_yw2 = np.sum(yw2) / np.sum(w2)

    tss_w = np.sum(w2 * ((y - avg_yw2) ** 2)) # weighted sum of squared deviations: y original
    y_calc = np.dot(x, coeffs.reshape((-1, 1))).ravel()
    # they are squared and summed after accounting for the weights
    rss_w = np.sum(w2 * ((y - y_calc) ** 2)) # weighted sum of squared deviations: y original - y calc
    wR2 = 1 - (rss_w / tss_w)

    if constant_term == False: # falls kein konstanter Term vorhanden ist
        coeffs = np.concatenate((np.array([0]), coeffs))
    return coeffs, y_calc, wR2, rss_w



def Gauss(x, params, derivs=False): # center, sigma
    x_centered = x-params[0]
    f = 1/np.sqrt(2 * np.pi * params[1]**2) * np.exp(-0.5*(x_centered/params[1])**2)

    if derivs:
        return (f, -x_centered/params[1]**2 * f, 1/params[1]**2 * (1/params[1]**2 * x_centered**2 - 1) * f)
    else:
        return f



def Lorentz(x, params, derivs=False): # center, gamma
    x_centered = x-params[0]
    main_term = (1 / ((params[1] ** 2) + (x_centered ** 2)))

    if derivs:
        return (
            params[1]/np.pi * main_term,
            params[1]/np.pi * ((-1) * (main_term ** 2) * 2 * x_centered),
            params[1]/np.pi * (8 * ((x_centered ** 2) / (((params[1] ** 2) + (x_centered ** 2)) ** 3)) - 2 * (main_term ** 2)),
        )
    else:
        return params[1]/np.pi * main_term



def Voigt(x, params, derivs=False): # center, sigma, gamma
    x_centered = x-params[0]
    wofz = special.wofz((x_centered + 1j * params[2]) / (params[1] * np.sqrt(2)))

    if derivs:
        return (
            np.real(wofz) / (params[1] * np.sqrt(2 * np.pi)),
            - x_centered / params[1] ** 2 * np.real(wofz) / (params[1] * np.sqrt(2 * np.pi)) + params[2] / params[1] ** 2 * np.imag(wofz) / (params[1] * np.sqrt(2 * np.pi)),
            (x_centered ** 2 - params[2] ** 2 - params[1] ** 2) / params[1] ** 4 * np.real(wofz) / (params[1] * np.sqrt(2 * np.pi)) - (2 * x_centered * params[2]) / params[1] ** 4 * np.imag(wofz) / (params[1] * np.sqrt(2 * np.pi)) + params[2] / params[1] ** 4 * 1 / np.pi
        )
    else:
        return np.real(wofz) / (params[1] * np.sqrt(2 * np.pi))



def ExpGauss(x, params, derivs=False):  # center (mu), sigma, tau (1/lambda)
    """
    Berechnet die exponentiell modifizierte Gauss-Verteilung nach dem modernen Ansatz.
    Behebt die Probleme des alten Ansatzes durch Overflow-Errors etc.

    [1] Roland. Delley, Series for the exponentially modified Gaussian peak shape, Anal. Chem. 57 (1985) 388–388. https://doi.org/10.1021/ac00279a094.
    [2] Y. Kalambet, Y. Kozmin, K. Mikhailova, I. Nagaev, P. Tikhonov, Reconstruction of chromatographic peaks using the exponentially modified Gaussian function, Journal of Chemometrics 25 (2011) 352–356. https://doi.org/10.1002/cem.1343.
    [3] Ableitungsrechner: https://www.ableitungsrechner.net/ (Stand 30.09.2024)

    :param x: Numpy array: x-Werte
    :param params: Numpy array: center, sigma, tau
    :param derivs: Bool, True: Ableitungen werden berechnet und ausgegeben, False: Nur die Verteilung wird berechnet und ausgegeben.
    :return: Numpy array: ExpGauss ODER Matrix mit [ExpGauss, Ableitung 1, Ableitung 2]
    """
    m = params[0] # mu bzw center
    s = params[1] # sigma
    t = params[2] # tau bzw 1/lambda

    z = 1/np.sqrt(2) * ((m-x)/s + s/t)
    h = 1/(np.sqrt(2*np.pi)*s)

    f = np.zeros_like(x, dtype=float)
    df = np.zeros_like(x, dtype=float)
    d2f = np.zeros_like(x, dtype=float)

    ind = np.argwhere(z < 0).T[0]
    f[ind] = h * s/t * np.sqrt(np.pi/2) * np.exp((m-x[ind])/t + s**2/(2*t**2)) * special.erfc(z[ind])
    df[ind] = 1/t * (h * np.exp(((m-x[ind])/t + s**2/(2*t**2))-z[ind]**2) - f[ind])
    d2f[ind] = 1/t * (h/s**2 * np.exp(((m-x[ind])/t + s**2/(2*t**2))-z[ind]**2)*(m-x[ind]) - df[ind])

    ind = np.intersect1d(np.argwhere(z >= 0).T[0], np.argwhere(z <= 6.71e7).T[0])
    f[ind] = h * s/t * np.sqrt(np.pi/2) * np.exp(-(m-x[ind])**2/(2*s**2)) * special.erfcx(z[ind])
    df[ind] = 1/t * (h * np.exp(-(m-x[ind])**2/(2*s**2)) - f[ind])
    d2f[ind] = 1/t * (h/s**2 * np.exp(-(m-x[ind])**2/(2*s**2)) * (m-x[ind]) - df[ind])

    ind = np.argwhere(z > 6.71e7).T[0]
    f[ind] = h * np.exp(-(m-x[ind])**2/(2*s**2)) / (1 + ((m-x[ind])*t)/s**2)
    df[ind] = f[ind] * 1/s**2 * (m - x[ind] + t/(1 + ((m-x[ind])*t)/s**2))
    d2f[ind] = 1/s**2 * ((m - x[ind] + t/(1 + ((m-x[ind])*t)/s**2)) * df[ind] + (t**2 / (s**2 * (1 + ((m-x[ind])*t)/s**2)**2) - 1) * f[ind])

    if derivs:
        return (
            f,
            df,
            d2f
        )
    else:
        return f



Shapes = {
    "gaussian": [Gauss, 2, [0, 1e-2], [1e4, 1e4]],
    "lorentz":  [Lorentz, 2, [0, 1e-2], [1e4, 1e4]],
    "voigt": [Voigt, 3, [0, 1e-2, 1e-2], [1e4, 1e4, 1e4]],
    "exp_gaussian": [ExpGauss, 3, [0, 1e-2, 1e-10], [1e4, 1e4, 1e4]],
}



class FitOptimizer:
    def __init__(self, Y, SavGolWindow, PeakShapes, X=None, w=None, d0w=None, d1w=None, d2w=None):
        # Peaks und Bounds
        self.PeakShapes = PeakShapes
        self._bounds_min = []
        self._bounds_max = []
        for i in range(len(PeakShapes)):
            self._bounds_min.extend(Shapes[PeakShapes[i]][2])
            self._bounds_max.extend(np.ones(Shapes[PeakShapes[i]][1])*len(Y))

        # Signal
        if X is not None:
            self.X = X
        else:
            self.X = np.arange(0, len(Y), 1)
        d1Y = signal.savgol_filter(Y, window_length=SavGolWindow, polyorder=3, deriv=1, delta=np.mean(np.gradient(self.X)))
        d2Y = signal.savgol_filter(Y, window_length=SavGolWindow, polyorder=3, deriv=2, delta=np.mean(np.gradient(self.X)))
        self.Y = np.ravel([Y, d1Y, d2Y])

        # Gewichtungen
        if w is None:
            if d0w is None and d1w is None and d2w is None:
                self.w = np.ones(len(Y)*3)
            else:
                if d0w is None:
                    d0w = np.zeros_like(Y)
                if d1w is None:
                    d1w = np.zeros_like(Y)
                if d2w is None:
                    d2w = np.zeros_like(Y)
                self.w = np.ravel([d0w, d1w, d2w])
        else:
            if len(w) == len(Y)*3:
                self.w = w
            else:
                self.w = np.ones(len(Y) * 3)

    def fitness(self, params):
        y_calc = []
        iParams = 0
        for i in range(len(self.PeakShapes)):
            y_p, dy_p, d2y_p = Shapes[self.PeakShapes[i]][0](self.X, params=params[iParams:iParams+Shapes[self.PeakShapes[i]][1]], derivs=True)
            y_calc.append(np.ravel([y_p, dy_p, d2y_p]))
            iParams += Shapes[self.PeakShapes[i]][1]
        y_calc = np.array(y_calc, dtype=float)

        coeffs, y_calc, wR2, rss_w = Weighted_Mulitilinear_Regression(x=y_calc.T, y=self.Y, sqrt_w=self.w, constant_term=False, coeff_signs=1, const_coeff_sign=False)
        # penalty_term = bound_violation_penalty(params, Bounds)
        return [rss_w]

    def get_bounds(self):
        return (self.bounds_min, self.bounds_max)

    def get_nobj(self):
        return 1

    def CalcResults(self, champion_x):
        y_calc = []
        iParams = 0
        for i in range(len(self.PeakShapes)):
            y_p, dy_p, d2y_p = Shapes[self.PeakShapes[i]][0](self.X, params=champion_x[iParams:iParams+Shapes[self.PeakShapes[i]][1]], derivs=True)
            y_calc.append(np.ravel([y_p, dy_p, d2y_p]))
            iParams += Shapes[self.PeakShapes[i]][1]
        y_calc = np.array(y_calc, dtype=float)

        coeffs, y_calc, wR2, rss_w = Weighted_Mulitilinear_Regression(x=y_calc.T, y=self.Y, sqrt_w=self.w, constant_term=False, coeff_signs=0, const_coeff_sign=False)
        return y_calc, champion_x, coeffs[1:]

    @property
    def bounds_max(self):
        return self._bounds_max

    @bounds_max.setter
    def bounds_max(self, value):
        if np.any(value) is not float:
            for i in range(len(value)):
                value[i] = float(value[i])
        self._bounds_max = value

    @property
    def bounds_min(self):
        return self._bounds_min

    @bounds_min.setter
    def bounds_min(self, value):
        if np.any(value) is not float:
            for i in range(len(value)):
                value[i] = float(value[i])
        self._bounds_min = value



scientific_colors = {
    # https://www.simplifiedsciencepublishing.com/resources/best-color-palettes-for-scientific-figures-and-data-visualizations
    "DarkBlue": "#003a7d",
    "MedBlue": "#008dff",
    "Pink": "#ff73b6",
    "Purple": "#c701ff",
    "Green": "#4ecb8d",
    "Orange": "#ff9d3a",
    "Yellow": "#f9e858",
    "Red": "#d83034",
    "DarkRed": "#9d2c00",
    "Grey": "#7f7f7f"
}



colormaps = {
    "vRate": matplotlib.cm.viridis,
    "pH": matplotlib.cm.jet_r,
    "Voltage": matplotlib.cm.plasma,
    "Cycle": cmcrameri.cm.lipari,
}



def set_scientific_colors_cycler():
    plt.rcParams.update({"axes.prop_cycle": plt.cycler("color", scientific_colors.values())})
