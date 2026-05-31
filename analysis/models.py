from django.db import models
from companies.models import Company


class CompanyRatios(models.Model):
    """
    Pre-computed CFA L1 ratios.
    Refreshed nightly by Celery task after new filings arrive.
    """
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ratios')
    fiscal_year   = models.PositiveSmallIntegerField()

    # Valuation
    pe_ratio      = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    pb_ratio      = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    ev_ebitda     = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    price_sales   = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    # Profitability
    roe           = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    roce          = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    roa           = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    gross_margin  = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    ebitda_margin = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    ebit_margin   = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %
    net_margin    = models.DecimalField(max_digits=7, decimal_places=2, null=True)   # %

    # Leverage
    debt_equity   = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    net_debt_ebitda = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    interest_coverage = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    # Liquidity
    current_ratio = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    quick_ratio   = models.DecimalField(max_digits=8, decimal_places=2, null=True)

    # Efficiency
    asset_turnover    = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    inventory_days    = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    debtor_days       = models.DecimalField(max_digits=8, decimal_places=2, null=True)

    # Shareholder returns
    dividend_yield    = models.DecimalField(max_digits=6, decimal_places=2, null=True)  # %
    eps_growth_yoy    = models.DecimalField(max_digits=8, decimal_places=2, null=True)  # %
    revenue_growth_yoy = models.DecimalField(max_digits=8, decimal_places=2, null=True) # %

    # India-specific
    promoter_holding  = models.DecimalField(max_digits=5, decimal_places=2, null=True)  # %
    promoter_pledged  = models.DecimalField(max_digits=5, decimal_places=2, null=True)  # %
    fcf_yield         = models.DecimalField(max_digits=7, decimal_places=2, null=True)  # %

    computed_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'company_ratios'
        unique_together = ('company', 'fiscal_year')
        ordering        = ['-fiscal_year']

    def __str__(self):
        return f'{self.company.ticker} FY{self.fiscal_year} ratios'


class RedFlag(models.Model):
    """Algorithmic red flags per company per year."""
    SEV_HIGH   = 'high'
    SEV_MEDIUM = 'med'
    SEV_LOW    = 'low'
    SEV_CHOICES = [(SEV_HIGH,'High'),(SEV_MEDIUM,'Medium'),(SEV_LOW,'Low')]

    FLAG_PROMOTER_PLEDGE    = 'promoter_pledge'
    FLAG_DEBTOR_DAYS        = 'debtor_days_rising'
    FLAG_CFO_NEGATIVE       = 'cfo_negative'
    FLAG_INTEREST_COVERAGE  = 'low_icr'
    FLAG_PAT_DECLINING      = 'pat_declining'
    FLAG_REVENUE_DECLINING  = 'revenue_declining'
    FLAG_HIGH_DEBT          = 'high_debt'
    FLAG_LOW_PROMOTER       = 'low_promoter_holding'

    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='flags')
    fiscal_year = models.PositiveSmallIntegerField()
    flag_type   = models.CharField(max_length=50)
    severity    = models.CharField(max_length=10, choices=SEV_CHOICES)
    title       = models.CharField(max_length=200)
    detail      = models.TextField()
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'red_flags'
        ordering = ['severity', '-created_at']

    def __str__(self):
        return f'{self.company.ticker} [{self.severity.upper()}] {self.title}'


class SectorMedian(models.Model):
    """Pre-computed sector median ratios for benchmarking."""
    sector      = models.CharField(max_length=100, db_index=True)
    fiscal_year = models.PositiveSmallIntegerField()
    pe_median   = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    pb_median   = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    roe_median  = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    roce_median = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    npm_median  = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    ebm_median  = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    de_median   = models.DecimalField(max_digits=7, decimal_places=2, null=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'sector_medians'
        unique_together = ('sector', 'fiscal_year')

    def __str__(self):
        return f'{self.sector} FY{self.fiscal_year} medians'


class AIAnalysis(models.Model):
    """Cached AI narrative per company per year."""
    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ai_analyses')
    fiscal_year = models.PositiveSmallIntegerField()
    narrative   = models.TextField()
    model_used  = models.CharField(max_length=60)
    prompt_hash = models.CharField(max_length=64)   # SHA256 of input — detect stale cache
    tokens_used = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'ai_analyses'
        unique_together = ('company', 'fiscal_year')
        ordering        = ['-updated_at']

    def __str__(self):
        return f'{self.company.ticker} FY{self.fiscal_year} AI analysis'


class MomentumSnapshot(models.Model):
    """
    Price momentum metrics computed from DailyPrice history.
    Refreshed nightly. One row per company per period.
    """
    PERIOD_3M  = '3m'
    PERIOD_6M  = '6m'
    PERIOD_12M = '12m'
    PERIOD_CHOICES = [(PERIOD_3M,'3 Month'),(PERIOD_6M,'6 Month'),(PERIOD_12M,'12 Month')]

    company      = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='momentum')
    period       = models.CharField(max_length=5, choices=PERIOD_CHOICES)

    # Price returns
    return_1m    = models.DecimalField(max_digits=8, decimal_places=2, null=True)   # %
    return_3m    = models.DecimalField(max_digits=8, decimal_places=2, null=True)   # %
    return_6m    = models.DecimalField(max_digits=8, decimal_places=2, null=True)   # %
    return_12m   = models.DecimalField(max_digits=8, decimal_places=2, null=True)   # %

    # Technical indicators
    rsi_14       = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    ma_20        = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    ma_50        = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    ma_200       = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    high_52w     = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    low_52w      = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    current_price= models.DecimalField(max_digits=10, decimal_places=2, null=True)

    # Derived signals
    signal       = models.CharField(max_length=30, blank=True)   # e.g. BULLISH_TREND
    emotion      = models.CharField(max_length=30, blank=True)   # e.g. OPTIMISM
    emotion_icon = models.CharField(max_length=4,  blank=True)

    # Shareholding summary
    promoter_current = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    promoter_trend_6q= models.DecimalField(max_digits=5, decimal_places=2, null=True)
    fii_current      = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    fii_trend_6q     = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    dii_current      = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    dii_trend_6q     = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    pledging         = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    computed_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'momentum_snapshots'
        unique_together = ('company', 'period')
        ordering        = ['company', 'period']

    def __str__(self):
        return f'{self.company.ticker} {self.period} momentum'
