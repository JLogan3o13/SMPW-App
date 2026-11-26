import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timezone, timedelta
import urllib.request

def get_sunset_time(lat, lng):
    """
    Get sunset time for given coordinates using sunrise-sunset.org API
    Returns timezone-aware datetime in UTC
    """
    try:
        url = f'https://api.sunrise-sunset.org/json?lat={lat}&lng={lng}&formatted=0'
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read())
            
        if data['status'] == 'OK':
            sunset_str = data['results']['sunset']
            sunset_dt = datetime.fromisoformat(sunset_str.replace('Z', '+00:00'))
            print(f"DEBUG - Sunset API returned: {sunset_dt.isoformat()}")
            return sunset_dt
    except Exception as e:
        print(f"DEBUG - Sunset API error: {str(e)}")
    
    # Fallback: 2 AM UTC tomorrow = 6 PM Vegas today (PST)
    fallback = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0) + timedelta(days=1)
    print(f"DEBUG - Using fallback sunset time: {fallback.isoformat()}")
    return fallback

def determine_parking_photo(item):
    """
    Determine which parking photo to show based on current time vs sunset.
    Supports both old (ParkingPhoto) and new (ParkingPhotoDay/Night) schema.
    """
    # Get coordinates
    lat = float(item.get('Lat', 36.0859))
    lng = float(item.get('Lng', -115.18582))
    
    # Get photo URLs
    photo_day = item.get('ParkingPhotoDay', '')
    photo_night = item.get('ParkingPhotoNight', '')
    photo_fallback = item.get('ParkingPhoto', '')
    
    # If no day/night photos configured, use old attribute
    if not photo_day and not photo_night:
        print(f"DEBUG - No day/night photos configured, using fallback")
        return photo_fallback
    
    try:
        sunset_time = get_sunset_time(lat, lng)
        current_time = datetime.now(timezone.utc)
        
        print(f"DEBUG - Location: {item.get('Label')}")
        print(f"DEBUG - Current UTC: {current_time.isoformat()}")
        print(f"DEBUG - Sunset UTC: {sunset_time.isoformat()}")
        
        time_diff = (sunset_time - current_time).total_seconds()
        print(f"DEBUG - Time until sunset: {time_diff / 3600:.2f} hours")
        
        if time_diff < 0 or time_diff > (12 * 3600):
            # After sunset - nighttime
            selected_photo = photo_night or photo_day or photo_fallback
            print(f"DEBUG - NIGHTTIME - Selected: {selected_photo}")
        else:
            # Before sunset - daytime
            selected_photo = photo_day or photo_night or photo_fallback
            print(f"DEBUG - DAYTIME - Selected: {selected_photo}")
        
        return selected_photo
        
    except Exception as e:
        print(f"ERROR - Photo determination failed: {str(e)}")
        return photo_day or photo_fallback

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
                
                # Determine which parking photo to show (day/night based on sunset)
                parking_photo = determine_parking_photo(item)
                
                location = {
                    'label': item['Label'],
                    'directions': active_route_url,  # The active route URL
                    'activeRoute': active_route,
                    'availableRoutes': {
                        'Route1': route1_url,
                        'Route2': route2_url, 
                        'Route3': route3_url
                    },
                    'parkingPhoto': parking_photo,
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
