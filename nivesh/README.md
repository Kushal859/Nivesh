# Nivesh — India AI Equity Analyst Backend

Production-grade Django backend. 8 apps, 11 models, full Celery pipeline, Razorpay subscriptions.

## Quick Start (5 minutes)

```bash
# 1. Clone and enter
git clone <your-repo> && cd nivesh

# 2. Copy env
cp .env.example .env
# Edit .env with your keys (ANTHROPIC_API_KEY is required for AI narratives)

# 3. Run setup
bash scripts/setup.sh

# 4. Start server
python manage.py runserver
```

## API Endpoints

| Method | Endpoint | Auth | Tier |
|--------|----------|------|------|
| POST | `/api/v1/auth/register/` | No | Any |
| POST | `/api/v1/auth/login/` | No | Any |
| GET | `/api/v1/auth/me/` | Token | Any |
| GET | `/api/v1/companies/` | No | Free (limited) |
| GET | `/api/v1/companies/{ticker}/` | Token | Free (5/day) |
| GET | `/api/v1/companies/{ticker}/analysis/` | Token | Pro+ |
| GET | `/api/v1/screener/?pe_max=20&roe_min=15` | No | Any |
| GET | `/api/v1/watchlist/` | Token | Any |
| POST | `/api/v1/subscription/create/` | Token | Any |
| POST | `/api/v1/subscription/webhook/` | Razorpay | System |
| GET | `/api/v1/health/` | No | Any |

## Tier System

| Tier | Price | Daily lookups | AI Narrative | PDF |
|------|-------|---------------|--------------|-----|
| Free | ₹0 | 5 | ✗ | ✗ |
| Pro | ₹299/mo | 500 | ✓ | ✓ |
| CA | ₹2,999/mo | 5,000 | ✓ | ✓ + White-label |

## Architecture

```
Frontend (nivesh.html) → Django REST API → PostgreSQL
                                        ↓
                              Celery Worker (async)
                                        ↓
                              BSE XBRL + NSE APIs
                              Anthropic Claude API
                              Razorpay Webhooks
```

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `ingest_bse_filings` | Daily 8PM IST | Pull new XBRL filings |
| `refresh_all_ratios` | Daily 9PM IST | Recompute all ratios |
| `refresh_sector_medians` | Daily 9:30PM IST | Update benchmarks |
| `send_weekly_digest` | Monday 8AM IST | Email digest to Pro+ |

## Deploy to Render.com (recommended, free tier available)

```bash
# 1. Push to GitHub
git init && git add . && git commit -m "Initial Nivesh backend"
git remote add origin <your-github-repo>
git push -u origin main

# 2. Go to render.com → New → Blueprint
# 3. Connect GitHub repo
# 4. render.yaml handles everything automatically
# 5. Add env vars in Render dashboard:
#    ANTHROPIC_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
```

## Deploy to Railway.app (simplest)

```bash
railway login
railway init
railway add --database postgresql
railway add --redis
railway up
```

## Environment Variables

See `.env.example` for all required variables.
Required for production: `DJANGO_SECRET_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`
Required for payments: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_PLAN_PRO`, `RAZORPAY_PLAN_CA`

## Adding More Companies

```python
# Via Django shell
from ingestion.tasks import seed_demo_data
seed_demo_data()  # loads 8 seeded companies

# Or via admin at /admin/companies/company/add/
# Then trigger ratio refresh:
from analysis.tasks import refresh_all_ratios
refresh_all_ratios()
```

## Connect Frontend

Update `nivesh.html` — replace the direct Anthropic API call with:
```javascript
const res = await fetch('https://your-backend.onrender.com/api/v1/companies/TCS/analysis/', {
  headers: { 'Authorization': `Token ${userToken}` }
});
```
