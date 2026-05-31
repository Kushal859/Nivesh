#!/bin/bash
set -e
echo "==> Installing dependencies..."
pip install -r requirements.txt
echo "==> Running migrations..."
python manage.py migrate
echo "==> Seeding demo data..."
python manage.py shell -c "from ingestion.tasks import seed_demo_data; seed_demo_data()"
echo "==> Computing ratios and sector medians..."
python manage.py shell -c "from analysis.tasks import refresh_all_ratios,refresh_sector_medians; refresh_all_ratios(); refresh_sector_medians()"
echo "==> Collecting static files..."
python manage.py collectstatic --noinput
echo ""
echo "Nivesh backend ready!"
echo "  Dev server:   python manage.py runserver"
echo "  Health check: http://localhost:8000/api/v1/health/"
echo "  Admin:        http://localhost:8000/admin/"
