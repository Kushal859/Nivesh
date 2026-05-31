from rest_framework import serializers
from companies.models import Company, FinancialStatement
from analysis.models import CompanyRatios, RedFlag, SectorMedian, AIAnalysis
from users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id','email','tier','tier_expires','firm_name','city','total_lookups','watchlist']
        read_only_fields = ['id','email','tier','tier_expires','total_lookups','watchlist']


class RegisterSerializer(serializers.Serializer):
    email     = serializers.EmailField()
    password  = serializers.CharField(min_length=8, write_only=True)
    firm_name = serializers.CharField(required=False, allow_blank=True)
    city      = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, val):
        if User.objects.filter(email=val.lower()).exists():
            raise serializers.ValidationError('Email already registered.')
        return val.lower()

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            firm_name=validated_data.get('firm_name',''),
            city=validated_data.get('city',''),
        )
        return user


class CompanyListSerializer(serializers.ModelSerializer):
    latest_price = serializers.SerializerMethodField()
    latest_pe    = serializers.SerializerMethodField()
    latest_roe   = serializers.SerializerMethodField()

    class Meta:
        model  = Company
        fields = ['ticker','name','sector','mcap_cr','is_nifty50','is_nifty500',
                  'latest_price','latest_pe','latest_roe']

    def get_latest_price(self, obj):
        try:
            p = obj.prices.latest('date')
            return float(p.close)
        except Exception:
            return None

    def get_latest_pe(self, obj):
        r = obj.ratios.order_by('-fiscal_year').first()
        return float(r.pe_ratio) if r and r.pe_ratio else None

    def get_latest_roe(self, obj):
        r = obj.ratios.order_by('-fiscal_year').first()
        return float(r.roe) if r and r.roe else None


class FinancialStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FinancialStatement
        fields = ['fiscal_year','period','revenue','ebitda','pat','ebit',
                  'interest_expense','total_assets','total_equity','total_debt',
                  'current_assets','current_liabilities','cash_equivalents',
                  'debtors','cfo','fcf','promoter_holding','promoter_pledged',
                  'filing_date']


class RatiosSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CompanyRatios
        exclude = ['id','company','computed_at']


class RedFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RedFlag
        fields = ['flag_type','severity','title','detail']


class SectorMedianSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SectorMedian
        fields = ['pe_median','pb_median','roe_median','roce_median',
                  'npm_median','ebm_median','de_median']


class CompanyDetailSerializer(serializers.ModelSerializer):
    statements    = FinancialStatementSerializer(many=True, read_only=True)
    latest_ratios = serializers.SerializerMethodField()
    red_flags     = serializers.SerializerMethodField()
    sector_medians = serializers.SerializerMethodField()
    latest_price  = serializers.SerializerMethodField()

    class Meta:
        model  = Company
        fields = ['ticker','bse_code','name','sector','industry','description','mcap_cr',
                  'is_nifty50','is_nifty500','statements','latest_ratios','red_flags',
                  'sector_medians','latest_price']

    def get_latest_ratios(self, obj):
        r = obj.ratios.order_by('-fiscal_year').first()
        return RatiosSerializer(r).data if r else {}

    def get_red_flags(self, obj):
        flags = obj.flags.filter(is_active=True).order_by('severity')[:10]
        return RedFlagSerializer(flags, many=True).data

    def get_sector_medians(self, obj):
        med = SectorMedian.objects.filter(sector=obj.sector).order_by('-fiscal_year').first()
        return SectorMedianSerializer(med).data if med else {}

    def get_latest_price(self, obj):
        try:
            p = obj.prices.latest('date')
            return {'price': float(p.close), 'date': str(p.date)}
        except Exception:
            return None
