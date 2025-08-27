import logging

import indexer
from database import Database
from mail import MailingList

logger = logging.getLogger(__name__)


def is_changeset_mail(mail):
    return (mail.subject.startswith('hg:') or mail.subject.startswith('git: ')) and (
            mail.subject.endswith('changesets') or mail.body.startswith('Changeset:'))


def process_mail(ml: MailingList, db: Database, mail_url: str, ngram_length: int, max_terms: int):
    mail = ml.fetch_mail(mail_url)
    md = mail._asdict()
    if is_changeset_mail(mail):
        logger.info(f'skipping changeset mail, month={mail.month}, id={mail.id}, subject=\'{mail.subject}\'')
        return md
    terms = indexer.index(
        author=mail.author,
        email=mail.email,
        subject=mail.subject,
        body=mail.body,
        ngram_length=ngram_length,
        max_terms=max_terms)
    if len(terms) == max_terms:
        logger.warning(f'truncated terms, month={mail.month}, id={mail.id}, subject=\'{mail.subject}\'')
    md['authorkey'] = indexer.normalize(mail.author)
    md['emailkey'] = indexer.normalize(mail.email)
    md['terms'] = len(terms)
    db.put_mail_record_and_terms(md, terms)
    logger.info(f'processed mail record, month={mail.month}, id={mail.id}, terms={len(terms)}')
    return md
