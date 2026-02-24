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
        print(f"Event received: {json.dumps(event)}")
        
        # Get eventDate from query parameters
        query_params = event.get('queryStringParameters')
        if not query_params:
            query_params = {}
        
        event_date = query_params.get('eventDate')
        
        print(f"Query params: {query_params}")
        print(f"Event date: {event_date}")
        
        if not event_date:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'eventDate parameter required'})
            }
        
        print(f"Fetching zone totals for event date: {event_date}")
        
        # Query all zones for this event date (note: EventDate is capitalized)
        try:
            response = table.query(
                KeyConditionExpression='EventDate = :date',
                ExpressionAttributeValues={
                    ':date': event_date
                }
            )
            zone_totals = response.get('Items', [])
            print(f"Found {len(zone_totals)} zone totals in database")
        except Exception as e:
            print(f"Error querying table: {str(e)}")
            zone_totals = []
        
        # Create a result with all zones (A, A3, B, C, D, E, F, Z)
        all_zones = ['A', 'A3', 'B', 'C', 'D', 'E', 'F', 'Z']
        zone_map = {zt['zone']: zt for zt in zone_totals}
        
        result = []
        for zone in all_zones:
            if zone in zone_map:
                zone_data = zone_map[zone]
                result.append({
                    'eventDate': event_date,
                    'zone': zone,
                    'totalDelivered': int(zone_data.get('totalDelivered', 0)),
                    'totalPickedUp': int(zone_data.get('totalPickedUp', 0)),
                    'netPassengers': int(zone_data.get('netPassengers', 0))
                })
            else:
                # Return zero values for zones with no data
                result.append({
                    'eventDate': event_date,
                    'zone': zone,
                    'totalDelivered': 0,
                    'totalPickedUp': 0,
                    'netPassengers': 0
                })
        
        print(f"Returning {len(result)} zone records")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': json.dumps(result, cls=DecimalEncoder)
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