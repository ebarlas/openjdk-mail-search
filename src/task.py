import logging
import re

from database import Database
from indexer import Indexer
from params import IndexParams
from mail import MailingList

logger = logging.getLogger(__name__)


def process_mail(ml: MailingList, db: Database, mail_url: str, params: IndexParams):
    mail = ml.fetch_mail(mail_url)
    if params.stop_func(mail):
        logger.info(f'skipping changeset mail, month={mail.month}, id={mail.id}, subject=\'{mail.subject}\'')
    else:
        body = mail.body
        for regex in params.stop_lines:
            body = "\n".join(line for line in body.splitlines() if not re.match(regex, line))
        terms = Indexer(params).index(
            author=mail.author,
            email=mail.email,
            subject=mail.subject,
            body=body)
        terms = [t for t in terms if t not in params.stop_terms]
        db.put_mail_record_and_terms(mail._asdict(), terms)
        logger.info(f'processed mail record, month={mail.month}, id={mail.id}, terms={len(terms)}')
    return mail
