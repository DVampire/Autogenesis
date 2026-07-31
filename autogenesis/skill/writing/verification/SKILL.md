---
name: verification
description: Use when about to claim work is complete, a chapter is finished, or references are verified - requires running verification commands and confirming output before making any success claims
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
allowed-tools: Read, Bash, Grep
metadata: {}
---

# Verification

## Core principle

**Claiming completion without verifying it is dishonest.**

```
No verification evidence, no completion claim.
```

## The verification gate

```
Before claiming any status or expressing satisfaction:

1. Identify: which command or action would prove this claim?
2. Execute: run the full verification
3. Read: the complete output, and check the result
4. Confirm: does the output actually support the claim?
   - No  -> state the real status and the evidence
   - Yes -> state the claim and the evidence
5. Only then: make the claim

Skipping any step = lying, not verifying.
```

## Common verification scenarios

| Claim | Verification required | Not sufficient |
|-------|----------------------|----------------|
| Chapter finished | Word count, structure check, file exists | "It should be done" |
| Reference is real | DOI resolves, confirmed via the CrossRef API | "It looks real" |
| Argument is supported | Paragraph-level evidence in the evidence map | "This paragraph reads like a paper" |
| Formatting is correct | Run the format-check script | Eyeballing it |
| No AI fingerprints | Run the style-check script | "It reads fine" |
| Literature search done | Result count, DOI list, JSON file exists | "I searched" |
| Skill rework done | Run `scripts/check_skill_integrity.ps1` | "I wrote all the files" |
| Draft passes the quality gate | Run `scripts/research_quality_gate.ps1` | Running only style_check |

## Red flags — stop

Verify first whenever you notice:

- Reaching for "should", "probably", "looks like"
- Expressing satisfaction before verifying ("Done!", "All set!")
- Preparing to submit / push / merge without verifying
- Trusting a sub-agent's success report
- Relying on partial verification
- Thinking "just this once"
- Being tired and wanting to wrap up
- **Any wording that implies success without a verification run behind it**

## Excuses vs. facts

| Excuse | Fact |
|--------|------|
| "It should work" | Run the verification command |
| "I'm quite sure" | Confidence is not evidence |
| "Just this once" | There are no exceptions |
| "The format check passed" | Format correctness is not content correctness |
| "The agent said it succeeded" | Verify independently |
| "I'm tired" | Fatigue is not an excuse |
| "A partial check is enough" | A partial check proves nothing |

## Key verification patterns

### Chapter completion

```
[run word count]      [saw: 3000 characters]                    "chapter meets the length target"
[check file exists]   [saw: chapters/01-introduction.md exists]  "chapter file created"
[run format check]    [saw: 0 errors]                            "formatting is correct"
NOT: "should be done" / "looks complete"
```

### Citation verification

```
[call the CrossRef API]   [saw: DOI exists, metadata matches]        "citation verified"
[search the original]     [saw: author, journal, year all agree]     "citation is real"
NOT: "the citation looks right" / "it's probably real"
```

### Argument support

```
[check the evidence map]   [saw: every gap claim backed by 2 sources]  "the research gap is supported"
[check citation slots]     [saw: paragraph P2 uses FL-05 + FL-07]      "citation placement is explicit"
NOT: "related work looks complete" / "this paragraph feels academic"
```

### Skill integrity

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_skill_integrity.ps1
```

Confirms that newly added skills, routing entries, verification scripts, and key gates are still in place.

### Manuscript quality gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts/research_quality_gate.ps1 -ProjectPath <paper-project>
```

Checks citation coverage, body-text contamination, list-ification, placeholder policy, the figure data manifest, and the evidence map. Add `-Submission` before submitting to forbid any un-backfilled placeholder.

### Literature search

```
[check the JSON file]     [saw: 20 results, each with a DOI]   "search complete"
[validate BibTeX output]  [saw: parses, no errors]             "BibTeX is valid"
NOT: "I searched" / "there should be results"
```

## Verification checklist

Verify before finishing any piece of work:

- [ ] The verification command was run
- [ ] The full output was read
- [ ] The result confirms the claim
- [ ] No reliance on "should" or "probably"
- [ ] The evidence appears in the current message

## Why this matters

From real failures:
- Fabricated citations got papers retracted
- Chapters below the length target forced rework
- Formatting errors caused submission rejection
- Obvious AI fingerprints drew reviewer suspicion

## Bottom line

**There is no shortcut around verification.**

Run the command. Read the output. Only then state the result.

This is non-negotiable.
