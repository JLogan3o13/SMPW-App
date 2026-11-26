import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('ZoneTotals')

# Standard zones, always returned (with zeros when there's no activity yet).
# Overflow zones (<Zone><Sub-zone>Z, e.g. B1Z) are listed at the end of their parent zone.
# Any other zone found in the table for the date is also returned, after these,
# so a new zone shows up without editing this list.
ALL_ZONES = [
    'A1', 'A2', 'A3',
    'B1', 'B2', 'B3', 'B4', 'B5', 'B1Z',
    'C1', 'C2', 'C3', 'C4', 'C2Z', 'C4Z',
    'D1', 'D2', 'D3', 'D4', 'D5', 'D3Z',
    'E1', 'E2', 'E3', 'E4', 'E5Z', 'E6Z', 'E7Z',
    'F1', 'F2', 'F3', 'F4', 'F5Z',
]

# Zones that are no longer used and should never be returned
RETIRED_ZONES = {'Z'}

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
            query_kwargs = {
                'KeyConditionExpression': 'EventDate = :date',
                'ExpressionAttributeValues': {':date': event_date}
            }
            zone_totals = []
            while True:
                response = table.query(**query_kwargs)
                zone_totals.extend(response.get('Items', []))
                if 'LastEvaluatedKey' not in response:
                    break
                query_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            print(f"Found {len(zone_totals)} zone totals in database")
        except Exception as e:
            print(f"Error querying table: {str(e)}")
            zone_totals = []
        
        zone_map = {zt['zone']: zt for zt in zone_totals if zt.get('zone')}

        # Standard zones first, then any other (non-retired) zones found in the table
        extra_zones = sorted(z for z in zone_map if z not in ALL_ZONES and z not in RETIRED_ZONES)
        zones_to_return = ALL_ZONES + extra_zones
        if extra_zones:
            print(f"Including zones not in standard list: {extra_zones}")
        
        result = []
        for zone in zones_to_return:
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