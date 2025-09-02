import logging

import database
import mail
import task

logger = logging.getLogger(__name__)

MAILING_LISTS = [
    'amber-dev',
    'babylon-dev',
    'classfile-api-dev',
    'compiler-dev',
    'crac-dev',
    'discuss',
    'graal-dev',
    'jdk-dev',
    'jigsaw-dev',
    'leyden-dev',
    'lilliput-dev',
    'loom-dev',
    'net-dev',
    'nio-dev',
    'panama-dev',
    'quality-discuss',
    'valhalla-dev',
    'valhalla-spec-comments',
    'valhalla-spec-experts',
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
    changed = False
    for mail_url in ml.mail_urls():
        md = task.process_mail(ml, db, mail_url, 3, 2_500, 500)
        db.put_checkpoint(md)
        changed = True
        logger.info(f'stored checkpoint, month={md["month"]}, id={md["id"]}')
    return changed


def lambda_handler(event, context):
    init_logging()
    db = database.Database()
    session = mail.http_session(1)
    changed = any(update_list(session, db, list_name) for list_name in MAILING_LISTS)
    date = db.update_status(changed)
    logger.info(f'updated status, changed={changed}, date={date}')

lambda_handler(None, None)