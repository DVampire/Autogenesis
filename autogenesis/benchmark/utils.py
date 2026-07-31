import os

from autogenesis.logger import logger
from autogenesis.utils import assemble_workspace_path


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = str(text).strip().replace(",", "").replace("$", "")
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return text


def _dir_has_content(path: str) -> bool:
    """True if `path` is a non-empty directory (ignoring caches/hidden cruft)."""
    if not os.path.isdir(path):
        return False
    for entry in os.listdir(path):
        if entry in (".cache", ".huggingface", ".gitattributes"):
            continue
        return True
    return False


def ensure_dataset(name: str, hf_repo_id: str, repo_type: str = "dataset", revision: str = None) -> str:
    """Return a local dataset directory under `datasets/<name>`, downloading from
    HuggingFace on first use.

    Each benchmark reads its data from `datasets/<name>/`. If that directory is
    missing or empty, the corresponding HuggingFace repo (`hf_repo_id`) is
    snapshot-downloaded into it. Set the `HF_ENDPOINT` env var (e.g. a mirror)
    to control where files are fetched from.

    Args:
        name: Local sub-directory under `datasets/` (e.g. "hle", "gsm8k").
        hf_repo_id: HuggingFace repo id to download from when data is absent.
        repo_type: HuggingFace repo type ("dataset" by default).
        revision: Optional git revision / tag / branch to pin.

    Returns:
        Absolute path to the local dataset directory.
    """
    local_dir = assemble_workspace_path(os.path.join("datasets", name))

    if _dir_has_content(local_dir):
        return local_dir

    if not hf_repo_id:
        raise FileNotFoundError(
            f"Dataset '{name}' not found at {local_dir} and no `hf_repo_id` configured to download it."
        )

    # Load .env so HF_TOKEN (e.g. for gated datasets like GPQA) is available.
    from dotenv import load_dotenv
    load_dotenv(assemble_workspace_path(".env"))
    hf_token = os.environ.get("HF_TOKEN") or None

    logger.info(f"| 📥 Dataset '{name}' not found locally; downloading '{hf_repo_id}' from HuggingFace into {local_dir} ...")
    from huggingface_hub import snapshot_download

    os.makedirs(local_dir, exist_ok=True)
    snapshot_download(
        repo_id=hf_repo_id,
        repo_type=repo_type,
        revision=revision,
        local_dir=local_dir,
        token=hf_token,
    )
    logger.info(f"| ✅ Dataset '{name}' ready at {local_dir}")
    return local_dir
