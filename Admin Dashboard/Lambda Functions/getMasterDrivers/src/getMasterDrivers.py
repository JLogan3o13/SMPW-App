import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MasterDrivers')


def display_name(driver):
    """'First Last' when available, else legacy 'name', else a visible warning."""
    full = f"{(driver.get('firstName') or '').strip()} {(driver.get('lastName') or '').strip()}".strip()
    return full or driver.get('name') or '⚠️ Unknown driver'

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    try:
        # Scan all items from MasterDrivers table
        # Scan all items, following pagination (scan returns at most 1 MB per call)
        response = table.scan()
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        # Always return a consistent display name
        for item in items:
            item['name'] = display_name(item)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps(items, cls=DecimalEncoder)
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