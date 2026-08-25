"""portpick.py — the app never fails to start because a port is taken.

LIFTED from `GDRIVE_DOWNLOADER_FLASK_MACOS/portpick.py`. Its reasoning
applies here word for word, and it matters MORE here, because Baba asked
for the page to open by itself. A server that refuses to start opens
nothing, and the thing most likely to be holding port 8099 is **this app,
still running from before** — so without this, the app would block on its
own success case and the error would tell him to go and edit something.

    IT NEVER GIVES UP. Preferred port, then the next fifteen, then
    whatever the operating system hands out. There is no path through
    this module that ends in "could not start".

WHAT IT MUST NOT DO is pick a port and let the rest of the app carry on
believing the old one. Two things depend on the real number:

    the opener    opens the port actually bound, or shows a dead page
    guard.check   compares Origin against the port. Told the wrong one,
                  it refuses every request from the page it just opened

So `pick()` returns the number and the caller uses THAT everywhere.
"""

import socket

MAX_TRIES = 16


def is_free(host, port, timeout=0.4):
    """Can we actually BIND it? Not "is something listening".

    Asking whether something is listening answers a different question: a
    socket in TIME_WAIT, or bound to another interface, or owned by
    another user, all answer "nothing is listening" and then refuse the
    bind. The only honest test is to try.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # NOT SO_REUSEADDR. With it this test can succeed on a port
        # another process is already serving from, and the server then
        # fails behind us.
        s.settimeout(timeout)
        s.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def whats_there(port, timeout=1.0):
    """A guess at what holds the port, for the message only. Never raises.

    A raw socket rather than urllib, so this can only ever speak HTTP to
    loopback — the same reasoning as the original: making a thing
    impossible beats arguing that it cannot happen.
    """
    try:
        port = int(port)
        if not (1 <= port <= 65535):
            return None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", port))
            s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n"
                      b"Connection: close\r\n\r\n")
            body = b""
            while len(body) < 4000:
                chunk = s.recv(2048)
                if not chunk:
                    break
                body += chunk
        finally:
            s.close()
        if not body:
            return None
        return "self" if b"<title>TOML</title>" in body else "something"
    except Exception:                                        # noqa: BLE001
        return None


def pick(host, preferred, tries=MAX_TRIES):
    """Find a port. Always returns (port, note).

    `note` is None when the preferred port was free, otherwise a sentence
    saying what happened — a page that quietly opens somewhere other than
    where he expects is its own confusion.
    """
    preferred = int(preferred or 8099)
    if is_free(host, preferred):
        return preferred, None

    holder = whats_there(preferred)
    if holder == "self":
        why = ("port %d is already being used by another copy of TOML"
               % preferred)
    elif holder == "something":
        why = "port %d is being used by another program" % preferred
    else:
        why = "port %d could not be opened" % preferred

    for offset in range(1, tries):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if is_free(host, candidate):
            return candidate, "%s, so this one is on %d instead." % (why,
                                                                     candidate)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        chosen = s.getsockname()[1]
    finally:
        s.close()
    return chosen, "%s, so this one is on %d instead." % (why, chosen)
