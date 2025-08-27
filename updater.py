import logging

import database
import mail
import task

logger = logging.getLogger(__name__)

MAILING_LISTS = [
    'amber-dev',
    'discuss',
    'leyden-dev',
    'lilliput-dev',
    'loom-dev',
    'net-dev',
    'nio-dev',
    'panama-dev',
    'valhalla-dev',
]


def init_logging():
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] <%(threadName)s> %(levelname)s - %(message)s')


def update_list(session, db, list_name):
    month, id = db.get_checkpoint(list_name)
    logger.info(f'loaded checkpoint, list={list_name}, month={month}, id={id}')
    cp = mail.Checkpoint(month=month, id=id)
    ml = mail.MailingList(session, list_name, cp, 1)
    db = database.Database()
    for mail_url in ml.mail_urls():
        md = task.process_mail(ml, db, mail_url, 3, 2500)
        db.put_checkpoint(md)
        logger.info(f'store checkpoint, month={md["month"]}, id={md["id"]}')


def lambda_handler(event, context):
    init_logging()
    db = database.Database()
    session = mail.http_session(1)
    for list_name in MAILING_LISTS:
        update_list(session, db, list_name)
