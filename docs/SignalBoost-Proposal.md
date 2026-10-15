# Proposal: Expand Moria's Temporal and Multivariate Signal Detection

**Objective:** Improve Moria's ability to detect emerging developments, contextual anomalies and structural changes across the IP ecosystem.

Proposed enhancements

1. Multi-horizon analysis: Expand configurable time windows to 3, 6, 12, 36, 60, 120 and 180 months, subject to source history and data quality. Apply methods appropriate to each horizon, distinguishing short-term anomalies from sustained trends and long-term structural shifts.

2. Multivariate anomaly detection: Introduce contextual models that predict expected activity using related topics, source volume, international indicators and historical patterns. Flag significant deviations from expected behaviour.

3. Relationship-change detection: Identify emerging associations and breakdowns in established relationships between topics, technologies, jurisdictions and IP activity.

4. Evidence-based evaluation: Benchmark enhancements against existing detectors using historical backtesting and synthetic anomalies. Retain enhancements only where they demonstrate measurable improvements in detection quality.

**Acceptance criteria**

- Time horizons are configurable by source and analytical method, with minimum-history requirements.
- New detectors provide interpretable explanations and retain provenance for supporting evidence.
- Evaluation measures incremental detection value, false positives and robustness against data-quality artefacts.
- Overlapping windows and correlated indicators are not treated as independent corroboration.
