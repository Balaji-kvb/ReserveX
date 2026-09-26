import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    AWS Lambda handler for the ReserveX webhook.
    Receives booking confirmation payloads and logs them.
    In a real system, this might send an email via SES or push a metric.
    
    CRITICAL ARCHITECTURE RULE (Phase 16):
    This function is invoked ASYNCHRONOUSLY by the Booking Service.
    If this function crashes, times out, or throws an error, it MUST NOT
    affect the user's booking, which has already been committed to PostgreSQL.
    """
    logger.info("Webhook received event!")
    
    try:
        # For API Gateway or Lambda Function URLs, the body is a string
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            body = event
            
        booking_id = body.get('booking_id')
        user_id = body.get('user_id')
        event_id = body.get('event_id')
        
        logger.info(f"Processing webhook for Booking ID: {booking_id}")
        logger.info(f"User {user_id} successfully booked Event {event_id}")
        
        # Simulate some processing time
        # import time; time.sleep(2)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Webhook processed successfully'})
        }
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        # We return 500, but because the caller used a fire-and-forget
        # non-blocking request, the main booking flow is unaffected.
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
