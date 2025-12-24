import os
import sys
import subprocess
import argparse
import socket
import shutil
from pathlib import Path

# Configuration Constants
CONFIG_DIR = Path.home() / ".config" / "ssh-backchannel"
PRIVATE_KEY = CONFIG_DIR / "id_ed25519"
PUBLIC_KEY = CONFIG_DIR / "id_ed25519.pub"
TAG = "# backchannel-key"
REMOTE_CONFIG_PATH = Path.home() / ".ssh_backchannel_config"

def ensure_keys():
    """Generates ED25519 keys if they don't exist."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, mode=0o700)
    if not PRIVATE_KEY.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(PRIVATE_KEY), "-N", ""], check=True)
    return PUBLIC_KEY, PRIVATE_KEY

def configure():
    """Sets up the local authorized_keys to allow restricted callback commands."""
    pub_path, _ = ensure_keys()
    auth_path = Path.home() / ".ssh" / "authorized_keys"
    
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()
    
    # Locate where this script is installed
    script_exe = shutil.which("ssh-backchannel") or f"{Path.home()}/.local/bin/ssh-backchannel"
    
    # Create the restricted command entry
    entry = f'command="{script_exe} connect",no-pty,no-port-forwarding {pub_key} {TAG}\n'
    
    lines = []
    if auth_path.exists():
        with open(auth_path, "r") as f:
            lines = f.readlines()
            
    # Remove existing backchannel entries to avoid duplicates
    new_lines = [l for l in lines if TAG not in l and l.strip()]
    new_lines.append(entry)
    
    auth_path.parent.mkdir(mode=0o700, exist_ok=True)
    with open(auth_path, "w") as f:
        f.writelines(new_lines)
    auth_path.chmod(0o600)
    print(f"Configured {auth_path} with restricted command access.")

def setup_remote(remote_target):
    """Pushes the private key and config to a remote server."""
    pub_path, _ = ensure_keys()
    local_host = socket.gethostname()
    local_user = os.getlogin()
    
    mapping_line = f"{local_host}:{local_user}\n"
    
    try:
        # Append host mapping to the remote config
        subprocess.run(["ssh", remote_target, f"cat >> {REMOTE_CONFIG_PATH}"], 
                       input=mapping_line, text=True, check=True)
        # Ensure .ssh exists on remote
        subprocess.run(["ssh", remote_target, "mkdir -p ~/.ssh && chmod 700 ~/.ssh"], check=True)
        # Copy the private key to the remote so it can "call back"
        subprocess.run(["scp", str(PRIVATE_KEY), f"{remote_target}:~/.ssh/id_backchannel"], check=True)
        subprocess.run(["ssh", remote_target, "chmod 600 ~/.ssh/id_backchannel"], check=True)
        print(f"Remote {remote_target} successfully provisioned.")
    except subprocess.CalledProcessError as e:
        print(f"Error during remote setup: {e}")
        sys.exit(1)

def run_callback(command_str):
    """Triggered from the remote to execute a command on the local machine."""
    ssh_client = os.environ.get("SSH_CLIENT")
    if not ssh_client:
        sys.exit("Error: SSH_CLIENT environment variable missing (not an SSH session).")
    
    current_ip = ssh_client.split()[0]
    target_user = None
    
    if REMOTE_CONFIG_PATH.exists():
        with open(REMOTE_CONFIG_PATH, "r") as f:
            for line in f:
                if ":" in line:
                    _, user = line.strip().split(":", 1)
                    target_user = user
                    
    if not target_user:
        target_user = os.getlogin()
        
    private_key = Path.home() / ".ssh" / "id_backchannel"
    
    # Execute the SSH command back to the original IP
    ssh_cmd = [
        "ssh", "-i", str(private_key), 
        "-o", "StrictHostKeyChecking=no", 
        f"{target_user}@{current_ip}", 
        command_str
    ]
    subprocess.run(ssh_cmd)

def handle_connect():
    """The entry point for restricted SSH connections."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "Ping")
    
    # If running in a GUI environment, ask for permission
    if shutil.which("zenity"):
        res = subprocess.run([
            "zenity", "--question", "--title=Backchannel", 
            f"--text=A remote server wants to run: {payload}?", "--width=400"
        ])
        if res.returncode != 0:
            print("Action denied by user.")
            return
            
    subprocess.run(payload, shell=True)

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel Utility")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("configure", help="Setup local authorized_keys")
    
    sr = subparsers.add_parser("setup-remote", help="Provision a remote server")
    sr.add_argument("remote", help="user@hostname")
    
    run = subparsers.add_parser("run", help="Run a command back on the local host")
    run.add_argument("cmd_str", help="The command to execute")
    
    subparsers.add_parser("connect", help="Internal use: handles incoming backchannel requests")
    
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