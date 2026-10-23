import json
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MasterDrivers')


def build_display_name(first, last):
    """Single source of truth for a driver's display name: 'First Last'."""
    return f"{(first or '').strip()} {(last or '').strip()}".strip()

def lambda_handler(event, context):
    try:
        print(f"Received event: {json.dumps(event)}")

        # Parse the request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body') or {}

        # Validate required fields up front (avoids raw KeyError -> 500)
        required_fields = ['firstName', 'lastName', 'phoneNumber', 'make', 'model', 'seatCapacity']
        missing = [f for f in required_fields if not str(body.get(f) or '').strip()]
        if missing:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f"Missing required field(s): {', '.join(missing)}"})
            }

        # Generate unique driverId
        driver_id = str(uuid.uuid4())

        # Core fields — same naming as Update_Master_Driver.py
        item = {
            'driverId': driver_id,
            'firstName': body['firstName'].strip(),
            'lastName': body['lastName'].strip(),
            # Derived automatically; Key Team never enters this
            'name': build_display_name(body['firstName'], body['lastName']),
            'phoneNumber': body['phoneNumber'],
            'make': body['make'],
            'model': body['model'],
            'seatCapacity': int(body['seatCapacity'])
        }

        # Copilot fields are optional — only store them if non-empty,
        # matching the SET/REMOVE convention used in Update_Master_Driver.py
        copilot_fields = ['copilotFirstName', 'copilotLastName', 'copilotPhone']
        for field in copilot_fields:
            if body.get(field):
                item[field] = body[field]

        # Put item in DynamoDB
        table.put_item(Item=item)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps({
                'message': 'Driver added successfully',
                'driver': item
            })
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
            'body': json.dumps({'error': str(e), 'type': type(e).__name__})
        }
