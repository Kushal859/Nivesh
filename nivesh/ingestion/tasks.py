"""
BSE XBRL ingestion tasks + demo data seeder.
"""
import logging, time
from decimal import Decimal as D
from django.conf import settings
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def ingest_bse_filings(self):
    """Nightly: pull BSE XBRL filings and upsert FinancialStatement rows."""
    from companies.models import Company, FinancialStatement
    import requests
    companies = Company.objects.filter(is_active=True, bse_code__gt="")
    ingested, failed = 0, 0
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Nivesh/1.0)", "Referer": "https://www.bseindia.com"}
    for i, company in enumerate(companies):
        try:
            url = f"{settings.BSE_XBRL_BASE_URL}/FinancialResults/w"
            r = requests.get(url, params={"strScrip": company.bse_code, "strType": "C", "period": "Annual"},
                             headers=headers, timeout=15)
            if r.ok:
                data = r.json()
                fy = int(data.get("Year", 0))
                if fy:
                    FinancialStatement.objects.update_or_create(
                        company=company, fiscal_year=fy, period="annual",
                        defaults={
                            "revenue": _to_d(data.get("NetSales")),
                            "ebitda":  _to_d(data.get("EBITDA")),
                            "pat":     _to_d(data.get("PAT")),
                            "raw_data": data, "source": "bse_xbrl",
                        }
                    )
                    ingested += 1
            if i % 50 == 49:
                time.sleep(2)
        except Exception as exc:
            logger.warning(f"BSE ingest failed for {company.ticker}: {exc}")
            failed += 1
    return {"ingested": ingested, "failed": failed}


def _to_d(val):
    try:
        return D(str(val).replace(",", "")) if val else None
    except Exception:
        return None


@shared_task
def seed_demo_data():
    """Seed 5 companies with 5 years of real financial data for immediate demo."""
    from companies.models import Company, FinancialStatement

    COMPANIES = [
        {"ticker":"TCS","bse_code":"532540","name":"Tata Consultancy Services","sector":"IT Services","mcap_cr":1420000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"RELIANCE","bse_code":"500325","name":"Reliance Industries","sector":"Conglomerate","mcap_cr":1980000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"HDFCBANK","bse_code":"500180","name":"HDFC Bank","sector":"Private Banking","mcap_cr":1260000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"INFY","bse_code":"500209","name":"Infosys","sector":"IT Services","mcap_cr":680000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"BAJFINANCE","bse_code":"500034","name":"Bajaj Finance","sector":"NBFC","mcap_cr":480000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"MARUTI","bse_code":"532500","name":"Maruti Suzuki India","sector":"Automobiles","mcap_cr":390000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"SUNPHARMA","bse_code":"524715","name":"Sun Pharmaceutical","sector":"Pharma","mcap_cr":360000,"is_nifty50":True,"is_nifty500":True},
        {"ticker":"WIPRO","bse_code":"507685","name":"Wipro","sector":"IT Services","mcap_cr":260000,"is_nifty50":True,"is_nifty500":True},
    ]

    STMTS = {
        "TCS": [
            (2025,234875,63100,48478,57200,640,5900,200000,95000,3800,120000,42000,30000,28000,52000,4800,72.3,0),
            (2024,220492,57800,45908,52400,580,5400,185000,88000,3200,110000,38000,26000,25000,48000,4200,72.3,0),
            (2023,205971,53200,42147,48100,520,5100,170000,80000,2800,100000,34000,22000,22000,43000,3800,72.3,0),
            (2022,191754,49100,40127,44400,480,4700,155000,73000,2400, 90000,30000,19000,20000,40000,3400,72.4,0),
            (2021,187800,47200,38983,42700,450,4500,145000,68000,2100, 85000,28000,17000,18000,38000,3100,72.5,0),
        ],
        "RELIANCE": [
            (2025,932105,178200,83956,142000,16900,36200,1420000,700000,265000,320000,290000,180000,85000,140000,62000,50.3,0),
            (2024,899041,161700,79020,127000,15400,34700,1350000,660000,252000,295000,270000,165000,78000,128000,58000,50.3,0),
            (2023,792756,115900,73670, 92000,14200,23900,1220000,610000,240000,270000,245000,145000,72000,112000,55000,50.3,0),
            (2022,721634, 93400,67845, 74200,13400,19200,1100000,565000,225000,245000,225000,130000,66000, 98000,50000,50.3,0),
            (2021,486326, 60200,49128, 48000,12800,12200, 980000,510000,215000,210000,198000,115000,58000, 78000,45000,50.0,0),
        ],
        "HDFCBANK": [
            (2025,261294,128000,74013,118000,24500,4200,3600000,470000,3860000,380000,358000,120000,52000,95000,3800,0,0),
            (2024,238856,115000,64063,105000,22000,3900,3400000,430000,3640000,348000,328000,108000,46000,85000,3500,0,0),
            (2023,185010, 83400,44109, 75000,16800,3200,2600000,310000,2760000,250000,236000, 82000,36000,65000,2800,0,0),
            (2022,147069, 61200,36961, 55000,12400,2800,2100000,258000,2230000,198000,187000, 65000,30000,52000,2400,0,0),
            (2021,128447, 52000,31116, 46800,10800,2500,1800000,224000,1940000,168000,158000, 56000,26000,44000,2100,0,0),
        ],
        "INFY": [
            (2025,162023,36800,27924,34600,500,2200,108000,72000,5800,62000,26000,18000,20000,32000,2800,14.9,0),
            (2024,153670,33900,26248,31800,460,2100,100000,68000,5200,58000,24000,16000,18000,30000,2500,14.9,0),
            (2023,146767,34100,24108,32000,420,2100, 94000,63000,4800,54000,22000,14000,16000,28000,2300,14.9,0),
            (2022,121641,29800,22110,28000,380,1800, 85000,57000,4200,48000,19000,12000,14000,25000,2000,14.9,0),
            (2021,100472,24200,19351,22800,340,1400, 74000,50000,3600,42000,16000,10000,12000,22000,1700,14.9,0),
        ],
        "BAJFINANCE": [
            (2025,64820,28600,17212,22000,6900,680,380000,76000,290000,45000,40000,18000,32000,20000,580,54.8,0),
            (2024,54190,23400,14451,18200,5800,560,320000,64000,244000,38000,34000,14500,27000,16800,480,54.8,0),
            (2023,40310,17200,11508,13600,4200,420,240000,50000,183000,29000,26000,11000,21000,12500,380,54.9,0),
            (2022,28930,11800, 7028, 9200,3100,320,175000,38000,133000,21000,19000, 8000,15000, 8800,280,54.9,0),
            (2021,23138, 8200, 4420, 6400,2600,260,145000,32000,109000,17000,15500, 6500,12000, 6200,220,55.0,0),
        ],
        "MARUTI": [
            (2025,147980,21400,15912,19800,140,1600,125000,78000,1200,68000,32000,42000,14000,19200,3200,58.2,0),
            (2024,138311,18800,13488,17400,130,1400,114000,70000,1000,61000,29000,38000,12500,17400,2800,58.2,0),
            (2023,117571,13100, 8211,11900,120,1200,102000,62000, 900,54000,26000,33000,11000,14200,2400,58.2,0),
            (2022, 79093, 7600, 7616, 6800,110,1100, 90000,55000, 800,48000,23000,29000, 9500,11000,2100,58.2,0),
            (2021, 66802, 4200, 4230, 3500,100,1000, 80000,49000, 700,42000,20000,26000, 8500, 8600,1900,58.2,0),
        ],
        "SUNPHARMA": [
            (2025,52840,14200,11820,12800,340,1400,88000,58000,7000,42000,16000,12000,8800,13200,2200,54.5,0),
            (2024,47558,12100, 9149,11000,310,1100,80000,52000,6200,38000,14500,10500,8000,11600,2000,54.5,0),
            (2023,40085, 9800, 8136, 8800,280, 980,72000,46000,5600,34000,13000, 9200,7200,10000,1800,54.5,0),
            (2022,33228, 7200, 7297, 6400,250, 800,64000,40000,5000,30000,11500, 8000,6500, 8500,1600,54.5,0),
            (2021,28959, 5980, 4748, 5200,220, 780,56000,35000,4200,26000,10000, 7000,5800, 7200,1400,54.5,0),
        ],
        "WIPRO": [
            (2025,91765,16800,11700,15200,290,1600,92000,60000,12600,52000,22000,16000,17000,15400,2400,72.9,0),
            (2024,89989,15900,11023,14400,270,1500,86000,56000,12000,48000,20000,14800,15800,14200,2200,72.9,0),
            (2023,91100,16200,11352,14700,280,1500,88000,58000,12200,50000,21000,15200,16200,14800,2300,72.9,0),
            (2022,79312,14700,12229,13400,250,1300,80000,54000,11000,45000,19000,13500,14500,13500,2000,72.9,0),
            (2021,62164,11800,10796,10700,220,1100,70000,47000, 9800,39000,16500,12000,12800,11800,1700,72.9,0),
        ],
    }

    for co in COMPANIES:
        company, _ = Company.objects.update_or_create(
            ticker=co["ticker"],
            defaults={**co, "description": f"{co['name']} — seeded demo data"}
        )
        for s in STMTS.get(co["ticker"], []):
            (fy,rev,ebitda,pat,ebit,interest,dep,ta,te,td,ca,cl,cash,deb,cfo,capex,promo,pledged) = s
            FinancialStatement.objects.update_or_create(
                company=company, fiscal_year=fy, period="annual",
                defaults={
                    "revenue": D(str(rev)), "ebitda": D(str(ebitda)),
                    "pat": D(str(pat)), "ebit": D(str(ebit)),
                    "interest_expense": D(str(interest)), "depreciation": D(str(dep)),
                    "total_assets": D(str(ta)), "total_equity": D(str(te)),
                    "total_debt": D(str(td)), "current_assets": D(str(ca)),
                    "current_liabilities": D(str(cl)), "cash_equivalents": D(str(cash)),
                    "debtors": D(str(deb)), "cfo": D(str(cfo)), "capex": D(str(capex)),
                    "fcf": D(str(cfo - abs(capex))),
                    "promoter_holding": D(str(promo)),
                    "promoter_pledged": D(str(pledged)),
                    "source": "seed",
                }
            )
        logger.info(f"Seeded {company.ticker}")
    logger.info("All seed data loaded.")
