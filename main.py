import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import batched

import database
import mail
import task

logger = logging.getLogger(__name__)


def init_logging():
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] <%(threadName)s> %(levelname)s - %(message)s')


def parse_args():
    p = argparse.ArgumentParser(description="Mailing list indexer")
    p.add_argument("--list", required=True)
    p.add_argument("--db_workers", type=int, default=50)
    p.add_argument("--mail_workers", type=int, default=25)
    p.add_argument("--max_terms", type=int, default=2500)
    p.add_argument("--max_token_length", type=int, default=500)
    p.add_argument("--ngram_length", type=int, default=3)
    p.add_argument("--throttle_sleep", type=int, default=1.5)
    return p.parse_args()


def main():
    init_logging()
    args = parse_args()
    logger.info(args)

    executor = ThreadPoolExecutor(max_workers=args.mail_workers)

    db = database.Database()
    month, id = db.get_checkpoint(args.list)
    logger.info(f'loaded checkpoint, month={month}, id={id}')

    cp = mail.Checkpoint(month=month, id=id)
    ml = mail.MailingList(mail.http_session(args.mail_workers), args.list, cp, args.mail_workers)

    def fn(mail_url):
        return task.process_mail(ml, db, mail_url, args.ngram_length, args.max_terms, args.max_token_length)

    for batch in batched(ml.mail_urls(), args.mail_workers):
        mds = list(executor.map(fn, batch))
        md = mds[-1]
        db.put_checkpoint(md)
        logger.info(f'store checkpoint, month={md["month"]}, id={md["id"]}')
        time.sleep(args.throttle_sleep)


if __name__ == '__main__':
    main()
