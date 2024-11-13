import os
import argparse
import tarfile
import shutil

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches / config file.')
    parser.add_argument('--target', required=True, help="Path to the old directory.")
    parser.add_argument('--patch', required=True, help="Path to the location of the patches.")
    args = parser.parse_args()
    target_path = os.path.abspath(args.target)
    patch_path = os.path.abspath(args.patch)
    tar = tarfile.open(patch_path)
    for tarinfo in tar:
        file_type = tarinfo.pax_headers["T"]
        abs_path = os.path.join(target_path,tarinfo.name)
        if file_type == "C":
            tar.extract(tarinfo,target_path)
        elif file_type == "A":
            tar.extract(tarinfo,target_path)
        if file_type == "D":
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path) # must be very careful here.
            else:
                os.remove(abs_path)
