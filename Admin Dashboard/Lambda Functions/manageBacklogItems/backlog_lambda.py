"""
manageBacklogItems - Lambda handler for the admin Backlog dashboard.

Routes (API Gateway REST API, Lambda proxy integration):
    GET    /backlog              -> list all backlog items
    POST   /backlog              -> create an item (ID is generated: MAP-001, ADMIN-001, BOTH-001, ...)
    GET    /backlog/{itemId}     -> get one item
    PUT    /backlog/{itemId}     -> update name/description/status/priority/event/notes
    DELETE /backlog/{itemId}     -> delete an item

DynamoDB table: BacklogItems (partition key: itemId, String)
    Counter records "COUNTER#MAP", "COUNTER#ADMIN" and "COUNTER#BOTH" live in the same table
    and hold the last number issued for each app. They are hidden from the list.
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


def sort_key(item):
    app = item.get('app', '')
    return (APPS.index(app) if app in APPS else 99, int(item.get('itemNumber', 0)))


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def list_items():
    items = []
    scan_kwargs = {}
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(with_defaults(i) for i in resp.get('Items', [])
                     if not i.get('itemId', '').startswith(COUNTER_PREFIX))
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
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
            return respond(201, {'item': item})
        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
    raise RuntimeError(f'Could not allocate a new {app} ID after 5 attempts')


def update_item(item_id, data):
    item_id = normalize_id(item_id)
    fields = clean_fields(data, creating=False)
    if not fields:
        raise ValidationError(f'Provide at least one of: {", ".join(EDITABLE_FIELDS)}')

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
    return respond(200, {'item': with_defaults(resp['Attributes'])})


def delete_item(item_id):
    item_id = normalize_id(item_id)
    try:
        table.delete_item(Key={'itemId': item_id}, ConditionExpression='attribute_exists(itemId)')
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise NotFoundError(f'Item {item_id} not found')
        raise
    print(f'Deleted {item_id}')
    return respond(200, {'deleted': item_id})


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
