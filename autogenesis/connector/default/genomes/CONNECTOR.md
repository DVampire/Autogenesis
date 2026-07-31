---
name: genomes_connector
description: Genome annotation via Ensembl REST (gene lookup, cross-references, VEP, homology, sequence, region overlap) plus UCSC Genome Browser REST (track listing/data, phyloP/phastCons conservation, ENCODE TFBS clusters, chromosome sizes). Public APIs, no auth.
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
  - ensembl_lookup
  - ensembl_xrefs
  - ensembl_vep_variant
  - ensembl_homology
  - ensembl_sequence
  - ensembl_overlap_region
  - ucsc_list_tracks
  - ucsc_track_data
  - ucsc_conservation
  - ucsc_tfbs_clusters
  - ucsc_chrom_sizes
---

# Genomes

A self-contained MCP connector for genome annotation over two **public** REST APIs,
no authentication: the **Ensembl REST API** (`rest.ensembl.org`) for gene-centric
annotation, and the **UCSC Genome Browser REST API** (`api.genome.ucsc.edu`) for
browser tracks, conservation and regulatory data.

## Tools

### Ensembl
- `ensembl_lookup` — gene/transcript by Ensembl id or symbol. Args: `query`, `species`.
- `ensembl_xrefs` — external DB cross-references for a gene. Args: `query`, `species`.
- `ensembl_vep_variant` — variant effect prediction for an rsID / HGVS. Args: `variant`, `species`.
- `ensembl_homology` — orthologues across species. Args: `gene`, `species`, `target_species`.
- `ensembl_sequence` — sequence for an id (genomic/cds/cdna/protein). Args: `ensembl_id`, `seq_type`, `max_len`.
- `ensembl_overlap_region` — features overlapping a region. Args: `region` ("chr:start-end"), `species`, `feature`.

### UCSC Genome Browser
- `ucsc_list_tracks` — queryable data tracks for an assembly (composite subtracks flattened). Args: `genome`, `search`.
- `ucsc_track_data` — raw feature rows for any track in a region. Args: `track`, `region`, `genome`.
- `ucsc_conservation` — count/mean/min/max of phyloP/phastCons scores over a region. Args: `region`, `genome`, `track`.
- `ucsc_tfbs_clusters` — ENCODE clustered TF binding sites in a region. Args: `region`, `genome`.
- `ucsc_chrom_sizes` — chromosome/contig names and sizes for an assembly. Args: `genome`, `search`.

## Typical workflow

1. `ensembl_lookup` for a gene's coordinates/id; `ensembl_xrefs` for external ids.
2. `ensembl_overlap_region` for what else is in a locus; `ensembl_sequence` for sequence.
3. `ensembl_vep_variant` for a variant's effect; `ensembl_homology` for orthologues.
4. `ucsc_list_tracks` to discover a track, then `ucsc_track_data` for its rows in a region.
5. `ucsc_conservation` / `ucsc_tfbs_clusters` for constraint and regulatory context; `ucsc_chrom_sizes` for assembly bounds.

## Notes

- Read-only; hits the public Ensembl and UCSC REST APIs, so responses depend on their uptime.
- Ensembl regions are 1-based; UCSC region strings are also given 1-based here and
  converted internally to the 0-based half-open coordinates the UCSC API expects.
- The `connection` above uses a relative `server.py` and `command: python`; the connector
  manager resolves both at load time (`server.py` → this connector's directory, `python` →
  the running interpreter via `sys.executable`), so no machine-specific paths are needed.
