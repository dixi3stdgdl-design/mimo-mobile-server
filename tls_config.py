"""
TLS configuration for secure WebSocket and HTTP connections.

Supports:
- Self-signed certificates (development)
- Let's Encrypt / ACME (production)
- Cloudflare origin certificates
"""

import os
import ssl
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class TLSConfig:
    """TLS configuration manager."""

    def __init__(self):
        self.enabled = os.environ.get("MIMO_TLS_ENABLED", "false").lower() == "true"
        self.cert_dir = Path(os.environ.get("MIMO_TLS_CERT_DIR", "./certs"))
        self.cert_file = self.cert_dir / "server.crt"
        self.key_file = self.cert_dir / "server.key"
        self.ca_file = self.cert_dir / "ca.crt"  # For mTLS

    def get_ssl_context(self, purpose: str = "server") -> Optional[ssl.SSLContext]:
        """
        Create SSL context for server or client.
        
        Args:
            purpose: "server" for WebSocket/HTTP server, "client" for outgoing connections
            
        Returns:
            SSLContext or None if TLS is disabled
        """
        if not self.enabled:
            return None

        if not self.cert_file.exists() or not self.key_file.exists():
            print(f"[TLS] Certificate files not found: {self.cert_file}, {self.key_file}", flush=True)
            print("[TLS] Generating self-signed certificate...", flush=True)
            self._generate_self_signed()

        if purpose == "server":
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(self.cert_file), str(self.key_file))
        else:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.load_verify_locations(str(self.cert_file))  # Trust self-signed

        # Security hardening
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS")
        ctx.check_hostname = False  # For self-signed
        ctx.verify_mode = ssl.CERT_NONE  # For self-signed; use CERT_REQUIRED in production

        return ctx

    def _generate_self_signed(self):
        """Generate self-signed certificate for development."""
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(self.key_file),
            "-out", str(self.cert_file),
            "-days", "365", "-nodes",
            "-subj", "/CN=localhost/O=MiMo Mobile/C=US"
        ], check=True, capture_output=True)
        
        print(f"[TLS] Self-signed certificate generated: {self.cert_file}", flush=True)

    def _generate_lets_encrypt(self, domain: str, email: str):
        """Generate Let's Encrypt certificate using certbot."""
        subprocess.run([
            "certbot", "certonly", "--standalone",
            "-d", domain,
            "--email", email,
            "--agree-tos",
            "--non-interactive"
        ], check=True)
        
        # Symlink to standard paths
        live_dir = Path(f"/etc/letsencrypt/live/{domain}")
        if live_dir.exists():
            self.cert_file = live_dir / "fullchain.pem"
            self.key_file = live_dir / "privkey.pem"

    def _generate_cloudflare_origin(self, domain: str, api_token: str):
        """
        Generate Cloudflare Origin Certificate.
        
        Requires:
        - Cloudflare API token with Zone:SSL permission
        - Domain managed by Cloudflare
        """
        import requests
        
        # This is a simplified version - in production use Cloudflare's API properly
        print(f"[TLS] Cloudflare Origin Certificate for {domain}", flush=True)
        print("[TLS] Please generate origin cert from Cloudflare Dashboard:", flush=True)
        print(f"[TLS] https://dash.cloudflare.com/ -> SSL/TLS -> Origin Server", flush=True)


class CloudflareTunnel:
    """Cloudflare Tunnel (cloudflared) configuration."""

    def __init__(self):
        self.enabled = os.environ.get("MIMO_CLOUDFLARE_TUNNEL", "false").lower() == "true"
        self.tunnel_token = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "")
        self.tunnel_name = os.environ.get("MIMO_TUNNEL_NAME", "mimo-mobile")
        self.external_host = os.environ.get("MIMO_EXTERNAL_HOST", "")

    def get_config(self) -> dict:
        """Generate cloudflared configuration."""
        return {
            "tunnel": self.tunnel_name,
            "credentials-file": os.path.expanduser("~/.cloudflared/credentials.json"),
            "ingress": [
                {
                    "hostname": self.external_host,
                    "service": "https://localhost:8765",
                    "originRequest": {
                        "noTLSVerify": False,
                        "connectTimeout": "30s"
                    }
                },
                {
                    "service": "http_status:404"
                }
            ]
        }

    def start_tunnel(self) -> subprocess.Popen:
        """Start cloudflared tunnel."""
        if not self.enabled or not self.tunnel_token:
            print("[TUNNEL] Cloudflare tunnel not configured", flush=True)
            return None

        import tempfile
        import json
        
        config = self.get_config()
        config_path = Path("/tmp/cloudflared_config.yml")
        
        # Write YAML config (simplified)
        with open(config_path, "w") as f:
            f.write(f"tunnel: {config['tunnel']}\n")
            f.write(f"credentials-file: {config['credentials-file']}\n")
            f.write("ingress:\n")
            for rule in config["ingress"][:-1]:
                f.write(f"  - hostname: {rule['hostname']}\n")
                f.write(f"    service: {rule['service']}\n")
            f.write(f"  - service: http_status:404\n")

        # Start cloudflared
        proc = subprocess.Popen([
            "cloudflared", "tunnel", "--config", str(config_path), "run"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"[TUNNEL] Cloudflare tunnel started: {self.tunnel_name}", flush=True)
        return proc


def setup_cloudflare_quick():
    """
    Quick setup script for Cloudflare Tunnel.
    
    Usage:
        MIMO_CLOUDFLARE_TUNNEL=true MIMO_EXTERNAL_HOST=your-domain.com python -c "from tls_config import setup_cloudflare_quick; setup_cloudflare_quick()"
    """
    print("=" * 60)
    print("Cloudflare Tunnel Quick Setup for MiMo Mobile")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("  1. Cloudflare account with domain")
    print("  2. cloudflared installed: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
    print()
    
    host = os.environ.get("MIMO_EXTERNAL_HOST", "")
    if not host:
        host = input("Enter your domain (e.g., mimo.yourdomain.com): ").strip()
    
    print(f"\nSetting up tunnel for: {host}")
    print()
    
    # Check if cloudflared is installed
    try:
        subprocess.run(["cloudflared", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("ERROR: cloudflared not installed!")
        print("Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        return
    
    # Create tunnel
    print("1. Creating tunnel...")
    tunnel_name = f"mimo-{host.replace('.', '-')}"
    
    # Check if tunnel exists
    result = subprocess.run(
        ["cloudflared", "tunnel", "list"],
        capture_output=True, text=True
    )
    
    if tunnel_name not in result.stdout:
        print(f"   Creating tunnel: {tunnel_name}")
        subprocess.run(["cloudflared", "tunnel", "create", tunnel_name], check=True)
    else:
        print(f"   Tunnel {tunnel_name} already exists")
    
    # Route DNS
    print("2. Routing DNS...")
    subprocess.run([
        "cloudflared", "tunnel", "route", "dns", tunnel_name, host
    ], check=False)  # May fail if already routed
    
    # Create config
    print("3. Creating config...")
    config_dir = Path.home() / ".cloudflared"
    config_dir.mkdir(exist_ok=True)
    
    config_path = config_dir / "config.yml"
    with open(config_path, "w") as f:
        f.write(f"tunnel: {tunnel_name}\n")
        f.write(f"credentials-file: {config_dir / 'credentials.json'}\n")
        f.write("ingress:\n")
        f.write(f"  - hostname: {host}\n")
        f.write(f"    service: https://localhost:8765\n")
        f.write(f"    originRequest:\n")
        f.write(f"      noTLSVerify: true\n")
        f.write(f"  - service: http_status:404\n")
    
    print(f"   Config written to: {config_path}")
    
    print()
    print("=" * 60)
    print("Setup complete!")
    print()
    print("To start the tunnel:")
    print(f"  cloudflared tunnel --config {config_path} run")
    print()
    print("To run MiMo Server with TLS:")
    print("  MIMO_TLS_ENABLED=true MIMO_EXTERNAL_HOST=" + host + " python server.py")
    print()
    print("Your external WebSocket URL:")
    print(f"  wss://{host}")
    print("=" * 60)


# Singleton
_tls_config = None

def get_tls_config() -> TLSConfig:
    global _tls_config
    if _tls_config is None:
        _tls_config = TLSConfig()
    return _tls_config
