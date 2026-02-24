import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('DailyOperations')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Parse the request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        print(f"Parsed body: {json.dumps(body)}")
        
        driver_id = body.get('driverId')
        event_date = body.get('eventDate')
        
        if not driver_id or not event_date:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'driverId and eventDate are required'})
            }
        
        # Get current state before update to detect status changes
        try:
            current_item = table.get_item(
                Key={
                    'driverId': driver_id,
                    'eventDate': event_date
                }
            ).get('Item', {})
            old_status = current_item.get('status')
            old_zone = current_item.get('zone')
            old_passengers = int(current_item.get('passengers', 0))
        except:
            old_status = None
            old_zone = None
            old_passengers = 0
        
        # Build update expression dynamically based on provided fields
        update_parts = []
        expression_values = {}
        expression_names = {}
        
        # CRITICAL: Set both lowercase (for table) and uppercase (for GSI) versions
        update_parts.append('EventDate = :EventDate')
        expression_values[':EventDate'] = event_date
        
        update_parts.append('DriverID = :DriverID')
        expression_values[':DriverID'] = driver_id
        
        new_status = body.get('status', old_status)
        new_zone = body.get('zone', old_zone)
        new_passengers = int(body.get('passengers', old_passengers)) if 'passengers' in body else old_passengers
        
        if 'carNumber' in body:
            update_parts.append('carNumber = :carNumber')
            expression_values[':carNumber'] = body['carNumber']
        
        if 'zone' in body:
            update_parts.append('#zone = :zone')
            expression_values[':zone'] = body['zone']
            expression_names['#zone'] = 'zone'
        
        if 'passengers' in body:
            update_parts.append('passengers = :passengers')
            expression_values[':passengers'] = int(body['passengers'])
        
        if 'driverType' in body:
            update_parts.append('driverType = :driverType')
            expression_values[':driverType'] = body['driverType']
        
        if 'status' in body:
            update_parts.append('#status = :status')
            expression_values[':status'] = body['status']
            expression_names['#status'] = 'status'
        
        update_expression = 'SET ' + ', '.join(update_parts)
        
        print(f"Update expression: {update_expression}")
        print(f"Expression values: {expression_values}")
        print(f"Expression names: {expression_names}")
        
        # Update or create the daily operation record
        update_params = {
            'Key': {
                'driverId': driver_id,
                'eventDate': event_date
            },
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values,
            'ReturnValues': 'ALL_NEW'
        }
        
        if expression_names:
            update_params['ExpressionAttributeNames'] = expression_names
        
        response = table.update_item(**update_params)
        updated_item = response.get('Attributes', {})
        
        print(f"Update response: {json.dumps(response, default=str)}")
        
        # Handle zone total updates based on status transitions
        zone_update_result = None
        
        # Status changed to "Dropped Off" - add passengers to zone
        if new_status == 'Dropped Off' and old_status != 'Dropped Off' and new_passengers > 0 and new_zone:
            print(f"Status changed to Dropped Off: Adding {new_passengers} to zone {new_zone}")
            zone_update_result = lambda_client.invoke(
                FunctionName='updateZoneTotals',
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'body': json.dumps({
                        'eventDate': event_date,
                        'zone': new_zone,
                        'action': 'deliver',
                        'passengers': new_passengers
                    })
                })
            )
            
            # Clear passengers after drop-off
            table.update_item(
                Key={
                    'driverId': driver_id,
                    'eventDate': event_date
                },
                UpdateExpression='SET passengers = :zero',
                ExpressionAttributeValues={':zero': 0}
            )
        
        # Status changed to "Picked Up" - subtract passengers from zone
        elif new_status == 'Picked Up' and old_status != 'Picked Up' and new_passengers > 0 and new_zone:
            print(f"Status changed to Picked Up: Subtracting {new_passengers} from zone {new_zone}")
            zone_update_result = lambda_client.invoke(
                FunctionName='updateZoneTotals',
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'body': json.dumps({
                        'eventDate': event_date,
                        'zone': new_zone,
                        'action': 'pickup',
                        'passengers': new_passengers
                    })
                })
            )
            
            # Clear passengers after pickup
            table.update_item(
                Key={
                    'driverId': driver_id,
                    'eventDate': event_date
                },
                UpdateExpression='SET passengers = :zero',
                ExpressionAttributeValues={':zero': 0}
            )
        
        # Status changed to "Available" from "Dropped Off" or "Picked Up"
        if new_status == 'Available' and old_status in ['Dropped Off', 'Picked Up']:
            print(f"Status changed to Available from {old_status}")
            
            # Get the driver type to check if it's Staged
            driver_type = updated_item.get('driverType', 'Normal')
            
            if driver_type == 'Staged':
                # Staged drivers: clear passengers but KEEP zone
                print(f"Driver is Staged - keeping zone, clearing passengers only")
                table.update_item(
                    Key={
                        'driverId': driver_id,
                        'eventDate': event_date
                    },
                    UpdateExpression='SET passengers = :zero',
                    ExpressionAttributeValues={':zero': 0}
                )
            else:
                # Normal/Reserved/Assigned drivers: clear both zone and passengers
                print(f"Driver is {driver_type} - clearing zone and passengers")
                table.update_item(
                    Key={
                        'driverId': driver_id,
                        'eventDate': event_date
                    },
                    UpdateExpression='SET #zone = :empty, passengers = :zero',
                    ExpressionAttributeNames={'#zone': 'zone'},
                    ExpressionAttributeValues={':empty': '', ':zero': 0}
                )
        
        # Status changed to "Checked Out" - clear passengers, zone, and reset driverType to Normal
        if new_status == 'Checked Out' and old_status != 'Checked Out':
            print(f"Status changed to Checked Out - clearing passengers, zone, and resetting driverType to Normal")
            table.update_item(
                Key={
                    'driverId': driver_id,
                    'eventDate': event_date
                },
                UpdateExpression='SET #zone = :empty, passengers = :zero, driverType = :normal',
                ExpressionAttributeNames={'#zone': 'zone'},
                ExpressionAttributeValues={':empty': '', ':zero': 0, ':normal': 'Normal'}
            )
        
        # Status changed FROM "Checked Out" to "Available" - ensure fields are cleared
        if new_status == 'Available' and old_status == 'Checked Out':
            print(f"Status changed from Checked Out to Available - ensuring passengers, zone cleared and driverType is Normal")
            table.update_item(
                Key={
                    'driverId': driver_id,
                    'eventDate': event_date
                },
                UpdateExpression='SET #zone = :empty, passengers = :zero, driverType = :normal',
                ExpressionAttributeNames={'#zone': 'zone'},
                ExpressionAttributeValues={':empty': '', ':zero': 0, ':normal': 'Normal'}
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
                'message': 'Daily operation updated successfully',
                'operation': updated_item,
                'zoneUpdate': zone_update_result is not None
            }, default=str)
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