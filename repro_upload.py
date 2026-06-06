"""Reproduce the upload flow end-to-end against the new presigned-URL pipeline.

1. POST /api/upload-url  →  get signed upload URL + token + path
2. PUT dummy file directly to Supabase signed URL
3. POST /api/upload  →  trigger analysis with {path, lat, lon, locationName}
"""
import os
import tempfile
import urllib.request
import urllib.error

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:3000")
FILE_SIZE_MB = 16  # reps the user's failing case

# 1. Build a dummy MP4
TMP = tempfile.mktemp(suffix=".mp4")
with open(TMP, "wb") as f:
    f.write(os.urandom(FILE_SIZE_MB * 1024 * 1024))
size_mb = os.path.getsize(TMP) / (1024 * 1024)
print(f"Created dummy file: {TMP} ({size_mb:.1f} MB)")

try:
    # 2. Get signed upload URL from server
    filename = "repro_test.mp4"
    url_req = urllib.request.Request(
        f"{BASE_URL}/api/upload-url",
        data=b'{"filename":"' + filename.encode() + b'","contentType":"video/mp4"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(url_req, timeout=15) as resp:
            url_data = __import__("json").loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: upload-url returned {e.code}: {body}")
        exit(1)

    signed_url = url_data.get("signedUrl")
    token = url_data.get("token")
    path = url_data.get("path")
    if not signed_url or not token or not path:
        print(f"FAIL: upload-url response missing fields: {url_data}")
        exit(1)
    print(f"Got signed URL for path: {path}")

    # 3. Upload directly to Supabase Storage via signed URL
    with open(TMP, "rb") as f:
        file_bytes = f.read()

    upload_req = urllib.request.Request(
        signed_url,
        data=file_bytes,
        headers={
            "Content-Type": "video/mp4",
            "x-upsert": "false",
        },
        method="PUT",
    )

    try:
        with urllib.request.urlopen(upload_req, timeout=60) as resp:
            print(f"Upload to Supabase: {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: direct upload returned {e.code}: {body}")
        exit(1)

    # 4. Trigger analysis via /api/upload
    payload = __import__("json").dumps({
        "path": path,
        "lat": 51.5,
        "lon": -0.1,
        "locationName": "Repro Test",
    }).encode()

    analyze_req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(analyze_req, timeout=90) as resp:
            result = resp.read().decode("utf-8", errors="replace")
            print(f"STATUS: {resp.status}")
            print(f"BODY: {result[:800]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: analyze returned {e.code}: {body[:800]}")
        exit(1)

except Exception as e:
    print(f"ERROR: {e}")
    exit(1)
finally:
    os.unlink(TMP)
    print(f"Cleaned up {TMP}")
