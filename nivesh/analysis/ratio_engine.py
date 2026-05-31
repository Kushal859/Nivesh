"""
Ratio Engine — computes all CFA L1 ratios from FinancialStatement data.
Pure functions, fully testable, no Django ORM dependencies.
"""
from decimal import Decimal, InvalidOperation
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def safe_div(numerator, denominator, default=None) -> Optional[Decimal]:
    """Safe division returning None instead of raising."""
    try:
        n = Decimal(str(numerator))
        d = Decimal(str(denominator))
        if d == 0:
            return default
        result = n / d
        # Clamp absurd values
        if abs(result) > Decimal('99999'):
            return default
        return result.quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return default


def compute_ratios(stmt, price: Optional[Decimal] = None) -> dict:
    """
    Compute all ratios from a FinancialStatement instance + optional current price.
    Returns a flat dict ready to save into CompanyRatios.
    """
    r = {}

    # ── VALUATION ──────────────────────────────────────────
    if price and stmt.eps and stmt.eps > 0:
        r['pe_ratio'] = safe_div(price, stmt.eps)

    if price and stmt.total_equity and stmt.total_equity > 0:
        # Approximate shares from mcap / price — use equity per share
        pass  # Needs shares_outstanding; left for ingestion to populate

    # ── PROFITABILITY ──────────────────────────────────────
    rev = stmt.revenue or stmt.total_income
    if rev and rev > 0:
        if stmt.ebitda:
            v = safe_div(stmt.ebitda, rev)
            r['ebitda_margin'] = v * 100 if v is not None else None
        if stmt.pat:
            v = safe_div(stmt.pat, rev)
            r['net_margin'] = v * 100 if v is not None else None
        if stmt.ebit:
            v = safe_div(stmt.ebit, rev)
            r['ebit_margin'] = v * 100 if v is not None else None

    if stmt.total_equity and stmt.total_equity > 0 and stmt.pat:
        v = safe_div(stmt.pat, stmt.total_equity)
        r['roe'] = v * 100 if v is not None else None

    if stmt.total_assets and stmt.current_liabilities:
        capital_employed = stmt.total_assets - stmt.current_liabilities
        if capital_employed > 0 and stmt.ebit:
            v = safe_div(stmt.ebit, capital_employed)
            r['roce'] = v * 100 if v is not None else None

    if stmt.total_assets and stmt.total_assets > 0 and stmt.pat:
        v = safe_div(stmt.pat, stmt.total_assets)
        r['roa'] = v * 100 if v is not None else None

    # ── LEVERAGE ──────────────────────────────────────────
    if stmt.total_equity and stmt.total_equity > 0:
        r['debt_equity'] = safe_div(stmt.total_debt, stmt.total_equity) if stmt.total_debt else Decimal('0.00')

    if stmt.interest_expense and stmt.interest_expense > 0:
        r['interest_coverage'] = safe_div(stmt.ebit, stmt.interest_expense) if stmt.ebit else None

    if stmt.ebitda and stmt.ebitda > 0:
        net_debt = (stmt.total_debt or 0) - (stmt.cash_equivalents or 0)
        r['net_debt_ebitda'] = safe_div(net_debt, stmt.ebitda)

    # ── LIQUIDITY ─────────────────────────────────────────
    if stmt.current_liabilities and stmt.current_liabilities > 0:
        r['current_ratio'] = safe_div(stmt.current_assets, stmt.current_liabilities) if stmt.current_assets else None
        liquid = (stmt.current_assets or 0) - (stmt.inventory or 0)
        r['quick_ratio']   = safe_div(liquid, stmt.current_liabilities)

    # ── EFFICIENCY ────────────────────────────────────────
    if stmt.total_assets and stmt.total_assets > 0 and rev:
        r['asset_turnover'] = safe_div(rev, stmt.total_assets)

    if rev and stmt.debtors:
        r['debtor_days'] = safe_div(stmt.debtors * 365, rev)

    if rev and stmt.inventory:
        cogs = rev * Decimal('0.6')  # approximation without explicit COGS
        r['inventory_days'] = safe_div(stmt.inventory * 365, cogs)

    # ── SHAREHOLDER / INDIA-SPECIFIC ──────────────────────
    r['promoter_holding'] = stmt.promoter_holding
    r['promoter_pledged'] = stmt.promoter_pledged or Decimal('0')

    if stmt.cfo and stmt.total_assets and stmt.total_assets > 0 and stmt.fcf:
        v = safe_div(stmt.fcf, stmt.total_assets)
        r['fcf_yield'] = v * 100 if v is not None else None

    # Clean None values
    return {k: v for k, v in r.items() if v is not None}


def detect_red_flags(company, stmts: list, ratios) -> list:
    """
    India-specific red flag detection.
    stmts: list of FinancialStatement ordered newest first (up to 5 years).
    ratios: latest CompanyRatios instance.
    Returns list of dicts ready to bulk-create RedFlag instances.
    """
    flags = []

    def add(flag_type, severity, title, detail):
        flags.append({
            'company': company,
            'fiscal_year': stmts[0].fiscal_year if stmts else 2025,
            'flag_type': flag_type,
            'severity': severity,
            'title': title,
            'detail': detail,
        })

    if not stmts or not ratios:
        return flags

    latest = stmts[0]

    # ── 1. Promoter pledging ───────────────────────────────
    pledged = float(ratios.promoter_pledged or 0)
    if pledged > 50:
        add('promoter_pledge', 'high',
            f'Promoter pledging critical: {pledged:.1f}%',
            f'Over 50% of promoter shares are pledged. This creates forced-selling risk if share price declines. Watch for margin calls.')
    elif pledged > 20:
        add('promoter_pledge', 'med',
            f'Promoter pledging elevated: {pledged:.1f}%',
            f'{pledged:.1f}% of promoter shares pledged. Elevated but not critical. Monitor quarterly disclosures.')

    # ── 2. Debtor days rising trend ───────────────────────
    if len(stmts) >= 3:
        debtor_series = []
        for s in stmts[:3]:
            rev = float(s.revenue or s.total_income or 0)
            deb = float(s.debtors or 0)
            if rev > 0 and deb > 0:
                debtor_series.append(deb * 365 / rev)
        if len(debtor_series) == 3 and debtor_series[0] > debtor_series[1] > debtor_series[2]:
            add('debtor_days_rising', 'med',
                'Debtor days rising 3 consecutive years',
                f'Debtor days: {debtor_series[2]:.0f} → {debtor_series[1]:.0f} → {debtor_series[0]:.0f}. '
                'Consistently rising debtor days may signal channel stuffing or collection weakness.')

    # ── 3. Negative operating cash flow ───────────────────
    if len(stmts) >= 2:
        neg_cfo = [s for s in stmts[:3] if s.cfo and s.cfo < 0]
        if len(neg_cfo) >= 2:
            add('cfo_negative', 'high',
                'Negative operating cash flow — 2+ consecutive years',
                'Operating cash flow negative in 2 or more of last 3 years. '
                'A company consistently burning cash from operations requires external funding to survive.')
        elif len(neg_cfo) == 1:
            add('cfo_negative', 'low',
                'Operating cash flow negative last year',
                'CFO turned negative last year. Watch if this reverses next quarter or becomes a trend.')

    # ── 4. Interest coverage ratio ────────────────────────
    icr = float(ratios.interest_coverage or 99)
    if icr < 1.5 and latest.interest_expense and latest.interest_expense > 0:
        add('low_icr', 'high',
            f'Interest coverage dangerously low: {icr:.1f}x',
            f'EBIT covers interest only {icr:.1f}x. Ratio below 1.5x means the company cannot comfortably service its debt from operations.')
    elif icr < 3.0 and latest.interest_expense and latest.interest_expense > 0:
        add('low_icr', 'med',
            f'Interest coverage below 3x: {icr:.1f}x',
            f'ICR of {icr:.1f}x is below the comfortable threshold of 3x. Any earnings pressure could stress debt servicing.')

    # ── 5. PAT declining trend ────────────────────────────
    if len(stmts) >= 3:
        pats = [float(s.pat or 0) for s in stmts[:3]]
        if pats[0] < pats[1] < pats[2] and pats[2] > 0:
            dec1 = (pats[1]-pats[0])/pats[1]*100
            dec2 = (pats[2]-pats[1])/pats[2]*100
            add('pat_declining', 'med',
                'Net profit declining 3 consecutive years',
                f'PAT has fallen {dec2:.1f}% then {dec1:.1f}% in last 2 years. Sustained profitability erosion warrants investigation.')

    # ── 6. Revenue stagnation / decline ───────────────────
    if len(stmts) >= 2 and stmts[0].revenue and stmts[1].revenue:
        rev_growth = float((stmts[0].revenue - stmts[1].revenue) / stmts[1].revenue * 100)
        if rev_growth < -5:
            add('revenue_declining', 'high',
                f'Revenue declined {abs(rev_growth):.1f}% YoY',
                f'Revenue fell {abs(rev_growth):.1f}% year-on-year. Meaningful revenue decline is a serious red flag unless driven by one-off divestiture.')
        elif rev_growth < 0:
            add('revenue_declining', 'med',
                f'Revenue flat/declining: {rev_growth:.1f}% YoY',
                'Revenue growth marginally negative. Watch next quarter to determine if this is a trend or temporary blip.')

    # ── 7. Low promoter holding ───────────────────────────
    promo = float(ratios.promoter_holding or 100)
    if promo < 25:
        add('low_promoter_holding', 'high',
            f'Very low promoter holding: {promo:.1f}%',
            f'Promoter holds only {promo:.1f}% — unusually low. Increases vulnerability to hostile takeover attempts or activist investor pressure.')
    elif promo < 40:
        add('low_promoter_holding', 'med',
            f'Below-average promoter holding: {promo:.1f}%',
            f'Promoter stake at {promo:.1f}% is below the typically preferred 40%+ threshold. Monitor for further dilution.')

    # ── 8. High debt/equity ───────────────────────────────
    de = float(ratios.debt_equity or 0)
    if de > 2.0:
        add('high_debt', 'med',
            f'High D/E ratio: {de:.1f}x',
            f'Debt-to-equity of {de:.1f}x is elevated. In rising interest rate environments, high-leverage companies face margin compression and refinancing risk.')

    return flags
