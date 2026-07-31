---
name: writing-core
description: Use when writing or revising academic papers, especially Chinese journal manuscripts, that need natural prose, de-AI-ification, Markdown formatting, or quality checks
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Core writing standards

This skill controls paper-writing quality. Its focus is natural phrasing, de-AI-ification, and submission-ready Markdown layout for academic manuscripts, Chinese-language journal manuscripts in particular.

Because the target manuscripts are written in Chinese, the banned-phrase tables and rewrite examples below stay in Chinese: they are the language data the rules operate on, and translating them would make the rules unenforceable. The surrounding instructions are in English.

<EXTREMELY-IMPORTANT>
The standards below are mandatory. Do not skip them in the name of "efficiency" or "simplification".
</EXTREMELY-IMPORTANT>

## 1. De-AI-ification of language

### 1.1 Banned expressions

| Category | Banned words / phrases |
|----------|------------------------|
| Mechanical transitions | 首先、其次、最后、此外、另外、接下来、总之 |
| Hollow emphasis openers | 值得注意的是、需要指出的是、重要的是、必须强调的是、显而易见 |
| Empty intensifiers | 非常、极其、十分、相当 (when no data backs them) |
| Subjective framing | 我认为、我觉得、我个人看法是 (banned in the body of a paper) |

### 1.2 Preferred expressions

1. Connect sentences by meaning, not by template connectives
2. Replace adjectives with data and facts
3. Alternate long and short sentences; avoid runs of equal-length sentences
4. Use objective subjects such as 本文, 实验结果表明, 表X显示 — but do not repeat one template over and over
5. Keep the necessary qualifiers, links, and a little repetition, so the paragraph reads like Chinese prose written by an actual researcher

### 1.3 Syntax and information density

1. When turning a list into prose, restore the subjects, predicates, and connectives
2. Build each sentence around one main relation; keep conditions, scope, and explanations where needed instead of forcing everything short
3. Preserve the method, conditions, objects, and data; do not fall back on vague wording such as 很多 or 较大提升
4. De-AI-ification is not compression. If shortening a sentence loses the data definition, experimental boundary, evaluation target, or conclusion limit, restore that information

### 1.4 Natural prose in Chinese journal papers

A Chinese journal paper does not aim for maximum terseness in every sentence. The natural pattern usually introduces the research object, material scope, or problem background first, then the method, the observed results, and the boundaries of the judgment. Sentences may run somewhat long, and a paragraph may contain links, qualifiers, and mild repetition, as long as the subject is explicit, the relations are clear, and the reader can follow the research process.

De-AI-ification targets templated phrasing, translationese, over-generalization, and empty elevation — not every modifier. Keep whatever specifies the object, time range, sample definition, method conditions, metric meaning, experimental boundary, and causal relation. Do not reduce a paragraph to a mechanical "background — method — result — significance" sequence, and do not make every sentence follow an "object — action — conclusion" shape.

When the user says the text is 太AI ("too AI"), 太精简 ("too terse"), or 像翻译 ("reads like a translation"), first check for over-compression, English word order, templated summaries, rebuttal-letter phrasing, or empty elevation. Fix in this order: restore the missing information, adjust to natural Chinese word order, then soften over-strong judgments. Do not just keep deleting words.

### 1.5 Common AI-writing symptoms and their fixes

| Symptom | Fix |
|---------|-----|
| Sentences read as literal English translation | Use normal Chinese word order: state the object and the phenomenon, then the judgment |
| Over-templated paragraphs | Drop the fixed "背景-方法-结果-意义" rhythm; keep explanatory and linking sentences |
| The rewrite lost information | Restore the research object, data range, method conditions, metric definition, and conclusion boundary |
| Rebuttal-letter tone | Turn 该指标反映的是 / 不能理解为 into body narration, e.g. 本文将...作为参照 |
| Empty elevation | Replace catch-alls like 显著, 关键, 重要意义 with concrete metrics, phenomena, or qualifiers |

## 2. Output formatting standards

### 2.1 Markdown body text

1. **No bold or italic in the body by default**
2. **Paragraphs are separated by a blank line**
3. **Body paragraphs run as continuous prose; do not stack points as bullets**
4. Keep one central point per paragraph where possible
5. Do not split a single complete point across too many short paragraphs

### 2.2 Where lists are allowed

Lists are allowed only in:
- Planning documents (`plan/*.md`)
- Checklists
- Parameter configurations
- Operating procedures

**The paper body uses no lists by default.**

## 3. Paragraph construction

A standard paragraph contains:

1. **Topic sentence**: the paragraph's core conclusion
2. **Supporting sentences**: grounds, evidence, explanation
3. **Closing sentence**: transition or wrap-up

**Suggested length:**
- Chinese body text: 150–300 characters
- English body text: 100–200 words

## 4. Turning lists into prose

### Wrong

```
本研究贡献如下：
- 提出新方法
- 完成自动化流程
- 验证有效性
```

### Preferred

```
本研究提出了一种新方法，并将其整合为可执行的自动化流程。
实验结果显示，该方法在目标任务上具有稳定增益，验证了其可行性与应用价值。
```

## 5. Citations and facts

<HARD-GATE>
1. Never fabricate references or data
2. Keep the citation format consistent across the whole paper
3. When a statement is conclusive, give the source or the data behind it
</HARD-GATE>

## 6. Three-pass quality check

### Pass 1: structure

- [ ] Is the body written as lists?
- [ ] Does each paragraph stay on one central point?
- [ ] Is the section-to-section logic continuous?
- [ ] Has the body been reduced to mechanical "背景-方法-结果-意义" template paragraphs?

### Pass 2: language

- [ ] Any banned transition words?
- [ ] Any banned emphasis openers?
- [ ] Any pile-up of information-free adjectives?
- [ ] Any subjective framing?
- [ ] Any translationese, English word order, or rebuttal-letter phrasing?
- [ ] Did over-compression drop the research object, data range, method conditions, metric definition, or conclusion boundary?
- [ ] Are judgments like 提升, 有效, 稳定 backed by concrete data and observations?

### Pass 3: formatting

- [ ] Any meaningless bold?
- [ ] Is the blank line between paragraphs consistent?
- [ ] Are punctuation and CJK/Latin spacing consistent?

## 7. Style self-check script

After writing, run the style checker:

**macOS/Linux:**
```bash
bash research-writing-skill/scripts/style_check.sh <file.md>
```

**Windows PowerShell:**
```powershell
powershell -ExecutionPolicy Bypass -File research-writing-skill/scripts/style_check.ps1 -FilePath <file.md>
```

## 8. Execution constraints

1. Read or create `plan/` before starting a long task
2. Update `plan/progress.md` and `plan/notes.md` after each writing session
3. If the user explicitly asks to keep a particular style, the user's requirement wins
