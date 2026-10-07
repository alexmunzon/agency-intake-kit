"""Read synthetic snapshot files relative to pinned directory descriptors."""
import hashlib
import json
import os
import stat
import sys

LIMIT = 12_000_000

def read_snapshot(root, paths):
    if os.open not in os.supports_dir_fd or any(not hasattr(os, flag) for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK')):
        raise ValueError('Safe descriptor-relative snapshot reads unavailable')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    directory = os.open('/', flags | os.O_DIRECTORY)
    try:
        for part in os.path.realpath(root).split('/'):
            if part:
                child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                os.close(directory)
                directory = child
        artifacts = []
        remaining = LIMIT
        for path in paths:
            parts = path.split('/')
            if path.startswith('/') or '\\' in path or any(p in ('', '.', '..') for p in parts):
                raise ValueError('Unsafe artifact path')
            parent = os.dup(directory)
            try:
                for part in parts[:-1]:
                    child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
                    os.close(parent)
                    parent = child
                fd = os.open(parts[-1], flags, dir_fd=parent)
                try:
                    before = os.fstat(fd)
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError('Snapshot artifact must be a regular file')
                    if before.st_size > remaining:
                        raise ValueError('Snapshot exceeds 12 MB')
                    content = bytearray()
                    while True:
                        chunk = os.read(fd, min(65536, remaining - len(content) + 1))
                        if not chunk:
                            break
                        content.extend(chunk)
                        if len(content) > remaining:
                            raise ValueError('Snapshot exceeds 12 MB')
                    after = os.fstat(fd)
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError('Snapshot changed during read')
                    remaining -= len(content)
                    artifacts.append(dict(path=path, content=content.decode('utf-8'), size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
                finally:
                    os.close(fd)
            finally:
                os.close(parent)
        return artifacts
    finally:
        os.close(directory)

if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        print(json.dumps(read_snapshot(request['root'], request['paths'])))
    except (OSError, ValueError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
