import grpc
from . import nsfw_detector_pb2
from . import nsfw_detector_pb2_grpc
import os
import jwt
import base64

token_fpath = "/Users/jaydhanwant/Documents/SS/nsfw_jwt_token.txt"
with open(token_fpath, 'r') as f:
    _JWT_TOKEN = f.read()

# server_url = 'prod-yral-nsfw-classification.fly.dev:443'
server_url = 'stage-yral-nsfw-classification.fly.dev:443'
# server_url = 'yral-nsfw-classification.fly.dev:443'
# Load the private key from a path specified in an environment variable

def run():
    # NOTE: Replace with the actual server address if different
    channel = grpc.secure_channel(server_url, grpc.ssl_channel_credentials())
    stub = nsfw_detector_pb2_grpc.NSFWDetectorStub(channel)

    # Test video ID (replace with an actual video ID for testing)
    video_id = "00034f1c9c9148388bf6873776222535" 

    image_url = "https://img-cdn.pixlr.com/image-generator/history/65bb506dcb310754719cf81f/ede935de-1138-4f66-8ed7-44bd16efc709/medium.webp"
    # Test image path for byte64
    image_path = "/Users/jaydhanwant/Downloads/WhatsApp Image 2024-08-29 at 13.18.09.jpeg"

    try:
        print("Sending video ID request to server")
        metadata = [('authorization', f'Bearer {_JWT_TOKEN}')]
        # video_response = stub.DetectNSFWVideoId(nsfw_detector_pb2.NSFWDetectorRequestVideoId(video_id=video_id), metadata=metadata)
        # print(video_response)

        # print("Sending image URL request to server")
        # url_response = stub.DetectNSFWURL(nsfw_detector_pb2.NSFWDetectorRequestURL(url=image_url), metadata=metadata)
        # print(url_response)

        # print("Sending image to byte64 request to server")
        # with open(image_path, "rb") as image_file:
        #     image_byte64 = base64.b64encode(image_file.read()).decode('utf-8')
        # byte64_response = stub.DetectNSFWImg(nsfw_detector_pb2.NSFWDetectorRequestImg(image=image_byte64), metadata=metadata)
        # print(byte64_response)

        print("Sending embedding request to server")
        video_id = "5c50e567999c4f9d8af20658c517639a"
        embedding_response = stub.DetectNSFWVideoId(nsfw_detector_pb2.EmbeddingNSFWDetectorRequest(video_id=video_id), metadata=metadata)
        # embedding_response = stub.DetectNSFWEmbedding(nsfw_detector_pb2.EmbeddingNSFWDetectorRequest(video_id=video_id), metadata=metadata)
        print(embedding_response)
    except grpc.RpcError as e:
        print(f"RPC failed: {e}")

if __name__ == '__main__':
    run()
