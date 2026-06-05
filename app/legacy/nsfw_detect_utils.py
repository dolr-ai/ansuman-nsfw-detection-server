import os
import json
from PIL import Image
from google.cloud import vision
from google.oauth2 import service_account
import logging

_LOGGER = logging.getLogger(__name__)

class NSFWDetect:
    def __init__(self, pipe3c, pipe5c):
        self.pipe3c = pipe3c
        self.pipe5c = pipe5c
        service_cred = os.environ.get("SERVICE_CRED")
        service_acc_creds = json.loads(service_cred, strict=False)
        credentials = service_account.Credentials.from_service_account_info(service_acc_creds)
        self.gclient = vision.ImageAnnotatorClient(credentials=credentials)

    def explicit_detect(self, imgs):
        marks = {'QUESTIONABLE provocative': 'provocative',
        'QUESTIONABLE porn': 'explicit',
        'QUESTIONABLE neutral': 'neutral',
        'QUESTIONABLE hentai': 'explicit',
        'QUESTIONABLE drawings': 'provocative',
        'UNSAFE provocative': 'nudity',
        'UNSAFE porn': 'explicit',
        'UNSAFE neutral': 'provocative',
        'UNSAFE hentai': 'explicit',
        'UNSAFE drawings': 'nudity',
        'SAFE provocative': 'provocative',
        'SAFE porn': 'explicit',
        'SAFE neutral': 'neutral',
        'SAFE hentai': 'explicit',
        'SAFE drawings': 'neutral'}
        
        from concurrent.futures import ThreadPoolExecutor

        res3cs = self.pipe3c(imgs)
        res5cs = self.pipe5c(imgs)

        """
        This is how the res3cs and res5cs look like 
        res3cs: [[{'label': 'QUESTIONABLE', 'score': 0.9604137539863586}, {'label': 'UNSAFE', 'score': 0.6502232551574707}, {'label': 'SAFE', 'score': 0.03905165567994118}], [{'label': 'SAFE', 'score': 0.9722312092781067}, {'label': 'UNSAFE', 'score': 0.31041547656059265}, {'label': 'QUESTIONABLE', 'score': 0.185553178191185}], [{'label': 'UNSAFE', 'score': 0.7398239970207214}, {'label': 'SAFE', 'score': 0.7222445607185364}, {'label': 'QUESTIONABLE', 'score': 0.2648926079273224}]]
        res5cs: [[{'label': 'provocative', 'score': 0.9864626526832581}, {'label': 'neutral', 'score': 0.7108702063560486}, {'label': 'drawings', 'score': 0.22955366969108582}, {'label': 'hentai', 'score': 0.14005741477012634}, {'label': 'porn', 'score': 0.1315544694662094}], [{'label': 'neutral', 'score': 0.99712735414505}, {'label': 'hentai', 'score': 0.25641435384750366}, {'label': 'provocative', 'score': 0.23076564073562622}, {'label': 'drawings', 'score': 0.2289031445980072}, {'label': 'porn', 'score': 0.10852369666099548}], [{'label': 'neutral', 'score': 0.9969491362571716}, {'label': 'drawings', 'score': 0.37695300579071045}, {'label': 'hentai', 'score': 0.15976859629154205}, {'label': 'provocative', 'score': 0.14641618728637695}, {'label': 'porn', 'score': 0.14610938727855682}]]
        
        
        Output corresponding to each image is a list of [{label, score}...] 
        and the res is a list of such lists
        """

        mark3cs = [max(res3c, key=lambda x: x['score']) for res3c in res3cs] # maintaining the max score with the label
        mark5cs = [max(res5c, key=lambda x: x['score']) for res5c in res5cs] # maintaining the max score with the label

        marks = [(marks[mark3c['label'] + ' ' + mark5c['label']], mark3c['score'], mark5c['score']) for mark3c, mark5c in zip(mark3cs, mark5cs)] # zipped label 
        return marks

    def gore_detect(self, pil_image):
        try:
            """Detects NSFW content in a PIL image and returns the safe search annotation."""

            # Convert PIL image to bytes
            import io
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='PNG')
            content = img_byte_arr.getvalue()

            image = vision.Image(content=content)

            # Perform safe search detection
            response = self.gclient.safe_search_detection(image=image)
            safe = response.safe_search_annotation

            # Define likelihood names
            likelihood_name = (
                "UNKNOWN",
                "VERY_UNLIKELY",
                "UNLIKELY",
                "POSSIBLE",
                "LIKELY",
                "VERY_LIKELY",
            )

            # Create a dictionary with the results
            result = {
                "adult": likelihood_name[safe.adult],
                "medical": likelihood_name[safe.medical],
                "spoofed": likelihood_name[safe.spoof],
                "violence": likelihood_name[safe.violence],
                "racy": likelihood_name[safe.racy]
            }

            if response.error.message:
                raise Exception(
                    "{}\nFor more info on error messages, check: "
                    "https://cloud.google.com/apis/design/errors".format(response.error.message)
                )

            return result['violence']
        except Exception as e:
            _LOGGER.error(f"Error detecting NSFW content: {e}")
            return "UNKNOWN"

if __name__ == "__main__":
    import torch
    import pickle
    def load_model_artifacts(artifact_path):
        print("Loading model artifacts")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        with open(artifact_path + '/pipe3c.pkl', "rb") as f:
            pipe3c = pickle.load(f)
        with open(artifact_path + '/pipe5c.pkl', "rb") as f:
            pipe5c = pickle.load(f)

        pipe3c.device = device
        pipe5c.device = device
        
        return pipe3c, pipe5c
    pipe3c, pipe5c = load_model_artifacts("model_artifacts")
    detector = NSFWDetect(pipe3c, pipe5c)
    img = Image.open("/Users/jaydhanwant/Downloads/WhatsApp Image 2024-08-29 at 13.18.09.jpeg")
    img2 = Image.open("/Users/jaydhanwant/Downloads/3.jpg")
    img3 = Image.open("/Users/jaydhanwant/Documents/questionable.png")
    imgs = [img, img2, img3]
    result = detector.explicit_detect(imgs) 
    print(result)
    