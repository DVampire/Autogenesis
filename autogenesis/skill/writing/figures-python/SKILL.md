---
name: figures-python
description: Use when creating data visualizations for papers - generates publication-quality plots with top-journal color schemes
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Python data figures

How to produce publication-quality data figures with Python.

## Checklist

- [ ] The conda environment (`research`) is activated
- [ ] Figure type and data confirmed
- [ ] The data manifest is recorded
- [ ] Any mock/synthetic data is clearly labeled as planning data
- [ ] A top-journal color scheme is used
- [ ] Resolution set to 450 DPI
- [ ] Both PNG and SVG exported
- [ ] CJK font rendering checked (if the labels are Chinese)
- [ ] Saved under `figures/`

## 1. Environment requirements

### 1.1 conda environment

**Default environment name**: `research`

**Activate:**
```bash
conda activate research
```

**Required libraries:**
```bash
pip install matplotlib seaborn numpy pandas
```

If the environment is not set up, invoke the `environment-setup` skill.

## 2. Figure standards

### 2.0 Data manifest and the mock-data boundary

Every data figure needs a data file and a data manifest first. Default paths:

```text
figures/data-manifest.md
figures/data/<figure-name>.csv
figures/<section>/<figure-name>.py
figures/<section>/<figure-name>.png
figures/<section>/<figure-name>.svg
```

`figures/data-manifest.md` records at least:

| Figure | Data file | Real/mock | Source | Script | Outputs |
|---|---|---|---|---|---|

Mock or synthetic data may only be used for planning versions of a figure. The file name must start with `mock_` or `synthetic_`, and the figure, table, or chapter draft must keep the placeholder `[待真实实验替换]` ("replace with real experiment"). Never describe mock data with "results show" or its Chinese equivalent `实验结果表明`.

### 2.1 Resolution

| Use | DPI | Notes |
|-----|-----|-------|
| Journal submission | 300–600 | What most journals require |
| Top-tier submission | 450+ | Nature / Science and similar |
| Screen display | 150 | Slides, web |

**This skill defaults to 450 DPI.**

### 2.2 Output formats

Export every figure in both formats:
- **PNG**: raster, for web and slides
- **SVG**: vector, for journal submission

### 2.3 Figure sizes

| Type | Width (inches) | Use |
|------|----------------|-----|
| Single column | 3.5 | Journal single column |
| Double column | 7.0 | Journal double column / full width |
| Slide figure | 10.0 | Presentations |

## 3. Top-journal color schemes

### 3.1 Nature / Science style

```python
NATURE_COLORS = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#95C623']
```

### 3.2 Cell style

```python
CELL_COLORS = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948']
```

### 3.3 Colorblind-safe

```python
COLORBLIND_SAFE = ['#0077BB', '#33BBEE', '#009988', '#EE7733', '#CC3311', '#EE3377']
```

### 3.4 Color rules

- Do NOT use matplotlib's default colors
- Do NOT use pure red, pure blue, pure green, or other primaries
- Keep a single figure to at most 5 colors
- Make sure the palette is colorblind-safe

## 4. Code template

```python
"""
Figure X: [figure title]
Paper section: [section this belongs to]
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path

# CJK font configuration (only needed for Chinese labels)
CHINESE_FONT = None
font_candidates = [
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/PingFang.ttc',
]
for fp in font_candidates:
    if Path(fp).exists():
        CHINESE_FONT = fm.FontProperties(fname=fp)
        break

plt.rcParams['axes.unicode_minus'] = False

# Top-journal palette
COLORS = ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F']

def setup_plot_style():
    plt.rcParams.update({
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'legend.frameon': False,
        'savefig.dpi': 450,
        'savefig.bbox': 'tight',
    })

def main():
    setup_plot_style()

    fig, ax = plt.subplots(figsize=(7, 5))

    # === plotting code ===
    x = np.linspace(0, 10, 100)
    ax.plot(x, np.sin(x), color=COLORS[0], label='Model A')
    ax.plot(x, np.cos(x), color=COLORS[1], label='Model B')

    if CHINESE_FONT:
        ax.set_xlabel('时间 (s)', fontproperties=CHINESE_FONT)
        ax.set_ylabel('幅值', fontproperties=CHINESE_FONT)
    else:
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Amplitude')

    ax.legend()
    # === end plotting code ===

    # Save
    output_dir = Path(__file__).parent
    fig_name = Path(__file__).stem
    plt.savefig(output_dir / f'{fig_name}.png', dpi=450)
    plt.savefig(output_dir / f'{fig_name}.svg')
    plt.show()

if __name__ == '__main__':
    main()
```

## 5. Common plot types

### Line chart
```python
ax.plot(x, y, color=COLORS[0], linewidth=1.5, marker='o', markersize=4)
```

### Bar chart
```python
ax.bar(x_pos, values, color=COLORS[:len(values)], edgecolor='white')
```

### Heatmap
```python
im = ax.imshow(matrix, cmap='RdBu_r', aspect='auto')
plt.colorbar(im, ax=ax)
```

### Box plot
```python
bp = ax.boxplot(data_list, patch_artist=True)
for patch, color in zip(bp['boxes'], COLORS):
    patch.set_facecolor(color)
```

### Scatter plot
```python
ax.scatter(x, y, c=colors, s=sizes, alpha=0.6, cmap='viridis')
```

## 6. File management

### Directory layout

```
figures/
├── chapter1/
│   ├── fig1_overview.py
│   ├── fig1_overview.png
│   └── fig1_overview.svg
├── chapter2/
└── chapter3/
```

### Naming convention

- File name format: `fig{number}_{description}.py`
- Example: `fig1_model_architecture.py`

## 7. Quality check

### Content
- [ ] The data are correct
- [ ] Axis labels are complete, including units
- [ ] The legend is legible

### Visuals
- [ ] A top-journal palette is used
- [ ] Resolution is 450 DPI
- [ ] Font sizes are appropriate

### Output files
- [ ] PNG generated
- [ ] SVG generated
- [ ] File naming follows the convention

## 8. FAQ

### Q1: Chinese characters render as boxes

```python
from matplotlib.font_manager import FontProperties
font = FontProperties(fname='/System/Library/Fonts/STHeiti Light.ttc')
ax.set_xlabel('中文标签', fontproperties=font)
```

### Q2: The image is blurry

```python
plt.savefig('figure.png', dpi=450, bbox_inches='tight')
```

### Q3: The legend covers the data

```python
ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1))
```
