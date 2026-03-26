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

        # Core fields always present
        set_parts = [
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

        # Copilot fields: SET if non-empty, REMOVE if empty
        remove_parts = []
        copilot_fields = ['copilotFirstName', 'copilotLastName', 'copilotPhone']

        for field in copilot_fields:
            if field in body:
                if body[field]:  # non-empty value — set it
                    set_parts.append(f'{field} = :{field}')
                    expression_values[f':{field}'] = body[field]
                else:  # empty string — remove the attribute entirely
                    remove_parts.append(field)

        # Build final update expression
        update_expression = 'SET ' + ', '.join(set_parts)
        if remove_parts:
            update_expression += ' REMOVE ' + ', '.join(remove_parts)

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
