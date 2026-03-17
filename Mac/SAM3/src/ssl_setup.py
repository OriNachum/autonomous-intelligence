"""SSL certificate setup for corporate proxy environments.

Exports system CA certificates (including corporate root CAs) to a PEM bundle
that httpx/huggingface-hub can use. This is needed when behind proxies like
Cato Networks, Zscaler, etc. that use self-signed root certificates.
"""

import base64
import os
import ssl
from pathlib import Path

CERT_BUNDLE_PATH = Path("/tmp/system_ca_bundle.pem")


def ensure_ssl_certs():
    """Export system CA certs and set env vars for httpx/requests."""
    if not CERT_BUNDLE_PATH.exists():
        ctx = ssl.create_default_context()
        certs = ctx.get_ca_certs(binary_form=True)
        with open(CERT_BUNDLE_PATH, "w") as f:
            for cert_der in certs:
                b64 = base64.b64encode(cert_der).decode("ascii")
                f.write("-----BEGIN CERTIFICATE-----\n")
                f.write("\n".join(b64[i : i + 64] for i in range(0, len(b64), 64)))
                f.write("\n-----END CERTIFICATE-----\n")

    os.environ["SSL_CERT_FILE"] = str(CERT_BUNDLE_PATH)
    os.environ["REQUESTS_CA_BUNDLE"] = str(CERT_BUNDLE_PATH)
