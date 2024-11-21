### SPECIFICATION:
### Stores all differing files between two versions of a folder in a tar (PAX format).
### Optionally stores patches instead of the whole file.
### Stores the file type (full file, patch, delete) in the PAX header per file.

import filecmp
import time
import os
import io
import tarfile
import argparse
import tqdm
import detools.create


def get_file_diff_match_blocks(old_file, new_file) -> bytes:
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


def get_folder_diff(dirs, diff_files: list, deleted: list, added: list) -> None:
    for file_root in dirs.diff_files:
        diff_files.append(os.path.join(dirs.right, file_root))
    for file_left in dirs.left_only:  # only in old version == deleted
        deleted.append(os.path.join(dirs.left, file_left))
    for file_right in dirs.right_only:  # only in new version == added
        abs_path = os.path.join(dirs.right, file_right)
        added.append(abs_path)
        if os.path.isdir(abs_path):  # if the whole folder is new, we need to recurse down.
            for root, _, files in os.walk(abs_path, topdown=True):
                for file in files:
                    added.append(os.path.join(root, file))
    for sub_dirs in dirs.subdirs.values():
        get_folder_diff(sub_dirs, diff_files, deleted, added)


def gen_patch(changed, added, deleted, path):
    tar = tarfile.open(path, "w|gz", compresslevel=3)
    print("Adding changed files...")
    for changed_file_path in tqdm.tqdm(changed):
        rel_path = os.path.relpath(changed_file_path, start=new_path)
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(changed_file_path).st_mode
        # Only calc per-file diffs >1K. It's an expensive operation.
        if os.path.getsize(changed_file_path) > 1000 and args.algo != "none":
            info.pax_headers = {"T": "M"}
            diff = get_file_diff_match_blocks(os.path.join(old_path, rel_path), changed_file_path)
            info.size = len(diff)
            tar.addfile(info, io.BytesIO(initial_bytes=diff))
        else:
            info.pax_headers = {"T": "A"}
            info.size = os.path.getsize(changed_file_path)
            tar.addfile(info, open(changed_file_path, "rb"))

    print("Adding new files...")
    for added_file_path in tqdm.tqdm(added):
        # we need the relative path to store the file name inside the tar properly.
        rel_path = os.path.relpath(added_file_path, start=new_path)
        info = tarfile.TarInfo(rel_path)
        info.mode = os.stat(added_file_path).st_mode
        info.pax_headers = {"T": "A"}
        # added may include directories - we need to handle this case.
        if os.path.isdir(added_file_path):
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        else:
            info.size = os.path.getsize(added_file_path)
            tar.addfile(info, open(added_file_path, "rb"))

    print("Adding ...deleted files...")
    for deleted_file_path in tqdm.tqdm(deleted):
        rel_path = os.path.relpath(deleted_file_path, start=old_path)
        info = tarfile.TarInfo(rel_path)
        info.pax_headers = {"T": "D"}
        tar.addfile(info)
    tar.close()


def get_folder_diff_result(old_dir: str, new_dir: str) -> tuple:
    dirs_comp = filecmp.dircmp(old_dir, new_dir)
    changed_files = []
    deleted_files = []
    added_files = []
    get_folder_diff(dirs_comp, changed_files, deleted_files, added_files)
    return changed_files, added_files, deleted_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches.')
    parser.add_argument("old", help="Path to the old directory.")
    parser.add_argument("new", help="Path to the new directory. ")
    parser.add_argument("dest", help="Path to the location of the patches.")
    parser.add_argument(
        "--algo",
        choices=["bsdiff", "none", "match-blocks"],
        default="match-blocks",
        help="Choice of patching algorithm.",
    )
    args = parser.parse_args()
    old_path = os.path.abspath(args.old)
    new_path = os.path.abspath(args.new)
    start_time = time.process_time()
    print("Diffing folders (this may take a while...)")
    changed, added, deleted = get_folder_diff_result(old_path, new_path)
    # all paths in the 3 returned lists are absolute.
    gen_patch(changed, added, deleted, args.dest)
    end_time = time.process_time()
    print(f"Patch generated!\nTime:{(end_time-start_time):.2f}s\nSize:{os.path.getsize(args.dest)>>20} MB")
    print(f"{len(changed)} modified files\n{len(added)} added files\n{len(deleted)} deleted files")
