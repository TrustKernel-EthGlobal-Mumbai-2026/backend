---
name: data-analysis
description: Analyze structured or quantitative data to answer a decision question through profiling, cleaning, segmentation, aggregation, disaggregation, validation, and reproducible findings. Use for datasets, metrics, experiments, forecasts, and quantitative comparisons. Do not use as the primary workflow for broad external research or unsupported narrative interpretation.
---

# Data Analysis

Turn data into a defensible decision model, not merely charts or summary statistics.

Read [the analysis protocol](references/analysis-protocol.md) for quality and validation checks. Read [aggregation and disaggregation](../../harness/references/aggregation-disaggregation.md) when totals, averages, segments, or rollups matter.

## Workflow

1. Define the decision, unit of analysis, outcome, comparison, time window, and success criteria.
2. Establish the data contract: sources, grain, keys, definitions, units, exclusions, and known limitations.
3. Profile completeness, uniqueness, validity, distributions, and suspicious discontinuities.
4. Clean transparently; preserve raw inputs and record consequential transformations.
5. Start with the aggregate signal, then disaggregate across plausible drivers and protected or strategically important segments.
6. Test alternative explanations, sensitivity to definitions, and robustness to outliers or missingness.
7. Separate description, association, prediction, and causation.
8. Reconcile detailed results back to totals and reproduce key calculations.
9. Communicate findings, uncertainty, implications, and the next useful analysis.

## Output

Include the question, data scope, method, decisive findings, segment differences, caveats, and decision implications. Prefer a small number of purposeful tables or charts over dashboards without a thesis.

## Boundaries

- Never fabricate rows, measurements, sample sizes, or precision.
- Do not silently drop inconvenient data.
- Do not average rates with incompatible denominators.
- Do not infer causality from observational association without a credible identification strategy.
- Flag small samples, survivorship, selection effects, leakage, and definition drift.
