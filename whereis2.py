import os
import sys
import stat
import fnmatch
import argparse
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import glob
import os
import sys
import stat
import fnmatch
import argparse
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import glob

# Debug masks
WHEREIS_DEBUG_INIT = 1 << 1
WHEREIS_DEBUG_PATH = 1 << 2
WHEREIS_DEBUG_ENV = 1 << 3
WHEREIS_DEBUG_ARGV = 1 << 4
WHEREIS_DEBUG_SEARCH = 1 << 5
WHEREIS_DEBUG_STATIC = 1 << 6
WHEREIS_DEBUG_LIST = 1 << 7
WHEREIS_DEBUG_ALL = 0xFFFF

# Global variables
uflag = False
use_glob = False
uflag = False
use_glob = False
use_regex = False
# Directory types
BIN_DIR = 1 << 1
MAN_DIR = 1 << 2
SRC_DIR = 1 << 3
ALL_DIRS = BIN_DIR | MAN_DIR | SRC_DIR

@dataclass
class WhDirlist:
    type: int
    st_dev: int
    st_ino: int
    path: str
    next: Optional['WhDirlist'] = None

# Predefined directory lists
bindirs = [
    "/usr/bin", "/usr/sbin", "/bin", "/sbin",
    "/usr/lib", "/usr/lib32", "/usr/lib64", "/etc", "/usr/etc",
    "/lib", "/lib32", "/lib64", "/usr/games", "/usr/games/bin",
    "/usr/games/lib", "/usr/emacs/etc", "/usr/lib/emacs/*/etc",
    "/usr/TeX/bin", "/usr/tex/bin", "/usr/interviews/bin/LINUX",
    "/usr/X11R6/bin", "/usr/X386/bin", "/usr/bin/X11",
    "/usr/X11/bin", "/usr/X11R5/bin", "/usr/local/bin",
    "/usr/local/sbin", "/usr/local/etc", "/usr/local/lib",
    "/usr/local/games", "/usr/local/games/bin", "/usr/local/emacs/etc",
    "/usr/local/TeX/bin", "/usr/local/tex/bin", "/usr/local/bin/X11",
    "/usr/contrib", "/usr/hosts", "/usr/include", "/usr/g++-include",
    "/usr/ucb", "/usr/old", "/usr/new", "/usr/local",
    "/usr/libexec", "/usr/share", "/opt/*/bin"
]

mandirs = [
    "/usr/man/*", "/usr/share/man/*", "/usr/X386/man/*",
    "/usr/X11/man/*", "/usr/TeX/man/*", "/usr/interviews/man/mann",
    "/usr/share/info"
]

srcdirs = [
    "/usr/src/*", "/usr/src/lib/libc/*", "/usr/src/lib/libc/net/*",
    "/usr/src/ucb/pascal", "/usr/src/ucb/pascal/utilities",
    "/usr/src/undoc"
]

def debug(mask: int, message: str):
    if os.environ.get('WHEREIS_DEBUG', '0') == '1':
        print(f"DEBUG: {message}", file=sys.stderr)

def whereis_type_to_name(type: int) -> str:
    if type == BIN_DIR:
        return "bin"
    elif type == MAN_DIR:
        return "man"
    elif type == SRC_DIR:
        return "src"
    else:
        return "???"

def dirlist_add_dir(ls0: Optional[WhDirlist], type: int, dir: str) -> Optional[WhDirlist]:
    if not os.access(dir, os.R_OK):
        return ls0
    
    try:
        st = os.stat(dir)
        if not stat.S_ISDIR(st.st_mode):
            return ls0
    except OSError:
        return ls0

    ls = ls0
    prev = None
    while ls:
        if ls.st_ino == st.st_ino and ls.st_dev == st.st_dev and ls.type == type:
            debug(WHEREIS_DEBUG_LIST, f"  ignore (already in list): {dir}")
            return ls0
        prev = ls
        ls = ls.next

    new_ls = WhDirlist(type=type, st_dev=st.st_dev, st_ino=st.st_ino, path=os.path.realpath(dir))
    
    if not ls0:
        ls0 = new_ls
    else:
        assert prev
        prev.next = new_ls

    debug(WHEREIS_DEBUG_LIST, f"  add dir: {new_ls.path}")
    return ls0

def dirlist_add_subdir(ls: Optional[WhDirlist], type: int, dir: str) -> Optional[WhDirlist]:
    if '*' not in dir:
        return dirlist_add_dir(ls, type, dir)

    base_dir, pattern = os.path.split(dir)
    try:
        for subdir in os.listdir(base_dir):
            full_path = os.path.join(base_dir, subdir)
            if fnmatch.fnmatch(subdir, pattern) and os.path.isdir(full_path):
                ls = dirlist_add_dir(ls, type, full_path)
    except OSError:
        debug(WHEREIS_DEBUG_LIST, f" ignore path: {dir}")

    return ls

def construct_dirlist_from_env(env: str, ls: Optional[WhDirlist], type: int) -> Optional[WhDirlist]:
    path = os.environ.get(env)
    if not path:
        return ls

    debug(WHEREIS_DEBUG_ENV, f"construct {whereis_type_to_name(type)} dirlist from: {path}")

    for dir in path.split(os.pathsep):
        ls = dirlist_add_dir(ls, type, dir)

    return ls

def construct_dirlist_from_argv(ls: Optional[WhDirlist], idx: int, argv: List[str], type: int) -> Tuple[Optional[WhDirlist], int]:
    debug(WHEREIS_DEBUG_ARGV, f"construct {whereis_type_to_name(type)} dirlist from argv[{idx}:]")

    while idx < len(argv):
        if argv[idx].startswith('-'):
            break
        debug(WHEREIS_DEBUG_ARGV, f"  using argv[{idx}]: {argv[idx]}")
        ls = dirlist_add_dir(ls, type, argv[idx])
        idx += 1

    return ls, idx - 1

def construct_dirlist(ls: Optional[WhDirlist], type: int, paths: List[str]) -> Optional[WhDirlist]:
    debug(WHEREIS_DEBUG_STATIC, f"construct {whereis_type_to_name(type)} dirlist from static array")

    for path in paths:
        if '*' not in path:
            ls = dirlist_add_dir(ls, type, path)
        else:
            ls = dirlist_add_subdir(ls, type, path)

    return ls

def free_dirlist(ls0: Optional[WhDirlist], type: int) -> Optional[WhDirlist]:
    debug(WHEREIS_DEBUG_LIST, "free dirlist")

    ls = ls0
    prev = None
    while ls:
        if ls.type & type:
            debug(WHEREIS_DEBUG_LIST, f" free: {ls.path}")
            next_ls = ls.next
            ls = next_ls
            if prev:
                prev.next = ls
        else:
            if not prev:
                ls0 = ls
            prev = ls
            ls = ls.next

    return ls0

def filename_equal(cp: str, dp: str, type: int) -> bool:
    debug(WHEREIS_DEBUG_SEARCH, f"compare '{cp}' and '{dp}'")

    if use_regex:
        return re.search(cp, dp) is not None

    if use_glob:
        return fnmatch.fnmatch(dp, cp)

    if type & SRC_DIR and dp.startswith('s.') and filename_equal(cp, dp[2:], type):
        return True

    if type & MAN_DIR:
        for ext in ('.Z', '.gz', '.xz', '.bz2', '.zst'):
            if dp.endswith(ext):
                dp = dp[:-len(ext)]
                break
        
        # Strip section number and additional extensions
        base, ext = os.path.splitext(dp)
        if ext.startswith('.'):
            ext = ext[1:]
        if ext.isdigit() or ext in ('n', 'ntcl', 'p', 'l', '1perl'):
            dp = base

    if cp == dp:
        return True

    if not (type & BIN_DIR) and cp == dp.split('.')[0]:
        parts = dp.split('.')
        return len(parts) > 1 and parts[-1] == 'C'

    return False


def findin(dir: str, pattern: str, count: List[int], wait: List[Optional[str]], type: int):
    try:
        with os.scandir(dir) as it:
            for entry in it:
                if filename_equal(pattern, entry.name, type):
                    if uflag and count[0] == 0:
                        wait[0] = os.path.join(dir, entry.name)
                    elif uflag and count[0] == 1 and wait[0]:
                        print(f"{pattern}: {wait[0]} {os.path.join(dir, entry.name)}", end='')
                        wait[0] = None
                    else:
                        print(f" {os.path.join(dir, entry.name)}", end='')
                    count[0] += 1
    except OSError:
        pass

def lookup(pattern: str, ls: Optional[WhDirlist], want: int):
    patbuf = pattern if use_regex else os.path.basename(pattern)
    count = [0]
    wait: List[Optional[str]] = [None]

    debug(WHEREIS_DEBUG_SEARCH, f"lookup dirs for '{patbuf}' ({pattern}), want: " +
          f"{'bin' if want & BIN_DIR else ''} {'man' if want & MAN_DIR else ''} {'src' if want & SRC_DIR else ''}")

    if not uflag:
        print(f"{patbuf}:", end='')

    while ls:
        if (ls.type & want) and ls.path:
            findin(ls.path, patbuf, count, wait, ls.type)
        ls = ls.next

    if not uflag or count[0] > 1:
        print()

def list_dirlist(ls: Optional[WhDirlist]):
    while ls:
        if ls.path:
            if ls.type == BIN_DIR:
                print("bin: ", end='')
            elif ls.type == MAN_DIR:
                print("man: ", end='')
            elif ls.type == SRC_DIR:
                print("src: ", end='')
            print(ls.path)
        ls = ls.next

def main():
    global uflag, use_glob, use_regex

    parser = argparse.ArgumentParser(description="Locate the binary, source, and manual-page files for a command.")
    parser.add_argument('-b', action='store_true', help='search only for binaries')
    parser.add_argument('-B', nargs='+', help='define binaries lookup path')
    parser.add_argument('-m', action='store_true', help='search only for manuals and infos')
    parser.add_argument('-M', nargs='+', help='define man and info lookup path')
    parser.add_argument('-s', action='store_true', help='search only for sources')
    parser.add_argument('-S', nargs='+', help='define sources lookup path')
    parser.add_argument('-u', action='store_true', help='search for unusual entries')
    parser.add_argument('-g', action='store_true', help='interpret name as glob (pathnames pattern)')
    parser.add_argument('-r', '--regex', action='store_true', help='use regex for searching')
    parser.add_argument('-l', action='store_true', help='output effective lookup paths')
    parser.add_argument('names', nargs='*', help='names to look up')

    args = parser.parse_args()

    uflag = args.u
    use_glob = args.g
    use_regex = args.regex

    if use_glob and use_regex:
        print("Error: Cannot use both glob and regex at the same time", file=sys.stderr)
        sys.exit(1)

    ls: Optional[WhDirlist] = None
    ls = construct_dirlist(ls, BIN_DIR, bindirs)
    ls = construct_dirlist_from_env("PATH", ls, BIN_DIR)

    ls = construct_dirlist(ls, MAN_DIR, mandirs)
    ls = construct_dirlist_from_env("MANPATH", ls, MAN_DIR)

    ls = construct_dirlist(ls, SRC_DIR, srcdirs)

    if args.B:
        ls = free_dirlist(ls, BIN_DIR)
        for dir in args.B:
            ls = dirlist_add_dir(ls, BIN_DIR, dir)

    if args.M:
        ls = free_dirlist(ls, MAN_DIR)
        for dir in args.M:
            ls = dirlist_add_dir(ls, MAN_DIR, dir)

    if args.S:
        ls = free_dirlist(ls, SRC_DIR)
        for dir in args.S:
            ls = dirlist_add_dir(ls, SRC_DIR, dir)

    want = ALL_DIRS
    if args.b:
        want = BIN_DIR
    if args.m:
        want = want | MAN_DIR if want != ALL_DIRS else MAN_DIR
    if args.s:
        want = want | SRC_DIR if want != ALL_DIRS else SRC_DIR

    if args.l:
        list_dirlist(ls)
    elif args.names:
        for name in args.names:
            lookup(name, ls, want)
    else:
        print("Error: no names provided to look up", file=sys.stderr)
        sys.exit(1)

    free_dirlist(ls, ALL_DIRS)

if __name__ == "__main__":
    main()
