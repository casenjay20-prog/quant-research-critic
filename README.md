# Quant Research Critic — v1.1

Quant Research Critic analyzes a CSV of returns and produces:
- strategy metrics (CAGR, Sharpe, max drawdown)
- a normalized scorecard (0–100 + letter grade)
- optional benchmark-relative evaluation (SPY-style)

This README documents the **frozen v1.1 contract**.

---

## API Versioning (Frozen Contract)

The API returns three explicit version fields:

- `api_version`: endpoint behavior
- `schema_version`: response JSON shape
- `scoring_version`: scoring math & weights

### Current versions (locked)
- `api_version = v1.1`
- `schema_version = v1.1`
- `scoring_version = v1.1`

Only bump:
- `schema_version` when response keys change
- `scoring_version` when score logic or weights change
- `api_version` when endpoint behavior changes in a breaking way

---

## Input CSV Format

Required columns:
- `date`
- `returns`

Optional column:
- `benchmark_returns`

Example:

```csv
date,returns,benchmark_returns
2024-01-02,0.010,0.008
2024-01-03,-0.005,-0.004


