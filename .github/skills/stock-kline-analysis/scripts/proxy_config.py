"""
proxy_config.py — Centralised proxy management for all scripts.

Intel corporate network requires a proxy.  Port selection matters:
  - Port 911 handles HTTP-only proxying
  - Port 912 handles HTTPS (CONNECT tunnels) correctly

Persists user settings in  scripts/data/proxy.json  so they survive restarts.

Usage (library):
    from proxy_config import apply_proxy
    apply_proxy()                        # load saved config or auto-detect

    from proxy_config import configure_proxy
    configure_proxy("http://proxy.ims.intel.com:912")   # explicit set + save

Usage (CLI):
    python proxy_config.py                        # show current settings
    python proxy_config.py --set http://proxy:912 # set + test
    python proxy_config.py --test                 # test connectivity
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
_CONF_FILE = _SCRIPTS_DIR / "data" / "proxy.json"

# Default proxy with port 912 for HTTPS CONNECT support
_DEFAULT_PROXY = "http://child-prc.intel.com:913"

# Domains that should bypass the proxy (comma-separated for NO_PROXY)
_DEFAULT_NO_PROXY = "localhost,127.0.0.1"


# ── Persistence ─────────────────────────────────────────────────────────────

def _load_conf() -> dict[str, Any]:
    if _CONF_FILE.exists():
        try:
            return json.loads(_CONF_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_conf(conf: dict[str, Any]) -> None:
    _CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONF_FILE.write_text(json.dumps(conf, indent=2, ensure_ascii=False),
                          encoding="utf-8")


# ── Core API ────────────────────────────────────────────────────────────────

def apply_proxy(proxy_url: str | None = None) -> str:
    """
    Apply proxy settings to the current process environment.

    Resolution order:
      1. Explicit *proxy_url* argument
      2. Saved config in proxy.json
      3. Existing env vars (http_proxy / https_proxy)
      4. _DEFAULT_PROXY

    Returns the proxy URL that was applied.
    """
    conf = _load_conf()

    url = (
        proxy_url
        or conf.get("proxy_url")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or _DEFAULT_PROXY
    )

    no_proxy = conf.get("no_proxy", _DEFAULT_NO_PROXY)

    os.environ["http_proxy"] = url
    os.environ["https_proxy"] = url
    os.environ["HTTP_PROXY"] = url
    os.environ["HTTPS_PROXY"] = url
    os.environ["no_proxy"] = no_proxy
    os.environ["NO_PROXY"] = no_proxy
    return url


def configure_proxy(proxy_url: str, no_proxy: str | None = None) -> None:
    """Set and persist proxy configuration."""
    conf = _load_conf()
    conf["proxy_url"] = proxy_url
    if no_proxy is not None:
        conf["no_proxy"] = no_proxy
    _save_conf(conf)
    apply_proxy(proxy_url)


def get_proxy_info() -> dict[str, str]:
    """Return current proxy settings (from saved config + env)."""
    conf = _load_conf()
    return {
        "saved_url": conf.get("proxy_url", ""),
        "no_proxy": conf.get("no_proxy", _DEFAULT_NO_PROXY),
        "env_http": os.environ.get("http_proxy", ""),
        "env_https": os.environ.get("https_proxy", ""),
        "default": _DEFAULT_PROXY,
    }


def test_proxy(proxy_url: str | None = None) -> dict[str, Any]:
    """
    Test proxy connectivity against key East Money domains.
    Returns {url, results: [{domain, ok, status/error}]}.
    """
    import requests

    url = apply_proxy(proxy_url)
    proxies = {"http": url, "https": url}

    test_targets = [
        ("push2.eastmoney.com",
         "https://push2.eastmoney.com/api/qt/clist/get",
         {"pn": "1", "pz": "1", "fs": "m:90 t:2 f:!50", "fields": "f14"}),
        ("datacenter-web.eastmoney.com",
         "https://datacenter-web.eastmoney.com/api/data/v1/get",
         {"reportName": "RPT_INDUSTRY_BOARD"}),
        ("quote.eastmoney.com",
         "https://quote.eastmoney.com/center/boardlist.html",
         None),
    ]

    results = []
    for domain, test_url, params in test_targets:
        try:
            kw: dict[str, Any] = {"proxies": proxies, "timeout": 15}
            if params:
                kw["params"] = params
            r = requests.get(test_url, **kw)
            results.append({"domain": domain, "ok": True, "status": r.status_code})
        except Exception as e:
            results.append({"domain": domain, "ok": False, "error": type(e).__name__})

    return {"proxy_url": url, "results": results}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Proxy configuration manager")
    parser.add_argument("--set", dest="proxy_url", help="Set proxy URL (e.g. http://proxy:912)")
    parser.add_argument("--no-proxy", help="Domains to bypass (comma-separated)")
    parser.add_argument("--test", action="store_true", help="Test connectivity")
    parser.add_argument("--show", action="store_true", help="Show current config")
    args = parser.parse_args()

    if args.proxy_url:
        configure_proxy(args.proxy_url, args.no_proxy)
        print(f"[proxy] Saved proxy: {args.proxy_url}")

    if args.show or (not args.proxy_url and not args.test):
        info = get_proxy_info()
        print(f"  Saved URL  : {info['saved_url'] or '(none)'}")
        print(f"  Default    : {info['default']}")
        print(f"  Env HTTP   : {info['env_http'] or '(none)'}")
        print(f"  Env HTTPS  : {info['env_https'] or '(none)'}")
        print(f"  NO_PROXY   : {info['no_proxy']}")

    if args.test:
        print("\n[proxy] Testing connectivity...")
        report = test_proxy(args.proxy_url)
        print(f"  Using: {report['proxy_url']}")
        for r in report["results"]:
            status = f"OK ({r['status']})" if r["ok"] else f"FAIL ({r.get('error', '?')})"
            print(f"  {r['domain']:<40} {status}")


if __name__ == "__main__":
    main()
