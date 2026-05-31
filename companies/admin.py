from django.contrib import admin
from .models import Company, FinancialStatement, DailyPrice

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display  = ['ticker','name','sector','mcap_cr','is_nifty50','is_active']
    search_fields = ['ticker','name','sector']
    list_filter   = ['sector','is_nifty50','is_active']

@admin.register(FinancialStatement)
class FSAdmin(admin.ModelAdmin):
    list_display  = ['company','fiscal_year','period','revenue','pat']
    list_filter   = ['period','fiscal_year']
    search_fields = ['company__ticker']

admin.site.register(DailyPrice)
