# pyflared

A lightweight, Pythonic wrapper around Cloudflare's `cloudflared` CLI for spinning up Quick Tunnels (`*.trycloudflare.com`) and named tunnels with clean context-manager lifecycle handling.

## Features

- **Context Manager Support:** Use `with Tunnel(port=8000) as tunnel:` for automatic startup and guaranteed process cleanup on exit.
- **Zero-Config Quick Tunnels:** Automatically parses and exposes the generated `https://*.trycloudflare.com` URL.
- **Named Tunnel Support:** Run persistent Cloudflare Zero Trust tunnels via `--token`.
- **Configurable Defaults:** Customize retry limits and binary paths via `config.json` or per-instance arguments.
- **Typed API & Custom Exceptions:** Strict type annotations (`Protocol`, `LogLevel`) and granular error handling (`PortError`, `TunnelStartupError`, `BinaryNotFoundError`).

## Prerequisites

1. **Python 3.8+**
2. **`cloudflared` binary:** Download the latest `cloudflared` release for your platform from [Cloudflare's GitHub Releases](https://github.com/cloudflare/cloudflared/releases) and place `cloudflared.exe` in the `pyflared` directory (or point `cloudflared_path` in `config.json` to its location).

## Configuration (`config.json`)

A default `config.json` is included in the package directory. You can edit it to change global defaults without passing arguments to `Tunnel()`:

```json
{
    "default_max_retries": 5,
    "cloudflared_path": "cloudflared.exe"
}
```

## Quick Start

### Quick Tunnel (Temporary Public URL)

```python
from pyflared import Tunnel

with Tunnel(port=8000) as tunnel:
    print(f"Public URL: {tunnel.url}")
    input("Press Enter to close the tunnel...")
```

### Named Tunnel (Cloudflare Zero Trust Token)

```python
from pyflared import Tunnel

with Tunnel(token="your-cloudflare-tunnel-token") as tunnel:
    print("Named tunnel connected.")
    input("Press Enter to stop...")
```

### Manual Lifecycle & Custom Options

```python
from pyflared import Tunnel, PyflaredError

tunnel = Tunnel(
    port=8080,
    retries=3,
    protocol="http2",
    loglevel="debug",
    timeout=20.0,
)

try:
    tunnel.start()
    print(f"Running: {tunnel.is_running} | URL: {tunnel.url}")

    # Inspect the underlying CLI command
    print("Command:", tunnel.build_command())

    # Restart the tunnel
    tunnel.restart()
except PyflaredError as exc:
    print(f"Tunnel error: {exc}")
finally:
    tunnel.stop()
```

## Exceptions

All exceptions inherit from `PyflaredError`:

| Exception | Description |
| :--- | :--- |
| `PyflaredError` | Base exception for all `pyflared` errors. |
| `PortError` | Raised when a port is invalid (`1–65535`), missing, or modified while running. |
| `BinaryNotFoundError` | Raised when `cloudflared` cannot be found at the configured path. |
| `TunnelStartupError` | Raised if `cloudflared` exits unexpectedly or times out during startup. |

## License

MIT
