---
name: science
description: "The workstation half of a project: a conversation with the agent, over one kernel the agent, the REPL and JupyterLab all share. Human-facing: not an agent capability."
version: 1.0.0
type: module
category: interface
requirements: []
metadata:
  document_version: 2
---
# Science

A **workstation**: you describe an experiment, the agent runs it, and its
results sit in a workspace with a live kernel already pointed at them. Train a
model, plot the result, write the paper.

Like the [canvas](../canvas/README.md) and the [IDE](../ide/README.md), this is
**human-facing**: the agent never calls into it, and it is not registered as a
capability the meta agent can see.

```python
from autogenesis.science import science_manager

await science_manager.start(session_id, workspace_root=workspace)
await science_manager.compute(session_id)          # GPUs, CPU, memory, disk
science_manager.notebooks(session_id)              # .ipynb files in the workspace
```

## One kernel, so there is nothing to synchronise

This is the whole design, and it took two wrong turns to reach.

Everything that runs code in a project goes through the *same* Jupyter Server,
held open by [`autogenesis.kernel`](../kernel/README.md):

- the agent's `code_interpreter_tool`,
- the Science view's REPL, and
- JupyterLab.

So when the agent runs a cell, `x` it defined is `x` at the prompt — it does not
always run one, which the next section is about. The panel labelled "Notebook"
is not a document anybody edits — it is **the kernel's own execution history**,
rendered. Nothing can drift out of step with what actually ran, because there is
only one record and one set of variables.

The two wrong turns are worth keeping written down:

1. **The agent writes a notebook file, the view reads it.** Two writers of one
   document, and edits made in JupyterLab silently lost.
2. **A separate "science" peer container with its own kernel.** Then the agent's
   variables were not the notebook's variables, and "keeping them in sync"
   became a problem with no good answer — invented entirely by the design.

## Why there is no science container

There was one. It ran JupyterLab and the heavy stack, and it was deleted.

It bought isolation that was already thin — `bash_tool` runs in the base
environment as root, on the same GPUs and the same disk — while costing:

- a second kernel the agent's state never reached;
- a routing decision for every execution ("which kernel does this go to?");
- a reaper that could kill a container, and a training run with it;
- a copy of the agent system baked in at image build time, going stale.

Merging its stack into `docker/base` cost **+2.8GB on a 21.6GB image** and made
all four stop existing. The base environment now carries CUDA PyTorch,
transformers, the scientific stack and LaTeX, so the agent can reach them too.

If Science ever genuinely needs to diverge from base — a different CUDA, a
domain stack that would break the agent — a container comes back. The kernel
manager is the seam that would take it.

## What the panel does not show

The agent picks its own tools. For "write a function and test it" a shell is
the natural choice, and `bash_tool` spawns a fresh process that has nothing to
do with this kernel — so that run leaves the panel empty and the workspace full.

That is deliberate. The agent's behaviour is not bent to fill a panel: the same
task behaves the same way in Chat, in Canvas and here. The bridge between the
two halves is the **workspace**, which both share — the kernel starts in it, so
a module the agent just wrote is importable at the prompt without ceremony.

The panel is honest about its own scope: it shows what went through the kernel,
which is the agent's `code_interpreter_tool` calls and yours.

## Nothing waits for the workstation but the workstation

A cold Jupyter Server takes about ten seconds to answer (the kernel inside it,
a tenth of one; every cell after that, milliseconds). The Science view is not
gated on it: the conversation needs no kernel, and the Compute panel reads the
machine, so both are up immediately while the server boots behind them. Only
the Notebook tab and the JupyterLab button wait, because those are the two
things that genuinely need it.

## Closed when idle, never when working

The gateway has no "close this project", so time is what frees a Jupyter
Server. Time **alone** would be wrong: a training run holds a kernel for hours
with nobody watching, and an idle clock would read that as abandoned. The
science container's reaper did exactly that.

So the check is idle *and* not computing, and "computing" is answered by the
server's own `execution_state` rather than by what this process happens to have
started — a cell run from an open JupyterLab tab counts too. Two hours idle,
checked every five minutes.

## Compute is the machine

The Compute panel shows the host's own GPUs, cores, memory and disk, not a
per-project slice, because that is exactly what the kernel gets. GPUs are
detected: a machine without an NVIDIA card is ordinary, and the panel says
"No GPU detected" rather than rendering a meter with nothing behind it.

## Notebooks are workspace files

`science_manager.notebooks()` reads `.ipynb` files off disk, so it answers
before a kernel has started and after it has stopped — a notebook is a workspace
file, and the server is not.

The live history is not one of them until you ask: `science.save` writes what
has run out as a real notebook, openable in the JupyterLab one button away, in
the Code view, or anywhere else.

## Served on the UI's own origin

JupyterLab starts with `--ServerApp.base_url=/science/<session>/`, so every
absolute URL it emits already carries the prefix and the UI hosts it at
`<whatever origin the browser used>/science/<session>/`.

Same fix the IDE needed: a per-session hostname is resolved by the BROWSER, so
it only ever worked when the browser ran on the server itself.
