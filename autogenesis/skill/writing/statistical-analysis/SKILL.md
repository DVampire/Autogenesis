---
name: statistical-analysis
description: Use when planning or reporting statistical analysis - provides test selection, execution code, and APA format guidelines
version: 1.0.0
type: worker
license: N/A
category: writing
requirements: [cpu]
metadata: {}
---

# Statistical analysis guide

How to choose, run, and report statistical analyses in an academic paper.

## 1. Choosing a statistical test

### Comparing two groups

| Data characteristics | Recommended test |
|----------------------|------------------|
| Independent, continuous, normal | Independent-samples t-test |
| Independent, continuous, non-normal | Mann-Whitney U test |
| Paired, continuous, normal | Paired-samples t-test |
| Paired, continuous, non-normal | Wilcoxon signed-rank test |
| Binary outcome | Chi-square test or Fisher's exact test |

### Comparing three or more groups

| Data characteristics | Recommended test |
|----------------------|------------------|
| Independent, continuous, normal | One-way ANOVA |
| Independent, continuous, non-normal | Kruskal-Wallis test |
| Paired, continuous, normal | Repeated-measures ANOVA |
| Paired, continuous, non-normal | Friedman test |

### Relationships

| Goal | Recommended method |
|------|--------------------|
| Relationship between two continuous variables | Pearson correlation (normal) or Spearman correlation (non-normal) |
| Continuous outcome vs. predictors | Linear regression |
| Binary outcome vs. predictors | Logistic regression |

## 2. Assumption checks

### Normality

```python
from scipy import stats

# Shapiro-Wilk test (sample size < 5000)
stat, p_value = stats.shapiro(data)
print(f"Shapiro-Wilk: W={stat:.4f}, p={p_value:.4f}")

if p_value > 0.05:
    print("Data are consistent with the normality assumption")
else:
    print("Data are not normal; consider a non-parametric test")
```

### Homogeneity of variance

```python
from scipy import stats

# Levene's test
stat, p_value = stats.levene(group1, group2)
print(f"Levene: F={stat:.4f}, p={p_value:.4f}")

if p_value > 0.05:
    print("Homogeneity of variance holds")
else:
    print("Variances are unequal; use Welch's t-test")
```

## 3. Effect sizes

### Reference values

| Test | Effect size | Small | Medium | Large |
|------|-------------|-------|--------|-------|
| t-test | Cohen's d | 0.20 | 0.50 | 0.80 |
| ANOVA | η²_p | 0.01 | 0.06 | 0.14 |
| Correlation | r | 0.10 | 0.30 | 0.50 |
| Regression | R² | 0.02 | 0.13 | 0.26 |

### Computing effect sizes in Python

```python
import pingouin as pg

# t-test returns Cohen's d
result = pg.ttest(group1, group2)
d = result['cohen-d'].values[0]
print(f"Cohen's d = {d:.2f}")

# ANOVA returns partial eta squared
aov = pg.anova(dv='score', between='group', data=df)
eta_p2 = aov['np2'].values[0]
print(f"Partial η² = {eta_p2:.3f}")
```

## 4. APA-style reporting

### Independent-samples t-test

```
Group A (n = 48, M = 75.2, SD = 8.5) scored significantly higher than
group B (n = 52, M = 68.3, SD = 9.2), t(98) = 3.82, p < .001,
d = 0.77, 95% CI [0.36, 1.18].
```

### One-way ANOVA

```
A one-way ANOVA revealed a significant main effect of treatment condition
on test scores, F(2, 147) = 8.45, p < .001, η²_p = .10. Tukey HSD post-hoc
comparisons showed that condition A (M = 78.2, SD = 7.3) scored significantly
higher than condition B (M = 71.5, SD = 8.1, p = .002).
```

### Multiple regression

```
Multiple linear regression predicting exam scores yielded a significant
overall model, F(3, 146) = 45.2, p < .001, R² = .48. Study time
(β = .35, p < .001) and prior GPA (β = .28, p < .001) were significant
predictors.
```

For a Chinese-language manuscript, keep the statistics exactly as formatted above and translate only the surrounding prose; do not localize the symbols, decimal points, or bracket style.

## 5. Common statistical pitfalls

<HARD-GATE>
The following must be avoided:
</HARD-GATE>

1. **P-hacking**: do not try analysis after analysis until something turns significant
2. **HARKing**: do not present exploratory findings as confirmatory
3. **Ignoring assumptions**: check them, and report any violations
4. **Confusing significance with importance**: p < .05 ≠ a meaningful effect
5. **Omitting effect sizes**: they are essential to interpretation
6. **Cherry-picking results**: report every planned analysis
7. **Multiple comparisons**: correct the family-wise error rate where appropriate
8. **Over-reading null results**: absence of evidence ≠ evidence of absence

## 6. Python example

### A complete t-test workflow

```python
import numpy as np
import pingouin as pg
from scipy import stats

# Data
group_a = np.array([75, 82, 68, 79, 85, 72, 88, 76])
group_b = np.array([65, 70, 62, 68, 75, 60, 72, 66])

# 1. Descriptive statistics
print(f"Group A: M={group_a.mean():.2f}, SD={group_a.std():.2f}")
print(f"Group B: M={group_b.mean():.2f}, SD={group_b.std():.2f}")

# 2. Normality
_, p_a = stats.shapiro(group_a)
_, p_b = stats.shapiro(group_b)
print(f"Normality: group A p={p_a:.3f}, group B p={p_b:.3f}")

# 3. t-test
result = pg.ttest(group_a, group_b)
print(f"t = {result['T'].values[0]:.2f}")
print(f"p = {result['p-val'].values[0]:.4f}")
print(f"Cohen's d = {result['cohen-d'].values[0]:.2f}")
```

## 7. Statistical analysis checklist

- [ ] Research question and hypotheses defined
- [ ] Appropriate statistical test identified
- [ ] Power analysis run to determine sample size
- [ ] Missing data and outliers checked
- [ ] Assumptions verified (normality, homogeneity of variance)
- [ ] Primary analysis run
- [ ] Effect sizes and confidence intervals computed
- [ ] Post-hoc tests run where needed
- [ ] Results written up in APA format

## 8. Recommended resources

### Python libraries
- **scipy.stats**: core statistical tests
- **statsmodels**: advanced regression and diagnostics
- **pingouin**: user-friendly tests that report effect sizes
