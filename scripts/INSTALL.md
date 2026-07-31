# Preface

> 🌐 中文版请见 [INSTALL_zh.md](INSTALL_zh.md)

## Quick start

One command sets up everything needed to run an agent:

```bash
bash scripts/install.sh
```

It creates a conda environment (`agentos`, Python 3.12), installs the package
and its dependencies, installs Node.js, writes an `.env` template, and verifies
the result. Re-running it is safe — an existing environment is reused.

```bash
bash scripts/install.sh --extras browser   # + playwright & chromium
bash scripts/install.sh --extras sandbox   # + build the container-sandbox images (needs Docker)
bash scripts/install.sh --uv               # use uv instead of conda
bash scripts/install.sh --help             # all options
```

Then fill in your API keys in `.env` and run:

```bash
conda activate agentos
python examples/run_meta_agent.py --task "..."
```

The rest of this document covers the pieces individually, and Vault for teams
that want centrally managed secrets.

## Where secrets come from

Keys are read from **Vault** when it is configured and reachable, and from
**`.env`** otherwise (see `autogenesis/utils/hvac_utils.py`). Vault is
therefore optional: it keeps keys out of plaintext files, which matters for
shared or production setups, but a local checkout works with `.env` alone.

For `.env`-only usage, skip to section 2 and set the provider variables
directly:

```bash
ANTHROPIC_API_BASE='...'      # a trailing /v1 is accepted, and stripped where needed
ANTHROPIC_API_KEY='...'
OPENROUTER_API_BASE='...'
OPENROUTER_API_KEY='...'
GOOGLE_API_BASE='https://generativelanguage.googleapis.com'
GOOGLE_API_KEY='...'
```

# 1. Install the API Key Manager (Vault) — optional

## Step 1:

```bash
1. If already installed, just start the service
vault server -config=/mnt/agent-framework/<your user path>/myapp/vault/config/vault.hcl > /mnt/agent-framework/<your user path>/myapp/vault/vault.log 2>&1 &

2. If not installed yet, use the install script
cd scripts
chmod +x install_vault.sh
./install_vault.sh /mnt/agent-framework/<your user path>/myapp # starts the service locally at http://127.0.0.1:8200 by default. When VSCode connects to the server it forwards the port automatically, so just click the popup in VSCode to open http://127.0.0.1:8200 and reach the frontend
```

## Step 2: Set the number of unseal key shares to 1
Set **Key shares** to **1** and **Key threshold** to **1**, then click **Initialize**.
![alt text](../docs/assets/step2.png)

## Step 3:
You will see two keys — one **Initial root token** and one login/unseal verification key **unseal token key1**. Be sure to record them!!! You can also save them locally (click **Download Keys** to download the JSON file).

It is recommended to put the **Initial root token** into the `.env` at the project root:
```bash
VAULT_ADDR='http://127.0.0.1:8200'
VAULT_TOKEN="<initial root token>"
UNSEAL_TOKEN='<unseal token key1>'
SECRET_ENGINE_PATH='cubbyhole/env'
```

![alt text](../docs/assets/step3.png)

Then click **Continue to Unseal**.

## Step 4:
The key to enter is **unseal token key1**.
![alt text](../docs/assets/step4.png)

## Step 5:
The key to enter is the **Initial root token**.
![alt text](../docs/assets/step5.png)

## Step 6:
Login succeeds. You will see a secret engine named **cubbyhole/** — click **View**.
![alt text](../docs/assets/step6.png)

## Step 7:
Click **Create secret** and set path to **env**, so it matches **SECRET_ENGINE_PATH='cubbyhole/env'** in `.env`.
![alt text](../docs/assets/step7.png)

## Step 8:
Fill in **key: value** pairs, then click **Save** — configuration is done. You may also paste a correctly formatted JSON blob directly, as below.
![alt text](../docs/assets/step8.png)

The keys to fill in should include:
```bash
{
  "AWS_CLAUDE_API_BASE": "internal aws-claude base url (required)",
  "AWS_CLAUDE_API_KEY": "internal aws-claude api key (required)",
  "FIRECRAWL_API_BASE": "official Firecrawl base url, e.g. https://api.firecrawl.dev/v2 (required)",
  "FIRECRAWL_API_KEY": "official Firecrawl api key (required)",
  "INT_OPENROUTER_API_BASE": "internal openrouter base url (required)",
  "INT_OPENROUTER_API_KEY": "internal openrouter api key (required)",
  "JINA_BASE_URL": "internal jina base url (required)",
  "JINA_API_KEY": "internal jina api key (required)",
  "SERPER_BASE_URL": "internal serper base url (required)",
  "SERPER_API_KEY": "internal serper api key (required)",
  "OPENROUTER_API_BASE": "official openrouter base url, e.g. https://openrouter.ai/api/v1 (optional)",
  "OPENROUTER_API_KEY": "official openrouter api key (optional)"
}
```


## Step 9: Verify the configuration works
```
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='your Initial root token'
vault kv get -field=OPENROUTER_API_KEY cubbyhole/env

The output is the content of your OPENROUTER_API_KEY:
abcabc...
```

# 2. Set up the Python environment

Python 3.12 is recommended (3.11+ required). All dependencies are declared in
`pyproject.toml` (there is no `requirements.txt`).

## Step 1 — Option A: the install script (recommended)

```bash
bash scripts/install.sh                 # conda env "agentos"
bash scripts/install.sh -n myenv        # a different env name
bash scripts/install.sh --extras all    # every optional extra
```

This performs Options B and C below, plus Node.js and the verification pass.
Skip to Step 2 if you use it.

## Step 1 — Option B: conda + pip
```bash
conda create -n agentos python=3.12
conda activate agentos
pip install -e .              # core deps + the autogenesis package (adds the `autogenesis` CLI)

# optional extras (browser automation / chemistry / sandboxes):
pip install -e ".[browser]"   # or ".[chem]", ".[sandbox]", ".[all]"

# playwright + browser-use need a one-time browser download:
python -m playwright install chromium
```

## Step 1 — Option C: uv (faster, reproducible)
[uv](https://docs.astral.sh/uv/) is a fast pip/venv replacement; `uv sync` installs from
`pyproject.toml` + the committed `uv.lock` for a reproducible environment.
```bash
# install uv (once)
curl -LsSf https://astral.sh/uv/install.sh | sh

# create .venv and install core deps + the package (uses uv.lock)
uv sync
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# optional extras:
uv sync --extra browser              # or --extra chem / sandbox / all

# playwright + browser-use need a one-time browser download:
python -m playwright install chromium
```

> Note: `pip install -e .` / `uv pip install -e .` installs this repo as the importable
> `autogenesis` package, so other projects can `import autogenesis` and you get the
> `autogenesis` console command. Run data goes to the current directory (or `$AUTOGENESIS_HOME`),
> never into the installed package.

## Step 2: configure `.env`

Using Vault — point the framework at it:
```bash
VAULT_ADDR='http://127.0.0.1:8200'
VAULT_TOKEN="<initial root token>"
UNSEAL_TOKEN='<unseal token key1>'
SECRET_ENGINE_PATH='cubbyhole/env'
```

Not using Vault — set the provider credentials directly (see the Preface). When
Vault is unset or unreachable, these are used automatically; nothing else needs
to change.

# 3. Node.js (only for the web UI)

The browser UI in [`frontend/`](../frontend/) is a Vite app and needs Node.js:

```bash
conda install -n agentos -c conda-forge nodejs   # or use nvm / your package manager
cd frontend && npm install && npm run dev
```

`scripts/install.sh` installs Node.js for you. Agent runs — CLI, TUI, and the
`examples/run_*.py` scripts — do not need it: trace events are written to
`<log_root>/trace/*.jsonl` and streamed to the frontend by the Gateway.

# 4. Container sandboxes & images

Agents run untrusted work (browser sessions, code execution, benchmark
cleanrooms) in isolated Docker containers. Building them is part of the
one-shot install when you pass the sandbox extra:

```bash
bash scripts/install.sh --extras sandbox   # builds the peer images below
bash scripts/install.sh --extras all       # sandbox + browser + everything
```

Step 5 of the installer checks the Docker daemon and, when reachable, builds:

| Image | Built from | Used by |
| --- | --- | --- |
| `autogenesis/chrome-vnc:latest` | `docker/chrome-vnc/` | `browser_environment`, `webapp_testing_skill` — headful Chrome on a virtual display with a **noVNC live view** |
| `autogenesis/code-interpreter:latest` | `docker/code-interpreter/` | the sandboxed code-interpreter peer |

Builds are idempotent — an image that already exists is not rebuilt. The
`opensandbox/*` base layers are pulled automatically as each Dockerfile's
`FROM`, and OpenSandbox's own helper images (`execd`, `egress`) are pulled by
the sandbox server on first use, so nothing else needs provisioning.

To (re)build a single image by hand:

```bash
docker build -t autogenesis/chrome-vnc:latest       docker/chrome-vnc/
docker build -t autogenesis/code-interpreter:latest docker/code-interpreter/
```

> The **Model X launcher** image (`autogenesis/base`) is a separate concern —
> it is the base container the whole framework runs *inside*, not a peer
> sandbox. Build and use it via `docker/base/` and `scripts/run-in-sandbox.sh`
> (see `docker/base/README.md`).

# 5. Misc

```bash
1. Test a model call
curl -X POST "https://xxx/v1/responses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer xxx" \
  -d '{
    "model": "gpt-5.4-pro",
    "input": "hello",
    "max_output_tokens": 2048
  }'

curl -X POST "https://xxx/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer xxx" \
  -d '{
  "model": "openai/gpt-5.4",
  "messages": [
    {
      "role": "user",
      "content": "Hello"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 2048
}'
```
