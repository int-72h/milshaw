import os
import argparse
import tarfile
import shutil
import io
import tqdm
import bsdiff4
import detools


def patch_file_bsdiff(old_file: str, patch: bytes) -> None:
    old = open(old_file, 'rb').read()
    new = bsdiff4.patch(old, patch)
    old = open(old_file, 'wb')
    old.write(new)
    old.close()


def patch_file_match_blocks(old_file, patch) -> None:
    old = open(old_file, 'rb')
    new = io.BytesIO()
    detools.apply_patch(old,patch,new)
    old = open(old_file, 'wb')
    old.write(new.getbuffer().tobytes())
    old.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches / config file.')
    parser.add_argument('--target', required=True, help="Path to the old directory.")
    parser.add_argument('--patch', required=True, help="Path to the location of the patches.")
    args = parser.parse_args()
    target_path = os.path.abspath(args.target)
    patch_path = os.path.abspath(args.patch)
    tar = tarfile.open(patch_path)
    for tarinfo in tqdm.tqdm(tar):
        file_type = tarinfo.pax_headers["T"]
        abs_path = os.path.join(target_path, tarinfo.name)
        match file_type:
            case "M":
                patch = tar.extractfile(tarinfo.name)
                patch_file_match_blocks(abs_path, patch)
            case "B":
                patch = tar.extractfile(tarinfo.name).read()
                patch_file_bsdiff(abs_path, patch)
            case "A" | "C":
                tar.extract(tarinfo, target_path)
            case "D":
                if os.path.isdir(abs_path):
                    shutil.rmtree(abs_path)  # must be very careful here.
                else:
                    os.remove(abs_path)
