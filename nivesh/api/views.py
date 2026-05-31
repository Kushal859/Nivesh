import hashlib, hmac, json, logging
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.core.cache import cache
from companies.models import Company
from analysis.models import CompanyRatios, AIAnalysis
from .serializers import (
    RegisterSerializer, UserSerializer,
    CompanyListSerializer, CompanyDetailSerializer,
)

logger = logging.getLogger(__name__)


# ── AUTH ──────────────────────────────────────────────────

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user  = s.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data},
                        status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email    = request.data.get('email','').lower()
        password = request.data.get('password','')
        user = authenticate(request, username=email, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


# ── COMPANIES ─────────────────────────────────────────────

class CompanyListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Company.objects.filter(is_active=True).prefetch_related('prices','ratios')

        sector = request.query_params.get('sector')
        nifty  = request.query_params.get('nifty500')
        search = request.query_params.get('q')

        if sector:
            qs = qs.filter(sector=sector)
        if nifty == '1':
            qs = qs.filter(is_nifty500=True)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(ticker__icontains=search)

        qs = qs[:200]
        return Response(CompanyListSerializer(qs, many=True).data)


class CompanyDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, ticker):
        # Rate limiting by tier
        user = request.user if request.user.is_authenticated else None
        if user:
            if not user.can_lookup():
                return Response(
                    {'error': f'Daily lookup limit reached ({user.lookup_limit}/day). Upgrade to Pro for more.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            user.record_lookup()

        cache_key = f'company_detail_{ticker}'
        cached    = cache.get(cache_key)
        if cached:
            return Response(cached)

        try:
            company = Company.objects.prefetch_related(
                'statements','ratios','flags','prices'
            ).get(ticker=ticker.upper())
        except Company.DoesNotExist:
            return Response({'error': f'Company {ticker} not found'}, status=404)

        data = CompanyDetailSerializer(company).data
        cache.set(cache_key, data, timeout=settings.RATIO_CACHE_TTL)
        return Response(data)


class CompanyAnalysisView(APIView):
    """AI narrative endpoint — Pro+ tier only."""

    def get(self, request, ticker):
        user = request.user

        if not user.has_ai_access:
            return Response(
                {'error': 'AI analysis requires Pro plan. Upgrade at /pricing'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            company = Company.objects.get(ticker=ticker.upper())
        except Company.DoesNotExist:
            return Response({'error': 'Company not found'}, status=404)

        from datetime import date as _d
        _t = _d.today(); _cur_fy = _t.year if _t.month >= 4 else _t.year - 1
        fiscal_year = int(request.query_params.get('fy', _cur_fy))
        force       = request.query_params.get('force', '0') == '1'

        # Check DB cache first
        existing = AIAnalysis.objects.filter(
            company=company, fiscal_year=fiscal_year
        ).first()

        if existing and not force:
            return Response({
                'ticker': ticker, 'fiscal_year': fiscal_year,
                'narrative': existing.narrative,
                'cached': True, 'updated_at': existing.updated_at,
            })

        # Trigger async generation
        from analysis.tasks import generate_ai_narrative
        task = generate_ai_narrative.delay(company.id, fiscal_year, force=force)

        # Wait up to 30s for result (acceptable for paid users)
        try:
            result = task.get(timeout=30)
            return Response({
                'ticker': ticker, 'fiscal_year': fiscal_year,
                'narrative': result['narrative'],
                'cached': result.get('cached', False),
            })
        except Exception as exc:
            logger.error(f'AI narrative task failed: {exc}')
            return Response({'error': 'Analysis generation failed. Please retry.'}, status=500)


# ── SCREENER ─────────────────────────────────────────────

class ScreenerView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db.models import Q

        params = request.query_params

        # Filter on ratios
        ratio_filters = {}
        field_map = {
            'pe_min':'pe_ratio__gte',    'pe_max':'pe_ratio__lte',
            'pb_min':'pb_ratio__gte',    'pb_max':'pb_ratio__lte',
            'roe_min':'roe__gte',        'roe_max':'roe__lte',
            'roce_min':'roce__gte',      'roce_max':'roce__lte',
            'de_min':'debt_equity__gte', 'de_max':'debt_equity__lte',
            'npm_min':'net_margin__gte', 'npm_max':'net_margin__lte',
            'mcap_min': None,            'mcap_max': None,
        }

        ratio_q = {}
        for param, db_field in field_map.items():
            val = params.get(param)
            if val and db_field:
                try:
                    ratio_q[db_field] = float(val)
                except ValueError:
                    pass

        # Get matching ratio IDs
        from datetime import date as _d2
        _t2 = _d2.today(); _fy2 = _t2.year if _t2.month >= 4 else _t2.year - 1
        ratios_qs = CompanyRatios.objects.filter(fiscal_year=_fy2)
        if ratio_q:
            ratios_qs = ratios_qs.filter(**ratio_q)

        company_ids = ratios_qs.values_list('company_id', flat=True)
        companies   = Company.objects.filter(id__in=company_ids, is_active=True)

        # Sector filter
        sector = params.get('sector')
        if sector:
            companies = companies.filter(sector=sector)

        # Mcap filter
        mcap_min = params.get('mcap_min')
        mcap_max = params.get('mcap_max')
        if mcap_min:
            try:
                companies = companies.filter(mcap_cr__gte=float(mcap_min))
            except ValueError:
                pass
        if mcap_max:
            try:
                companies = companies.filter(mcap_cr__lte=float(mcap_max))
            except ValueError:
                pass

        companies = companies.prefetch_related('prices','ratios')[:100]
        return Response({
            'count':   len(companies),
            'results': CompanyListSerializer(companies, many=True).data,
        })


# ── WATCHLIST ─────────────────────────────────────────────

class WatchlistView(APIView):
    def get(self, request):
        tickers   = request.user.watchlist or []
        companies = Company.objects.filter(ticker__in=tickers).prefetch_related('prices','ratios')
        return Response(CompanyListSerializer(companies, many=True).data)

    def post(self, request):
        ticker = request.data.get('ticker','').upper()
        if not Company.objects.filter(ticker=ticker).exists():
            return Response({'error': 'Ticker not found'}, status=400)
        wl = request.user.watchlist or []
        if ticker not in wl:
            wl.append(ticker)
            request.user.watchlist = wl
            request.user.save(update_fields=['watchlist'])
        return Response({'watchlist': wl})

    def delete(self, request):
        ticker = request.data.get('ticker','').upper()
        wl = request.user.watchlist or []
        wl = [t for t in wl if t != ticker]
        request.user.watchlist = wl
        request.user.save(update_fields=['watchlist'])
        return Response({'watchlist': wl})


# ── SUBSCRIPTION / RAZORPAY ───────────────────────────────

class CreateSubscriptionView(APIView):
    def post(self, request):
        plan = request.data.get('plan')
        if plan not in ('pro','ca'):
            return Response({'error': 'Invalid plan'}, status=400)

        if not settings.RAZORPAY_KEY_ID:
            return Response({'error': 'Payment not configured'}, status=503)

        try:
            import razorpay
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

            sub = client.subscription.create({
                'plan_id':    settings.RAZORPAY_PLANS[plan],
                'total_count': 12,
                'quantity':    1,
                'customer_notify': 1,
                'notes': {
                    'user_id': str(request.user.id),
                    'plan':    plan,
                },
            })

            request.user.razorpay_subscription_id = sub['id']
            request.user.save(update_fields=['razorpay_subscription_id'])

            return Response({
                'subscription_id': sub['id'],
                'razorpay_key':    settings.RAZORPAY_KEY_ID,
                'plan':            plan,
            })
        except Exception as exc:
            logger.error(f'Razorpay subscription creation failed: {exc}')
            return Response({'error': 'Payment processing failed. Please try again.'}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload   = request.body
        signature = request.headers.get('X-Razorpay-Signature','')

        # Verify signature
        expected = hmac.HMAC(
            settings.RAZORPAY_KEY_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            return Response({'error': 'Invalid signature'}, status=400)

        event = json.loads(payload)
        self._handle_event(event)
        return Response({'status': 'ok'})

    def _handle_event(self, event):
        from users.models import User, Subscription
        from datetime import datetime

        ev_type = event.get('event')
        entity  = event.get('payload',{}).get('subscription',{}).get('entity',{})
        sub_id  = entity.get('id','')

        try:
            user = User.objects.get(razorpay_subscription_id=sub_id)
        except User.DoesNotExist:
            # Try notes
            notes   = entity.get('notes',{})
            user_id = notes.get('user_id')
            if not user_id:
                return
            try:
                user = User.objects.get(id=user_id)
                user.razorpay_subscription_id = sub_id
            except User.DoesNotExist:
                return

        plan = entity.get('notes',{}).get('plan','pro')

        if ev_type == 'subscription.activated':
            user.tier = plan
            end_ts = entity.get('current_end')
            if end_ts:
                user.tier_expires = datetime.fromtimestamp(end_ts, tz=timezone.utc)
            user.save(update_fields=['tier','tier_expires','razorpay_subscription_id'])
            logger.info(f'Subscription activated: {user.email} → {plan}')

        elif ev_type in ('subscription.cancelled','subscription.completed'):
            user.tier = 'free'
            user.save(update_fields=['tier'])
            logger.info(f'Subscription ended: {user.email}')

        elif ev_type == 'subscription.charged':
            end_ts = entity.get('current_end')
            if end_ts:
                user.tier_expires = datetime.fromtimestamp(end_ts, tz=timezone.utc)
                user.save(update_fields=['tier_expires'])

        Subscription.objects.update_or_create(
            razorpay_sub_id=sub_id,
            defaults={
                'user':   user,
                'plan':   plan,
                'status': entity.get('status',''),
                'current_start': datetime.fromtimestamp(entity['current_start'], tz=timezone.utc) if entity.get('current_start') else None,
                'current_end':   datetime.fromtimestamp(entity['current_end'],   tz=timezone.utc) if entity.get('current_end')   else None,
            }
        )


class SubscriptionStatusView(APIView):
    def get(self, request):
        from users.models import Subscription
        sub = Subscription.objects.filter(user=request.user).order_by('-created_at').first()
        return Response({
            'tier':         request.user.tier,
            'tier_expires': request.user.tier_expires,
            'has_ai_access': request.user.has_ai_access,
            'lookup_limit': request.user.lookup_limit,
            'daily_lookups': request.user.daily_lookups,
            'subscription': {
                'id':     sub.razorpay_sub_id if sub else None,
                'plan':   sub.plan if sub else None,
                'status': sub.status if sub else None,
            } if sub else None,
        })


# ── HEALTH ───────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from companies.models import Company
        from analysis.models import CompanyRatios
        return Response({
            'status':    'ok',
            'companies': Company.objects.filter(is_active=True).count(),
            'ratios':    CompanyRatios.objects.count(),
            'version':   '1.0.0',
        })
