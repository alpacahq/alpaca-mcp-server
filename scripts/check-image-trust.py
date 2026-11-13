"""Fail if the built image still trusts the compromised eMudhra roots.

Runs inside the image with the system interpreter, stdlib only:

    docker run --rm -v "$PWD/scripts:/check:ro" --entrypoint /usr/local/bin/python3 \
        alpaca-mcp-server /check/check-image-trust.py
"""

import hashlib
import importlib.util
import os
import re
import ssl
import sys

FORBIDDEN = {
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b": "emSign ECC Root CA - G3",
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4": "AAA Certificate Services",
}

# The check is vacuous unless these bundles are present and scanned.
REQUIRED_BUNDLES = {
    "/etc/ssl/certs/ca-certificates.crt",
    "/app/.venv/lib/python3.12/site-packages/certifi/cacert.pem",
}

# /usr/share/ca-certificates holds the sources update-ca-certificates builds
# the system bundle from; nothing reads them directly.
SKIP_PREFIXES = ("/proc", "/sys", "/dev", "/check", "/usr/share/ca-certificates")
MAX_FILE_BYTES = 16 * 1024 * 1024
PEM_BLOCK = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s+.+?\s+-----END CERTIFICATE-----", re.S
)


def pem_files():
    for dirpath, dirnames, filenames in os.walk("/"):
        dirnames[:] = [
            d for d in dirnames
            if not os.path.join(dirpath, d).startswith(SKIP_PREFIXES)
        ]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            if os.path.getsize(path) > MAX_FILE_BYTES:
                continue
            with open(path, "rb") as f:
                data = f.read()
            if b"-----BEGIN CERTIFICATE-----" in data:
                yield path, data


def main():
    failures = []

    if importlib.util.find_spec("pip") is not None:
        failures.append(f"system pip is importable by {sys.executable}")
    for path in ("/usr/local/bin/pip", "/usr/local/bin/pip3"):
        if os.path.lexists(path):
            failures.append(f"system pip entry point exists: {path}")

    scanned = set()
    for path, data in pem_files():
        scanned.add(path)
        for block in PEM_BLOCK.findall(data):
            try:
                der = ssl.PEM_cert_to_DER_cert(block.decode("ascii"))
            except ValueError:
                continue
            name = FORBIDDEN.get(hashlib.sha256(der).hexdigest())
            if name:
                failures.append(f"{path} trusts {name}")

    for path in sorted(REQUIRED_BUNDLES - scanned):
        failures.append(f"expected bundle not found: {path}")

    print(f"scanned {len(scanned)} files containing PEM certificates")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        sys.exit(1)
    print("PASS: no certificate bundle trusts the compromised roots")


if __name__ == "__main__":
    main()
