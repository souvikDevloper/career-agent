"""Voice: short-lived presigned Transcribe streaming URLs and Polly speech synthesis."""

from __future__ import annotations

import base64
import re
import urllib.parse

from .config import settings as cfg

LANGS = {"en-IN", "en-US", "hi-IN"}
VOICES = {"en-IN": "Kajal", "en-US": "Joanna", "hi-IN": "Kajal"}


def presign_transcribe(language: str = "en-IN", sample_rate: int = 16000, expires: int = 60) -> dict:
    """Sign with credentials of a dedicated role that can ONLY start streaming transcription.

    The browser never receives AWS keys: the URL carries a signature bound to this request, valid for
    connection establishment for `expires` seconds.
    """
    import boto3
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    if language not in LANGS:
        language = "en-IN"
    s = cfg()
    creds = boto3.client("sts").assume_role(RoleArn=s.transcribe_role_arn, RoleSessionName="voice", DurationSeconds=900)["Credentials"]
    credentials = Credentials(creds["AccessKeyId"], creds["SecretAccessKey"], creds["SessionToken"])
    host = f"transcribestreaming.{s.region}.amazonaws.com:8443"
    query = urllib.parse.urlencode({"language-code": language, "media-encoding": "pcm", "sample-rate": str(sample_rate)})
    request = AWSRequest(method="GET", url=f"https://{host}/stream-transcription-websocket?{query}", headers={"Host": host})
    SigV4QueryAuth(credentials, "transcribe", s.region, expires=expires).add_auth(request)
    return {"url": request.url.replace("https://", "wss://", 1), "language": language, "sample_rate": sample_rate,
            "expires_in": expires}


def clean_for_speech(text: str) -> str:
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:1500]


def synthesize(text: str, language: str = "en-IN") -> dict:
    import boto3

    polly = boto3.client("polly", region_name=cfg().region)
    speech = clean_for_speech(text)
    res = polly.synthesize_speech(Text=speech, OutputFormat="mp3", VoiceId=VOICES.get(language, "Kajal"), Engine="neural",
                                  LanguageCode="en-IN" if language not in LANGS else language)
    audio = res["AudioStream"].read()
    return {"audio_base64": base64.b64encode(audio).decode(), "content_type": "audio/mpeg", "characters": len(speech),
            "caption": speech}
