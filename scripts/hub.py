"""Minimal HF Hub client. stdlib only; certifi because python.org builds ship no CA bundle."""
import gzip, json, ssl, time, urllib.error, urllib.request
from pathlib import Path
import certifi

API = "https://huggingface.co/api"
_CTX = ssl.create_default_context(cafile=certifi.where())
_UA = {"User-Agent": "model-launch-lag/0.1 (research)"}


def get(path, tries=4):
    """GET an API path. Returns (headers, parsed). Retries on 429/5xx with backoff."""
    url = path if path.startswith("http") else f"{API}/{path}"
    for n in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=45, context=_CTX)
            return r.headers, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            if e.code in (429, 500, 502, 503) and n < tries - 1:
                time.sleep(2 ** n * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if n < tries - 1:
                time.sleep(2 ** n * 2)
                continue
            raise


def save_raw(obj, root: Path, name: str):
    """Gzip a raw response so the DB can be rebuilt without re-fetching (README: raw first)."""
    f = root / f"{name.replace('/', '__')}.json.gz"
    f.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(f, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return f


def all_commits(hf_id, cap=1200):
    """Every commit on main, newest first. Follows Link rel=next; cap guards runaway repos."""
    out, url = [], f"{API}/models/{hf_id}/commits/main?limit=100"
    while url and len(out) < cap:
        h, page = get(url)
        if not page:
            break
        out += page
        nxt = None
        for part in (h.get("Link") or "").split(","):
            if 'rel="next"' in part and "<" in part:
                nxt = part[part.index("<") + 1 : part.index(">")]
        url = nxt if not nxt or nxt.startswith("http") else f"https://huggingface.co{nxt}"
    return out
