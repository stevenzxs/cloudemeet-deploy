"""Canonicalize a user-supplied web origin and capture DNS address evidence."""

from __future__ import annotations

import ipaddress
import json
import socket
import argparse
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit, urlunsplit


Resolver = Callable[[str, int], list[str]]


def _resolve(host: str, port: int) -> list[str]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"DNS resolution failed for {host}: {exc}") from exc
    addresses = {record[4][0].split("%", 1)[0] for record in records}
    return sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, int(ipaddress.ip_address(value))))


def normalize_origin(value: str, resolver: Resolver | None = None) -> dict:
    """Validate an absolute HTTP(S) origin and return its canonical DNS contract.

    The domain remains the origin authority. Resolved addresses are evidence only
    and are never substituted into the URL.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("origin must be a non-empty URL without surrounding whitespace")

    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("origin must be an absolute http:// or https:// URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("origin must not contain user information")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("origin must not contain a path, query, or fragment")
        host = parsed.hostname
        if not host:
            raise ValueError("origin hostname is missing")
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError(f"invalid origin {value!r}: {exc}") from exc

    if not 1 <= port <= 65535:
        raise ValueError("origin port must be between 1 and 65535")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        # IDNA canonicalization gives stable origin and resolver input.
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
        if not host or any(not label or len(label) > 63 for label in host.split(".")):
            raise ValueError("origin hostname is invalid")
        addresses = (resolver or _resolve)(host, port)
    else:
        addresses = [str(literal)]
        host = f"[{literal.compressed}]" if literal.version == 6 else str(literal)

    normalized_addresses = set()
    for address in addresses:
        try:
            normalized_addresses.add(ipaddress.ip_address(address.split("%", 1)[0]).compressed)
        except ValueError as exc:
            raise ValueError(f"resolver returned an invalid IP address: {address!r}") from exc
    if not normalized_addresses:
        raise ValueError(f"DNS resolution returned no addresses for {host}")
    sorted_addresses = sorted(
        normalized_addresses,
        key=lambda value: (ipaddress.ip_address(value).version, int(ipaddress.ip_address(value))),
    )

    authority_host = host
    authority = f"{authority_host}:{port}" if parsed.port is not None else authority_host
    if parsed.port is None and port != (443 if scheme == "https" else 80):
        authority = f"{authority_host}:{port}"
    canonical_origin = urlunsplit((scheme, authority, "", "", ""))
    return {
        "origin": canonical_origin,
        "scheme": scheme,
        "host": host.strip("[]"),
    "port": port,
    "addresses": sorted_addresses,
        "tls_mode": None,
        "client_ca_file": None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import os
    contract = normalize_origin(os.environ["EXPECTED_ORIGIN"])
    if os.environ.get("EXPECTED_TLS_MODE"):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from tls_contract import parse, validate
        effective = validate(parse((Path(__file__).resolve().parents[1] / "config/client.env").read_text(encoding="utf-8")),
                             os.environ["EXPECTED_TLS_MODE"], contract["origin"])
        contract.update(effective)
        contract["addresses"] = normalize_origin(contract["origin"])["addresses"]
    Path(args.output).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(contract, sort_keys=True))
