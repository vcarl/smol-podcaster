import os
import boto3
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = 'smol-podcaster'

session = boto3.session.Session()
client = session.client(
    's3',
    region_name=os.environ.get('OPTIONAL_REGION', 'nyc3'),
    endpoint_url=os.environ.get('OPTIONAL_ENDPOINT_URL', 'https://nyc3.digitaloceanspaces.com'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID')
)
response = client.list_buckets()
if len(response["Buckets"]) == 0:
    client.create_bucket(Bucket=BUCKET_NAME)

def get_public_url(path):
    return f"https://{BUCKET_NAME}.{os.environ.get('REGION', 'nyc3')}.digitaloceanspaces.com/{path}"

# Function to upload a file to a given bucket
def upload_file(path, upload_path):
    # Don't upload if the hash matches
    hash = _get_file_hash(path)
    original_file_hash = None
    try:
        response = client.head_object(Bucket=BUCKET_NAME, Key=upload_path)
        original_file_hash = response['Metadata'].get('sha256')
    except Exception as e:
        original_file_hash = None

    if original_file_hash == hash:
        print('Not uploading again, found a remote file with the same hash')
        return 

    print('uploading file…')
    client.upload_file(path, BUCKET_NAME, upload_path, ExtraArgs={'ACL': 'public-read', 'Metadata': {'sha256': hash}})
    print('uploading file… done')

import hashlib

def _get_file_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read only 4K at a time to avoid memory overflow
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
