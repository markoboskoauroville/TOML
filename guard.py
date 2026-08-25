"""guard.py — a page holding real keys, open to nobody but this phone.

LIFTED, NOT RE-DERIVED. This is `localguard.py` from
GDRIVE_DOWNLOADER_FLASK_MACOS, which already has the reasoning and
already had its one real bug removed. MANTRA_MANIFEST README rule 1: take
the version that has already been hurt.

THE THREAT, AND IT IS NOT EXOTIC. Binding to 127.0.0.1 stops the network.
It does not stop a WEB PAGE. Any site open in another tab can make the
browser send requests to http://127.0.0.1:8099 in the background. Without
a check, that page could ask this app to read a file off the disk and
hand back its contents — and this app's whole job is reading files full
of API keys.

That is a worse case here than in the downloader it came from. There, a
hostile page could start a download. Here it could read the keyring.

    1  HOST        the Host header must be a loopback name. Stops DNS
                   rebinding: evil.com resolved to 127.0.0.1 really is a
                   local connection, but the browser still sends
                   "Host: evil.com". Binding does not catch that
    2  ORIGIN      an Origin or Referer that is present must be this app
    3  FETCH SITE  a custom header the page always sends and a
                   cross-site request cannot. A form POST cannot set
                   headers at all; a fetch that tries triggers a CORS
                   preflight that never gets an allow

GET on / passes with 1 and 2 only — typing the address yourself sends no
Origin and no custom header. Everything that READS A FILE needs all three.

NOT 0.0.0.0 IN THE LOOPBACK LIST. It was there by copy-and-paste in the
original and it was the one entry that would have mattered: 0.0.0.0 means
every interface, so accepting it as a loopback name lets a request that
arrived from the network past the first check.

AND THIS ONE SERVES 127.0.0.1 ONLY. The Termux app it is modelled on
(MAHA_TRANSCRIBE_TERMUX) binds 0.0.0.0 so any device on the Wi-Fi can
reach it, which is right for a transcription page and wrong for this. A
café network is a room full of strangers.
"""

from flask import jsonify, request

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
GUARD_HEADER = "X-Toml-Local"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
OPEN_ENDPOINTS = {"static", "index", "favicon_ico"}


def _host_ok(host_header):
    if not host_header:
        return False
    host = (host_header.rsplit(":", 1)[0]
            if host_header.count(":") == 1 else host_header)
    if host.startswith("[") and "]" in host:
        host = host[:host.index("]") + 1]
    return host in LOCAL_HOSTS


def _origin_ok(origin, port):
    if not origin:
        return True
    allowed = {"http://%s:%d" % (h, port)
               for h in ("127.0.0.1", "localhost", "[::1]")}
    return origin.rstrip("/") in allowed


def check(port):
    """Called from before_request. Returns a response to refuse, or None."""
    if not _host_ok(request.headers.get("Host", "")):
        return jsonify(error="not a local host"), 403

    origin = (request.headers.get("Origin")
              or request.headers.get("Referer") or "")
    if origin:
        base = origin
        if base.count("/") > 2:
            parts = base.split("/")
            base = parts[0] + "//" + parts[2]
        if not _origin_ok(base, port):
            return jsonify(error="not this app"), 403

    if request.endpoint in OPEN_ENDPOINTS and request.method in SAFE_METHODS:
        return None

    if not request.headers.get(GUARD_HEADER):
        return jsonify(error="not this page"), 403
    return None
