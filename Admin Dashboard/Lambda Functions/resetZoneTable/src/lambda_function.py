import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('ZoneTotals')

def lambda_handler(event, context):
    try:
        # Get eventDate from query parameters
        query_params = event.get('queryStringParameters') or {}
        event_date = query_params.get('eventDate')
        
        if not event_date:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'eventDate parameter required'})
            }
        
        print(f"Resetting zone totals for event date: {event_date}")
        
        # Query all items for this event date
        response = table.query(
            KeyConditionExpression='EventDate = :date',
            ExpressionAttributeValues={
                ':date': event_date
            }
        )
        
        items = response.get('Items', [])
        deleted_count = 0
        
        # Delete each item
        for item in items:
            table.delete_item(
                Key={
                    'EventDate': item['EventDate'],
                    'zone': item['zone']
                }
            )
            deleted_count += 1
        
        print(f"Deleted {deleted_count} zone total records")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, DELETE, OPTIONS'
            },
            'body': json.dumps({
                'message': f'Successfully reset {deleted_count} zones for {event_date}'
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
            'body': json.dumps({'error': str(e)})
        }