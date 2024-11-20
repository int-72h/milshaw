import os
import argparse
import tarfile
import shutil
import io
import tqdm
import detools

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
        unsafe_abs_path = os.path.join(target_path, tarinfo.name)
        tarinfo = tarfile.data_filter(tarinfo,unsafe_abs_path)
        abs_path = os.path.join(target_path, tarinfo.name)
        file_type = tarinfo.pax_headers["T"]
        match file_type:
            case "M":
                patch = tar.extractfile(tarinfo.name)
                patch_file_match_blocks(abs_path, patch)
            case "A":
                tar.extract(tarinfo, target_path)
            case "D":
                if os.path.isdir(abs_path):
                    shutil.rmtree(abs_path)
                else:
                    os.remove(abs_path)
            case _:
                print(f"Unknown file header {file_type} detected. Ignoring.")
