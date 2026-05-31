from django.contrib import admin
from .models import CompanyRatios, RedFlag, SectorMedian, AIAnalysis

@admin.register(CompanyRatios)
class RatiosAdmin(admin.ModelAdmin):
    list_display  = ['company','fiscal_year','pe_ratio','roe','roce','debt_equity']
    list_filter   = ['fiscal_year']
    search_fields = ['company__ticker']

@admin.register(RedFlag)
class RedFlagAdmin(admin.ModelAdmin):
    list_display  = ['company','fiscal_year','severity','flag_type','title']
    list_filter   = ['severity','flag_type']
    search_fields = ['company__ticker']

admin.site.register(SectorMedian)
admin.site.register(AIAnalysis)
