import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
operations_table = dynamodb.Table('DailyOperations')
master_table = dynamodb.Table('MasterDrivers')

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    try:
        # Get eventDate from query parameters
        event_date = event.get('queryStringParameters', {}).get('eventDate')
        
        if not event_date:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'eventDate parameter required'})
            }
        
        # Get all master drivers
        master_response = master_table.scan()
        master_drivers = master_response.get('Items', [])
        
        # Query DailyOperations by EventDate using GSI
        operations_response = operations_table.query(
            IndexName='EventDateIndex',
            KeyConditionExpression='EventDate = :date',
            ExpressionAttributeValues={
                ':date': event_date
            }
        )
        
        daily_ops = operations_response.get('Items', [])
        
        # Create a map of driverId to daily operations
        ops_map = {op.get('driverId', ''): op for op in daily_ops}
        
        result = []
        for driver in master_drivers:
            driver_id = driver['driverId']
            
            # Get daily operation if it exists, otherwise use defaults
            daily_op = ops_map.get(driver_id, {})
            
            # Merge data - all drivers start as "Checked Out" with no assignments
            merged = {
                'driverId': driver_id,
                'name': driver['name'],
                'make': driver['make'],
                'model': driver['model'],
                'seatCapacity': driver['seatCapacity'],
                'carNumber': daily_op.get('carNumber', ''),
                'zone': daily_op.get('zone', ''),
                'passengers': daily_op.get('passengers', 0),
                'driverType': daily_op.get('driverType', 'Normal'),
                'status': daily_op.get('status', 'Checked Out')
            }
            result.append(merged)
        
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
            'body': json.dumps({'error': str(e)})
        }