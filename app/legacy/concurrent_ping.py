import grpc
from . import nsfw_detector_pb2
from . import nsfw_detector_pb2_grpc
import time
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.DEBUG)

def send_request(stub, video_id):
    try:
        response = stub.DetectNSFW(nsfw_detector_pb2.NSFWDetectorRequest(video_id=video_id))
        print(response)
    except grpc.RpcError as e:
        logging.error(f"RPC failed: {e}")

def run():
    # NOTE: Replace with the actual server address if different
    channel = grpc.insecure_channel('localhost:50051')
    stub = nsfw_detector_pb2_grpc.NSFWDetectorStub(channel)

    # Test video ID (replace with an actual video ID for testing)
    video_id = "00034f1c9c9148388bf6873776222535" 

    print("Sending requests to server")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(send_request, stub, video_id) for _ in range(100)]
        for future in futures:
            future.result()

    end_time = time.time()
    print(f"Time taken for 10 requests: {end_time - start_time} seconds")

if __name__ == '__main__':
    run()
