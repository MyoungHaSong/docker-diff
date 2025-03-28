import tarfile
import tempfile
import os
import json

from utils.log import logger

def extract_tar(tar_path, extract_to) -> None:
    with tarfile.open(tar_path) as tar:
        tar.extractall(path=extract_to)

def extract_layers_info(image_tar) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_tar(image_tar, tmpdir)
        manifest_path: str = os.path.join(tmpdir, 'manifest.json')

        if not os.path.exists(manifest_path):
            logger.error(f'manifest.json not found in {image_tar}')
            return dict()

        with open(manifest_path, 'r') as f:
            manifest: dict = json.load(f)

        layers_info: dict = {'Layers': [layer.split("/")[0] for layer in manifest[0]['Layers']]}
        return layers_info
