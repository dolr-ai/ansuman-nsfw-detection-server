# %%
import os 
import requests
import pickle
from google.cloud import storage
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from google.oauth2 import service_account
import json

def download_blob_to_memory(blob):
    """Helper function to download a single blob to memory and return it as a PIL image."""
    image_data = blob.download_as_bytes()
    image = Image.open(BytesIO(image_data))
    return {'file_name': blob.name, 'image': image}

def get_images_from_gcs(bucket_name='yral-video-frames', folder_name='', n_workers=20):
    """Downloads all files from a GCS folder and returns a list of PIL images using multithreading."""

    
    service_cred = os.environ.get("SERVICE_CRED")
    service_acc_creds = json.loads(service_cred)
    credentials = service_account.Credentials.from_service_account_info(service_acc_creds)
    storage_client = storage.Client(credentials=credentials, project="hot-or-not-feed-intelligence")
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=folder_name))

    images = []

    with ThreadPoolExecutor(n_workers) as executor:
        futures = []
        for blob in blobs:
            futures.append(executor.submit(download_blob_to_memory, blob))

        # Wait for all threads to complete and collect the images
        for future in futures:
            images.append(future.result())

    return images

if __name__ == "__main__":  
    frame_folder = "00034f1c9c9148388bf6873776222535"
    images = get_images_from_gcs("yral-video-frames", frame_folder)
    print(sorted(images, key = lambda x: x['file_name']))