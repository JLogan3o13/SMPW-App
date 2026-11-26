import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('Destinations')
    
    try:
        # Handle CORS preflight
        if event['httpMethod'] == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS'
                },
                'body': ''
            }
        
        # Parse request body
        if not event.get('body'):
            raise ValueError("Missing request body")
            
        body = json.loads(event['body'])
        
        # Validate required fields
        required_fields = ['eventId', 'updates']
        for field in required_fields:
            if field not in body:
                raise ValueError(f"Missing required field: {field}")
        
        event_id = body['eventId']
        updates = body['updates']  # List of {zone, label, newRoute}
        
        print(f"DEBUG - Processing {len(updates)} route updates for event: {event_id}")
        
        # Process each update
        success_count = 0
        error_count = 0
        errors = []
        
        for update in updates:
            try:
                zone = update['zone']
                label = update['label']  
                new_route = update['newRoute']
                
                print(f"DEBUG - Updating {label} to {new_route}")
                
                # Update using the new key structure: EventID + Label
                response = table.update_item(
                    Key={
                        'EventID': event_id,
                        'Label': label
                    },
                    UpdateExpression='SET ActiveRoute = :route',
                    ExpressionAttributeValues={
                        ':route': new_route
                    },
                    ReturnValues='UPDATED_NEW'
                )
                
                success_count += 1
                print(f"DEBUG - Successfully updated {label} to {new_route}")
                
            except ClientError as e:
                error_msg = f"Failed to update {update.get('label', 'unknown')}: {str(e)}"
                print(f"ERROR - {error_msg}")
                errors.append(error_msg)
                error_count += 1
            except Exception as e:
                error_msg = f"Unexpected error updating {update.get('label', 'unknown')}: {str(e)}"
                print(f"ERROR - {error_msg}")
                errors.append(error_msg)
                error_count += 1
        
        # Return results
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': True,
                'message': f'Updated {success_count} routes successfully',
                'successCount': success_count,
                'errorCount': error_count,
                'errors': errors,
                'eventId': event_id
            })
        }
        
    except ValueError as e:
        print(f"ERROR - Validation error: {str(e)}")
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': False,
                'error': f'Validation error: {str(e)}'
            })
        }
    except Exception as e:
        print(f"ERROR - Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
        }