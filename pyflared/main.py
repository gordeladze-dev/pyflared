# DECLARATIONS

from __future__ import annotations # prevent compiler warnings about annotations in Python

import json
import re
import queue
import threading
import time
import subprocess as sp
from typing import Literal
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
CONFIG: dict = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {} # stop windows cp1252 shenanigans with encode=...

TRYCLOUDFLARE_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
TRYCLOUDFLARE_TOKENIZED_RE = re.compile(r"Registered tunnel connection")

# CONFIGURATION

DEFAULT_MAX_RETRIES: int = CONFIG.get("default_max_retries", 5)
CLOUDFLARED_PATH: str = CONFIG.get("cloudflared_path", "cloudflared.exe")

# TYPES

Protocol = Literal["auto", "quic", "http2"]
LogLevel = Literal["debug", "info"]

# ERRORS

class PyflaredError(Exception):
    """Base exception for all pyflared errors."""
    pass

class PortError(PyflaredError):
    """Raised when a port is invalid, missing, or modified while running."""
    pass

class TunnelStartupError(PyflaredError):
    """Raised when cloudflared fails to start or obtain a public URL."""
    pass

class BinaryNotFoundError(PyflaredError):
    """Raised when the cloudflared executable cannot be found at the expected path.."""
    pass

# API

class Tunnel:
    def __init__(
        self,
        port: int | None = None,
        token: str | None = None,
        retries: int = DEFAULT_MAX_RETRIES,
        protocol: Protocol = "auto",
        loglevel: LogLevel = "info",
        timeout: float = 15.0,
        cloudflared_path: str = CLOUDFLARED_PATH,
    ) -> None:
        """Creates a new Tunnel instance with the specified configuration.

        ## Args:
            **port** *(int | None, optional)*: The port to tunnel to. Defaults to *None*.
            **token** *(str | None, optional)*: The Cloudflare Tunnel token. Defaults to *None*.
            **retries** *(int, optional)*: The maximum number of retry attempts. Defaults to *DEFAULT_MAX_RETRIES*.
            **protocol** *(Protocol, optional)*: The protocol to use for the tunnel. Defaults to *"auto"*.
            **loglevel** *(LogLevel, optional)*: The logging level. Defaults to *"info"*.
            **timeout** *(float, optional)*: The timeout for the tunnel startup. Defaults to *15.0*.
            **cloudflared_path** *(str, optional)*: The path to the cloudflared executable. Defaults to *CLOUDFLARED_PATH*.
        """

        self._process: sp.Popen | None = None
        self._port: int | None = None
        self._url: str | None = None
        self._token: str | None = token
        self._retries: int = retries
        self._protocol: Protocol = protocol
        self._loglevel: LogLevel = loglevel
        self._timeout: float = timeout
        self.cloudflared_path: str = cloudflared_path
        self.port = port

    def _resolve_binary_path(self, custom_path: str) -> Path:
        """Resolves the path to the cloudflared binary, erroring accordingly."""

        path = BASE_DIR / custom_path

        if not path.is_file():
            raise BinaryNotFoundError(f"Could not find cloudflared at: {path}")
        
        return path

    def build_command(self) -> list[str]:
        """Builds the command to run cloudflared with the specified options.

        ## Raises:
            **PortError:** If a port is not set and no token is provided.

        ## Returns:
            **list[str]:** The cloudflared command to run the tunnel with subprocess.
        """

        binary = str(self._resolve_binary_path(self.cloudflared_path))

        base_cmd = [
            binary,
            "tunnel",
            "--retries", str(self._retries),
            "--protocol", self._protocol,
            "--loglevel", self._loglevel,
        ]

        if self._token:
            return [*base_cmd, "run", "--token", self._token]

        if self._port is None:
            raise PortError("A port (1-65535) must be set before starting a quick tunnel.")

        return [*base_cmd, "--url", f"http://localhost:{self._port}"]

    def start(self) -> Tunnel:
        """Starts the cloudflared tunnel and waits for a public URL if running a quick tunnel. 
        
        ## Note:
            The startup process typically takes a few seconds, as cloudflared has its own internal latency.

        ## Raises:
            **PortError:** If no port or token is configured.
            **BinaryNotFoundError:** If cloudflared cannot be found.
            **TunnelStartupError:** If cloudflared exits unexpectedly during startup.
            **TunnelStartupError:** If cloudflared times out waiting for a public URL.

        ## Returns:
            **Tunnel**: The running Tunnel instance.
        """

        if self.is_running:
            return self

        CMD = self.build_command()
        
        self._process = sp.Popen(
            CMD,
            stdout=sp.DEVNULL,
            stderr=sp.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        lines: queue.Queue[str] = queue.Queue()

        def _reader() -> None:
            assert self._process is not None and self._process.stderr is not None

            for line in self._process.stderr:
                lines.put(line)

        threading.Thread(target=_reader, daemon=True).start()

        PATTERN = TRYCLOUDFLARE_TOKENIZED_RE if self._token else TRYCLOUDFLARE_RE
        DEADLINE = time.monotonic() + self._timeout # you learn alot doing random projects. didnt even realise monotonic was a thing until i needed it for this

        while time.monotonic() < DEADLINE:
            if self._process.poll() is not None:
                self.stop()
                raise TunnelStartupError("Cloudflared exited unexpectedly during startup.")

            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue

            match = PATTERN.search(line)

            if match:
                if not self._token:
                    self._url = match.group(0)

                return self

        self.stop()
        raise TunnelStartupError(f"Timed out after {self._timeout}s waiting for tunnel startup.")

    def stop(self) -> None:
        """Stops the cloudflared tunnel, cleaning up its assosciated subprocess cleanly without erroring."""
        self._url = None

        if self._process is None:
            return

        if self._process.poll() is None:
            self._process.terminate()

            try:
                self._process.wait(timeout=5)
            except sp.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        if self._process.stderr is not None:
            self._process.stderr.close()

        self._process = None

    def restart(self) -> Tunnel:
        """Restarts the cloudflared tunnel by stopping and starting it.

        ## Returns:
            **Tunnel**: The restarted Tunnel instance.
        """

        self.stop()
        return self.start() # see this is why i made .start return the tunnel, clean syntax >:)

    @property
    def is_running(self) -> bool:
        """Whether the tunnel is currently running."""
        return self._process is not None and self._process.poll() is None

    @property
    def url(self) -> str | None:
        """The public URL of the tunnel. Will be None if the tunnel is not running or if a token is used."""
        return self._url

    @property
    def port(self) -> int | None:
        """The port of the tunnel. Can be set before starting the tunnel, but cannot be changed while the tunnel is running."""
        return self._port

    @port.setter
    def port(self, new_port: int | None) -> None:
        if self.is_running:
            raise PortError("Port cannot be changed whilst tunnel is running. Stop the tunnel first.")
        
        if new_port is not None and (isinstance(new_port, bool) or not (1 <= new_port <= 65535)): # bool being a subclass of int is some js level weirdness but whatever
            raise PortError(f"Invalid port number; {new_port}. Must be between 1-65535.")
        
        self._port = new_port

    # allow for "with Tunnel() as tunnel:" syntax which is really clean and i like :)
    def __enter__(self) -> Tunnel:
        return self.start()

    def __exit__(self, *args: object) -> bool:
        self.stop()
        return False