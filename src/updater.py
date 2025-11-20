import logging

import database
import mail
import params
import task

logger = logging.getLogger(__name__)

MAILING_LISTS = [
    'amber-dev',
    'babylon-dev',
    'classfile-api-dev',
    'client-libs-dev',
    'compiler-dev',
    'core-libs-dev',
    'crac-dev',
    'discuss',
    'graal-dev',
    'jdk-dev',
    'jextract-dev',
    'jigsaw-dev',
    'jmh-dev',
    'leyden-dev',
    'lilliput-dev',
    'loom-dev',
    'mobile-dev',
    'net-dev',
    'nio-dev',
    'openjfx-dev',
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
    ml = mail.MailingList(session, list_name, cp)
    db = database.Database()
    changed = False
    for mail_url in ml.mail_urls():
        last_mail = task.process_mail(ml, db, mail_url, params.DEFAULT_PARAMS)
        db.put_checkpoint(last_mail.list, last_mail.month, last_mail.id)
        changed = True
        logger.info(f'stored checkpoint, month={last_mail.month}, id={last_mail.id}')
    return changed


def lambda_handler(event, context):
    init_logging()
    db = database.Database()
    session = mail.http_session(1)
    changed = any([update_list(session, db, list_name) for list_name in MAILING_LISTS])
    date = db.update_status(changed)
    logger.info(f'updated status, changed={changed}, date={date}')