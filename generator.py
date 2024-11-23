### SPECIFICATION:
### Stores all differing files between two versions of a folder in a tar (PAX format).
### Optionally stores patches instead of the whole file.
### Stores the file type (full file, patch, delete) in the PAX header per file.

from filecmp import dircmp
import filecmp
import time
import os
import io
import tarfile
import argparse
import tqdm
import detools.create
import xxhash
import msgpack
import zlib

def get_file_diff_match_blocks(old_file: str, new_file: str) -> bytes:
    old = open(old_file, "rb")
    new = open(new_file, "rb")
    patch = io.BytesIO()
    detools.create.create_patch(
        old,
        new,
        patch,
        compression="none",
        algorithm="match-blocks",
        patch_type="hdiffpatch",
    )
    return patch.getbuffer().tobytes()


def hash_file(filepath):
    hasher = xxhash.xxh64()
    with open(filepath, "rb") as f:
        while chunk := f.read(2**20):
            hasher.update(chunk)
    return hasher.digest()


def list_files(folder):
    files = {}
    for root, _, filenames in os.walk(folder):
        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(root, filename), folder)
            files[rel_path] = os.path.join(root, filename)
    return files


def get_folder_diff(folder1, folder2):
    files_old = list_files(folder1)
    files_new = list_files(folder2)
    changed = []
    paths_old = set(files_old.keys())
    paths_new = set(files_new.keys())
    added = [(x,files_new[x]) for x in paths_new - paths_old]
    deleted = paths_old - paths_new

    for common_file in files_old.keys() & files_new.keys():
        hash1 = hash_file(files_old[common_file])
        hash2 = hash_file(files_new[common_file])
        if hash1 != hash2:
            changed.append((common_file,files_new[common_file]))
    return changed, added, deleted


def gen_patch(changed: list, added: list, deleted: list, path: str) -> None:
    tar = tarfile.open(path, "w|gz", compresslevel=3)
    print("Adding changed files...")
    for changed_file_paths in tqdm.tqdm(changed):
        rel_path = changed_file_paths[0]
        abs_path = changed_file_paths[1]
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(abs_path).st_mode
        # Only calc per-file diffs >1K. It's an expensive operation.
        if os.path.getsize(abs_path) > 1000 and args.algo != "none":
            info.pax_headers = {"T": "M"}
            diff = get_file_diff_match_blocks(os.path.join(old_path, rel_path), abs_path)
            info.size = len(diff)
            tar.addfile(info, io.BytesIO(initial_bytes=diff))
        else:
            info.pax_headers = {"T": "A"}
            info.size = os.path.getsize(abs_path)
            tar.addfile(info, open(abs_path, "rb"))

    print("Adding new files...")
    for added_file_paths in tqdm.tqdm(added):
        # we need the relative path to store the file name inside the tar properly.
        rel_path = added_file_paths[0]
        abs_path = added_file_paths[1]
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(abs_path).st_mode
        info.pax_headers = {"T": "A"}
        # added may include directories - we need to handle this case.
        if os.path.isdir(abs_path):
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        else:
            info.size = os.path.getsize(abs_path)
            tar.addfile(info, open(abs_path, "rb"))

    print("Adding ...deleted files...")
    for deleted_file_path in tqdm.tqdm(deleted):
        info = tarfile.TarInfo(deleted_file_path)
        info.pax_headers = {"T": "D"}
        tar.addfile(info)
    tar.close()

def gen_sig(path,dest):
    hashes = {}
    files = list_files(path)
    for relative,absolute in files.items():
        hashes[relative] = hash_file(absolute)
    with open(dest,"wb") as f:
        f.write(zlib.compress(msgpack.packb(hashes),level=9))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches.')
    subparser = parser.add_subparsers(dest="mode", required=True, help="Operation mode (diff or sign).")
    diff_parser = subparser.add_parser("diff", help="Calculate a diff.")
    diff_parser.add_argument("old", help="Path to the old directory.")
    diff_parser.add_argument("new", help="Path to the new directory. ")
    diff_parser.add_argument("dest", help="Path to the location of the patches.")
    diff_parser.add_argument(
        "--algo",
        choices=["bsdiff", "none", "match-blocks"],
        default="match-blocks",
        help="Choice of patching algorithm.",
    )
    sign_parser = subparser.add_parser('sign', help="Sign a folder.")
    sign_parser.add_argument('folder', help="Path to the folder to sign.")
    sign_parser.add_argument('dest', help="Destination path for the signature file.")
    args = parser.parse_args()
    if args.mode == "diff":
        old_path = os.path.abspath(args.old)
        new_path = os.path.abspath(args.new)
        dest_path = os.path.abspath(args.dest)
        start_time = time.process_time()
        print("Diffing folders (this may take a while...)")
        changed, added, deleted = get_folder_diff(old_path, new_path)
        # all paths in the 3 returned lists are absolute.
        gen_patch(changed, added, deleted, dest_path)
        end_time = time.process_time()
        print(f"Patch generated!\nTime:{(end_time-start_time):.2f}s\nSize:{os.path.getsize(dest_path)>>20} MB")
        print(f"{len(changed)} modified files\n{len(added)} added files\n{len(deleted)} deleted files")
    else:
        folder_path = os.path.abspath(args.folder)
        dest_path = os.path.abspath(args.dest)
        start_time = time.process_time()
        gen_sig(folder_path,dest_path)
        end_time = time.process_time()
        print(f"Signature generated!\nTime:{(end_time - start_time):.2f}s\nSize:{os.path.getsize(dest_path) >> 20} MB")

