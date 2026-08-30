# Final cleanup changes

This package is the pure-comparables version of EquityComps.

## Removed
- Analyst sentiment, analyst provider integrations, Finnhub integrations.
- FinBERT, news sentiment, news and market-intelligence services.
- Sentiment scheduler jobs and configuration.
- Top Opportunities page and opportunity score.
- Stock detail research page and sentiment-driven detail API.
- Sentiment/opportunity API endpoints and frontend columns.

## Architecture correction
- The FastAPI API process no longer starts the scheduler.
- Use `python -m app.jobs.run_scheduler` as the dedicated scheduler process.
- API requests read prepared database data; sector/universe switching does not run SEC extraction or scheduler work.

## Financial calculation correction
- Recalculation prefers TTM flow values, then correctly annualized flow values, then full-year raw values.
- Point-in-time values such as debt, cash, equity, shares and price are not annualized by this fallback logic.

## Database migration
Before starting against an existing database, run:

`psql "$SYNC_DATABASE_URL" -f backend/migrations/0001_remove_sentiment.sql`

Then start the API and scheduler as separate processes.
