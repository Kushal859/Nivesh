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

        prompt = f"""You are a senior Indian equity research analyst (CFA charterholder). Write a rigorous, data-driven analyst note for {company.name} ({company.ticker}) in the {company.sector} sector.

FINANCIAL DATA — FY{fiscal_year}:
P/E: {ratios.pe_ratio}x (sector median: {sm_pe}x) | P/B: {ratios.pb_ratio}x
ROE: {ratios.roe}% (sector median: {sm_roe}%) | ROCE: {ratios.roce}%
Net margin: {ratios.net_margin}% (sector median: {sm_npm}%) | EBITDA margin: {ratios.ebitda_margin}%
D/E: {ratios.debt_equity}x (sector median: {sm_de}x) | Current ratio: {ratios.current_ratio}x
Interest coverage: {ratios.interest_coverage}x | Asset turnover: {ratios.asset_turnover}x
Promoter holding: {ratios.promoter_holding}% (pledged: {ratios.promoter_pledged}%)
Dividend yield: {ratios.dividend_yield}%

REVENUE TREND (₹ Cr): {rev_trend}
PAT TREND (₹ Cr): {pat_trend}

ALGORITHMIC RED FLAGS DETECTED:
{flag_lines if flag_lines else 'No significant flags detected.'}

Write EXACTLY 3 paragraphs (3–4 sentences each). Use plain English. Be specific with numbers. India market context throughout.

Paragraph 1 — Business quality and financial health: What the ratios reveal about this business model and its financial strength or weakness. Reference specific numbers and compare to sector.

Paragraph 2 — Key risks: The 2–3 most material risks specific to this company. Reference Indian regulatory context (SEBI, RBI, sector regulations) where relevant. Be direct and honest about concerns.

Paragraph 3 — Valuation and outlook: Is the stock cheap, fairly valued, or expensive? What is the key metric to watch next quarter? What would make you more positive or negative on the thesis?

Rules: No buy/sell advice. No bullet points. Paragraph format only. No generic statements — every sentence must reference specific data from above."""

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
