from typing import IO
import os
import argparse
import tarfile
import shutil
import io
import tqdm
import detools


def patch_file_match_blocks(old_file: str, patch_data: IO[bytes]) -> None:
    old = open(old_file, "rb")
    new = io.BytesIO()
    detools.apply_patch(old, patch_data, new)
    old = open(old_file, "wb")
    old.write(new.getbuffer().tobytes())
    old.close()


def main(target_path: str,patch_path: str) -> None:
    tar = tarfile.open(patch_path)
    for tar_entry in tqdm.tqdm(tar):
        # paths from the tar might be malicious. Filter them first.
        unsafe_abs_path = os.path.join(target_path, tar_entry.name)
        tar_entry = tarfile.data_filter(tar_entry, unsafe_abs_path)
        abs_path = os.path.join(target_path, tar_entry.name)
        file_type = tar_entry.pax_headers["T"]
        try:
            match file_type:
                case "M":
                    patch = tar.extractfile(tar_entry.name)
                    if patch is not None:
                        patch_file_match_blocks(abs_path, patch)
                    else:
                        raise IOError(f"Patch has no data (Type M, {tar_entry.name})")
                case "A":
                    tar.extract(tar_entry, target_path, filter="data")
                case "D":
                    if os.path.isdir(abs_path):
                        shutil.rmtree(abs_path)
                    else:
                        os.remove(abs_path)
                case _:
                    print(f"Unknown file header {file_type} detected. Ignoring.")
        except (IOError, tarfile.TarError) as e:
            print(f"Error when extracting patch: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply a 'Milshaw' patch.")
    parser.add_argument("target", help="Path to the old directory.")
    parser.add_argument("patch", help="Path to the location of the patches.")
    args = parser.parse_args()
    target = os.path.abspath(args.target)
    patch = os.path.abspath(args.patch)
    main(target,patch)

