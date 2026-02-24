import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MasterDrivers')

def lambda_handler(event, context):
    try:
        # Parse the request body or path parameters
        if event.get('body'):
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
            driver_id = body['driverId']
        elif event.get('pathParameters'):
            driver_id = event['pathParameters']['driverId']
        else:
            raise ValueError('driverId not provided')
        
        # Delete driver from DynamoDB
        table.delete_item(
            Key={'driverId': driver_id}
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps({
                'message': 'Driver deleted successfully',
                'driverId': driver_id
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