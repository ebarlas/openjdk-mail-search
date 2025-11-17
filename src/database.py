import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3

import indexer

TABLE_RECORDS = 'openjdk-mail-records'
TABLE_CHECKPOINTS = 'openjdk-mail-checkpoints'
TABLE_TERMS = 'openjdk-mail-terms'
TABLE_STATUS = 'openjdk-mail-status'

REGION = 'us-west-1'

class Database:
    def __init__(self, workers=10, max_retries=10, max_sleep=5.0):
        self.client = boto3.client('dynamodb', region_name=REGION)
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
        authorkey = indexer.normalize(author)
        email = mail['email']
        emailkey = indexer.normalize(email)
        subject = mail['subject']
        num_terms = str(len(terms))

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
            'terms': {'N': num_terms},
            'datekey': {'N': '1'}
        }

        search_terms_reqs = []
        for term_array in terms:
            joined_term = '|'.join(term_array)
            list_term = f"{list_name}/{joined_term}"
            date_month_id = f"{date}/{month}/{mail_id}"
            mst_item = {
                'p': {'S': list_term},
                's': {'S': date_month_id},
                'd': {'S': date},
                't': {'S': joined_term}
            }
            search_terms_reqs.append({'PutRequest': {'Item': mst_item}})

        request_items = {
            TABLE_RECORDS: [{'PutRequest': {'Item': mail_records_item}}],
            TABLE_TERMS: search_terms_reqs
        }

        self._batch_write_all(request_items)

    def put_checkpoint(self, mailing_list: str, month: str, mail_id: str):
        item = {
            'list': {'S': mailing_list},
            'month': {'S': month},
            'id': {'S': mail_id},
        }
        self.client.put_item(
            TableName=TABLE_CHECKPOINTS,
            Item=item
        )

    def get_checkpoint(self, list_name):
        res = self.client.get_item(
            TableName=TABLE_CHECKPOINTS,
            Key={
                'list': {
                    'S': list_name
                }
            })
        if 'Item' in res:
            return res['Item']['month']['S'], res['Item']['id']['S']
        return '', ''

    def update_status(self, changed):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        update_expr = "SET #last_check = :now"
        expr_attr_names = {"#last_check": "last_check"}
        expr_attr_values = {":now": {"S": now}}

        if changed:
            update_expr += ", #last_update = :now"
            expr_attr_names["#last_update"] = "last_update"

        self.client.update_item(
            TableName=TABLE_STATUS,
            Key={"pk": {"N": "1"}},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

        return now
