---
name: ketcher_chemistry_connector
description: Interactive 2D molecule sketcher (Ketcher) — the agent-facing form. Renders a molecule (or a blank start) into a self-contained HTML sketch-pad artifact with a 2D depiction plus the editable MOL block and identifiers. Fully local via RDKit, no network, no auth.
version: 1.0.0
type: worker
permission_mode: read_only
featured: true
connection:
  transport: stdio
  command: python
  args:
    - server.py
actions:
  - open_sketcher
---

# Ketcher Chemistry

The agent-facing counterpart of **Ketcher**, EPAM's interactive 2D molecule sketcher.
A human uses Ketcher by drawing on a canvas; an autonomous agent has no canvas, and a
sandboxed artifact cannot load Ketcher's external JS/WASM bundle. So this connector
reproduces the sketcher's **output** locally via **RDKit** (no network, no auth): it
lays a molecule out in 2D and emits a self-contained HTML "sketch pad" artifact.

## Tools

- `open_sketcher` — open a 2D sketch pad and return it as a self-contained HTML artifact
  (inline SVG depiction + the editable MOL block, which is Ketcher's native import/export
  format, + canonical SMILES / formula / MW / InChIKey).
  Args: `structure` (SMILES/MOL/InChI, optional — empty = blank pad), `from_format`,
  `title`, `width`, `height`.

## Typical workflow

1. `open_sketcher(structure="CC(=O)Oc1ccccc1C(=O)O")` to render a molecule as an editable
   sketch-pad artifact; the returned HTML can be saved as a construct/artifact.
2. Copy the MOL block from the artifact into a full Ketcher instance for further hand-editing,
   or feed the canonical SMILES to the `chemistry` / `molecule_toolkit` connectors.

## Notes

- Fully local (RDKit); no network dependency. The returned HTML is self-contained (inline
  SVG + CSS, theme-aware) with no external assets, so it renders as an artifact directly.
- A blank canvas is returned when no `structure` is supplied. For programmatic molecule
  operations (format conversion, descriptors, scaffolds, reactions) see `molecule_toolkit`.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
