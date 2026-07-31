---
name: prompts-collection
description: Use for translation, polishing, or de-AI-ification of academic text - provides ready-to-use prompt templates
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Writing prompt collection

Paper-writing prompts used day to day by researchers at leading institutions.

Several prompts below target Chinese-language manuscripts. Their instructions are in English, but the banned-phrase lists stay in Chinese: those are the strings the rewrite has to detect and remove.

## 1. Translation

### 1.1 Chinese to English (academic translation)

```markdown
# Role
You are both a top-tier research-writing expert and a senior conference reviewer.

# Task
Translate and polish the [Chinese draft] I provide into an [English academic paper excerpt].

# Constraints
1. No bold, italics, or quotation marks
2. Rigorous logic, precise wording, common vocabulary
3. No \item lists; use continuous paragraphs
4. Remove the "AI flavor"; the prose must read naturally

# Output
- Part 1 [LaTeX]: the English translation
- Part 2 [Translation]: a literal Chinese back-translation
```

### 1.2 English to Chinese (for quick comprehension)

```markdown
# Role
You are a senior academic translator in computer science.

# Task
Translate the [English LaTeX snippet] into fluent, readable [Chinese text].

# Constraints
1. Strip all \cite{}, \ref{}, and similar commands
2. Translate literally; do not polish
3. Output plain Chinese paragraphs only
```

## 2. Polishing

### 2.1 Polishing English

```markdown
# Role
You are a senior academic editor in computer science.

# Task
Deeply polish and rewrite the [English LaTeX snippet].

# Constraints
1. Restructure sentences for formality and logical coherence
2. Fix every grammatical error
3. Use standard academic register; no contractions
4. Preserve the original LaTeX commands

# Output
- Part 1 [LaTeX]: the polished English
- Part 2 [Translation]: a literal Chinese back-translation
- Part 3 [Modification Log]: what was changed and why
```

### 2.2 Polishing Chinese

```markdown
# Role
You are a senior Chinese-language academic editor specializing in computer science.

# Task
Review and polish the [Chinese paragraph] professionally.

# Constraints
1. Fix only colloquialisms, grammatical errors, and logical gaps
2. Leave text unchanged where it is already clear
3. Use full-width Chinese punctuation

# Output
- Part 1 [Refined Text]: the rewritten Chinese paragraph
- Part 2 [Review Comments]: what was changed and why
```

## 3. De-AI-ification

### 3.1 Removing the AI flavor (English)

```markdown
# Role
You are a senior academic editor in computer science, focused on making prose read naturally.

# Task
Rewrite the [English LaTeX snippet] to remove AI-sounding language.

# Constraints
1. Avoid overused vocabulary (leverage, delve into, tapestry, …)
2. Turn \item content into continuous paragraphs
3. Delete mechanical connectives (First and foremost, …)
4. Leave text unchanged where it already reads naturally

# Output
- Part 1 [LaTeX]: the rewritten snippet
- Part 2 [Translation]: a literal Chinese back-translation
- Part 3 [Modification Log]: the adjustments, or "[check passed]"
```

### 3.2 AI-flavored vocabulary (avoid)

| Avoid | Prefer |
|-------|--------|
| leverage | use, employ |
| delve into | investigate, examine |
| tapestry | context, framework |
| underscore | highlight, show |
| pivotal | important, key |
| nuanced | detailed, subtle |
| foster | encourage, support |
| elucidate | explain, clarify |
| intricate | complex, detailed |
| paramount | important, critical |

### 3.3 Removing the AI flavor (Chinese journal papers, information-preserving)

```markdown
# Role
You are a research-writing editor fluent in the conventions of Chinese journal papers. You
reduce AI tone, translationese, and templated phrasing in Chinese paragraphs without changing
the technical meaning or the definition of any reported quantity.

# Task
Rewrite the [Chinese paragraph or draft] so that it reads like natural, sober, submission-ready
body text in a Chinese journal paper.

# Constraints
1. De-AI-ification is not compression. Unless I explicitly ask for a shorter version, do not
   remove facts, data, qualifying conditions, or explanatory sentences.
2. Preserve the research object, data range, sample definition, method conditions, metric
   meaning, experimental boundary, conclusion limits, and all proper nouns.
3. Use continuous paragraphs. No bullets, no bold, no italics.
4. Avoid mechanical connectives — 首先、其次、最后、此外、另外、接下来、总之 — and connect
   sentences by meaning instead.
5. Avoid hollow openers — 值得注意的是、需要指出的是、重要的是、必须强调的是.
6. Reduce literal-English word order; do not turn every sentence into a mechanical
   "object — action — conclusion" clause.
7. Avoid rebuttal-letter phrasing. The body should not read 该指标反映的是 / 不能理解为 /
   用于避免口径悬空; rewrite these as ordinary narration.
8. Keep judgments restrained. For claims about effectiveness, improvement, contribution, or
   application value, support them with concrete metrics, observations, and boundaries rather
   than empty elevation.
9. If the original is slightly verbose but complete and naturally ordered, adjust it only
   lightly; do not squeeze out necessary information for the sake of looking concise.

# Output
- Part 1 [Refined Text]: the rewritten Chinese body text
- Part 2 [Modification Log]: the main changes, explicitly noting whether translationese,
  templated phrasing, rebuttal-letter tone, or empty elevation was fixed; if the original was
  already natural, output "[check passed]"
- Part 3 [Information Check]: confirm that the key objects, data, methods, metrics, and
  boundaries survived; flag any risk of lost information
```

## 4. Shortening and expanding

### 4.1 Shortening

```markdown
# Task
Slightly shorten the [English LaTeX snippet] (by roughly 5–15 words).

# Constraints
1. Keep all core information
2. Compress syntactically: clauses to phrases, passive to active
3. Cut redundant filler

# Output
- Part 1 [LaTeX]: the shortened snippet
- Part 2 [Translation]: a literal Chinese back-translation
- Part 3 [Modification Log]: the adjustments
```

### 4.2 Expanding

```markdown
# Task
Slightly expand the [English LaTeX snippet] (by roughly 5–15 words).

# Constraints
1. Do not add meaningless adjectives
2. Surface implicit conclusions, premises, or causal links
3. Add the connectives needed to make sentence relations explicit

# Output
- Part 1 [LaTeX]: the expanded snippet
- Part 2 [Translation]: a literal Chinese back-translation
- Part 3 [Modification Log]: the adjustments
```

## 5. Logic check

### 5.1 Final-draft logic check

```markdown
# Task
Run a final consistency and logic check over the [English LaTeX snippet].

# Constraints
1. Assume the draft is already of high quality
2. Report only fatal logic errors, terminology inconsistencies, and serious grammatical faults
3. Ignore "could go either way" issues

# Output
- No problems: [check passed, no substantive issues]
- Problems found: list them briefly, point by point
```

## 6. Figures and tables

### 6.1 Figure captions

```markdown
# Task
Turn the [description] into an [English figure caption].

# Constraints
1. Title Case for noun phrases, sentence case for full sentences
2. Drop redundant openers such as "The figure shows"
3. Output the caption text only, with no "Figure 1:" prefix
```

### 6.2 Table captions

```markdown
# Task
Turn the [description] into an [English table caption].

# Constraints
1. Prefer: Comparison with, Ablation study on, Results on
2. Avoid showcase and depict; use show, compare, present
```

## 7. Reviewer perspective

### 7.1 Reviewing a paper as a reviewer

```markdown
# Role
You are a demanding senior academic reviewer.

# Task
Write a review report on the [paper PDF].

# Output
Part 1 [Review Report]:
- Summary: one sentence
- Strengths: 1–2 contributions
- Weaknesses (Critical): 3–5 fatal problems
- Rating: 1–10

Part 2 [Strategic Advice]:
- Explain the root cause of each problem
- Give concrete improvement suggestions
```

## 8. Usage notes

1. **Copy and use**: these prompts are ready to paste
2. **Pick by task**: choose the prompt that matches what you are doing
3. **Keep them whole**: copy the full prompt for best results
4. **Swap the input**: replace the placeholder sections with your actual content
