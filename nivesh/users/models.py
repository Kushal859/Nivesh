from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    """Extended user with subscription tier tracking."""

    TIER_FREE = 'free'
    TIER_PRO  = 'pro'
    TIER_CA   = 'ca'
    TIER_CHOICES = [
        (TIER_FREE, 'Free'),
        (TIER_PRO,  'Pro — ₹299/month'),
        (TIER_CA,   'CA/Business — ₹2,999/month'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email        = models.EmailField(unique=True)
    tier         = models.CharField(max_length=10, choices=TIER_CHOICES, default=TIER_FREE)
    tier_expires = models.DateTimeField(null=True, blank=True)
    firm_name    = models.CharField(max_length=200, blank=True)  # for CA accounts
    phone        = models.CharField(max_length=15, blank=True)
    city         = models.CharField(max_length=100, blank=True)

    # Razorpay
    razorpay_customer_id     = models.CharField(max_length=100, blank=True)
    razorpay_subscription_id = models.CharField(max_length=100, blank=True)

    # Usage tracking
    daily_lookups     = models.PositiveIntegerField(default=0)
    daily_reset_date  = models.DateField(null=True, blank=True)
    total_lookups     = models.PositiveIntegerField(default=0)

    # Watchlist (stored as list of tickers)
    watchlist = models.JSONField(default=list)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email

    @property
    def lookup_limit(self):
        limits = {self.TIER_FREE: 5, self.TIER_PRO: 500, self.TIER_CA: 5000}
        return limits.get(self.tier, 5)

    @property
    def has_ai_access(self):
        return self.tier in (self.TIER_PRO, self.TIER_CA)

    @property
    def has_pdf_access(self):
        return self.tier in (self.TIER_PRO, self.TIER_CA)

    def reset_daily_if_needed(self):
        from django.utils import timezone
        today = timezone.now().date()
        if self.daily_reset_date != today:
            self.daily_lookups = 0
            self.daily_reset_date = today
            self.save(update_fields=['daily_lookups', 'daily_reset_date'])

    def can_lookup(self):
        self.reset_daily_if_needed()
        return self.daily_lookups < self.lookup_limit

    def record_lookup(self):
        self.daily_lookups  += 1
        self.total_lookups  += 1
        self.save(update_fields=['daily_lookups', 'total_lookups'])


class Subscription(models.Model):
    """Razorpay subscription audit trail."""
    user                 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    razorpay_sub_id      = models.CharField(max_length=100, unique=True)
    plan                 = models.CharField(max_length=20)
    status               = models.CharField(max_length=30)
    current_start        = models.DateTimeField(null=True)
    current_end          = models.DateTimeField(null=True)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'
        ordering = ['-created_at']
