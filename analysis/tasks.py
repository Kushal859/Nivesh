"""Celery tasks for analysis: ratio refresh, sector medians, AI narrative."""
import hashlib, json, logging
from decimal import Decimal
from django.conf import settings
from django.db.models import Avg, Count
from celery import shared_task
import anthropic

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def refresh_all_ratios(self):
    """Nightly task: recompute ratios for every active company."""
    from companies.models import Company, FinancialStatement
    from analysis.models import CompanyRatios, RedFlag
    from analysis.ratio_engine import compute_ratios, detect_red_flags

    companies = Company.objects.filter(is_active=True)
    updated, failed = 0, 0

    for company in companies:
        try:
            stmts = list(
                FinancialStatement.objects
                .filter(company=company, period='annual')
                .order_by('-fiscal_year')[:5]
            )
            if not stmts:
                continue

            latest = stmts[0]

            # Get latest price for PE calculation
            try:
                from companies.models import DailyPrice
                price_obj = DailyPrice.objects.filter(company=company).latest('date')
                price = price_obj.close
            except Exception:
                price = None

            ratio_data = compute_ratios(latest, price=price)
            if not ratio_data:
                continue

            ratios_obj, _ = CompanyRatios.objects.update_or_create(
                company=company, fiscal_year=latest.fiscal_year,
                defaults=ratio_data
            )

            # Refresh red flags
            RedFlag.objects.filter(company=company, fiscal_year=latest.fiscal_year).delete()
            flags = detect_red_flags(company, stmts, ratios_obj)
            RedFlag.objects.bulk_create([
                RedFlag(**f) for f in flags
            ], ignore_conflicts=True)

            updated += 1
        except Exception as exc:
            logger.error(f'Ratio refresh failed for {company.ticker}: {exc}')
            failed += 1

    logger.info(f'Ratio refresh complete: {updated} updated, {failed} failed')
    return {'updated': updated, 'failed': failed}


@shared_task
def refresh_sector_medians():
    """Compute sector-level median ratios for benchmarking."""
    from analysis.models import CompanyRatios, SectorMedian
    from companies.models import Company

    from datetime import date as _d
    _t = _d.today()
    current_year = _t.year if _t.month >= 4 else _t.year - 1
    sectors = Company.objects.filter(is_active=True).values_list('sector', flat=True).distinct()

    for sector in sectors:
        tickers = Company.objects.filter(sector=sector, is_active=True).values_list('id', flat=True)
        ratios  = CompanyRatios.objects.filter(company_id__in=tickers, fiscal_year=current_year)

        if ratios.count() < 3:
            continue

        import statistics
        def med(vals):
            cleaned = [float(v) for v in vals if v is not None]
            return round(statistics.median(cleaned), 2) if len(cleaned) >= 2 else None

        pe_vals  = list(ratios.values_list('pe_ratio',      flat=True))
        pb_vals  = list(ratios.values_list('pb_ratio',      flat=True))
        roe_vals = list(ratios.values_list('roe',           flat=True))
        roc_vals = list(ratios.values_list('roce',          flat=True))
        npm_vals = list(ratios.values_list('net_margin',    flat=True))
        ebm_vals = list(ratios.values_list('ebitda_margin', flat=True))
        de_vals  = list(ratios.values_list('debt_equity',   flat=True))

        SectorMedian.objects.update_or_create(
            sector=sector, fiscal_year=current_year,
            defaults={
                'pe_median':  med(pe_vals),
                'pb_median':  med(pb_vals),
                'roe_median': med(roe_vals),
                'roce_median':med(roc_vals),
                'npm_median': med(npm_vals),
                'ebm_median': med(ebm_vals),
                'de_median':  med(de_vals),
            }
        )

    logger.info(f'Sector medians refreshed for {len(list(sectors))} sectors')


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_ai_narrative(self, company_id: int, fiscal_year: int, force: bool = False):
    """
    Generate and cache AI analyst narrative for a company.
    Called on-demand when a user requests it (Pro+ tier).
    """
    from companies.models import Company, FinancialStatement
    from analysis.models import CompanyRatios, RedFlag, SectorMedian, AIAnalysis

    try:
        company = Company.objects.get(id=company_id)
        ratios  = CompanyRatios.objects.filter(company=company, fiscal_year=fiscal_year).first()
        flags   = RedFlag.objects.filter(company=company, fiscal_year=fiscal_year, is_active=True)
        stmts   = FinancialStatement.objects.filter(company=company, period='annual').order_by('-fiscal_year')[:5]
        sector_med = SectorMedian.objects.filter(sector=company.sector, fiscal_year=fiscal_year).first()

        if not ratios:
            return {'error': 'No ratios available'}

        # Build prompt input dict for hashing
        prompt_data = {
            'ticker': company.ticker, 'fy': fiscal_year,
            'pe': str(ratios.pe_ratio), 'pb': str(ratios.pb_ratio),
            'roe': str(ratios.roe), 'npm': str(ratios.net_margin),
        }
        prompt_hash = hashlib.sha256(json.dumps(prompt_data, sort_keys=True).encode()).hexdigest()

        # Check cache
        existing = AIAnalysis.objects.filter(company=company, fiscal_year=fiscal_year).first()
        if existing and existing.prompt_hash == prompt_hash and not force:
            return {'narrative': existing.narrative, 'cached': True}

        # Build prompt
        rev_trend = ' | '.join([
            f"FY{s.fiscal_year}: ₹{int(s.revenue or 0):,} Cr"
            for s in reversed(list(stmts))
        ])
        pat_trend = ' | '.join([
            f"FY{s.fiscal_year}: ₹{int(s.pat or 0):,} Cr"
            for s in reversed(list(stmts))
        ])

        sm_pe  = float(sector_med.pe_median)  if sector_med and sector_med.pe_median  else 'N/A'
        sm_roe = float(sector_med.roe_median) if sector_med and sector_med.roe_median else 'N/A'
        sm_npm = float(sector_med.npm_median) if sector_med and sector_med.npm_median else 'N/A'
        sm_de  = float(sector_med.de_median)  if sector_med and sector_med.de_median  else 'N/A'

        flag_lines = '\n'.join([
            f"[{f.severity.upper()}] {f.title}: {f.detail}"
            for f in flags
        ])

        # ── TRANSLATE NUMBERS TO PLAIN ENGLISH ──────────────
        def rate(val, good_above, label):
            """Turn a number into a friendly verdict."""
            if val is None: return f"no {label} data available"
            v = float(val)
            if label in ('pe', 'de'):  # lower is better
                if v < good_above * 0.8: return f"{v:.1f} — which is quite low and generally a good sign"
                elif v < good_above * 1.1: return f"{v:.1f} — which is about average for the sector"
                else: return f"{v:.1f} — which is higher than most similar companies"
            else:  # higher is better
                if v > good_above * 1.1: return f"{v:.1f}% — which is better than most similar companies"
                elif v > good_above * 0.8: return f"{v:.1f}% — which is about average for the sector"
                else: return f"{v:.1f}% — which is below what we'd hope for"

        pe_desc  = rate(ratios.pe_ratio,  float(sm_pe)  if sm_pe != 'N/A' else 20, 'pe')
        roe_desc = rate(ratios.roe,       float(sm_roe) if sm_roe != 'N/A' else 15, 'roe')
        npm_desc = rate(ratios.net_margin,float(sm_npm) if sm_npm != 'N/A' else 10, 'npm')
        de_val   = float(ratios.debt_equity or 0)
        de_desc  = f"{de_val:.2f}x — {('very low debt, which is great' if de_val < 0.3 else 'moderate debt, manageable' if de_val < 1.0 else 'quite a bit of debt, worth watching')}"
        promo_val= float(ratios.promoter_holding or 0)
        pledge_val=float(ratios.promoter_pledged or 0)

        prompt = f"""You are writing a simple stock report for someone who has never studied finance.
Use ONLY everyday words that any person can understand. No financial jargon at all.
Write like you are explaining this to a friend who is curious but knows nothing about stocks.

COMPANY: {company.name} ({company.ticker}) — a {company.sector} company

KEY NUMBERS (explained simply):
- For every ₹{pe_desc.split('—')[0].strip()} you invest, you get ₹1 of yearly profit (P/E ratio: {pe_desc})
- The company earns {roe_desc} (return on investment / ROE)
- For every ₹100 of sales, the company keeps {npm_desc} as profit (net margin)
- Debt level: {de_desc}
- The founders/owners hold {promo_val:.1f}% of the company{f" — and {pledge_val:.1f}% of their shares are kept as loan security (this can be risky if the price falls)" if pledge_val > 10 else " — with no shares kept as loan security (which is safe)"}

MONEY OVER THE YEARS (₹ Crore = ₹ 10 million):
Revenue earned: {rev_trend}
Profit after tax: {pat_trend}

THINGS TO WATCH OUT FOR:
{flag_lines if flag_lines else 'No major warning signs found right now.'}

Write EXACTLY 3 short paragraphs. Each should have 3-4 sentences.
NEVER use these words: ratio, metric, valuation, earnings, EBITDA, P/E, ROE, margin, leverage, equity, fiscal, YoY, QoQ, CFA, sector median, benchmark.
Use these instead: profit, money, sales, debt, owners, investors, cheap, expensive, risky, safe.

Paragraph 1 — Is this a healthy business?
Talk about whether the company is making good money and managing its debt well. Is the business doing better or worse over time? Use simple comparisons — like "for every ₹100 they sell, they keep ₹X as profit." Make it feel real and easy to picture.

Paragraph 2 — What could go wrong?
Mention the risks in plain words. If there is a lot of debt, say "they owe quite a bit of money." If promoters have pledged shares, explain it like "the owners have kept their shares as security for a loan — if the stock price falls, they might be forced to sell, which could push the price down more." Be honest but not scary.

Paragraph 3 — Is the price cheap or expensive right now?
Without saying "buy" or "sell," help the reader understand if the current price seems reasonable. If it is expensive compared to similar companies, say so simply. Tell them one thing to watch — like the next quarter's results — to see if the company is improving. End by reminding them this is just information, not advice.

REMEMBER: No jargon. No buy/sell advice. Simple words only. Friendly tone."""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=900,
            messages=[{'role': 'user', 'content': prompt}]
        )

        narrative  = response.content[0].text
        tokens_in  = response.usage.input_tokens
        tokens_out = response.usage.output_tokens

        AIAnalysis.objects.update_or_create(
            company=company, fiscal_year=fiscal_year,
            defaults={
                'narrative':   narrative,
                'model_used':  settings.ANTHROPIC_MODEL,
                'prompt_hash': prompt_hash,
                'tokens_used': tokens_in + tokens_out,
            }
        )

        return {'narrative': narrative, 'cached': False, 'tokens': tokens_in + tokens_out}

    except Exception as exc:
        logger.error(f'AI narrative failed for company {company_id}: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def refresh_momentum(self, company_id: int = None):
    """
    Compute momentum snapshots for one company (or all active companies).
    Runs nightly after price feed is updated.
    """
    from companies.models import Company, DailyPrice, FinancialStatement
    from analysis.models import MomentumSnapshot
    from analysis.momentum_engine import compute_all, compute_sh_trend

    companies = Company.objects.filter(is_active=True)
    if company_id:
        companies = companies.filter(id=company_id)

    updated, failed = 0, 0

    for company in companies:
        try:
            # Fetch up to 52 weeks of close prices (oldest → newest)
            prices = list(
                DailyPrice.objects.filter(company=company)
                .order_by('date')
                .values_list('close', flat=True)
                .last(52*5)   # ~5 years of weekly prices
            )
            closes = [float(p) for p in prices]

            if len(closes) < 10:
                continue

            # Shareholding from annual statements (newest first)
            stmts = list(
                FinancialStatement.objects
                .filter(company=company, period='annual')
                .order_by('-fiscal_year')[:6]
            )
            sh_data = compute_sh_trend(stmts)

            for period in ('3m', '6m', '12m'):
                snapshot = compute_all(closes, period=period)
                if not snapshot:
                    continue
                MomentumSnapshot.objects.update_or_create(
                    company=company, period=period,
                    defaults={**snapshot, **sh_data}
                )
            updated += 1
        except Exception as exc:
            logger.error(f'Momentum refresh failed for {company.ticker}: {exc}')
            failed += 1

    logger.info(f'Momentum refresh: {updated} updated, {failed} failed')
    return {'updated': updated, 'failed': failed}


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_momentum_narrative(self, company_id: int, period: str = '6m', force: bool = False):
    """
    Generate plain-English AI narrative for momentum + shareholder data.
    Stored in AIAnalysis with a momentum-specific key.
    """
    from companies.models import Company
    from analysis.models import MomentumSnapshot, AIAnalysis

    try:
        company  = Company.objects.get(id=company_id)
        snap     = MomentumSnapshot.objects.filter(company=company, period=period).first()
        if not snap:
            return {'error': 'No momentum data available. Run refresh_momentum first.'}

        cache_key_prefix = f'mom_{period}'
        existing = AIAnalysis.objects.filter(
            company=company, fiscal_year=0  # 0 = momentum record
        ).first()

        prompt_hash_input = f"{company.ticker}_{period}_{snap.rsi_14}_{snap.return_6m}_{snap.computed_at}"
        import hashlib
        prompt_hash = hashlib.md5(prompt_hash_input.encode()).hexdigest()

        if existing and existing.prompt_hash == prompt_hash and not force:
            return {'narrative': existing.narrative, 'cached': True}

        # ── BUILD PLAIN-ENGLISH PROMPT ──────────────────────
        # Translate signal to human readable
        signal_map = {
            'STRONG_BULL': 'the stock has been going up strongly',
            'BULLISH':     'the stock has been going up',
            'MILD_UPTREND':'the stock has been slowly going up',
            'SIDEWAYS':    'the stock has not moved much',
            'MILD_DOWNTREND': 'the stock has been slowly going down',
            'BEARISH':     'the stock has been going down',
            'STRONG_BEAR': 'the stock has been falling sharply',
        }
        emotion_map = {
            'EXTREME_GREED': 'most investors are very excited and buying aggressively',
            'GREED':         'most investors feel positive and are buying',
            'OPTIMISM':      'investors feel hopeful',
            'NEUTRAL':       'investors are unsure — some buying, some selling',
            'ANXIETY':       'investors are nervous',
            'FEAR':          'investors are worried and many are selling',
            'PANIC':         'investors are panicking and selling fast',
        }
        signal_desc  = signal_map.get(snap.signal,  snap.signal or 'unclear')
        emotion_desc = emotion_map.get(snap.emotion, snap.emotion or 'uncertain')

        period_label = {'3m': '3 months', '6m': '6 months', '12m': '1 year'}[period]

        promo_dir = 'increasing' if (snap.promoter_trend_6q or 0) > 0.1 else \
                    'decreasing' if (snap.promoter_trend_6q or 0) < -0.1 else 'holding steady'
        fii_dir   = 'buying more' if (snap.fii_trend_6q or 0) > 0.3 else \
                    'selling' if (snap.fii_trend_6q or 0) < -0.3 else 'roughly unchanged'
        dii_dir   = 'buying more' if (snap.dii_trend_6q or 0) > 0.3 else \
                    'selling' if (snap.dii_trend_6q or 0) < -0.3 else 'roughly unchanged'

        prompt = f"""You are writing a short stock analysis for someone who knows nothing about finance.
Use ONLY simple words. No jargon. Explain everything like you're talking to a friend over tea.

STOCK: {company.name} ({company.ticker})
SECTOR: {company.sector}

PRICE MOVEMENT (last {period_label}):
- The stock price has changed by {snap.return_6m}% in 6 months
- In the last 1 month: {snap.return_1m}%
- In the last 3 months: {snap.return_3m}%
- In the last year: {snap.return_12m}%
- Price signal: {signal_desc}
- RSI indicator: {snap.rsi_14} (under 30 = very cheap zone, above 70 = expensive zone, 50 = middle)

CURRENT INVESTOR FEELINGS:
- Overall mood: {snap.emotion or 'unclear'}
- What investors are doing: {emotion_desc}

WHO OWNS THE COMPANY:
- Company founders/owners (Promoters): own {snap.promoter_current}% — and over the last 6 quarters they are {promo_dir}
- Foreign investors (FII): own {snap.fii_current}% — they are currently {fii_dir}
- Indian mutual funds and LIC (DII): own {snap.dii_current}% — they are currently {dii_dir}
- Promoter pledging (shares kept as loan collateral): {snap.pledging}%{' — this is risky' if (snap.pledging or 0) > 20 else ' — this is fine'}

Write EXACTLY 3 short paragraphs. Each paragraph should have 3-4 sentences.
Use very simple words. Avoid all technical terms. Write like you are explaining to someone who has never invested before.
DO NOT say "buy" or "sell". DO NOT give investment advice.

Paragraph 1 — What is the price doing and why does it matter?
Write about the price trend in simple words. Tell them if the price has gone up or down and by how much. Tell them what the RSI number means in simple terms (like "the stock is in a comfortable zone" or "many people are already buying — late entry could be risky"). Keep it simple.

Paragraph 2 — How are investors feeling right now?
Describe the investor mood in everyday language. Are people excited, nervous, or calm about this stock? What does this usually mean? Remember — do not tell them what to do.

Paragraph 3 — Who is putting money in or taking money out?
Talk about the promoters, foreign investors, and Indian mutual funds in simple language. A promoter increasing their stake is like the business owner putting more of their own money in — that is a good sign. Foreign investors selling could mean they are worried, or they might just need the money for other reasons. Keep it balanced and honest.

IMPORTANT RULES:
- No financial jargon whatsoever
- If something looks risky, say it clearly but kindly
- If something looks good, explain why in simple terms  
- Never say "you should buy" or "you should sell"
- End with a reminder that this is for learning only, not financial advice"""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=700,
            messages=[{'role': 'user', 'content': prompt}]
        )

        narrative = response.content[0].text
        tokens    = response.usage.input_tokens + response.usage.output_tokens

        AIAnalysis.objects.update_or_create(
            company=company, fiscal_year=0,
            defaults={
                'narrative':   narrative,
                'model_used':  settings.ANTHROPIC_MODEL,
                'prompt_hash': prompt_hash,
                'tokens_used': tokens,
            }
        )
        return {'narrative': narrative, 'cached': False, 'tokens': tokens}

    except Exception as exc:
        logger.error(f'Momentum narrative failed: {exc}')
        raise self.retry(exc=exc)
