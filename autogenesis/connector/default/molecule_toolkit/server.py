#!/usr/bin/env python3
"""Molecule Toolkit MCP server — local cheminformatics via RDKit (open-source, no network).

The agent-usable capabilities behind a 2D molecule sketcher: parse/convert between
chemical formats (SMILES / MOL / SDF / InChI), render a 2D depiction as SVG, compute
molecular descriptors, extract scaffolds, and parse reaction SMILES.

Run as a stdio MCP server:  python server.py
"""
from __future__ import annotations

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, Draw, Lipinski, rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem.Draw import rdMolDraw2D
from mcp.server.fastmcp import FastMCP

RDLogger.DisableLog("rdApp.*")   # silence RDKit parse warnings on stderr

mcp = FastMCP("molecule_toolkit")


def _parse(structure: str, fmt: str):
    fmt = fmt.lower().strip()
    s = structure.strip()
    if fmt in ("smiles", "smi"):
        return Chem.MolFromSmiles(s)
    if fmt in ("mol", "molblock", "sdf"):
        return Chem.MolFromMolBlock(s)
    if fmt == "inchi":
        return Chem.MolFromInchi(s)
    if fmt == "smarts":
        return Chem.MolFromSmarts(s)
    raise ValueError(f"Unsupported input format '{fmt}' (use smiles/mol/sdf/inchi/smarts).")


@mcp.tool()
def molecule_convert(structure: str, from_format: str = "smiles", to_format: str = "mol") -> str:
    """Convert a molecule between chemical formats.

    Args:
        structure: the molecule in `from_format` (e.g. a SMILES string or a MOL block).
        from_format: input format — smiles / mol / sdf / inchi / smarts.
        to_format: output format — smiles / mol / inchi / inchikey / formula.
    """
    mol = _parse(structure, from_format)
    if mol is None:
        return f"Could not parse the input as {from_format}."
    out = to_format.lower().strip()
    try:
        if out in ("smiles", "smi"):
            return Chem.MolToSmiles(mol)
        if out in ("mol", "molblock"):
            return Chem.MolToMolBlock(mol)
        if out == "inchi":
            return Chem.MolToInchi(mol)
        if out == "inchikey":
            return Chem.MolToInchiKey(mol)
        if out == "formula":
            return rdMolDescriptors.CalcMolFormula(mol)
        return f"Unsupported output format '{to_format}' (use smiles/mol/inchi/inchikey/formula)."
    except Exception as e:
        return f"Conversion failed: {e}"


@mcp.tool()
def molecule_descriptors(smiles: str) -> str:
    """Compute key molecular descriptors and Lipinski rule-of-five for a molecule.

    Args:
        smiles: molecule as SMILES (e.g. "CC(=O)Oc1ccccc1C(=O)O").
    """
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return f"Could not parse SMILES '{smiles}'."
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    lipinski_ok = sum([mw <= 500, logp <= 5, hbd <= 5, hba <= 10]) >= 3
    fields = [
        ("canonical_smiles", Chem.MolToSmiles(mol)),
        ("formula", rdMolDescriptors.CalcMolFormula(mol)),
        ("mol_weight", f"{mw:.2f}"),
        ("exact_mass", f"{Descriptors.ExactMolWt(mol):.4f}"),
        ("logP", f"{logp:.2f}"),
        ("TPSA", f"{Descriptors.TPSA(mol):.2f}"),
        ("H_donors", hbd),
        ("H_acceptors", hba),
        ("rotatable_bonds", Descriptors.NumRotatableBonds(mol)),
        ("rings", rdMolDescriptors.CalcNumRings(mol)),
        ("aromatic_rings", rdMolDescriptors.CalcNumAromaticRings(mol)),
        ("heavy_atoms", mol.GetNumHeavyAtoms()),
        ("InChIKey", Chem.MolToInchiKey(mol)),
        ("lipinski_ro5_pass", lipinski_ok),
    ]
    return "\n".join(f"{k}: {v}" for k, v in fields)


@mcp.tool()
def molecule_depict(smiles: str, width: int = 400, height: int = 300) -> str:
    """Render a 2D structure depiction of a molecule as an SVG string (embeddable in reports).

    Args:
        smiles: molecule as SMILES.
        width: image width in px (default 400).
        height: image height in px (default 300).
    """
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return f"Could not parse SMILES '{smiles}'."
    AllChem.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DSVG(max(100, width), max(100, height))
    d.DrawMolecule(mol)
    d.FinishDrawing()
    return d.GetDrawingText()


@mcp.tool()
def molecule_scaffold(smiles: str, generic: bool = False) -> str:
    """Extract the Bemis-Murcko scaffold (core ring system) of a molecule.

    Args:
        smiles: molecule as SMILES.
        generic: if True, return the generic (atom/bond-agnostic) scaffold framework.
    """
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return f"Could not parse SMILES '{smiles}'."
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    if generic:
        scaffold = MurckoScaffold.MakeScaffoldGeneric(scaffold)
    smi = Chem.MolToSmiles(scaffold)
    return f"scaffold_smiles: {smi or '(none — acyclic molecule)'}"


@mcp.tool()
def reaction_parse(reaction_smiles: str) -> str:
    """Parse a reaction SMILES (reactants>>products) into its components.

    Args:
        reaction_smiles: e.g. "CC(=O)O.OCC>>CC(=O)OCC.O".
    """
    try:
        rxn = AllChem.ReactionFromSmarts(reaction_smiles.strip(), useSmiles=True)
    except Exception as e:
        return f"Could not parse reaction SMILES: {e}"
    if rxn is None:
        return "Could not parse reaction SMILES."
    reactants = [Chem.MolToSmiles(m) for m in rxn.GetReactants()]
    products = [Chem.MolToSmiles(m) for m in rxn.GetProducts()]
    agents = [Chem.MolToSmiles(m) for m in rxn.GetAgents()]
    out = [f"reactants ({len(reactants)}): {', '.join(reactants)}",
           f"products ({len(products)}): {', '.join(products)}"]
    if agents:
        out.append(f"agents ({len(agents)}): {', '.join(agents)}")
    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
