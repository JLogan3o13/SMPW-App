"""
manageBacklogItems - Lambda handler for the admin Backlog dashboard.

Routes (API Gateway REST API, Lambda proxy integration):
    GET    /backlog              -> list all backlog items
    POST   /backlog              -> create an item (ID is generated: MAP-001, ADMIN-001, BOTH-001, ...)
    GET    /backlog/{itemId}     -> get one item
    PUT    /backlog/{itemId}     -> update name/description/status/priority/event/notes/rank
    DELETE /backlog/{itemId}     -> delete an item

DynamoDB table: BacklogItems (partition key: itemId, String)
    Counter records "COUNTER#MAP", "COUNTER#ADMIN" and "COUNTER#BOTH" live in the same table
    and hold the last number issued for each app. They are hidden from the list.

Rank: open items can have a rank (1 = work on first). Ranks are kept consecutive
(1, 2, 3, ... with no gaps or duplicates): placing an item at rank 3 moves the old
#3 and below down one, and completing, closing or deleting a ranked item closes
the gap. Responses include "rankChanges": {itemId: newRank or null} so the page
can update every row that moved.
"""

import json
import os
import traceback
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get('TABLE_NAME', 'BacklogItems')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

APPS = ('MAP', 'ADMIN', 'BOTH')
STATUSES = ('Under Review', 'In Development', 'Completed', 'Delayed', 'Future Enhancement', 'Not Planned')
PRIORITIES = ('High', 'Medium', 'Low')
EVENTS = ('Raiders Games', 'Formula 1', 'General')
DEFAULT_EVENT = 'General'
COMPLETED = 'Completed'
# Closed items drop out of the ranking
CLOSED_STATUSES = ('Completed', 'Not Planned')
COUNTER_PREFIX = 'COUNTER#'

EDITABLE_FIELDS = ('name', 'description', 'status', 'priority', 'event', 'notes')
MAX_LENGTHS = {'name': 200, 'description': 4000, 'notes': 4000}

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
}


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def respond(status_code, body):
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body, cls=DecimalEncoder),
    }


def now_iso():
    """UTC timestamp; the browser converts it to local time for display."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Request parsing and validation
# ---------------------------------------------------------------------------

def parse_body(event):
    raw = event.get('body')
    if raw is None or raw == '':
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValidationError('Request body must be valid JSON')
    if not isinstance(data, dict):
        raise ValidationError('Request body must be a JSON object')
    return data


def clean_fields(data, creating):
    """Return a dict of validated, trimmed editable fields from the request."""
    cleaned = {}
    for field in EDITABLE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            value = ''
        if not isinstance(value, str):
            raise ValidationError(f'{field} must be text')
        value = value.strip()

        if field in MAX_LENGTHS and len(value) > MAX_LENGTHS[field]:
            raise ValidationError(f'{field} must be {MAX_LENGTHS[field]} characters or fewer')
        if field == 'name' and not value:
            raise ValidationError('name is required')
        if field == 'status' and value not in STATUSES:
            raise ValidationError(f'status must be one of: {", ".join(STATUSES)}')
        if field == 'priority' and value not in PRIORITIES:
            raise ValidationError(f'priority must be one of: {", ".join(PRIORITIES)}')
        if field == 'event' and value not in EVENTS:
            raise ValidationError(f'event must be one of: {", ".join(EVENTS)}')
        cleaned[field] = value

    if creating and not cleaned.get('name'):
        raise ValidationError('name is required')
    return cleaned


def normalize_id(item_id):
    item_id = (item_id or '').strip().upper()
    if not item_id or item_id.startswith(COUNTER_PREFIX):
        raise NotFoundError(f'Item {item_id} not found')
    return item_id


def with_defaults(item):
    """Items created before the Event field existed are treated as General."""
    item.setdefault('event', DEFAULT_EVENT)
    return item


def parse_rank(value):
    """None or '' clears the rank; otherwise a whole number, 1 or higher."""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValidationError('rank must be a whole number, 1 or higher')
    try:
        number = Decimal(str(value).strip())
    except Exception:
        raise ValidationError('rank must be a whole number, 1 or higher')
    if not number.is_finite() or number != number.to_integral_value() or number < 1:
        raise ValidationError('rank must be a whole number, 1 or higher')
    return int(number)


def sort_key(item):
    app = item.get('app', '')
    return (APPS.index(app) if app in APPS else 99, int(item.get('itemNumber', 0)))


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def scan_all():
    items = []
    scan_kwargs = {}
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(i for i in resp.get('Items', [])
                     if not i.get('itemId', '').startswith(COUNTER_PREFIX))
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
    return items


def set_rank(item_id, rank):
    """Set (rank=int) or clear (rank=None) one item's rank. Skips items deleted meanwhile."""
    kwargs = {
        'Key': {'itemId': item_id},
        'ConditionExpression': 'attribute_exists(itemId)',
        'ExpressionAttributeNames': {'#rank': 'rank'},
    }
    if rank is None:
        kwargs['UpdateExpression'] = 'REMOVE #rank'
    else:
        kwargs['UpdateExpression'] = 'SET #rank = :rank'
        kwargs['ExpressionAttributeValues'] = {':rank': rank}
    try:
        table.update_item(**kwargs)
    except ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise


def rerank(item_id, desired, write_self=True):
    """Place item_id at rank `desired` (None = unranked) and renumber every other
    ranked open item 1..n. Returns {itemId: rank or None} for each item that changed."""
    others = sorted(
        (i for i in scan_all()
         if 'rank' in i and i['itemId'] != item_id and i.get('status') not in CLOSED_STATUSES),
        key=lambda i: (int(i['rank']), sort_key(i)),
    )
    current = {i['itemId']: int(i['rank']) for i in others}
    order = [i['itemId'] for i in others]
    if desired is not None:
        order.insert(min(desired, len(order) + 1) - 1, item_id)

    changes = {}
    for position, iid in enumerate(order, start=1):
        if iid == item_id:
            if write_self:
                set_rank(iid, position)
            changes[iid] = position
        elif current.get(iid) != position:
            set_rank(iid, position)
            changes[iid] = position
    if desired is None:
        if write_self:
            set_rank(item_id, None)
        changes[item_id] = None
    print(f'Reranked around {item_id}: {changes}')
    return changes


def apply_own_rank(item, changes):
    if item['itemId'] in changes:
        if changes[item['itemId']] is None:
            item.pop('rank', None)
        else:
            item['rank'] = changes[item['itemId']]
    return item


def list_items():
    items = [with_defaults(i) for i in scan_all()]
    items.sort(key=sort_key)
    return respond(200, {'items': items, 'count': len(items)})


def get_item(item_id):
    item_id = normalize_id(item_id)
    resp = table.get_item(Key={'itemId': item_id})
    if 'Item' not in resp:
        raise NotFoundError(f'Item {item_id} not found')
    return respond(200, {'item': with_defaults(resp['Item'])})


def next_number(app):
    """Atomically increment the per-app counter so IDs never collide."""
    resp = table.update_item(
        Key={'itemId': COUNTER_PREFIX + app},
        UpdateExpression='ADD seq :one',
        ExpressionAttributeValues={':one': 1},
        ReturnValues='UPDATED_NEW',
    )
    return int(resp['Attributes']['seq'])


def create_item(data):
    app = str(data.get('app', '')).strip().upper()
    if app not in APPS:
        raise ValidationError(f'app must be one of: {", ".join(APPS)}')

    fields = clean_fields(data, creating=True)
    desired_rank = parse_rank(data.get('rank'))
    timestamp = now_iso()
    item = {
        'app': app,
        'name': fields['name'],
        'description': fields.get('description', ''),
        'status': fields.get('status', 'Under Review'),
        'priority': fields.get('priority', 'Medium'),
        'event': fields.get('event', DEFAULT_EVENT),
        'notes': fields.get('notes', ''),
        'createdAt': timestamp,
        'updatedAt': timestamp,
    }
    if item['status'] == COMPLETED:
        item['dateCompleted'] = timestamp

    # Retry in case someone created an item by hand in the console with the next ID.
    for _ in range(5):
        number = next_number(app)
        item['itemId'] = f'{app}-{number:03d}'
        item['itemNumber'] = number
        try:
            table.put_item(Item=item, ConditionExpression='attribute_not_exists(itemId)')
            print(f'Created {item["itemId"]}')
            changes = {}
            if desired_rank is not None and item['status'] not in CLOSED_STATUSES:
                changes = rerank(item['itemId'], desired_rank)
                apply_own_rank(item, changes)
            return respond(201, {'item': item, 'rankChanges': changes})
        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
    raise RuntimeError(f'Could not allocate a new {app} ID after 5 attempts')


def update_item(item_id, data):
    item_id = normalize_id(item_id)
    fields = clean_fields(data, creating=False)
    rank_given = 'rank' in data
    desired_rank = parse_rank(data.get('rank')) if rank_given else None
    if not fields and not rank_given:
        raise ValidationError(f'Provide at least one of: {", ".join(EDITABLE_FIELDS + ("rank",))}')

    item = save_fields(item_id, fields) if fields else fetch_item(item_id)

    # Closed items always drop out of the ranking; open items move only when asked.
    changes = {}
    had_rank = 'rank' in item
    if item.get('status') in CLOSED_STATUSES:
        if had_rank:
            changes = rerank(item_id, None)
    elif rank_given and (desired_rank is not None or had_rank):
        changes = rerank(item_id, desired_rank)
    apply_own_rank(item, changes)
    return respond(200, {'item': with_defaults(item), 'rankChanges': changes})


def fetch_item(item_id):
    resp = table.get_item(Key={'itemId': item_id})
    if 'Item' not in resp:
        raise NotFoundError(f'Item {item_id} not found')
    return resp['Item']


def save_fields(item_id, fields):
    names = {'#updatedAt': 'updatedAt'}
    values = {':updatedAt': now_iso()}
    set_parts = ['#updatedAt = :updatedAt']
    remove_parts = []

    for field, value in fields.items():
        names[f'#{field}'] = field
        values[f':{field}'] = value
        set_parts.append(f'#{field} = :{field}')

    # Completed date fills in automatically and clears if the item is reopened.
    if 'status' in fields:
        names['#dateCompleted'] = 'dateCompleted'
        if fields['status'] == COMPLETED:
            set_parts.append('#dateCompleted = if_not_exists(#dateCompleted, :updatedAt)')
        else:
            remove_parts.append('#dateCompleted')

    expression = 'SET ' + ', '.join(set_parts)
    if remove_parts:
        expression += ' REMOVE ' + ', '.join(remove_parts)

    try:
        resp = table.update_item(
            Key={'itemId': item_id},
            UpdateExpression=expression,
            ConditionExpression='attribute_exists(itemId)',
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues='ALL_NEW',
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise NotFoundError(f'Item {item_id} not found')
        raise
    print(f'Updated {item_id}: {list(fields)}')
    return resp['Attributes']


def delete_item(item_id):
    item_id = normalize_id(item_id)
    try:
        resp = table.delete_item(Key={'itemId': item_id},
                                 ConditionExpression='attribute_exists(itemId)',
                                 ReturnValues='ALL_OLD')
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise NotFoundError(f'Item {item_id} not found')
        raise
    print(f'Deleted {item_id}')
    old = resp.get('Attributes', {})
    changes = {}
    if 'rank' in old and old.get('status') not in CLOSED_STATUSES:
        changes = rerank(item_id, None, write_self=False)
        changes.pop(item_id, None)
    return respond(200, {'deleted': item_id, 'rankChanges': changes})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    method = (event.get('httpMethod')
              or event.get('requestContext', {}).get('http', {}).get('method', '')).upper()
    item_id = (event.get('pathParameters') or {}).get('itemId')
    print(f'{method} itemId={item_id}')

    if method == 'OPTIONS':
        return respond(200, {})

    try:
        if method == 'GET':
            return get_item(item_id) if item_id else list_items()
        if method == 'POST' and not item_id:
            return create_item(parse_body(event))
        if method == 'PUT' and item_id:
            return update_item(item_id, parse_body(event))
        if method == 'DELETE' and item_id:
            return delete_item(item_id)
        return respond(405, {'error': f'{method} is not supported on this path'})
    except ValidationError as e:
        return respond(400, {'error': str(e)})
    except NotFoundError as e:
        return respond(404, {'error': str(e)})
    except Exception as e:
        print(f'Error: {e}')
        traceback.print_exc()
        return respond(500, {'error': str(e), 'type': type(e).__name__})
