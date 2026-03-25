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

        # Build update expression dynamically so copilot fields are optional
        update_parts = [
            'firstName = :firstName',
            'lastName = :lastName',
            'phoneNumber = :phoneNumber',
            'make = :make',
            'model = :model',
            'seatCapacity = :capacity'
        ]

        expression_values = {
            ':firstName':   body['firstName'],
            ':lastName':    body['lastName'],
            ':phoneNumber': body['phoneNumber'],
            ':make':        body['make'],
            ':model':       body['model'],
            ':capacity':    int(body['seatCapacity'])
        }

        # Include copilot fields only if present in the payload
        if 'copilotFirstName' in body:
            update_parts.append('copilotFirstName = :copilotFirstName')
            expression_values[':copilotFirstName'] = body['copilotFirstName']

        if 'copilotLastName' in body:
            update_parts.append('copilotLastName = :copilotLastName')
            expression_values[':copilotLastName'] = body['copilotLastName']

        if 'copilotPhone' in body:
            update_parts.append('copilotPhone = :copilotPhone')
            expression_values[':copilotPhone'] = body['copilotPhone']

        update_expression = 'SET ' + ', '.join(update_parts)

        response = table.update_item(
            Key={'driverId': driver_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
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
