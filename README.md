
# Tiki product crawler

## Setup

This crawler uses `curl-cffi` to match a Chrome TLS/HTTP2 client profile:

```powershell
uv sync
# or: pip install -e .
```

If the lock file needs refreshing, run `uv lock` with network access. The
current environment could not download the new `curl-cffi` package.

Put one product ID per line in `txt_files/products-01.txt`, then run:

```powershell
uv run python crawl.py
```

Set `TIKI_PROXY` for a proxy on every request. HTTP, HTTPS, and SOCKS5 URLs
are accepted by `curl-cffi`, for example:

```powershell
$env:TIKI_PROXY = "socks5://user:password@host:port"
uv run python crawl.py
```

`RateLimiter` applies a shared rate limit, 50-250 ms full jitter, and a global
backoff when any worker receives HTTP 429. Retries also cover timeouts,
transport errors, server errors, and HTML bot-block responses.
