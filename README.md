# Nivesh — India AI Equity Analyst

**v2.0** — Now with Momentum Engine + Plain-English AI explanations.

## What's new in v2
- **📈 Momentum tab**: RSI, 3M/6M/1Y returns, price signal, investor emotion gauge
- **👥 Shareholding tracker**: Promoter/FII/DII trends over 6 quarters with plain-English interpretation
- **🗣️ Plain-English AI**: All AI summaries now written in simple everyday language — no finance jargon
- **New API endpoints**: `/companies/{ticker}/momentum/` and `/companies/{ticker}/momentum/narrative/`

## Quick Start
```bash
cp .env.example .env   # fill in DJANGO_SECRET_KEY and ANTHROPIC_API_KEY
bash scripts/setup.sh
python manage.py runserver
```

## API Endpoints
| Endpoint | Auth | Description |
|----------|------|-------------|
| GET `/api/v1/companies/` | None | List all companies |
| GET `/api/v1/companies/{ticker}/` | Token | Company detail + ratios |
| GET `/api/v1/companies/{ticker}/analysis/` | Pro+ | Plain-English AI fundamental analysis |
| GET `/api/v1/companies/{ticker}/momentum/?period=6m` | None | Momentum snapshot (3m/6m/12m) |
| GET `/api/v1/companies/{ticker}/momentum/narrative/` | Pro+ | Plain-English momentum explanation |
| GET `/api/v1/screener/` | None | Filter stocks by ratios |
| POST `/api/v1/auth/register/` | None | Create account |
| POST `/api/v1/auth/login/` | None | Sign in |

## Deploy to Render.com
Push to GitHub → render.com → New Blueprint → connect repo → render.yaml handles everything.

Add env vars: `DJANGO_SECRET_KEY`, `ANTHROPIC_API_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
