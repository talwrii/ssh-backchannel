import os
import sys
import subprocess
import argparse
import socket
import shutil
from pathlib import Path

# Constants
CONFIG_DIR = Path.home() / ".config" / "ssh-backchannel"
PRIVATE_KEY = CONFIG_DIR / "id_ed25519"
PUBLIC_KEY = CONFIG_DIR / "id_ed25519.pub"
TAG = "# backchannel-key"
REMOTE_CONFIG_PATH = "~/.ssh_backchannel_config"

def get_local_target():
    """Prioritizes the .local hostname for mDNS stability on local networks."""
    hostname = socket.gethostname()
    local_hostname = hostname if hostname.endswith(".local") else f"{hostname}.local"
    
    # Verify if .local is resolvable
    try:
        socket.gethostbyname(local_hostname)
        return local_hostname
    except socket.gaierror:
        # Fallback to IP if mDNS is not present
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

def ensure_keys():
    """Generates a chronic keypair if not already present."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, mode=0o700)
    
    if not PRIVATE_KEY.exists():
        print(f"Generating persistent keys in {CONFIG_DIR}...")
        subprocess.run([
            "ssh-keygen", "-t", "ed25519", 
            "-f", str(PRIVATE_KEY), "-N", ""
        ], check=True)
    return PUBLIC_KEY, PRIVATE_KEY

def configure():
    """Updates authorized_keys on the local machine to allow the backchannel."""
    pub_path, _ = ensure_keys()
    auth_path = Path.home() / ".ssh" / "authorized_keys"
    
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()

    # Find where this script is installed
    script_exe = shutil.which("ssh-backchannel")
    if not script_exe:
        script_exe = f"{Path.home()}/.local/bin/ssh-backchannel"

    entry = f'command="{script_exe} connect",no-pty,no-port-forwarding {pub_key} {TAG}\n'

    lines = []
    if auth_path.exists():
        with open(auth_path, "r") as f:
            lines = f.readlines()

    # Remove existing entries to prevent chronic duplication
    new_lines = [l for l in lines if TAG not in l and l.strip()]
    new_lines.append(entry)

    auth_path.parent.mkdir(mode=0o700, exist_ok=True)
    with open(auth_path, "w") as f:
        f.writelines(new_lines)
    
    auth_path.chmod(0o600)
    print(f"Success: Local gatekeeper configured in {auth_path}")

def setup_remote(remote_target):
    """Provisions the remote machine with callback details."""
    pub_path, _ = ensure_keys()
    local_addr = get_local_target()
    local_user = os.getlogin()

    with open(pub_path, "r") as f:
        pub_key = f.read().strip()

    config_content = (
        f"BACKCHANNEL_PUBKEY='{pub_key}'\n"
        f"BACKCHANNEL_TARGET='{local_addr}'\n"
        f"BACKCHANNEL_USER='{local_user}'\n"
    )

    print(f"Provisioning {remote_target} for callback to {local_user}@{local_addr}...")
    
    cmd = ["ssh", remote_target, f"cat > {REMOTE_CONFIG_PATH}"]
    try:
        subprocess.run(cmd, input=config_content, text=True, check=True)
        print(f"Success: Remote configured at {REMOTE_CONFIG_PATH}")
    except subprocess.CalledProcessError as e:
        print(f"Error: Could not configure remote machine: {e}", file=sys.stderr)
        sys.exit(1)

def handle_connect():
    """Forced command entry point triggered by SSH."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "Ping received")
    
    # Notify the local user on their tablet/desktop
    subprocess.run([
        "notify-send", 
        "SSH Backchannel", 
        f"Remote Action: {payload}",
        "--icon=utilities-terminal"
    ])
    
    # Chronic log for auditing
    log_file = Path.home() / "backchannel.log"
    with open(log_file, "a") as f:
        f.write(f"{payload}\n")

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel Management Tool")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("configure", help="Setup local machine to receive callbacks")
    
    sr_parser = subparsers.add_parser("setup-remote", help="Provision a remote machine")
    sr_parser.add_argument("remote", help="user@remote-host")
    
    subparsers.add_parser("connect", help="Internal SSH forced-command hook")

    args = parser.parse_args()

    if args.command == "configure":
        configure()
    elif args.command == "setup-remote":
        setup_remote(args.remote)
    elif args.command == "connect":
        handle_connect()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()