import json
import boto3
import uuid
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MasterDrivers')

def lambda_handler(event, context):
    try:
        # Parse the request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event['body']
        
        # Generate unique driverId
        driver_id = str(uuid.uuid4())
        
        # Create driver item
        item = {
            'driverId': driver_id,
            'name': body['name'],
            'make': body['make'],
            'model': body['model'],
            'seatCapacity': int(body['seatCapacity'])
        }
        
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
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }