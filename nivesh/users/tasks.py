"""User-related Celery tasks."""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task
def send_weekly_digest():
    """Send weekly watchlist digest to Pro+ users."""
    from users.models import User
    from companies.models import Company

    users = User.objects.filter(tier__in=['pro','ca']).exclude(watchlist=[])
    sent  = 0
    for user in users:
        if not user.watchlist:
            continue
        try:
            # TODO: render digest template and send via SendGrid
            logger.info(f'Would send digest to {user.email} for {user.watchlist}')
            sent += 1
        except Exception as exc:
            logger.error(f'Digest failed for {user.email}: {exc}')
    return {'sent': sent}
