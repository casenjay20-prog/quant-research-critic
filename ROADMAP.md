# Quant Research Critic — Roadmap

## Current (Stable)
Tier 1: /v1/analyze, /v1/compare
Tier 2: /v1/report/pdf, /v1/compare/pdf, /v1/compare/allocator-pdf (paid)

## Next (Tier 3 — Plan D)

### Phase 1 — Monitoring Engine (Health Monitor)
Add:
- backend/app/services/monitoring/health.py
- backend/app/services/monitoring/signals.py
- backend/app/services/monitoring/models.py

Change:
- backend/app/api/routes.py (new endpoints)

### Phase 2 — Portfolio Intelligence (math core)
Add:
- backend/app/services/portfolio/returns_matrix.py
- backend/app/services/portfolio/correlation.py
- backend/app/services/portfolio/clustering.py
- backend/app/services/portfolio/diversification.py
- backend/app/services/portfolio/models.py

Change:
- backend/app/api/routes.py (new endpoints)

### Phase 3 — Portfolio Interaction layer
Add:
- backend/app/services/portfolio/recommendations.py

Change:
- backend/app/api/routes.py
- (optional later) allocator_pdf.py for portfolio appendix page