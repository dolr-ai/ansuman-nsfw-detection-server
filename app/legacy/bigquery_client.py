##
import os
import pickle
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import json
from . import consts

def video_id_to_uri(video_id):
    return f"gs://yral-videos/{video_id}.mp4"

def validate_embedding_dim(embeddings: list[list[float]]):
    validated_embeddings = []
    for embedding in embeddings:
        if len(embedding) != consts.EMBEDDING_DIM:
            continue
        validated_embeddings.append(embedding)
    return validated_embeddings

class BigQueryClient:
    def __init__(self):
        service_cred = os.environ.get("SERVICE_CRED")
        service_acc_creds = json.loads(service_cred)
        credentials = service_account.Credentials.from_service_account_info(service_acc_creds)
        self.client = bigquery.Client(
            credentials=credentials, project=consts.PROJECT_NAME
        )

    def query(self, query):
        query_job = self.client.query(query)
        results = query_job.result()
        return self._to_dataframe(results)

    def _to_dataframe(self, results):
        rows = [dict(row) for row in results]
        return pd.DataFrame(rows)

    def get_embeddings(self, video_id):
        uri = video_id_to_uri(video_id)
        query = f"SELECT ml_generate_embedding_result as embedding FROM `hot-or-not-feed-intelligence.yral_ds.video_embeddings` WHERE uri = '{uri}'"
        df = self.query(query)
        return validate_embedding_dim(df.embedding.tolist())



if __name__ == "__main__":
    bq_client = BigQueryClient()
    embedding_list = (bq_client.get_embeddings("5c50e567999c4f9d8af20658c517639a"))
    print(embedding_list)
