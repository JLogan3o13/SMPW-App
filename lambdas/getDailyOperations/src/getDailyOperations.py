import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
operations_table = dynamodb.Table('DailyOperations')
master_table = dynamodb.Table('MasterDrivers')

HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
}


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)


def display_name(driver):
    """'First Last' when available, else legacy 'name', else a visible warning."""
    full = f"{(driver.get('firstName') or '').strip()} {(driver.get('lastName') or '').strip()}".strip()
    return full or driver.get('name') or '⚠️ Unknown driver'


def scan_all(table):
    """Scan every item, following pagination (each call returns at most 1 MB)."""
    response = table.scan()
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    return items


def query_all_for_date(event_date):
    """Query every DailyOperations row for one date, following pagination."""
    kwargs = {
        'IndexName': 'EventDateIndex',
        'KeyConditionExpression': 'EventDate = :date',
        'ExpressionAttributeValues': {':date': event_date}
    }
    response = operations_table.query(**kwargs)
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = operations_table.query(ExclusiveStartKey=response['LastEvaluatedKey'], **kwargs)
        items.extend(response.get('Items', []))
    return items


def lambda_handler(event, context):
    try:
        # queryStringParameters is None (not {}) when no query string is sent
        params = event.get('queryStringParameters') or {}
        event_date = params.get('eventDate')

        if not event_date:
            return {
                'statusCode': 400,
                'headers': HEADERS,
                'body': json.dumps({'error': 'eventDate parameter required'})
            }

        master_drivers = scan_all(master_table)
        daily_ops = query_all_for_date(event_date)

        ops_map = {op.get('driverId', ''): op for op in daily_ops}

        result = []
        for driver in master_drivers:
            driver_id = driver.get('driverId')
            if not driver_id:
                print(f"Skipping master record with no driverId: {driver}")
                continue

            daily_op = ops_map.get(driver_id, {})

            # Every field uses .get so one incomplete record can't take down the board
            merged = {
                'driverId': driver_id,
                'name': display_name(driver),
                'make': driver.get('make', ''),
                'model': driver.get('model', ''),
                'seatCapacity': driver.get('seatCapacity', 0),
                'carNumber': daily_op.get('carNumber', ''),
                'zone': daily_op.get('zone', ''),
                'passengers': daily_op.get('passengers', 0),
                'driverType': daily_op.get('driverType', 'Normal'),
                'status': daily_op.get('status', 'Checked Out')
            }
            result.append(merged)

        return {
            'statusCode': 200,
            'headers': HEADERS,
            'body': json.dumps(result, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
