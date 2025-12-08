import json
import boto3
from boto3.dynamodb.conditions import Key, Attr

def lambda_handler(event, context):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('Destinations')
    
    try:
        query_params = event.get('queryStringParameters') or {}
        event_id = query_params.get('event', 'RaidersGames')
        zone = query_params.get('zone')
        
        print(f"DEBUG - Event ID: {event_id}, Zone: {zone}")
        
        if zone:
            # Get locations for specific zone within the event
            response = table.scan(
                FilterExpression=Attr('EventID').eq(event_id) & Attr('Zone').eq(zone)
            )
            
            # Build locations using each location's individual ActiveRoute setting
            locations = []
            for item in response['Items']:
                # Get the active route for this specific location (default to Route1)
                active_route = item.get('ActiveRoute', 'Route1')
                
                # Get all available routes for this location
                route1_url = item.get('Route1', '')
                route2_url = item.get('Route2', '')
                route3_url = item.get('Route3', '')
                
                # Get the URL for the currently active route
                active_route_url = item.get(active_route, route1_url)
                
                location = {
                    'label': item['Label'],
                    'directions': active_route_url,  # The active route URL
                    'activeRoute': active_route,
                    'availableRoutes': {
                        'Route1': route1_url,
                        'Route2': route2_url, 
                        'Route3': route3_url
                    },
                    'parkingPhoto': item.get('ParkingPhoto', ''),
                    'locationId': f"{item['Zone']}-{item['Label'].replace(' ', '-')}"
                }
                locations.append(location)
                print(f"DEBUG - {item['Label']} using {active_route} -> {active_route_url[:50]}...")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'locations': locations,
                    'event': event_id
                })
            }
        else:
            # Get all zones for the specific event
            response = table.scan(
                FilterExpression=Attr('EventID').eq(event_id),
                ProjectionExpression='#z',
                ExpressionAttributeNames={'#z': 'Zone'}
            )
            zones = list(set(item['Zone'] for item in response['Items']))
            zones.sort()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'zones': zones, 
                    'event': event_id
                })
            }
            
    except Exception as e:
        print(f"DEBUG - Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }