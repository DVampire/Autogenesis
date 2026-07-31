# Autogenesis project sandbox image (Model X): the container the whole agent runs
# in — the framework, every agent, and all tool execution (bash / file edits / git /
# experiment code). The host only launches it (scripts/run-in-sandbox.sh); the repo
# is bind-mounted in so source is live and outputs land back on the host. Service
# peers (browser / deploy) are spawned as sibling containers via the mounted Docker
# socket, so this image does NOT need opensandbox's execd/kernel runtime — it is a
# plain, general dev environment.
#
# conda base (parity with the host's agentos env) with the languages an agent may
# run locally: Python, Node/JS, R. Plus git, a CPU data-science stack, and the
# autogenesis framework itself.
#
# Build FROM THE REPO ROOT (context must be the repo, this installs the framework):
#   docker build -f docker/base/Dockerfile -t autogenesis/base:latest .
#
# Smoke-test:
#   docker run --rm autogenesis/base:latest python -c "import autogenesis, lightgbm; print('ok')"
#   docker run --rm autogenesis/base:latest bash -lc "node -v && Rscript -e 'cat(R.version.string)'"

FROM continuumio/miniconda3:latest

# System tools: git (git_tool), build-essential (native wheels), curl/ca-certs.
# libgl1 + libglib2.0-0: opencv (pulled in by camelot/markitdown) loads libGL.so.1
# and libgthread at import; the slim conda base doesn't ship them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Languages the agent may run locally inside the sandbox: Node/JS and R (Python is
# the conda base). Installed from conda-forge into the base env so they're on PATH.
RUN conda install -y -c conda-forge nodejs r-base \
    && conda clean -afy

# CPU data-science stack for experiments (numpy/pandas/scikit-learn/etc. also come
# in as framework deps; lightgbm/xgboost/matplotlib/seaborn are listed explicitly).
RUN pip install --no-cache-dir \
        numpy pandas scipy scikit-learn matplotlib seaborn lightgbm xgboost

# Jupyter: the kernel behind code_interpreter_tool AND the server that owns it.
#
# One server per project, started lazily (see autogenesis/kernel). Everything
# that runs code goes through it — the agent's code_interpreter_tool, the
# Science view's REPL, and JupyterLab — so all three share ONE kernel and one
# set of variables. It used to be a raw kernel here plus a second, unrelated
# kernel in a "science" peer container, which meant a variable the agent defined
# was not defined in the notebook you were reading.
#
# One kernelspec per language this image can actually run: Python, Bash, R and
# JS/TS (node is here). Go and Java have no toolchain in this image, so they get
# no kernelspec rather than one that fails at first use — code_interpreter passes
# an unknown language straight through, so adding a toolchain here is all it
# takes to reach it.
RUN pip install --no-cache-dir jupyter_client ipykernel ipywidgets matplotlib-inline bash_kernel \
        jupyterlab notebook jupyter-server-proxy jupyterlab-git jupytext nbconvert nbformat \
    && python -m ipykernel install --name python3 --display-name "Python 3" --prefix /opt/conda \
    && python -m bash_kernel.install --prefix /opt/conda \
    && npm install -g tslab && tslab install --prefix /opt/conda \
    && R -e "install.packages('IRkernel', repos='https://cloud.r-project.org'); IRkernel::installspec(prefix='/opt/conda')"

# GPU deep-learning: torch built for CUDA 12.6. The default PyPI wheel targets
# CUDA 13, which is too new for the host driver (575 / CUDA 12.9) and would report
# cuda_available=False; the cu126 wheel matches. Only the host driver is required —
# the CUDA userspace ships inside the wheel. The launcher passes --gpus.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu126

# The scientific workstation stack. This used to be a separate "science" image
# and a peer container; it is here because the container bought isolation that
# was already thin — bash_tool runs here as root — while costing a second kernel
# the agent's variables did not reach, a routing decision for every execution,
# and a reaper that could kill a training run. Merged, it is +2.8GB on a 21.6GB
# image and all of those problems stop existing.
#
# LaTeX + pandoc: "write the paper" has to end in a PDF. nbconvert shells out to
# xelatex. texlive-xetex rather than texlive-full — the full distribution is
# ~5GB, most of it fonts and languages nothing here reaches for.
RUN apt-get update && apt-get install -y --no-install-recommends \
        pandoc \
        texlive-xetex \
        texlive-fonts-recommended \
        texlive-latex-recommended \
        texlive-plain-generic \
        graphviz \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Deep learning around the torch installed above. Same index so the vision/audio
# wheels match that CUDA build instead of pulling a second, conflicting torch.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu126 \
        torchvision torchaudio

RUN pip install --no-cache-dir \
        transformers accelerate peft trl safetensors sentencepiece \
        tokenizers evaluate timm einops

# Experiment tracking and tuning — what turns a script into an experiment.
RUN pip install --no-cache-dir \
        tensorboard wandb mlflow optuna

# Numerics, data and plotting beyond the CPU stack above.
RUN pip install --no-cache-dir \
        statsmodels sympy networkx numba \
        polars pyarrow duckdb h5py zarr xarray netCDF4 \
        plotly altair bokeh holoviews datashader \
        scikit-image opencv-python-headless pillow \
        tqdm rich pyyaml openpyxl xlsxwriter

# Paper-writing helpers: bibliography handling, unit-aware numbers, tables.
RUN pip install --no-cache-dir \
        pybtex bibtexparser pint uncertainties tabulate

# The autogenesis framework + sandbox extra (opensandbox / opensandbox-server /
# docker) so the in-container agent can spawn peer containers through the mounted
# Docker socket. Editable install off a COPY bakes deps into the image; at runtime
# the launcher bind-mounts the host repo over /Autogenesis so source edits are picked up live.
COPY . /Autogenesis
RUN pip install --no-cache-dir -e "/Autogenesis[sandbox]"

# The host repo is bind-mounted at runtime (different owner uid); mark it safe so
# git_tool works. WORKDIR is the mounted project.
RUN git config --global --add safe.directory /Autogenesis
WORKDIR /Autogenesis

# Entrypoint runs the command as root (pip install + Docker socket access) and, on
# exit, chowns the run's outputs back to the mounted project's host owner so they are
# not left root-owned on the host.
COPY docker/base/entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint"]
