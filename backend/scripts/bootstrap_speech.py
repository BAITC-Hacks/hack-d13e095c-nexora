"""Downloads only public model weights, without receiving meeting data."""
import os
from huggingface_hub import snapshot_download
snapshot_download(repo_id=os.getenv("SPEECH_REPO", "Systran/faster-whisper-large-v3"),
                  revision=os.getenv("SPEECH_REVISION", "main"), local_dir="/models/whisper")
