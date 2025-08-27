import time
from concurrent.futures import ThreadPoolExecutor

import boto3


class Database:
    def __init__(self, region='us-west-1', workers=10, max_retries=10, max_sleep=5.0):
        self.client = boto3.client('dynamodb', region_name=region)
        self.executor = ThreadPoolExecutor(max_workers=workers) if workers > 0 else None
        self.max_retries = max_retries
        self.max_sleep = max_sleep

    def _batch_write(self, to_send):
        attempt = 0
        backoff = 0.1  # start at 100ms
        while True:
            resp = self.client.batch_write_item(RequestItems=to_send)
            unprocessed = resp.get('UnprocessedItems', {})
            if not unprocessed or all(len(v) == 0 for v in unprocessed.values()):
                break

            attempt += 1
            if attempt > self.max_retries:
                raise RuntimeError(f"Exceeded retries; still unprocessed: {unprocessed}")

            to_send = unprocessed
            time.sleep(backoff)
            backoff = min(backoff * 2, self.max_sleep)

    @staticmethod
    def prepare_chunks_to_send(request_items):
        flattened = []
        for table, reqs in request_items.items():
            for r in reqs:
                flattened.append((table, r))
        chunks = [flattened[i:i + 25] for i in range(0, len(flattened), 25)]
        to_sends = []
        for chunk in chunks:
            to_send = {}
            for table, r in chunk:
                to_send.setdefault(table, []).append(r)
            to_sends.append(to_send)
        return to_sends

    def _batch_write_all(self, request_items: dict):
        to_sends = self.prepare_chunks_to_send(request_items)
        if self.executor:
            list(self.executor.map(self._batch_write, to_sends))
        else:
            for to_send in to_sends:
                self._batch_write(to_send)

    def put_mail_record_and_terms(self, mail: dict, terms: list[list[str]]):
        date = mail['date']
        list_name = mail['list']
        month = mail['month']
        mail_id = mail['id']
        author = mail['author']
        authorkey = mail['authorkey']
        email = mail['email']
        emailkey = mail['emailkey']
        subject = mail['subject']
        num_terms = f'{mail["terms"]}'

        month_id = f"{month}/{mail_id}"
        authorkey_date = f"{authorkey}/{date}"
        emailkey_date = f"{emailkey}/{date}"

        mail_records_item = {
            'list': {'S': list_name},
            'month_id': {'S': month_id},
            'date': {'S': date},
            'month': {'S': month},
            'id': {'S': mail_id},
            'author': {'S': author},
            'authorkey': {'S': authorkey},
            'email': {'S': email},
            'emailkey': {'S': emailkey},
            'authorkey_date': {'S': authorkey_date},
            'emailkey_date': {'S': emailkey_date},
            'subject': {'S': subject},
            'terms': {'N': num_terms}
        }

        search_terms_reqs = []
        for term_array in terms:
            joined_term = '|'.join(term_array)
            list_term = f"{list_name}/{joined_term}"
            date_month_id = f"{date}/{month}/{mail_id}"
            mst_item = {
                'list_term': {'S': list_term},
                'date_month_id': {'S': date_month_id},
                'date': {'S': date},
                'list': {'S': list_name},
                'month': {'S': month},
                'id': {'S': mail_id},
                'author': {'S': author},
                'email': {'S': email},
                'subject': {'S': subject},
            }
            search_terms_reqs.append({'PutRequest': {'Item': mst_item}})

        request_items = {
            'mail-records': [{'PutRequest': {'Item': mail_records_item}}],
            'mail-search-terms': search_terms_reqs
        }

        self._batch_write_all(request_items)

    def put_checkpoint(self, mail: dict):
        item = {
            'list': {'S': mail['list']},
            'month': {'S': mail['month']},
            'id': {'S': mail['id']},
        }
        self.client.put_item(
            TableName='mail-checkpoints',
            Item=item
        )

    def get_checkpoint(self, list_name):
        res = self.client.get_item(
            TableName='mail-checkpoints',
            Key={
                'list': {
                    'S': list_name
                }
            })
        if 'Item' in res:
            return res['Item']['month']['S'], res['Item']['id']['S']
        return '', ''
