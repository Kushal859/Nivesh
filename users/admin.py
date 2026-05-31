from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseAdmin
from .models import User, Subscription

@admin.register(User)
class UserAdmin(BaseAdmin):
    list_display  = ['email','tier','daily_lookups','total_lookups','date_joined']
    list_filter   = ['tier']
    search_fields = ['email']
    fieldsets     = BaseAdmin.fieldsets + (('Nivesh', {'fields': ('tier','tier_expires','firm_name','phone','city','watchlist','daily_lookups','total_lookups','razorpay_customer_id','razorpay_subscription_id')}),)

admin.site.register(Subscription)
