---
name: writing-medical
description: Use when writing medical, biological, or clinical research papers - provides IMRaD structure and reporting guidelines
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Medical writing

Guidance specific to medical, biological, and clinical research papers.

## 1. What makes medical papers different

### Compared with other disciplines

| Aspect | Medical papers | General STEM |
|--------|----------------|--------------|
| Structure | Strict IMRaD + a reporting guideline | IMRaD |
| Ethics | Ethics approval must be stated | Case by case |
| Statistics | Detailed statistical methods required | Basic statistics |
| Reporting | Must follow a specific reporting guideline | Not mandated |
| Registration | Clinical trials must be pre-registered | Not required |

### Common study types

- **Randomized controlled trial (RCT)**: evaluating a drug or treatment effect
- **Cohort study**: long-term follow-up observation
- **Case-control study**: retrospective analysis
- **Cross-sectional study**: a survey at one point in time
- **Systematic review / meta-analysis**: synthesis of the literature
- **Case report**: description of a rare case

## 2. Reporting guidelines

<EXTREMELY-IMPORTANT>
Select the reporting guideline that matches the study type.
</EXTREMELY-IMPORTANT>

| Study type | Guideline | Core requirements |
|------------|-----------|-------------------|
| Randomized controlled trial | **CONSORT** | Flow diagram, randomization method, blinding, ITT analysis |
| Observational study | **STROBE** | Design, participants, variables, bias |
| Systematic review | **PRISMA** | Search strategy, screening flow, quality assessment |
| Diagnostic accuracy | **STARD** | Reference standard, blinding, 2×2 table |
| Case report | **CARE** | Timeline, diagnostic reasoning, follow-up |
| Animal study | **ARRIVE** | Sample size, randomization, blinding |

## 3. Medical writing conventions

### Ethics statement

**Must include:**

```
This study was approved by the ethics committee of [hospital name]
(approval number: XXX-XXX-XXX). All participants provided written
informed consent. The study followed the principles of the Declaration
of Helsinki.
```

**Trial registration:**
```
This trial was registered with the Chinese Clinical Trial Registry
(registration number: ChiCTR-XXX-XXXXXXXX).
```

### Describing the statistical methods

**Standard template:**

```
Statistical analyses were performed with SPSS 26.0 (IBM Corp., Armonk, NY, USA).
Continuous data are presented as mean ± standard deviation and compared between
groups using the independent-samples t-test; categorical data are presented as
counts (percentages) and compared using the chi-square test. P < 0.05 was
considered statistically significant.
```

### Reporting results

**Continuous variables:**
- Normally distributed: mean ± SD, e.g. `45.3 ± 12.7 years`
- Non-normal: median (interquartile range), e.g. `23.5 (15.2–38.7)`

**Categorical variables:**
- Count (percentage), e.g. `156 (62.4%)`

**Test results:**
- t-test: `t = 2.45, P = 0.016`
- Chi-square: `χ² = 8.32, P = 0.004`
- Regression: `OR = 2.35, 95% CI: 1.42–3.89, P = 0.001`

### Table conventions

**Baseline characteristics table:**

| Characteristic | Treatment (n=50) | Control (n=50) | P |
|----------------|------------------|----------------|---|
| Age (years) | 45.3 ± 12.7 | 44.8 ± 11.9 | 0.842 |
| Male, n (%) | 28 (56.0) | 25 (50.0) | 0.548 |
| BMI (kg/m²) | 24.2 ± 3.1 | 23.8 ± 2.9 | 0.498 |

## 4. Numerical conventions

### Reporting P values

- P < 0.001: write `P < 0.001`
- 0.001 ≤ P < 0.05: write the exact value, e.g. `P = 0.023`
- P ≥ 0.05: write the exact value, e.g. `P = 0.156`
- Never write `P = 0.000`; write `P < 0.001`

### Number formatting

- Use a consistent number of decimal places
- Percentages: 1 decimal place
- P values: 3 decimal places
- Confidence intervals: 2 decimal places

## 5. Medical paper checklist

### Ethics and registration
- [ ] Ethics approval number stated
- [ ] Informed consent described
- [ ] Trial registered (where applicable)
- [ ] Conflicts of interest declared

### Reporting guideline
- [ ] The correct guideline was selected
- [ ] Its checklist has been completed
- [ ] The flow diagram is included (where required)

### Statistical methods
- [ ] Statistical software stated
- [ ] Methods match the data types
- [ ] Sample-size calculation described

### Results presentation
- [ ] Effect size with confidence interval
- [ ] P values formatted correctly
- [ ] Tables follow the conventions

## 6. Resources

### Reporting guidelines
- EQUATOR Network: https://www.equator-network.org/
- CONSORT: http://www.consort-statement.org/
- STROBE: https://www.strobe-statement.org/

### Trial registries
- Chinese Clinical Trial Registry: http://www.chictr.org.cn/
- ClinicalTrials.gov: https://clinicaltrials.gov/
