import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('Destinations')

def lambda_handler(event, context):
    try:
        # Scan all items from Destinations table
        response = table.scan()
        items = response.get('Items', [])
        
        # Extract unique zones
        zones = set()
        for item in items:
            if 'Zone' in item and item['Zone'].get('S'):
                zones.add(item['Zone']['S'])
        
        # Sort zones
        sorted_zones = sorted(list(zones))
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps(sorted_zones)
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