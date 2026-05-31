web: gunicorn core.wsgi --workers 3 --timeout 60 --bind 0.0.0.0:$PORT
worker: celery -A core worker --loglevel=info --concurrency=4
beat: celery -A core beat --loglevel=info
