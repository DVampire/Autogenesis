---
name: peer-review
description: Use before submission or when reviewing papers - provides evaluation checklists, bias detection, and self-review templates
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Peer review and self-review

A complete guide to reviewing papers, reviewing your own work, and analyzing it critically.

## Checklist

- [ ] Initial assessment: grasp the core of the paper
- [ ] Section-by-section review
- [ ] Methodological and statistical rigor
- [ ] Reproducibility and transparency
- [ ] Write the review report
- [ ] Give concrete improvement suggestions

## 1. The peer-review workflow

### Stage 1: initial assessment

**Key questions:**
- What is the core research question or hypothesis?
- What are the main findings and conclusions?
- Is the work scientifically sound and meaningful?
- Does it fit the target journal / conference?
- Are there obvious fatal flaws?

**Output**: a 2–3 sentence summary.

### Stage 2: section-by-section review

#### Abstract and title
- Does the abstract accurately reflect the content and the conclusions?
- Is the title specific, accurate, and informative?

#### Introduction
- Is the background sufficient and current?
- Is the research question clearly motivated and justified?
- Is the relevant prior work cited appropriately?

#### Methods
- Could another researcher reproduce the study from this description?
- Are the methods appropriate for the research question?
- Are the statistical methods appropriate?

#### Results
- Are the results presented in a clear, logical order?
- Are the figures and tables appropriate, legible, and correctly labeled?
- Are all relevant results included?

#### Discussion
- Are the conclusions supported by the data?
- Are the limitations acknowledged and discussed?
- Is speculation clearly separated from data-supported conclusions?

### Stage 3: methodological and statistical rigor

**Statistical assessment:**
- Are the statistical assumptions satisfied?
- Are effect sizes reported alongside p-values?
- Is multiple-comparison correction applied where needed?
- Is the sample size backed by a power analysis?

**Experimental design:**
- Are the controls appropriate and sufficient?
- Is there enough replication?
- Are potential confounders controlled?

## 2. Structure of a review report

### Summary statement

```markdown
## Overall assessment

**Study overview**: [1–2 sentences]

**Recommendation**: [Accept / Minor revision / Major revision / Reject]

**Key strengths**:
1. [Strength 1]
2. [Strength 2]

**Key weaknesses**:
1. [Weakness 1]
2. [Weakness 2]
```

### Major comments

Issues that materially affect the paper's validity:
- Fundamental methodological flaws
- Inappropriate statistical analysis
- Unsupported or overstated conclusions
- Missing critical controls or experiments

### Minor comments

Issues that improve clarity and completeness:
- Unclear figure labels or legends
- Missing methodological details
- Typesetting or grammatical errors

## 3. Critical-thinking framework

### Bias detection

| Bias type | What to check |
|-----------|---------------|
| Confirmation bias | Are only supporting findings emphasized? |
| Selection bias | Is the sample representative of the target population? |
| Publication bias | Are negative results missing? |
| P-hacking | Were analyses repeated until something turned significant? |

### Logical fallacies

| Fallacy | How it shows up |
|---------|-----------------|
| Post hoc | "B followed A, therefore A caused B" |
| Correlation = causation | Association conflated with causation |
| Hasty generalization | Broad conclusions from a small sample |
| Cherry-picking | Only supporting evidence is selected |

## 4. Self-review prompts

### Pre-submission self-check

```markdown
# Role
You are a demanding senior academic reviewer.

# Task
Read and analyze my paper in depth, then write a harsh but constructive review report.

# Review dimensions
1. **Originality**: a substantive breakthrough, or a marginal increment?
2. **Rigor**: are there gaps in the derivations? Are the experimental comparisons fair?
3. **Consistency**: are the claimed contributions actually verified?

# Output
- Part 1 [Review Report]: Summary, Strengths, Weaknesses, Rating
- Part 2 [Strategic Advice]: concrete improvement suggestions

# Input
Submission target: [journal / conference name]
Paper content: [paste]
```

### Quick quality check

```markdown
# Task
Quickly check the paper for the following problems:

1. Logical consistency: are the claims in the introduction verified by the experiments?
2. Terminology consistency: are core concepts named consistently throughout?
3. Data support: is every conclusion backed by data?
4. Baseline completeness: are the comparisons against enough baselines?
5. Ablation adequacy: is each key module validated?

# Output
- No problems: [check passed]
- Problems found: list the location and the specific issue, point by point
```

## 5. Review tone

### Best practice

- **Constructive**: frame criticism as an opportunity to improve
- **Specific**: give concrete examples and actionable suggestions
- **Balanced**: acknowledge strengths as well as weaknesses
- **Respectful**: remember the authors put in substantial effort
- **Objective**: focus on the science, not the scientist

### Avoid

- Personal attacks or dismissive language
- Vague criticism with no concrete examples
- Demanding unnecessary experiments outside the paper's scope
- Revealing your identity in a double-blind review

## 6. Review checklist

- [ ] The summary statement conveys the overall assessment clearly
- [ ] Major issues are clearly identified and argued
- [ ] Suggested revisions are specific and actionable
- [ ] The statistical methods have been assessed
- [ ] Reproducibility and data availability have been assessed
- [ ] Figures and tables have been assessed for quality and completeness
- [ ] The tone is constructive and professional throughout
