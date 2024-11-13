### idea: use rdiff / bsdiff to load a file into memory, diff it, then store the diff inside the tar with compression

import filecmp
import time
import os
import tarfile
import argparse





def get_diff_files(dirs,diff_files,deleted,added):
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
        get_diff_files(sub_dirs,diff_files,deleted,added)


def get_header(old_dir: str, new_dir: str) -> tuple:
    dirs_comp = filecmp.dircmp(old_dir,new_dir)
    changed_files = [] # note that these are all absolute paths; when stored they need to be relative.
    deleted_files = []
    added_files = []
    get_diff_files(dirs_comp,changed_files,deleted_files,added_files)
    return changed_files,added_files,deleted_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate "Milshaw" patches / config file.')
    parser.add_argument('--old', required=True, help="Path to the old directory.")
    parser.add_argument('--new', required=True, help="Path to the new directory")
    parser.add_argument('--dest', required=True, help="Path to the location of the patches.")
    args = parser.parse_args()
    old_path = os.path.abspath(args.old)
    new_path = os.path.abspath(args.new)
    start_time = time.process_time()
    changed,added,deleted = get_header(old_path,new_path) # note: paths are absolute.
    f = open("beans.txt",'w+')
    f.write(str(added))
    f.write(str(changed))
    f.write(str(deleted))
    f.close()
    tar = tarfile.open(args.dest,'w|gz',compresslevel=3)
    for changed_file in changed:
        rel_path = os.path.relpath(changed_file, start=new_path)
        print(f"C | {rel_path}")
        info = tarfile.TarInfo(rel_path)
        info.pax_headers = {"T":"C"}
        info.mode = os.stat(changed_file).st_mode
        info.size = os.path.getsize(changed_file)
        tar.addfile(info,open(changed_file,'rb'))

    for added_file in added:
        rel_path = os.path.relpath(added_file, start=new_path) # we need the relative path to store the file name inside the tar properly.
        print(f"A | {rel_path}")
        info = tarfile.TarInfo(rel_path)
        info.pax_headers = {"T":"A"}
        info.mode = os.stat(added_file).st_mode
        if os.path.isdir(added_file): # added may include directories, so handling it here.
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        else:
            info.size = os.path.getsize(added_file)
            tar.addfile(info,open(added_file,'rb'))

    for deleted_file in deleted:
        rel_path = os.path.relpath(deleted_file, start=old_path)
        print(f"D | {rel_path}")
        info = tarfile.TarInfo(rel_path)
        info.pax_headers = {"T":"D"}
        tar.addfile(info)

    tar.close()
    end_time = time.process_time()
    print(f"Patch generated!\nTime:{(end_time-start_time)*10:.2f}s\nSize:{os.path.getsize(args.dest)>>20} MB")
    print(f"{len(changed)} modified files\n{len(added)} added files\n{len(deleted)} deleted files")




