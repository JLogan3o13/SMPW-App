import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('ZoneTotals')

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Parse the request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        event_date = body.get('eventDate')
        zone = body.get('zone')
        action = body.get('action')  # 'deliver' or 'pickup'
        passengers = int(body.get('passengers', 0))
        
        if not event_date or not zone or not action:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'eventDate, zone, and action are required'})
            }
        
        print(f"Updating zone {zone} on {event_date}: {action} {passengers} passengers")
        
        # Update zone totals (note: EventDate is capitalized in table)
        if action == 'deliver':
            response = table.update_item(
                Key={
                    'EventDate': event_date,
                    'zone': zone
                },
                UpdateExpression='SET totalDelivered = if_not_exists(totalDelivered, :zero) + :passengers, netPassengers = if_not_exists(netPassengers, :zero) + :passengers',
                ExpressionAttributeValues={
                    ':passengers': passengers,
                    ':zero': 0
                },
                ReturnValues='ALL_NEW'
            )
        elif action == 'pickup':
            response = table.update_item(
                Key={
                    'EventDate': event_date,
                    'zone': zone
                },
                UpdateExpression='SET totalPickedUp = if_not_exists(totalPickedUp, :zero) + :passengers, netPassengers = if_not_exists(netPassengers, :zero) - :passengers',
                ExpressionAttributeValues={
                    ':passengers': passengers,
                    ':zero': 0
                },
                ReturnValues='ALL_NEW'
            )
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'action must be "deliver" or "pickup"'})
            }
        
        print(f"Update response: {json.dumps(response, cls=DecimalEncoder)}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps({
                'message': 'Zone totals updated successfully',
                'zoneTotals': response.get('Attributes', {})
            }, cls=DecimalEncoder)
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