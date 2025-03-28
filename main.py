import tarfile
import json
import os
import shutil
import argparse
import tempfile

from tarfile import TarInfo, ExFileObject
from utils.tar_utils import extract_tar, extract_layers_info
from utils.log import logger



def compare_images(base_image, new_image, output_diff):
    """Make a diff between two images and save it as a TAR file."""

    # 1. extract layers info
    base_layers: dict = extract_layers_info(base_image)

    if not base_layers:
        logger.error('Failed to extract base image layers info')
        return False

    # 2. create diff.tar
    mode_1_create_diff(new_image, base_layers, output_diff)

    return True


def mode_1_create_diff(update_src, base_layers, output_diff_tar):
    with tarfile.open(update_src) as tar:
        all_files: list[TarInfo] = tar.getmembers()

        files_to_add: list = []
        filenames_to_add: set = set()
        kept_layers: list = []
        total_size: float = 0

        for file_tar in all_files:
            if file_tar.isdir() and ( len(file_tar.name.split("/")) < 2):
                try:
                    if file_tar.name not in base_layers["Layers"]:
                        filenames_to_add.add(file_tar.name)
                    else:
                        kept_layers.append(file_tar.name)
                except Exception as e:
                    logger.warning(f"Could not process {file_tar.name}: {e}")

            subfiles: list[str] = file_tar.name.split('/')
            root_dir: str = subfiles[0]
            if root_dir in filenames_to_add or (len(subfiles) == 1 and not file_tar.isdir()):
                files_to_add.append(file_tar)
                total_size += file_tar.size / 1e6

        if os.path.exists(output_diff_tar):
            os.remove(output_diff_tar)

        with tarfile.open(name=output_diff_tar, mode='w') as tar_new:
            for tarinfo in files_to_add:
                try:
                    f: ExFileObject | None = tar.extractfile(tarinfo.name)
                    tar_new.addfile(tarinfo, f)
                except Exception as e:
                    logger.warning(f"Could not add {tarinfo.name} to diff: {e}")

        with open(output_diff_tar + '.json', 'w') as f:
            json.dump(kept_layers, f)

        logger.info(f'total {total_size:.2f} MB to transfer')
        logger.info(f'kept old layers: {len(kept_layers)}')
        logger.info(f'new layers: {len(filenames_to_add)}')

        summary = [
            "=== compare between two images ===",
            f"- reuse layer: {len(kept_layers)}개",
            f"- new layer: {len(filenames_to_add)}개",
            f"- 전송 필요 용량: {total_size:.2f} MB",
            f"- diff file: {output_diff_tar}",
            "======================="
        ]

        for line in summary:
            logger.info(line)


def merge_base_diff_images(base_tar, diff_tar, output_tar):
    logger.info(f'Starting image merge: {base_tar} + {diff_tar} -> {output_tar}')

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            base_dir: str = os.path.join(tmpdir, "base")
            diff_dir: str = os.path.join(tmpdir, "diff")
            merged_dir: str = os.path.join(tmpdir, "merged")

            for dir in [base_dir, diff_dir, merged_dir]:
                os.makedirs(dir)

            logger.info(f'Extracting base image: {base_tar}')
            extract_tar(base_tar, base_dir)

            logger.info(f'Extracting diff image: {diff_tar}')
            extract_tar(diff_tar, diff_dir)

            logger.info(f'Merging files')
            shutil.copytree(base_dir, merged_dir, dirs_exist_ok=True)
            shutil.copytree(diff_dir, merged_dir, dirs_exist_ok=True)

            manifest_path = os.path.join(diff_dir, 'manifest.json')
            if not os.path.exists(manifest_path):
                raise FileNotFoundError(f"manifest.json not found in diff image")

            with open(manifest_path) as f:
                manifest = json.load(f)

            layers: list[str] = manifest[0]['Layers']
            logger.info(f'Found {len(layers)} layers in manifest')

            logger.info(f'Creating output tar: {output_tar}')
            with tarfile.open(output_tar, 'w') as outtar:
                for root, _, files in os.walk(merged_dir):
                    for file in files:
                        fullpath = os.path.join(root, file)
                        arcname = os.path.relpath(fullpath, merged_dir)
                        outtar.add(fullpath, arcname=arcname)

            logger.info(f'Successfully merged image created at: {output_tar}')

        except Exception as e:
            logger.error(f'Error during image merge: {str(e)}')
            raise

    logger.info(f'Temporary directories cleaned up')


def main():
    parser = argparse.ArgumentParser(description='Docker image diff tool')

    # sub parse setting
    subparsers = parser.add_subparsers(dest='command', help='select a mode')

    # compare docker image -> make a diff.tar (difference of two images)
    compare_parser = subparsers.add_parser('compare', help='make a diff between two images')
    compare_parser.add_argument('--base', required=True, help='base image TAR file')
    compare_parser.add_argument('--new', required=True, help='new image TAR file')
    compare_parser.add_argument('--output', required=True, help='output diff TAR file')

    # merge base image and diff.tar -> make a new image
    mode2_parser = subparsers.add_parser('merge', help='merge base image and diff')
    mode2_parser.add_argument('--base', required=True, help='base image TAR file')
    mode2_parser.add_argument('--diff-tar', required=True, help='diff tar')
    mode2_parser.add_argument('--output', required=True, help='output new image TAR file')

    args = parser.parse_args()

    if args.command == 'compare':
        compare_images(args.base, args.new, args.output)

    elif args.command == 'merge':
        merge_base_diff_images(args.base, args.diff_tar, args.output)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()