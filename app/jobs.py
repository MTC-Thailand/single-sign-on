import logging

import requests
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig()


def notify_sponsor_expiration():
    resp = requests.get('https://mtc-webservices.herokuapp.com/cmte/sponsor-expiration/notification')


scheduler = BlockingScheduler()
scheduler.add_job(notify_sponsor_expiration, 'cron', hour=9, minute=0, timezone='Asia/Bangkok')
scheduler.start()
