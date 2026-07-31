---
name: environment-setup
description: Use when Python environment setup is needed for data visualization or conda installation is required
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Environment setup

End-to-end terminal setup of a Python plotting environment.

## When to use

- The user asks to install Miniconda
- The user asks to create a virtual environment
- The user asks to "plot this in Python" but the environment is not ready
- A plotting script fails with an environment-related error

## Checklist

- [ ] Identify the system (macOS / Linux / Windows)
- [ ] Install or repair Miniconda
- [ ] Initialize conda
- [ ] Create the `research` environment
- [ ] Install the plotting dependencies
- [ ] Run the environment self-check
- [ ] Update `plan/progress.md`

## 1. Identify the system

### macOS / Linux

```bash
uname -s
uname -m
echo "$SHELL"
```

### Windows PowerShell

```powershell
$PSVersionTable.PSVersion
$env:OS
```

## 2. Installing Miniconda

### macOS, fully automated

```bash
set -euo pipefail

# 1) pick the installer
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
else
  URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh"
fi

# 2) download and install silently
INSTALLER="$HOME/Downloads/miniconda.sh"
curl -fsSL "$URL" -o "$INSTALLER"
bash "$INSTALLER" -b -p "$HOME/miniconda3"

# 3) make it usable in the current shell
export PATH="$HOME/miniconda3/bin:$PATH"

# 4) initialize the shell
"$HOME/miniconda3/bin/conda" init "$(basename "$SHELL")"

# 5) verify
conda --version
```

### Windows, fully automated (PowerShell)

```powershell
$ErrorActionPreference = "Stop"

# 1) download
$installer = Join-Path $env:TEMP "Miniconda3-latest-Windows-x86_64.exe"
Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile $installer

# 2) silent install
$target = "$env:USERPROFILE\miniconda3"
Start-Process -FilePath $installer -ArgumentList "/InstallationType=JustMe","/RegisterPython=0","/S","/D=$target" -Wait

# 3) initialize powershell
& "$target\Scripts\conda.exe" init powershell

# 4) verify
$env:Path = "$target;$target\Scripts;$target\condabin;" + $env:Path
conda --version
```

## 3. Creating the research environment

**Default environment name**: `research`

### Create and activate

```bash
conda create -n research python=3.11 -y
conda activate research
python -m pip install --upgrade pip
```

## 4. Installing plotting dependencies

```bash
pip install numpy pandas scipy matplotlib seaborn scikit-learn statsmodels jupyter ipykernel openpyxl
python -m ipykernel install --user --name research --display-name "Python (research)"
```

Optional:

```bash
pip install plotly pingouin
```

## 5. Environment self-check

```bash
python - <<'PY'
import sys
import numpy, pandas, matplotlib, seaborn, sklearn, statsmodels
print('Python:', sys.version.split()[0])
print('numpy:', numpy.__version__)
print('pandas:', pandas.__version__)
print('matplotlib:', matplotlib.__version__)
print('seaborn:', seaborn.__version__)
print('sklearn:', sklearn.__version__)
print('statsmodels:', statsmodels.__version__)
print('ENV CHECK: OK')
PY
```

## 6. Pre-flight check before a plotting task

Before running any plotting task, confirm at minimum:
1. The `research` environment is activated
2. `matplotlib` and `seaborn` import cleanly
3. The output directory exists (e.g. `figures/`)

## 7. Common problems and fixes

### `conda: command not found`

macOS / Linux:
```bash
export PATH="$HOME/miniconda3/bin:$PATH"
conda init "$(basename "$SHELL")"
```

Windows PowerShell:
```powershell
$env:Path = "$env:USERPROFILE\miniconda3;$env:USERPROFILE\miniconda3\Scripts;" + $env:Path
```

### Slow downloads or timeouts

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### Package conflicts

```bash
conda create -n research_clean python=3.11 -y
conda activate research_clean
pip install -r requirements.txt
```

## 8. Execution constraints

<HARD-GATE>
1. When the user mentions "install the environment" or a plotting error, run this skill first
2. Identify the system before issuing commands; never mix commands across platforms
3. After finishing, write the outcome back to `plan/progress.md`
</HARD-GATE>
