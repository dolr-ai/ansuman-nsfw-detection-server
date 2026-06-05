import pickle
from concurrent import futures
import contextlib
import datetime
import logging
import multiprocessing
import socket
import sys
import time
import os
from typing import Any
import jwt
from . import consts
import grpc
from grpc_reflection.v1alpha import reflection
from . import nsfw_detector_pb2
from . import nsfw_detector_pb2_grpc
from .utils.gcs_utils import get_images_from_gcs
from .nsfw_detect_utils import NSFWDetect
from .save_model_artifacts import download_artifacts # hardocded the gcr paths here TODO: Move that to a config
from .bigquery_client import BigQueryClient
import torch 
from PIL import Image
import io
import base64
import requests

_LOGGER = logging.getLogger(__name__)

_ONE_DAY = datetime.timedelta(days=1)
_PROCESS_COUNT = multiprocessing.cpu_count()
# _PROCESS_COUNT = 1 # TODO: change this back after testing
_THREAD_CONCURRENCY = 10 # heuristic
_BIND_ADDRESS = "[::]:50051"


_AUTH_HEADER_KEY = "authorization"

_PUBLIC_KEY = consts.NSFW_JWT_PUB_KEY
_PUBLIC_KEY = os.environ.get("PUBLIC_KEY_TO_VERIFY_INCOMING_CALLS_FROM_FRONTEND_LEPTOS_SSR_SERVICE")
_JWT_PAYLOAD =  {
    "sub": "yral-nsfw-detector-server",
    "company": "Yral",
}

# downloading model artifacts 
artifact_path = "model_artifacts"
artifact_files = ['pipe3c.pkl', 'pipe5c.pkl', 'nsfw_rf_classifier_40k.pkl']
missing_files = [file for file in artifact_files if not os.path.exists(os.path.join(artifact_path, file))]

if missing_files:
    download_artifacts()



def load_model_artifacts(artifact_path):
    print("Loading model artifacts")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with open(artifact_path + '/pipe3c.pkl', "rb") as f:
        pipe3c = pickle.load(f)
    with open(artifact_path + '/pipe5c.pkl', "rb") as f:
        pipe5c = pickle.load(f)
    with open(artifact_path + '/nsfw_rf_classifier_40k.pkl', "rb") as f:
        nsfw_model = pickle.load(f)

    pipe3c.device = device
    pipe5c.device = device
    
    return pipe3c, pipe5c, nsfw_model
    # return 1,1,nsfw_model

class SignatureValidationInterceptor(grpc.ServerInterceptor):
    def __init__(self):
        def abort(ignored_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid signature")

        self._abort_handler = grpc.unary_unary_rpc_method_handler(abort)

    def intercept_service(self, continuation, handler_call_details):
        metadata_dict = dict(handler_call_details.invocation_metadata)
        token = metadata_dict[_AUTH_HEADER_KEY].split()[1]
        payload = jwt.decode(
            token,
            _PUBLIC_KEY,
            algorithms=["EdDSA"],
        )

        if payload == _JWT_PAYLOAD:
            return continuation(handler_call_details)
        else:
            print(f"Received payload: {payload}")
            return self._abort_handler


class NSFWDetectorServicer(nsfw_detector_pb2_grpc.NSFWDetectorServicer):
    def __init__(self):
        self.pipe3c, self.pipe5c, self.nsfw_model = load_model_artifacts("model_artifacts")
        self.nsfw_detector = NSFWDetect(self.pipe3c, self.pipe5c)
        self.bq_client = BigQueryClient()
        _LOGGER.info("Loaded models: ")
        _LOGGER.info(self.pipe3c.model.config) 
        _LOGGER.info(self.pipe5c.model.config)
        _LOGGER.info('='*100)

    def DetectNSFWVideoId(self, request, context):
        _LOGGER.info("Request received")
        video_id = request.video_id
        nsfw_tag, gore_tag = self.process_frames(video_id)
        response = nsfw_detector_pb2.NSFWDetectorResponse(nsfw_ec=nsfw_tag, nsfw_gore=gore_tag, csam_detected=False)
        return response

    def DetectNSFWURL(self, request, context):
        _LOGGER.info("Request received")
        image_url = request.url
        nsfw_tag, gore_tag = self.process_image_url(image_url)
        response = nsfw_detector_pb2.NSFWDetectorResponse(nsfw_ec=nsfw_tag, nsfw_gore=gore_tag, csam_detected=False)
        return response

    def DetectNSFWImg(self, request, context):
        _LOGGER.info("Request received")
        image_byte64 = request.image
        nsfw_tag, gore_tag = self.process_image_byte64(image_byte64)
        response = nsfw_detector_pb2.NSFWDetectorResponse(nsfw_ec=nsfw_tag, nsfw_gore=gore_tag, csam_detected=False)
        return response
    
    def DetectNSFWEmbedding(self, request, context):
        _LOGGER.info("Request received")
        video_id = request.video_id
        embedding_list = self.bq_client.get_embeddings(video_id)
        if len(embedding_list) > 0:
            probabilities = self.nsfw_model.predict_proba(embedding_list)[:,-1]
            probability = float(probabilities.max())
            response = nsfw_detector_pb2.EmbeddingNSFWDetectorResponse(probability=probability)
        else:
            response = nsfw_detector_pb2.EmbeddingNSFWDetectorResponse(probability=0.0)
        return response

    def process_frames(self, video_id):
        frames = get_images_from_gcs("yral-video-frames", video_id)
        nsfw_tags = self.nsfw_detector.explicit_detect([frame['image'] for frame in frames]) 
        gore_tags = []
        for frame in frames:
            gore_tags.append(self.nsfw_detector.gore_detect(frame['image']))
        tag_priority = "explicit nudity provocative neutral".split()
        gore_priority = ["UNKNOWN", "VERY_UNLIKELY", "UNLIKELY", "POSSIBLE", "LIKELY", "VERY_LIKELY"][::-1]
        # Sort nsfw_tags based on the priority defined in tag_priority
        nsfw_tags = [i[0] for i in nsfw_tags if i[1] > 0.82 and i[2]>0.9]
        nsfw_tags.sort(key=lambda tag: tag_priority.index(tag))

        gore_tags.sort(key=lambda tag: gore_priority.index(tag))

        nsfw_tag = None
        gore_tag = None
        if len(nsfw_tags) > 0:
            nsfw_tag = nsfw_tags[0]
        if len(gore_tags) > 0:
            gore_tag = gore_tags[0]
            
        return [nsfw_tag, gore_tag]

    def process_image_byte64(self, image_byte64):
        image = Image.open(io.BytesIO(base64.b64decode(image_byte64)))
        nsfw_res = self.nsfw_detector.explicit_detect([image])[0]
        mark3c_score = nsfw_res[1]
        mark5c_score = nsfw_res[2]
        if mark3c_score > 0.82 and mark5c_score > 0.9:
            nsfw_tag = nsfw_res[0]
        else:
            nsfw_tag = None 

        gore_tag = self.nsfw_detector.gore_detect(image)
        return [nsfw_tag, gore_tag]

    def process_image_url(self, image_url):
        image = Image.open(requests.get(image_url, stream=True).raw)
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        image_byte64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        nsfw_res = self.process_image_byte64(image_byte64)
        return nsfw_res

        

def _wait_forever(server):
    try:
        while True:
            time.sleep(_ONE_DAY.total_seconds())
    except KeyboardInterrupt:
        server.stop(None)

def _run_server():
    _LOGGER.info("Starting new server.")
    options = (("grpc.so_reuseport", 1),)

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=_THREAD_CONCURRENCY),
        interceptors=(SignatureValidationInterceptor(),), # TODO: decomment this when on prod
        options=options,
    )
    nsfw_detector_pb2_grpc.add_NSFWDetectorServicer_to_server(
        NSFWDetectorServicer(), server
    )
    SERVICE_NAMES = (
        nsfw_detector_pb2.DESCRIPTOR.services_by_name['NSFWDetector'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    server.add_insecure_port(_BIND_ADDRESS)
    server.start()
    _LOGGER.info(f"Server started on {_BIND_ADDRESS}")
    _wait_forever(server)

def main():
    multiprocessing.set_start_method("spawn", force=True)
    _LOGGER.info(f"Binding to '{_BIND_ADDRESS}' with Process Count: {_PROCESS_COUNT}")
    sys.stdout.flush()
    workers = []
    for _ in range(_PROCESS_COUNT):
        worker = multiprocessing.Process(target=_run_server)
        worker.start()
        workers.append(worker)
    for worker in workers:
        worker.join()

if __name__ == "__main__":
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[PID %(process)d] %(message)s")
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    main()
