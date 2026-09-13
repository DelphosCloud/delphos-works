import os


AUTH_KEY = os.environ["AUTH_KEY"]
SPACES_KEY = os.environ["SPACES_KEY"]
SPACES_SECRET = os.environ["SPACES_SECRET"]
SPACES_REGION = os.environ["SPACES_REGION"]
SPACES_BUCKET = os.environ["SPACES_BUCKET"]

# How many PDF conversions may run at the same time (#13 — was hardcoded).
LIBREOFFICE_CONCURRENCY = int(os.environ.get("LIBREOFFICE_CONCURRENCY", "5"))

# How long to wait on a single call to Spaces before giving up (#11).
SPACES_CONNECT_TIMEOUT = float(os.environ.get("SPACES_CONNECT_TIMEOUT", "5"))
SPACES_READ_TIMEOUT = float(os.environ.get("SPACES_READ_TIMEOUT", "30"))

# How long a presigned download link stays valid (#10). Short by design —
# just long enough for a browser to start the download.
DOWNLOAD_URL_EXPIRY_SECONDS = int(os.environ.get("DOWNLOAD_URL_EXPIRY_SECONDS", "30"))

# Reject a template if, once opened, its uncompressed content would exceed
# this size — guards against a "zip bomb" style upload (#15).
MAX_TEMPLATE_UNCOMPRESSED_SIZE = int(
    os.environ.get("MAX_TEMPLATE_UNCOMPRESSED_SIZE", str(200 * 1024 * 1024))
)
