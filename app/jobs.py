import logging
from apscheduler.schedulers.blocking import BlockingScheduler

from app.cmte.views import notify_sponsor_expiration

logging.basicConfig()

scheduler = BlockingScheduler()
scheduler.add_job(notify_sponsor_expiration, 'cron', hour=9, minute=0, timezone='Asia/Bangkok')
scheduler.start()
