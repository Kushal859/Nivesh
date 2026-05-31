from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('auth/register/',    views.RegisterView.as_view()),
    path('auth/login/',       views.LoginView.as_view()),
    path('auth/me/',          views.MeView.as_view()),

    # Companies
    path('companies/',                    views.CompanyListView.as_view()),
    path('companies/<str:ticker>/',       views.CompanyDetailView.as_view()),
    path('companies/<str:ticker>/analysis/', views.CompanyAnalysisView.as_view()),

    # Screener
    path('screener/',   views.ScreenerView.as_view()),

    # Watchlist
    path('watchlist/',  views.WatchlistView.as_view()),

    # Subscription / Payments
    path('subscription/create/',   views.CreateSubscriptionView.as_view()),
    path('subscription/webhook/',  views.RazorpayWebhookView.as_view()),
    path('subscription/status/',   views.SubscriptionStatusView.as_view()),

    # Momentum
    path('companies/<str:ticker>/momentum/', views.MomentumView.as_view()),
    path('companies/<str:ticker>/momentum/narrative/', views.MomentumNarrativeView.as_view()),

    # Health
    path('health/', views.HealthView.as_view()),
]
