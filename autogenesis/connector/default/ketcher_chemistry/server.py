#!/usr/bin/env python3
"""Ketcher Chemistry MCP server — the agent-facing form of an interactive 2D molecule
sketcher (EPAM Ketcher). Fully LOCAL via RDKit, no network, no auth.

A human uses Ketcher by drawing on a canvas; an autonomous agent has no canvas, and a
sandboxed artifact cannot load Ketcher's external JS/WASM bundle. So `open_sketcher`
reproduces the sketcher's *output*: it takes a molecule (or a blank start), lays it out
in 2D, and emits a self-contained HTML "sketch pad" artifact — a labelled 2D depiction
plus the editable MOL block (Ketcher's native import/export format) and key identifiers.
The returned HTML is self-contained (inline SVG/CSS, no external assets) so the host can
save it directly as a construct/artifact.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

import html

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from mcp.server.fastmcp import FastMCP

RDLogger.DisableLog("rdApp.*")

mcp = FastMCP("ketcher_chemistry")


def _parse(structure: str, fmt: str):
    fmt = fmt.lower().strip()
    s = structure.strip()
    if not s:
        return None
    if fmt in ("smiles", "smi"):
        return Chem.MolFromSmiles(s)
    if fmt in ("mol", "molblock", "sdf", "ket"):
        return Chem.MolFromMolBlock(s)
    if fmt == "inchi":
        return Chem.MolFromInchi(s)
    raise ValueError(f"Unsupported input format '{fmt}' (use smiles/mol/sdf/inchi).")


@mcp.tool()
def open_sketcher(structure: str = "", from_format: str = "smiles",
                  title: str = "", width: int = 600, height: int = 450) -> str:
    """Open a 2D molecule sketcher and return it as a self-contained HTML artifact.

    Lays out a molecule in 2D and produces a "sketch pad" HTML document: a rendered 2D
    depiction alongside the editable MOL block (Ketcher's native format) and the molecule's
    identifiers (canonical SMILES, formula, MW, InChIKey). The HTML is fully self-contained
    (inline SVG + CSS, no external assets) so it can be saved directly as an artifact.

    Args:
        structure: the starting molecule (e.g. a SMILES string); leave empty for a blank pad.
        from_format: input format — smiles / mol / sdf / inchi (default smiles).
        title: optional heading for the sketch pad.
        width: depiction width in px (default 600).
        height: depiction height in px (default 450).
    """
    w, h = max(200, width), max(150, height)
    mol = _parse(structure, from_format)
    heading = html.escape(title or ("Molecule Sketch" if mol is not None else "Blank Sketch Pad"))

    if mol is None:
        if structure.strip():
            return f"Could not parse the input as {from_format}: '{structure[:80]}'."
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
               f'<rect width="100%" height="100%" fill="none" stroke="#bbb" '
               f'stroke-dasharray="6 6"/><text x="50%" y="50%" text-anchor="middle" '
               f'fill="#999" font-family="sans-serif">empty canvas — pass a SMILES to sketch</text></svg>')
        molblock, smiles, formula, mw, ikey = "", "", "", "", ""
    else:
        AllChem.Compute2DCoords(mol)
        d = rdMolDraw2D.MolDraw2DSVG(w, h)
        d.DrawMolecule(mol)
        d.FinishDrawing()
        svg = d.GetDrawingText()
        molblock = Chem.MolToMolBlock(mol)
        smiles = Chem.MolToSmiles(mol)
        formula = rdMolDescriptors.CalcMolFormula(mol)
        mw = f"{Descriptors.MolWt(mol):.2f}"
        ikey = Chem.MolToInchiKey(mol)

    ident_rows = "".join(
        f"<tr><th>{k}</th><td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in (("SMILES", smiles), ("Formula", formula), ("MW", mw), ("InChIKey", ikey))
        if v
    )
    ident_html = f"<table class='ident'>{ident_rows}</table>" if ident_rows else ""
    molblock_html = (f"<label>Editable MOL block (import into Ketcher):</label>"
                     f"<textarea spellcheck='false' rows='12'>{html.escape(molblock)}</textarea>"
                     if molblock else
                     "<p class='hint'>No structure yet — this pad starts blank.</p>")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 1.25rem;
         background: #fafafa; color: #1a1a1a; }}
  @media (prefers-color-scheme: dark) {{ body {{ background:#161616; color:#eaeaea; }}
    .canvas, textarea {{ background:#1f1f1f !important; border-color:#3a3a3a !important; }} }}
  h1 {{ font-size: 1.15rem; margin: 0 0 1rem; }}
  .wrap {{ display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: flex-start; }}
  .canvas {{ background:#fff; border:1px solid #ddd; border-radius:8px; padding:8px;
            max-width:100%; overflow:auto; }}
  .side {{ flex:1 1 260px; min-width:240px; }}
  table.ident {{ border-collapse: collapse; margin-bottom: 1rem; }}
  table.ident th {{ text-align:left; padding:3px 10px 3px 0; color:#666; font-weight:600;
                   vertical-align:top; white-space:nowrap; }}
  table.ident td {{ padding:3px 0; word-break:break-all; }}
  label {{ display:block; font-size:.8rem; color:#666; margin-bottom:.35rem; }}
  textarea {{ width:100%; box-sizing:border-box; font-family:ui-monospace,monospace;
             font-size:.72rem; border:1px solid #ddd; border-radius:6px; padding:8px;
             background:#fff; color:inherit; }}
  .hint {{ color:#888; }}
  code {{ font-family: ui-monospace, monospace; font-size:.8rem; }}
</style></head>
<body>
  <h1>{heading}</h1>
  <div class="wrap">
    <div class="canvas">{svg}</div>
    <div class="side">{ident_html}{molblock_html}</div>
  </div>
</body></html>"""


if __name__ == "__main__":
    mcp.run()
