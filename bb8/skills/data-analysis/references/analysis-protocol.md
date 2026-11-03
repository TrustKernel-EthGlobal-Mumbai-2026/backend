# Analysis Protocol

## Question contract

Specify:

- decision to support;
- metric or outcome;
- unit of analysis;
- population and comparison group;
- observation and attribution windows;
- threshold for practical significance.

## Data quality

Check schema, types, keys, duplicates, missingness, impossible values, time zones, currency, units, category drift, join cardinality, and reconciliation to known totals.

Treat missingness as a possible signal. Distinguish zero, not applicable, not observed, and unknown.

## Analytical ladder

1. Counts and coverage.
2. Distributions and trends.
3. Aggregates and reconciliations.
4. Segment differences.
5. Relationships and candidate drivers.
6. Sensitivity and robustness.
7. Predictive or causal analysis only when justified.

## Validation

- Recalculate key metrics independently when practical.
- Reconcile segment totals to the whole.
- Test alternate denominators and definitions.
- Inspect surprising results at row level.
- Check whether results persist across time and important segments.
- Separate statistical from practical significance.

## Finding format

For each material finding state:

1. What happened.
2. Magnitude and population.
3. Evidence and method.
4. Plausible explanation.
5. Alternative explanations.
6. Decision implication.
7. Confidence and next test.
