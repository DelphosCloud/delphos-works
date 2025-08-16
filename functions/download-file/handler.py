import json
import os
import boto3
from botocore.exceptions import ClientError
import base64

def main(event, context):
    """
    Main handler for file downloads
    Streams files from Spaces storage
    """
    try:
        # Get filename from query parameters or path
        filename = None
        
        # Try to get filename from query parameters
        if event.get('queryStringParameters'):
            filename = event['queryStringParameters'].get('file')
        
        # Try to get from path parameters
        if not filename and event.get('pathParameters'):
            filename = event['pathParameters'].get('filename')
        
        # Try to get from headers (for API key auth)
        api_key = None
        if event.get('headers'):
            api_key = event['headers'].get('x-api-key') or event['headers'].get('Authorization')
        
        if not filename:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    "Title": "Error",
                    "Message": "Filename parameter is required"
                })
            }
        
        # Initialize Spaces client
        spaces_client = boto3.client(
            's3',
            endpoint_url=f"https://{os.environ['SPACES_ENDPOINT']}",
            aws_access_key_id=os.environ['SPACES_KEY'],
            aws_secret_access_key=os.environ['SPACES_SECRET']
        )
        
        bucket_name = os.environ['SPACES_BUCKET']
        
        # Determine file path (assume it's in generated folder)
        file_key = f"generated/{filename}"
        
        try:
            # Get the file from Spaces
            file_response = spaces_client.get_object(Bucket=bucket_name, Key=file_key)
            file_content = file_response['Body'].read()
            
            # Determine content type
            content_type = 'application/octet-stream'
            if filename.endswith('.docx'):
                content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif filename.endswith('.pdf'):
                content_type = 'application/pdf'
            
            # Return file as binary response
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': content_type,
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Content-Length': str(len(file_content))
                },
                'body': base64.b64encode(file_content).decode('utf-8'),
                'isBase64Encoded': True
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        "Title": "Error",
                        "Message": "File not found"
                    })
                }
            else:
                raise e
                
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                "Title": "Error",
                "Message": f"Internal server error: {str(e)}"
            })
        }