### idea: use rdiff / bsdiff to load a file into memory, diff it, then store the diff inside the tar with compression

import filecmp
import time
import os
import io
import tarfile
import bsdiff4
import argparse
import tqdm
import detools.create


def get_file_diff_match_blocks(old_file,new_file) -> bytes:
    old = open(old_file,'rb')
    new = open(new_file,'rb')
    patch = io.BytesIO()
    detools.create.create_patch(old,new,patch,compression='none',algorithm='match-blocks',patch_type='hdiffpatch')
    return patch.getbuffer().tobytes()

def get_file_diff_bsdiff4(old_file,new_file) -> bytes:
    old = open(old_file, 'rb').read()
    new = open(new_file, 'rb').read()
    return bsdiff4.diff(old, new)


def get_folder_diff(dirs, diff_files: list, deleted: list, added: list) -> None:
    for file_root in dirs.diff_files:
        diff_files.append(os.path.join(dirs.right, file_root))
    for file_left in dirs.left_only: ## only in old version == deleted
        deleted.append(os.path.join(dirs.left, file_left))
    for file_right in dirs.right_only: ## only in new version == added
        abs_path = os.path.join(dirs.right, file_right)
        added.append(abs_path)
        if os.path.isdir(abs_path): ## if the whole folder is new, we need to recurse down.
            for root, _, files in os.walk(abs_path,topdown=True):
                for file in files:
                    added.append(os.path.join(root,file))
    for sub_dirs in dirs.subdirs.values():
        get_folder_diff(sub_dirs, diff_files, deleted, added)


def get_header(old_dir: str, new_dir: str) -> tuple:
    dirs_comp = filecmp.dircmp(old_dir,new_dir)
    changed_files = [] # note that these are all absolute paths; when stored they need to be relative.
    deleted_files = []
    added_files = []
    get_folder_diff(dirs_comp, changed_files, deleted_files, added_files)
    return changed_files,added_files,deleted_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches / config file.')
    parser.add_argument('--old', required=True, help="Path to the old directory.")
    parser.add_argument('--new', required=True, help="Path to the new directory")
    parser.add_argument('--dest', required=True, help="Path to the location of the patches.")
    parser.add_argument('--algo',choices=['bsdiff','none','match-blocks'],default='match-blocks', help="Choice of patching algorithm.")
    args = parser.parse_args()
    old_path = os.path.abspath(args.old)
    new_path = os.path.abspath(args.new)
    start_time = time.process_time()
    print("Diffing folders (this may take a while...)")
    changed,added,deleted = get_header(old_path,new_path) # note: paths are absolute.
    tar = tarfile.open(args.dest,'w|gz',compresslevel=3)
    print("Adding changed files...")
    for changed_file_path in tqdm.tqdm(changed):
        rel_path = os.path.relpath(changed_file_path, start=new_path)
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(changed_file_path).st_mode
        if os.path.getsize(changed_file_path) > 1 and args.algo != "none": # 100K
            if args.algo == "bsdiff":
                info.pax_headers = {"T":"B"}
                diff = get_file_diff_bsdiff4(os.path.join(old_path, rel_path),changed_file_path) # os.path.join converts the relpath to the old path.
            elif args.algo == "match-blocks":
                info.pax_headers = {"T":"M"}
                diff = get_file_diff_match_blocks(os.path.join(old_path, rel_path),changed_file_path) # os.path.join converts the relpath to the old
                # path.
            info.size = len(diff)
            tar.addfile(info, io.BytesIO(initial_bytes=diff))
        else:
            info.pax_headers = {"T": "C"}
            info.size = os.path.getsize(changed_file_path)
            tar.addfile(info, open(changed_file_path, 'rb'))
    print("Adding new files...")
    for added_file_path in tqdm.tqdm(added):
        rel_path = os.path.relpath(added_file_path, start=new_path) # we need the relative path to store the file name inside the tar properly.
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(added_file_path).st_mode
        info.pax_headers = {"T":"A"}
        if os.path.isdir(added_file_path): # added may include directories, so handling it here.
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        else:
            info.size = os.path.getsize(added_file_path)
            tar.addfile(info, open(added_file_path, 'rb'))
    print("Adding ...deleted files...")
    for deleted_file_path in tqdm.tqdm(deleted):
        rel_path = os.path.relpath(deleted_file_path, start=old_path)
        info = tarfile.TarInfo(rel_path)
        info.pax_headers = {"T":"D"}
        tar.addfile(info)

    tar.close()
    end_time = time.process_time()
    print(f"Patch generated!\nTime:{(end_time-start_time):.2f}s\nSize:{os.path.getsize(args.dest)>>20} MB")
    print(f"{len(changed)} modified files\n{len(added)} added files\n{len(deleted)} deleted files")