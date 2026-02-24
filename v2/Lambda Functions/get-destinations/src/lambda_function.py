import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timezone, timedelta
import urllib.request
from decimal import Decimal

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def get_geometry(item, route_key: str):
    """
    route_key examples:
      'Route1', 'Route2', 'Route3',
      'Route1Return', 'Route2Return', 'Route3Return'
    Looks for e.g. 'Route1Geometry', 'Route1ReturnGeometry'
    """
    geometry_attr = f"{route_key}Geometry"
    geo = item.get(geometry_attr)

    # Expect DynamoDB Map that already looks like GeoJSON
    # when deserialized via boto3: {'type': 'LineString', 'coordinates': [[lng, lat], ...]}
    if isinstance(geo, dict) and geo.get("type") == "LineString":
        return geo

    return None

def get_instructions(item, route_key: str):
    """
    Get turn-by-turn instructions for a route.
    route_key examples: 'Route1', 'Route1Return'
    Looks for 'routeInstructions' (for Route1) or 'returnRouteInstructions' (for Route1Return)
    
    Note: Currently we only support instructions for the base routes (Route1/Route1Return)
    since we're storing them as 'routeInstructions' and 'returnRouteInstructions'
    """
    # Map route keys to instruction attribute names
    # For now, we assume Route1 uses the base attributes
    if 'Return' in route_key:
        instructions_attr = 'returnRouteInstructions'
    else:
        instructions_attr = 'routeInstructions'
    
    instructions = item.get(instructions_attr)
    
    # Return the instructions array if it exists and is not empty
    if isinstance(instructions, list) and len(instructions) > 0:
        return instructions
    
    return None

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
            # Parse sunset time - comes in ISO format with timezone
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
    Determine which parking photo to show based on current time vs sunset
    Returns the appropriate photo URL with fallback logic
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
        # Get sunset time for this location (timezone-aware UTC)
        sunset_time = get_sunset_time(lat, lng)
        
        # Get current time (timezone-aware UTC)
        current_time = datetime.now(timezone.utc)
        
        print(f"DEBUG - Location: {item.get('Label')}")
        print(f"DEBUG - Current UTC: {current_time.isoformat()}")
        print(f"DEBUG - Sunset UTC: {sunset_time.isoformat()}")
        
        # Calculate time difference to see if we're within the same "day cycle"
        # If sunset is more than 12 hours in the future, it's tomorrow's sunset
        time_diff = (sunset_time - current_time).total_seconds()
        print(f"DEBUG - Time until sunset: {time_diff / 3600:.2f} hours")
        
        # Determine which photo to use
        # If time_diff is negative, we're past sunset
        # If time_diff is positive but > 12 hours, sunset is tomorrow (so we're past today's sunset)
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
        # If anything goes wrong, use day photo as safe default
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
            
            print(f"DEBUG - Found {len(response['Items'])} items")
            
            # Build locations using each location's individual ActiveRoute setting
            locations = []
            for item in response['Items']:
                # Get the active route for this specific location (default to Route1)
                active_route = item.get('ActiveRoute', 'Route1')
                
                # Get all available routes for this location (outbound)
                route1_url = item.get('Route1', '')
                route2_url = item.get('Route2', '')
                route3_url = item.get('Route3', '')
                
                # Get return routes
                route1_return_url = item.get('Route1Return', '')
                route2_return_url = item.get('Route2Return', '')
                route3_return_url = item.get('Route3Return', '')
                
                # Get the URL for the currently active route (outbound)
                active_route_url = item.get(active_route, route1_url)
                
                # Get the URL for the currently active return route
                active_return_route = f"{active_route}Return"
                active_return_url = item.get(active_return_route, route1_return_url)
                
                # Determine which parking photo to show (day/night based on sunset)
                parking_photo = determine_parking_photo(item)

                # Get geometry for the current active route
                active_route_geometry = get_geometry(item, active_route)
                active_return_geometry = get_geometry(item, active_return_route)

                # NEW: Get turn-by-turn instructions for the current active route
                active_route_instructions = get_instructions(item, active_route)
                active_return_instructions = get_instructions(item, active_return_route)

                available_route_geometries = {
                    'Route1': get_geometry(item, 'Route1'),
                    'Route2': get_geometry(item, 'Route2'),
                    'Route3': get_geometry(item, 'Route3')
                }

                available_return_route_geometries = {
                    'Route1Return': get_geometry(item, 'Route1Return'),
                    'Route2Return': get_geometry(item, 'Route2Return'),
                    'Route3Return': get_geometry(item, 'Route3Return')
                }
                
                location = {
                    'label': item['Label'],
                    'directions': active_route_url,  # Outbound route
                    'directionsReturn': active_return_url,  # Return route
                    'activeRoute': active_route,
                    'availableRoutes': {
                        'Route1': route1_url,
                        'Route2': route2_url, 
                        'Route3': route3_url
                    },
                    'availableReturnRoutes': {
                        'Route1Return': route1_return_url,
                        'Route2Return': route2_return_url,
                        'Route3Return': route3_return_url
                    },
                    'parkingPhoto': parking_photo,
                    'locationId': f"{item['Zone']}-{item['Label'].replace(' ', '-')}",
                    'routeGeometry': active_route_geometry,
                    'returnRouteGeometry': active_return_geometry,
                    'routeInstructions': active_route_instructions,  # NEW
                    'returnRouteInstructions': active_return_instructions,  # NEW
                    'availableRouteGeometries': available_route_geometries,
                    'availableReturnRouteGeometries': available_return_route_geometries
                }

                locations.append(location)
                print(f"DEBUG - Added location: {item['Label']} with {len(active_route_instructions) if active_route_instructions else 0} outbound instructions")
                print(f"DEBUG locations sample: ",json.dumps(locations[:1], default=str)[:500])
            
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
                }, default=decimal_default)
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
                }, default=decimal_default)
            }
            
    except Exception as e:
        print(f"ERROR - Lambda handler error: {str(e)}")
        import traceback
        print(f"ERROR - Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }