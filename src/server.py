import base64
import json
import re
import urllib.parse
from typing import NamedTuple  # Added this import

import boto3

import indexer
from params import DEFAULT_PARAMS

TABLE_RECORDS = 'openjdk-mail-records'
TABLE_TERMS = 'openjdk-mail-terms'
TABLE_STATUS = 'openjdk-mail-status'

REGION = 'us-west-1'

client = boto3.client('dynamodb', region_name=REGION)


class CommonParams(NamedTuple):
    forward: bool
    limit: int
    start_key: dict | None
    date_range: tuple[str, str] | None


def search_mail(list_name, term, cp: CommonParams):
    params = {
        'TableName': TABLE_TERMS,
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'KeyConditionExpression': '#list_term = :list_term',
        'ExpressionAttributeNames': {'#list_term': 'p'},
        'ExpressionAttributeValues': {':list_term': {'S': f'{list_name}/{term}'}}
    }
    if cp.date_range:
        start_iso, end_iso = cp.date_range
        # Include all items whose SK begins with start_iso/ ... up to end_iso/...
        # Use a high sentinel to include the entire end prefix range.
        start_sk = f'{start_iso}/'
        end_sk = f'{end_iso}/\uffff'
        params['KeyConditionExpression'] += ' AND #date_month_id BETWEEN :from AND :to'
        params['ExpressionAttributeNames']['#date_month_id'] = 's'
        params['ExpressionAttributeValues'][':from'] = {'S': start_sk}
        params['ExpressionAttributeValues'][':to'] = {'S': end_sk}
    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key
    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def search_mail_global(term, cp: CommonParams):
    params = {
        'TableName': TABLE_TERMS,
        "IndexName": "term_date",
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'KeyConditionExpression': '#term = :term',
        'ExpressionAttributeNames': {'#term': 't'},
        'ExpressionAttributeValues': {':term': {'S': f'{term}'}}
    }
    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params["KeyConditionExpression"] += " AND #date BETWEEN :from AND :to"
        params["ExpressionAttributeNames"]["#date"] = "d"
        params["ExpressionAttributeValues"][":from"] = {"S": f"{start_iso}"}
        params["ExpressionAttributeValues"][":to"] = {"S": f"{end_iso}\uffff"}
    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key
    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def mail_key_from_search_item(item):
    list_term = item['p']['S']
    date_month_id = item['s']['S']
    return {
        'list': {
            'S': list_term[:list_term.index('/')]
        },
        'month_id': {
            'S': date_month_id[date_month_id.index('/') + 1:]
        }
    }


def mail_keys_from_search_items(items):
    return [mail_key_from_search_item(item) for item in items]


def get_mail(search_items):
    keys = mail_keys_from_search_items(search_items)
    if not keys:
        return []
    res = client.batch_get_item(
        RequestItems={
            TABLE_RECORDS: {
                'Keys': keys
            }
        }
    )
    mails = []
    for key in keys:
        found = False
        for item in res['Responses'][TABLE_RECORDS]:
            if item['list'] == key['list'] and item['month_id'] == key['month_id']:
                mails.append(item)
                found = True
                break
        if not found:
            raise Exception(f'item key not found, list={key["list"]}, month_id={key["month_id"]}')
    return mails


def latest_mail(list_name, cp: CommonParams):
    params = {
        "TableName": TABLE_RECORDS,
        "IndexName": "list_date",
        "KeyConditionExpression": "#list = :list",
        "ExpressionAttributeNames": {"#list": "list"},
        "ExpressionAttributeValues": {":list": {"S": list_name}},
        "ScanIndexForward": cp.forward,
        "Limit": cp.limit,
    }
    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params["KeyConditionExpression"] += " AND #date BETWEEN :from AND :to"
        params["ExpressionAttributeNames"]["#date"] = "date"
        params["ExpressionAttributeValues"][":from"] = {"S": f"{start_iso}"}
        params["ExpressionAttributeValues"][":to"] = {"S": f"{end_iso}\uffff"}
    if cp.start_key:
        params["ExclusiveStartKey"] = cp.start_key
    res = client.query(**params)
    return res["Items"], res.get("LastEvaluatedKey")


def latest_mail_global(cp: CommonParams):
    params = {
        "TableName": TABLE_RECORDS,
        "IndexName": "datekey_date",
        "KeyConditionExpression": "#datekey = :dk",
        "ExpressionAttributeNames": {"#datekey": "datekey"},
        "ExpressionAttributeValues": {":dk": {"N": '1'}},
        "ScanIndexForward": cp.forward,
        "Limit": cp.limit,
    }
    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params["KeyConditionExpression"] += " AND #date BETWEEN :from AND :to"
        params["ExpressionAttributeNames"]["#date"] = "date"
        params["ExpressionAttributeValues"][":from"] = {"S": f"{start_iso}"}
        params["ExpressionAttributeValues"][":to"] = {"S": f"{end_iso}\uffff"}
    if cp.start_key:
        params["ExclusiveStartKey"] = cp.start_key
    res = client.query(**params)
    return res["Items"], res.get("LastEvaluatedKey")


def mail_by_author(list_name, authorkey, cp: CommonParams):
    params = {
        'TableName': TABLE_RECORDS,
        'IndexName': 'list_authorkey_date',
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'ExpressionAttributeNames': {
            '#list': 'list',
            '#akd': 'authorkey_date',
        },
        'ExpressionAttributeValues': {
            ':list': {'S': list_name},
        },
    }

    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params['KeyConditionExpression'] = '#list = :list AND #akd BETWEEN :from AND :to'
        params['ExpressionAttributeValues'][':from'] = {'S': f'{authorkey}/{start_iso}'}
        params['ExpressionAttributeValues'][':to'] = {'S': f'{authorkey}/{end_iso}\uffff'}  # inclusive upper
    else:
        params['KeyConditionExpression'] = '#list = :list AND begins_with(#akd, :prefix)'
        params['ExpressionAttributeValues'][':prefix'] = {'S': f'{authorkey}/'}

    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key

    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def mail_by_email(list_name, emailkey, cp: CommonParams):
    params = {
        'TableName': TABLE_RECORDS,
        'IndexName': 'list_emailkey_date',
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'ExpressionAttributeNames': {
            '#list': 'list',
            '#ekd': 'emailkey_date',
        },
        'ExpressionAttributeValues': {
            ':list': {'S': list_name},
        },
    }

    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params['KeyConditionExpression'] = '#list = :list AND #ekd BETWEEN :from AND :to'
        params['ExpressionAttributeValues'][':from'] = {'S': f'{emailkey}/{start_iso}'}
        params['ExpressionAttributeValues'][':to'] = {'S': f'{emailkey}/{end_iso}\uffff'}  # inclusive upper
    else:
        params['KeyConditionExpression'] = '#list = :list AND begins_with(#ekd, :prefix)'
        params['ExpressionAttributeValues'][':prefix'] = {'S': f'{emailkey}/'}

    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key

    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def mail_by_author_global(authorkey, cp: CommonParams):
    params = {
        'TableName': TABLE_RECORDS,
        'IndexName': 'authorkey_date',
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'KeyConditionExpression': '#ak = :ak',
        'ExpressionAttributeNames': {'#ak': 'authorkey'},
        'ExpressionAttributeValues': {':ak': {'S': authorkey}},
    }

    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params['KeyConditionExpression'] += ' AND #dt BETWEEN :from AND :to'
        params['ExpressionAttributeNames']['#dt'] = 'date'
        params['ExpressionAttributeValues'][':from'] = {'S': start_iso}
        params['ExpressionAttributeValues'][':to'] = {'S': f'{end_iso}\uffff'}  # inclusive upper bound

    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key

    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def mail_by_email_global(emailkey, cp: CommonParams):
    params = {
        'TableName': TABLE_RECORDS,
        'IndexName': 'emailkey_date',
        'ScanIndexForward': cp.forward,
        'Limit': cp.limit,
        'KeyConditionExpression': '#ek = :ek',
        'ExpressionAttributeNames': {'#ek': 'emailkey'},
        'ExpressionAttributeValues': {':ek': {'S': emailkey}},
    }

    if cp.date_range:
        start_iso, end_iso = cp.date_range
        params['KeyConditionExpression'] += ' AND #dt BETWEEN :from AND :to'
        params['ExpressionAttributeNames']['#dt'] = 'date'
        params['ExpressionAttributeValues'][':from'] = {'S': start_iso}
        params['ExpressionAttributeValues'][':to'] = {'S': f'{end_iso}\uffff'}  # inclusive upper bound

    if cp.start_key:
        params['ExclusiveStartKey'] = cp.start_key

    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def get_status():
    response = client.get_item(
        TableName=TABLE_STATUS,
        Key={"pk": {"N": "1"}}
    )

    item = response.get("Item", {})
    last_check = item.get("last_check", {}).get("S")
    last_update = item.get("last_update", {}).get("S")
    return last_check, last_update


def convert_item(item):
    return {
        'list': item['list']['S'],
        'month': item['month']['S'],
        'id': item['id']['S'],
        'date': item['date']['S'],
        'author': item['author']['S'],
        'email': item['email']['S'],
        'subject': item['subject']['S'],
    }


def convert(items):
    return [convert_item(i) for i in items]


def to_json_string(val):
    return json.dumps(val, separators=(',', ':'))


def _b64e(d: dict) -> str:
    return base64.urlsafe_b64encode(to_json_string(d).encode("utf-8")).decode("ascii")


def _b64d(s: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8"))


def to_response_string(val, cursor):
    res = {"items": val}
    if cursor:
        res["cursor"] = _b64e(cursor)
    return to_json_string(res)


def to_json_response(body):
    return {
        'status': '200',
        'statusDescription': 'OK',
        'headers': {
            'content-type': [
                {
                    'key': 'Content-Type',
                    'value': 'application/json'
                }
            ]
        },
        'body': body
    }


def extract_param(params, name, default=None, func=None):
    if name not in params:
        return default

    val = params[name][0]
    if not func:
        return val if val else default

    try:
        return func(val)
    except Exception:
        return default


def common_params(params):
    forward = extract_param(params, 'order', False, lambda p: p == 'asc')
    limit = max(1, min(100, extract_param(params, "limit", 10, int)))
    start_key = extract_param(params, "cursor", None, _b64d)
    from_date = extract_param(params, 'from')
    to_date = extract_param(params, 'to')
    date_range = (from_date, to_date) if from_date and to_date else None
    return CommonParams(forward=forward, limit=limit, start_key=start_key, date_range=date_range)


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    qs = request['querystring'] if 'querystring' in request else ''
    print(f'method={request["method"]}, path={request["uri"]}?{qs}')

    params = urllib.parse.parse_qs(qs)

    if request['method'] == 'GET' and (
            m := re.match(r'.*/lists/([^/]+)/mail/search$', request['uri'])) and 'q' in params:
        list_name = m.group(1)
        query = extract_param(params, 'q')
        idx = indexer.Indexer(DEFAULT_PARAMS)
        term = '|'.join(idx.normalize_and_filter(idx.tokenize(query)))
        cp = common_params(params)
        items, start_key = search_mail(list_name, term, cp)
        return to_json_response(to_response_string(convert(get_mail(items)), start_key))
    if request['method'] == 'GET' and request['uri'].endswith('/mail/search') and 'q' in params:
        query = extract_param(params, 'q')
        idx = indexer.Indexer(DEFAULT_PARAMS)
        term = '|'.join(idx.normalize_and_filter(idx.tokenize(query)))
        cp = common_params(params)
        items, start_key = search_mail_global(term, cp)
        return to_json_response(to_response_string(convert(get_mail(items)), start_key))
    if request['method'] == 'GET' and (m := re.match(r'.*/lists/([^/]+)/mail$', request['uri'])):
        list_name = m.group(1)
        cp = common_params(params)
        items, start_key = latest_mail(list_name, cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and request['uri'].endswith('/mail'):
        cp = common_params(params)
        items, start_key = latest_mail_global(cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and (
            m := re.match(r'.*/lists/([^/]+)/mail/byauthor$', request['uri'])) and 'author' in params:
        list_name = m.group(1)
        author = extract_param(params, 'author')
        authorkey = indexer.normalize(author)
        cp = common_params(params)
        items, start_key = mail_by_author(list_name, authorkey, cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and (
            m := re.match(r'.*/lists/([^/]+)/mail/byemail$', request['uri'])) and 'email' in params:
        list_name = m.group(1)
        email = extract_param(params, 'email')
        emailkey = indexer.normalize(email)
        cp = common_params(params)
        items, start_key = mail_by_email(list_name, emailkey, cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and request['uri'].endswith('/mail/byauthor') and 'author' in params:
        author = extract_param(params, 'author')
        authorkey = indexer.normalize(author)
        cp = common_params(params)
        items, start_key = mail_by_author_global(authorkey, cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and request['uri'].endswith('/mail/byemail') and 'email' in params:
        email = extract_param(params, 'email')
        emailkey = indexer.normalize(email)
        cp = common_params(params)
        items, start_key = mail_by_email_global(emailkey, cp)
        return to_json_response(to_response_string(convert(items), start_key))
    if request['method'] == 'GET' and request['uri'].endswith('/mail/status'):
        last_check, last_update = get_status()
        res = {
            'last_check': last_check,
            'last_update': last_update
        }
        return to_json_response(to_json_string(res))

    return {
        'status': '404',
        'statusDescription': 'Not Found',
        'body': 'Not Found'
    }
