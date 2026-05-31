from django.db import models


class Company(models.Model):
    """Master company table — one row per listed company."""
    ticker      = models.CharField(max_length=20, unique=True, db_index=True)
    bse_code    = models.CharField(max_length=10, blank=True, db_index=True)
    name        = models.CharField(max_length=200)
    sector      = models.CharField(max_length=100, db_index=True)
    industry    = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    mcap_cr     = models.DecimalField(max_digits=14, decimal_places=2, null=True)  # ₹ Crore
    is_nifty50  = models.BooleanField(default=False)
    is_nifty500 = models.BooleanField(default=False)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table  = 'companies'
        ordering  = ['name']
        verbose_name_plural = 'companies'

    def __str__(self):
        return f'{self.ticker} — {self.name}'


class FinancialStatement(models.Model):
    """
    Normalised financial statement data.
    One row per company per fiscal year.
    Source: BSE XBRL filings.
    """
    PERIOD_ANNUAL    = 'annual'
    PERIOD_Q1        = 'q1'
    PERIOD_Q2        = 'q2'
    PERIOD_Q3        = 'q3'
    PERIOD_Q4        = 'q4'
    PERIOD_CHOICES   = [(PERIOD_ANNUAL,'Annual'),(PERIOD_Q1,'Q1'),(PERIOD_Q2,'Q2'),(PERIOD_Q3,'Q3'),(PERIOD_Q4,'Q4')]

    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='statements')
    fiscal_year      = models.PositiveSmallIntegerField()   # e.g. 2025 means FY2025
    period           = models.CharField(max_length=10, choices=PERIOD_CHOICES, default=PERIOD_ANNUAL)

    # Income Statement (₹ Crore)
    revenue          = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    other_income     = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    total_income     = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    ebitda           = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    depreciation     = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    ebit             = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    interest_expense = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    pbt              = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    tax              = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    pat              = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    eps              = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    # Balance Sheet
    total_assets     = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    current_assets   = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    current_liabilities = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    total_debt       = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    total_equity     = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    reserves         = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    cash_equivalents = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    debtors          = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    inventory        = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    # Cash Flow
    cfo              = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    capex            = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    fcf              = models.DecimalField(max_digits=14, decimal_places=2, null=True)

    # Shareholding
    promoter_holding = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    promoter_pledged = models.DecimalField(max_digits=5, decimal_places=2, null=True, default=0)
    fii_holding      = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    dii_holding      = models.DecimalField(max_digits=5, decimal_places=2, null=True)

    # Metadata
    source           = models.CharField(max_length=30, default='bse_xbrl')
    raw_data         = models.JSONField(default=dict)   # original XBRL payload
    filing_date      = models.DateField(null=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'financial_statements'
        unique_together = ('company', 'fiscal_year', 'period')
        ordering        = ['-fiscal_year', 'period']

    def __str__(self):
        return f'{self.company.ticker} FY{self.fiscal_year} {self.period}'


class DailyPrice(models.Model):
    """NSE end-of-day price data."""
    company   = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='prices')
    date      = models.DateField(db_index=True)
    open      = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    high      = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    low       = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    close     = models.DecimalField(max_digits=10, decimal_places=2)
    volume    = models.BigIntegerField(null=True)
    market_cap_cr = models.DecimalField(max_digits=14, decimal_places=2, null=True)

    class Meta:
        db_table        = 'daily_prices'
        unique_together = ('company', 'date')
        ordering        = ['-date']
