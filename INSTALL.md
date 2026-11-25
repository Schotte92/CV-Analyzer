# Installation

Detailed setup instructions for Linux and Windows. For a quick overview see
the [README](README.md).

CV-Analyzer needs **Python 3.10 or newer**. Recommended is **3.11 – 3.14**:
those are the versions for which the peak-fitting library
[pygmo](https://esa.github.io/pygmo2/) ships prebuilt packages. On Python 3.10
the peak fitting falls back to the much older pygmo 2.19.0, and on Windows
pygmo cannot be installed with pip at all — see the Windows section.

Everything except the peak fitting works without pygmo.

Tested on Python 3.12 (Windows and Linux) and Python 3.14 (Linux).

---

## Linux

### 1. System packages

Tkinter is not part of a default Python installation on most distributions:

```
# Debian / Ubuntu / Mint
sudo apt install python3-tk python3-venv

# Fedora
sudo dnf install python3-tkinter

# Arch / Manjaro
sudo pacman -S tk
```

### 2. Get the code

```
git clone https://github.com/Schotte92/CV-Analyzer.git
cd CV-Analyzer
```

### 3. Create a virtual environment

```
python3 -m venv .venv
source .venv/bin/activate
```

From here on, `python` and `pip` refer to the environment. Check with
`which python` — it must point into `.venv`.

### 4. Install the dependencies

```
pip install -r requirements.txt
```

### 5. Install CV-Analyzer

```
pip install -e .
```

This adds a `cv-analyzer` command that works from any directory. Alternatively
`python -m cv_analyzer` runs it from inside the repository folder.

pygmo is declared as a Linux-only dependency, so this step installs the peak
fitter as well. It needs Python 3.11 or newer for a prebuilt package — if pip
starts compiling Boost, abort and use a newer Python.

### 6. Start it

```
cv-analyzer
```

The window needs a graphical session. Over SSH, X forwarding has to be
enabled; a pure terminal session cannot display it.

---

## Windows

The peak fitting needs pygmo, and pygmo has **no pip packages for Windows** —
neither wheels nor a source distribution that builds. The only route is
[conda-forge](https://conda-forge.org), which is why this section uses conda.

### 1. Install Miniforge

Miniforge is a minimal conda installer that uses conda-forge as its default
channel.

Download: **<https://conda-forge.org/download/>** — take the
`Windows x86_64` installer and run it.

Or via winget in a terminal:

```
winget install --id CondaForge.Miniforge3 -e
```

Accept the defaults in the installer. You do not need to add conda to the
PATH — Miniforge installs its own start menu entry.

### 2. Open the right terminal

Start **Miniforge Prompt** from the start menu.

Do not use PowerShell or cmd unless you set them up for conda first: conda
writes an activation block into the shell profile, and Windows blocks
PowerShell scripts by default, so the profile fails to load and `conda` stays
unknown. If you prefer PowerShell, run this once (no admin rights needed):

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then close and reopen PowerShell. The prompt should show `(base)`.

### 3. Create an environment

```
conda create -n cv python=3.12
conda activate cv
```

`cv` is just a name, pick whatever you like. Check that you are in the right
place:

```
where python
```

The first line must point to `...\miniforge3\envs\cv\python.exe`.

### 4. Install pygmo

```
conda install -c conda-forge pygmo
```

If this hangs or fails on a company or university network, it is usually a
proxy — configure it with `conda config --set proxy_servers.http ...` or use
the download route described at the end of this file.

### 5. Get the code and install

```
cd %USERPROFILE%\Desktop
git clone https://github.com/Schotte92/CV-Analyzer.git
cd CV-Analyzer
pip install -r requirements.txt
pip install -e .
```

Note that `requirements.txt` deliberately does **not** contain pygmo — it
would break the installation on Windows. pygmo comes from conda in step 4.

If you do not have git, download the repository as a ZIP from GitHub and
unpack it instead.

### 6. Start it

```
cv-analyzer
```

Or double-click `CV_Analyzer.pyw` in the repository folder — same program,
without a console window behind it.

---

## Checking the installation

Start the program and import a file from `Testdaten/`. Then select a peak and
press *Fit starten*. If pygmo is missing, a dialog says so and tells you which
command to run — the rest of the program still works.

From a terminal you can also verify the imports:

```
python -c "import numpy, scipy, pandas, matplotlib, pandastable; print('ok')"
python -c "import pygmo; print('pygmo', pygmo.__version__)"
```

The second one fails if the peak fitting is not available. That is expected on
Windows until step 4 is done.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'tkinter'` (Linux)**
Tkinter is missing — see step 1 of the Linux section.

**`ModuleNotFoundError: No module named 'pygmo'`**
The peak fitting is not installed. Linux: `pip install pygmo`. Windows:
`conda install -c conda-forge pygmo`.

**`RuntimeError: x must be a sequence`**
Only appears in versions before 2.0 — matplotlib 3.10 no longer accepts single
numbers where it expects a list. Update to the current version.

**`pip` installs into the wrong Python**
The environment is not active. Linux: `source .venv/bin/activate`. Windows:
`conda activate cv`. Verify with `where python` (Windows) or `which python`
(Linux).

**conda commands are unknown in PowerShell**
See step 2 — either use the Miniforge Prompt or change the execution policy.

---

## Removing the installation

Linux:

```
rm -rf .venv          # from inside the repository folder
```

Windows:

```
conda deactivate
conda remove -n cv --all
```

The repository folder itself can simply be deleted.
