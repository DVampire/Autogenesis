---
name: figures-diagram
description: Use when creating flowcharts, architecture diagrams, or conceptual diagrams - generates prompts for image AI
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Flowchart and structure-diagram generation

Recognize requests for flowcharts, structure diagrams, and concept diagrams, then produce a professional drawing prompt for an image-generation AI.

## 1. When to use

### Diagram types handled here

| Diagram type | Description | Examples |
|--------------|-------------|----------|
| **Flowchart** | Steps, processes, algorithms | Data-processing pipeline, experimental procedure |
| **Architecture diagram** | System or model structure | Neural-network architecture, system architecture |
| **Concept diagram** | Relationships among concepts | Theoretical framework, knowledge structure |
| **Hierarchy chart** | Hierarchical relationships | Taxonomy, organizational structure |
| **Timeline** | Chronological order | Research history, development stages |

### Diagrams that do NOT belong here

Use the `figures-python` skill for:
- Line charts, bar charts, pie charts, and other data charts
- Scatter plots, heatmaps, and other statistical plots
- Any chart that requires exact numeric values

## 2. Checklist

- [ ] Confirm this is a flow/structure diagram, not a data chart
- [ ] Collect the diagram information (purpose, elements, relationships)
- [ ] Confirm style preferences and label language
- [ ] Generate the prompt
- [ ] Recommend an image-generation tool

## 3. Prompt templates

### 3.1 General template

```
Draw a publication-quality [diagram type] for an academic paper, showing "[topic]".

[Overall layout]
- Direction: [top-to-bottom / left-to-right / radial from center]
- Background: white
- Style: professional academic
- Resolution: 450 DPI

[Content]
[Describe every element and relationship in detail]

[Color scheme]
- [Color 1]: [what it marks]
- [Color 2]: [what it marks]

[Style requirements]
- All text clearly legible
- Arrow direction unambiguous
- Add the necessary annotations
```

### 3.2 Flowchart template

```
Draw a publication-quality flowchart for an academic paper, showing "[process name]".

[Process steps]
Step 1: [name]
- Box color: [color]
- Content: [content]

Step 2: [name]
- Relationship to step 1: [arrow description]
...

[Color scheme]
- Blue  (#4E79A7): data-processing steps
- Orange (#F28E2B): core algorithm steps
- Green  (#59A14F): output / result steps

[Style requirements]
- Rounded rectangles
- Arrowed connectors
- Bold borders on key steps
```

### 3.3 Neural-network architecture template

```
Draw a publication-quality neural-network architecture diagram for an academic paper,
showing "[model name]".

[Network structure]
Input layer: [shape, how it is drawn]

Hidden layer 1: [layer type]
- Parameters: [kernel size, channel count, ...]
- Color: [color]

[continue with further layers...]

Output layer: [shape, activation function]

[Color scheme]
- Blues:   convolution layers
- Greens:  pooling layers
- Oranges: fully connected layers
- Purples: attention layers

[Annotation requirements]
- Label every layer with its name and parameters
- Label input and output dimensions
- Mark the novel components with a red dashed box
```

Set the label language (English or Chinese) explicitly in the prompt so the generated diagram matches the manuscript.

## 4. Recommended image-generation tools

| Tool | Strength | Best for |
|------|----------|----------|
| **Nano Banana** | Purpose-built for academic figures | Flowcharts, architecture diagrams |
| **Midjourney** | Strong aesthetics | Concept diagrams, cover art |
| **DALL-E 3** | Strong prompt comprehension | Complex structure diagrams |

**Guidance:**
- Prefer Nano Banana: designed for academic figures
- Use DALL-E 3 for complex structures: it follows long descriptions better
- Use Midjourney when you need to iterate: it supports variant generation

## 5. Color references

### Nature / Science style
```
Blue:      #2E86AB
Magenta:   #A23B72
Orange:    #F18F01
Brick red: #C73E1D
Yellow-green: #95C623
```

### Minimal academic style
```
Dark blue:  #1D3557
Mid blue:   #457B9D
Light blue: #A8DADC
Off-white:  #F1FAEE
Brick red:  #E63946
```

### How to apply the colors

- **Input / output**: blues
- **Core processing**: oranges, with a bold border
- **Auxiliary steps**: grays
- **Novelty markers**: red dashed lines
- **Success / completion**: greens

## 6. Conversation flow

### When the user asks for a flowchart

> "I'll generate the drawing prompt for you. First, a few questions:
>
> 1. **Purpose**: what should this flowchart show?
> 2. **Main steps**: which key steps does it include?
> 3. **Step relationships**: is it linear, or are there branches and loops?
> 4. **Label language**: English or Chinese labels?
> 5. **Target venue**: what kind of journal are you submitting to?"

### After generating the prompt

> "Here is the drawing prompt — copy it into your image-generation AI:
>
> ---
> [prompt text]
> ---
>
> **Recommended tool**: Nano Banana
>
> If the result needs adjusting, tell me what to change."
