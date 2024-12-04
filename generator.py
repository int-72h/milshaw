### SPECIFICATION:
### Stores all differing files between two versions of a folder in a tar (PAX format).
### Optionally stores patches instead of the whole file.
### Stores the file type (full file, patch, delete) in the PAX header per file.

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
from concurrent.futures import ProcessPoolExecutor
import zstandard

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
        patch_type="sequential",
        match_block_size=10*(2**20)
    )
    return patch.getbuffer().tobytes()


def hash_file(filepath):
    hasher = xxhash.xxh64()
    with open(filepath, "rb") as f:
        while chunk := f.read((2**20)):
            hasher.update(chunk)
    return hasher.digest()



def list_files(folder):
    files = {}
    for root, _, filenames in os.walk(folder):
        for filename in filenames:
            rel_path = os.path.relpath(os.path.join(root, filename), folder)
            files[rel_path] = os.path.join(root, filename)
    return files

def p_do_diff(f):
    return f[0],f[1],get_file_diff_match_blocks(f[2], f[1])

def p_do_hash(f):
    file1 = f[0]
    file2 = f[1]
    common_file = f[2]
    if os.path.getsize(file1) != os.path.getsize(file2):
        return (common_file, file2)
    else:
        hash1 = hash_file(file1)
        hash2 = hash_file(file2)
        if hash1 != hash2:
            return(common_file, file2)

def get_folder_diff(folder1, folder2):
    files_old = list_files(folder1)
    files_new = list_files(folder2)
    paths_old = set(files_old.keys())
    paths_new = set(files_new.keys())
    added = [(x,files_new[x]) for x in paths_new - paths_old]
    deleted = paths_old - paths_new
    start_time = time.perf_counter()
    changed = []
    h_map = [(files_old[x],files_new[x],x) for x in files_old.keys() & files_new.keys()]
    with ProcessPoolExecutor(max_workers=16) as executor:
        for r in tqdm.tqdm(executor.map(p_do_hash, h_map)):
            if r is not None:
                changed.append(r)
    end_time = time.perf_counter()
    print(f"hashing took {end_time - start_time:2f}s")
    return changed, added, deleted


def gen_patch(changed: list, added: list, deleted: list, path: str) -> None:
    to_file = open(path,"wb")
    to_zstd = zstandard.ZstdCompressor(level=10,threads=13)
    stream = to_zstd.stream_writer(to_file)
    tar = tarfile.open(mode="w|",fileobj=stream)
    #tar = tarfile.open(path,mode="w|")
    print("Adding changed files...")
    if args.algo == "none":
        added.extend(changed)
    else:
        to_add = [x for x in changed if os.path.getsize(x[1]) < 1*(2**20)] # slow?
        added.extend(to_add)
        to_diff = [(x[0],x[1],os.path.join(old_path, x[0]))
                   for x in changed if os.path.getsize(x[1]) > 1* (2**20)]
        with ProcessPoolExecutor(max_workers=16) as executor:
            for r in tqdm.tqdm(executor.map(p_do_diff,to_diff)):
                rel_path = r[0]
                abs_path = r[1]
                info = tarfile.TarInfo(rel_path)
                info.mode = os.stat(abs_path).st_mode
                info.pax_headers = {"T": "M"}
                info.size = len(r[2])
                tar.addfile(info, io.BytesIO(initial_bytes=r[2]))

    print("Adding new files / changed files we're not diffing...")
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
    stream.close()
    to_file.close()

def gen_sig(path,dest):
    hashes = {}
    files = list_files(path)
    for relative,absolute in files.items():
        hashes[relative] = hash_file(absolute)
    with open(dest,"wb") as f:
        f.write(zlib.compress(msgpack.packb(hashes),level=9))

def load_sig(path):
    with open(path,"rb") as f:
        hashes_undecoded = msgpack.unpack(zlib.decompress(f.read()))
        hashes = {h[0].decode("utf-8"):h[1] for h in hashes_undecoded}
        return hashes


def verify(target_path,sig_path):
    hashes = load_sig(sig_path)
    target_files = list_files(target_path)
    sig_files = [x[0] for x in hashes]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate a "sten" patch.')
    subparser = parser.add_subparsers(dest="mode", required=True, help="Operation mode (diff or sign).")
    diff_parser = subparser.add_parser("diff", help="Calculate a diff.")
    diff_parser.add_argument("old", help="Path to the old directory.")
    diff_parser.add_argument("new", help="Path to the new directory. ")
    diff_parser.add_argument("dest", help="Path to the location of the patches.")
    diff_parser.add_argument(
        "--algo",
        choices=["none", "match-blocks"],
        default="match-blocks",
        help="Choice of patching algorithm.",
    )
    sign_parser = subparser.add_parser('sign', help="Sign a folder.")
    sign_parser.add_argument('folder', help="Path to the folder to sign.")
    sign_parser.add_argument('dest', help="Destination path for the signature file.")
    verif_parser = subparser.add_parser('verify',help="Verify and heal a folder.")

    args = parser.parse_args()
    if args.mode == "diff":
        old_path = os.path.abspath(args.old)
        new_path = os.path.abspath(args.new)
        dest_path = os.path.abspath(args.dest)
        start_time = time.perf_counter()
        print("Diffing folders (this may take a while...)")
        changed, added, deleted = get_folder_diff(old_path, new_path)
        # all paths in the 3 returned lists are absolute.
        gen_patch(changed, added, deleted, dest_path)
        end_time = time.perf_counter()
        print(f"Patch generated!\nTime:{(end_time-start_time):.2f}s\nSize:{os.path.getsize(dest_path)>>20} MB")
        print(f"{len(changed)} modified files\n{len(added)} added files\n{len(deleted)} deleted files")
    else:
        folder_path = os.path.abspath(args.folder)
        dest_path = os.path.abspath(args.dest)
        start_time = time.perf_counter()
        gen_sig(folder_path,dest_path)
        end_time = time.perf_counter()
        print(f"Signature generated!\nTime:{(end_time - start_time):.2f}s\nSize:{os.path.getsize(dest_path) >> 20} MB")


