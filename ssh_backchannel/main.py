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
REMOTE_CONFIG_PATH = Path.home() / ".ssh_backchannel_config"

def get_local_target():
    """Prioritizes the .local hostname for mDNS stability on local networks."""
    hostname = socket.gethostname()
    local_hostname = hostname if hostname.endswith(".local") else f"{hostname}.local"
    try:
        socket.gethostbyname(local_hostname)
        return local_hostname
    except socket.gaierror:
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

    script_exe = shutil.which("ssh-backchannel") or f"{Path.home()}/.local/bin/ssh-backchannel"
    entry = f'command="{script_exe} connect",no-pty,no-port-forwarding {pub_key} {TAG}\n'
    
    lines = []
    if auth_path.exists():
        with open(auth_path, "r") as f:
            lines = f.readlines()

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
    
    print(f"Provisioning {remote_target}...")
    cmd = ["ssh", remote_target, f"cat > {REMOTE_CONFIG_PATH}"]
    try:
        subprocess.run(cmd, input=config_content, text=True, check=True)
        # Copy private key to remote so 'run' can use it
        subprocess.run(["scp", str(PRIVATE_KEY), f"{remote_target}:.ssh/id_backchannel"], check=True)
        print(f"Success: Remote configured.")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def run_callback(command_str):
    """Uses SSH environment variables to call back to the local machine."""
    ssh_client = os.environ.get("SSH_CLIENT")
    if not ssh_client:
        print("Error: SSH_CLIENT not found.", file=sys.stderr)
        sys.exit(1)

    local_ip = ssh_client.split()[0]
    local_user = os.getlogin()
    if REMOTE_CONFIG_PATH.exists():
        with open(REMOTE_CONFIG_PATH, "r") as f:
            for line in f:
                if "BACKCHANNEL_USER=" in line:
                    local_user = line.split("=")[1].strip("'\"\n ")

    print(f"Calling back to {local_user}@{local_ip}...")
    private_key = Path.home() / ".ssh" / "id_backchannel"
    ssh_cmd = [
        "ssh", "-i", str(private_key),
        "-o", "StrictHostKeyChecking=no",
        f"{local_user}@{local_ip}",
        command_str
    ]
    subprocess.run(ssh_cmd)

def handle_connect():
    """Forced command entry point with GUI approval."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "Ping received")
    zenity = shutil.which("zenity")
    
    if zenity:
        res = subprocess.run([
            "zenity", "--question", 
            "--title=SSH Backchannel",
            f"--text=Allow remote command?\n\n{payload}",
            "--width=400"
        ])
        if res.returncode != 0:
            return
    else:
        print("No GUI tool found. Aborting.")
        return

    subprocess.run(payload, shell=True)

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("configure")
    
    sr_parser = subparsers.add_parser("setup-remote")
    sr_parser.add_argument("remote")
    
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("cmd_str")
    
    subparsers.add_parser("connect")
    
    args = parser.parse_args()
    if args.command == "configure":
        configure()
    elif args.command == "setup-remote":
        setup_remote(args.remote)
    elif args.command == "run":
        run_callback(args.cmd_str)
    elif args.command == "connect":
        handle_connect()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()