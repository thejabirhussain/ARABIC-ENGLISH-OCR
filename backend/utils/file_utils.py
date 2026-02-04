import tempfile
import os
import contextlib

def save_content_to_temp(content: bytes, suffix: str = ".pdf") -> str:
    """
    Saves bytes content to a temporary file and returns the path.
    The caller is responsible for cleaning up the file.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return tmp.name

def cleanup_file(path: str):
    """
    Safely deletes a file if it exists.
    """
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass

@contextlib.contextmanager
def temporary_file(content: bytes, suffix: str = ".pdf"):
    """
    Context manager that saves content to a temp file and yields the path.
    Automatically cleans up the file after the block exits.
    """
    path = save_content_to_temp(content, suffix)
    try:
        yield path
    finally:
        cleanup_file(path)
