class Curve(object):
    id = None
    name = None                     # z.B. Dateiname
    active = None                   # Daten zur Verarbeitung aktiv?
    zyklus_verworfen = False        # von der Zyklus-Auswahl (DelCyclus) verworfen?
    electrode = None                # Leer lassen?
    channel = None                  # Betrifft eher nur PalmSens
    cycle = None                    # Zyklus
    vRate = None                    # Spannungsvorschub
    raw_data = None                 # Rohdaten aus der Datei
    working_data = None             # Verarbeitete Daten, z.B. geglättet: {t, E, I, E_rev, dt, dE}
    calculated_data = None          # Berechnete Kurven mit Kurvenfit: {t, E, I}
    peak_results = None             # Peakdaten aus dem Kurvenfit: {forward, Ep, σ, τ, Ip, Ip_F, Ip_C, Qp}
    feature_1 = None                # Feature 1-5: Andere Daten, wie pH-Wert, Leitwert, etc
    feature_2 = None
    feature_3 = None
    feature_4 = None
    feature_5 = None