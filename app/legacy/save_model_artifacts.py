# %%
import os 
import requests
import pickle
from google.cloud import storage
from google.oauth2 import service_account
import json

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    # The ID of your GCS bucket
    # bucket_name = "your-bucket-name"

    # The ID of your GCS object
    # source_blob_name = "storage-object-name"

    # The path to which the file should be downloaded
    # destination_file_name = "local/path/to/file"
    
    service_cred = os.environ.get("SERVICE_CRED")
    service_acc_creds = json.loads(service_cred)
    credentials = service_account.Credentials.from_service_account_info(service_acc_creds)
    storage_client = storage.Client(credentials=credentials, project="hot-or-not-feed-intelligence")

    bucket = storage_client.bucket(bucket_name)

    # Construct a client side representation of a blob.
    # Note `Bucket.blob` differs from `Bucket.get_blob` as it doesn't retrieve
    # any content from Google Cloud Storage. As we don't need additional data,
    # using `Bucket.blob` is preferred here.
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)

    print(
        "Downloaded storage object {} from bucket {} to local file {}.".format(
            source_blob_name, bucket_name, destination_file_name
        )
    )

def download_artifacts():
    # Create the directory if it doesn't exist
    print("Downloading model artifacts")
    os.makedirs("model_artifacts", exist_ok=True)

    # Download the files if they don't already exist
    if not os.path.exists("model_artifacts/pipe3c.pkl"):
        download_blob("yral-ds-model-artifacts", "pipe3c.pkl", "model_artifacts/pipe3c.pkl")

    if not os.path.exists("model_artifacts/pipe5c.pkl"):
        download_blob("yral-ds-model-artifacts", "pipe5c.pkl", "model_artifacts/pipe5c.pkl")

    if not os.path.exists("model_artifacts/nsfw_rf_classifier_40k.pkl"):
        download_blob("yral-ds-model-artifacts", "nsfw_rf_classifier_40k.pkl", "model_artifacts/nsfw_rf_classifier_40k.pkl")

    with open("model_artifacts/pipe3c.pkl", "rb") as f:
        pipe3c = pickle.load(f)

    with open("model_artifacts/pipe5c.pkl", "rb") as f: 
        pipe5c = pickle.load(f)

    with open("model_artifacts/nsfw_rf_classifier_40k.pkl", "rb") as f:
        nsfw_rf_classifier_40k = pickle.load(f)

    print(pipe3c.model.config)  
    print(pipe5c.model.config)  

    return pipe3c, pipe5c, nsfw_rf_classifier_40k


