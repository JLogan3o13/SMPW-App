import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MasterDrivers')

def lambda_handler(event, context):
    try:
        # Parse the request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event['body']
        
        driver_id = body['driverId']
        
        # Update driver item
        response = table.update_item(
            Key={'driverId': driver_id},
            UpdateExpression='SET #name = :name, phoneNumber = :phoneNumber, make = :make, model = :model, seatCapacity = :capacity',
            ExpressionAttributeNames={
                '#name': 'name'  # 'name' is a reserved word in DynamoDB
            },
            ExpressionAttributeValues={
                ':name': body['name'],
                ':phoneNumber': body['phoneNumber'],
                ':make': body['make'],
                ':model': body['model'],
                ':capacity': int(body['seatCapacity'])
            },
            ReturnValues='ALL_NEW'
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
                'message': 'Driver updated successfully',
                'driver': response['Attributes']
            }, default=str)
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