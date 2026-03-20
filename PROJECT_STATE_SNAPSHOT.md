# Quant Research Critic — Project State Snapshot (March 2026)

## What this is
A deterministic quant strategy evaluator that produces:
- Tier 1: analysis JSON + scoring + flags
- Tier 2: committee-grade PDFs (strategy report + allocator memo)
- Tier 3 (planned): monitoring + portfolio intelligence (correlation/clustering/diversification)

## Current working endpoints (FastAPI)
- POST /v1/analyze
  - Input: 1 CSV (date, returns)
  - Output: deterministic payload + report text

- POST /v1/report/pdf
  - Input: 1 CSV
  - Output: strategy_report.pdf (Page 1 summary template)

- POST /v1/compare
  - Input: multiple CSVs
  - Output: List[StrategySummary] ranked by deployability_score

- POST /v1/compare/pdf
  - Input: multiple CSVs
  - Output: strategy_ranking_memo.pdf (watermark ON)

- POST /v1/compare/allocator-pdf   (Tier 2 paid/gated)
  - Input: multiple CSVs
  - Output: allocator_view.pdf (NO watermark)
  - Behavior: picks top-ranked strategy and enriches it with fragility/robustness/constraints/sizing + “returns” list for sparkline

## Tier 3 state
- Tier 3 is in SOFT-DELETE MODE (Option A)
- Toggle: env var TIER3_ENABLED (default OFF)
- Tier 3 persistence is intentionally NOT called from Tier 2 allocator-pdf endpoint right now

## Key code files
- backend/app/api/routes.py
  - Main API router and endpoints
  - StrategySummary model
  - Tier 3 toggle logic
  - Allocator PDF endpoint enriches top strategy and calls build_allocator_view_pdf()

- backend/app/services/reporting/allocator/allocator_pdf.py
  - build_allocator_view_pdf(strategy, signature) -> bytes
  - Includes SparklineWithDD flowable
  - IMPORTANT FIX: Sparkline auto-shrinks to Table cell width in wrap() and clips chart region to prevent “blue line” bleed

- backend/app/services/reporting/page1/layout.py
  - _draw_footer(canvas, doc, signature) used on first+later pages for PDF footer signature stamp

## Determinism + signatures
- Page 1 PDF uses analysis_signature(payload)
- Compare PDFs use _stable_results_signature(results)
- Allocator PDF uses _stable_results_signature(ranked results list)

## Known pain point that was fixed
- “Blue line” rendering bug in allocator_view.pdf caused by sparkline width exceeding the table cell width
- Fix is implemented in SparklineWithDD.wrap() + clip rect inside draw()

## Tier 3 roadmap (D plan)
Phase 1: Monitoring Engine (Strategy Health Monitor)
- roll/boot drift + DD envelope + regime shift signals
- output: Current Health (OK/WARNING/CRITICAL) + recommended sizing action

Phase 2: Portfolio Intelligence Engine (math core)
- returns matrix + correlation graph + clustering + diversification score
- output: redundancy + cluster map + portfolio-level risk summary

Phase 3: Portfolio Interaction layer
- allocation balancing suggestions using correlation + health signals
- “what to reduce/what to increase” based on redundancy + drift

## Buyer-facing positioning
Tier 1 = evaluate
Tier 2 = approve (committee memo)
Tier 3 = oversee + optimize (monitor + portfolio intelligence)