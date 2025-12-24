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
# This path is relative to the HOME of the user on the remote machine
REMOTE_CONFIG_PATH = ".ssh_backchannel_config"

def ensure_keys():
    """Generates ED25519 keys if they don't exist."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, mode=0o700)
    if not PRIVATE_KEY.exists():
        print(f"Generating new identity: {PRIVATE_KEY}")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(PRIVATE_KEY), "-N", ""], check=True)
    return PUBLIC_KEY, PRIVATE_KEY

def configure():
    """Sets up the local authorized_keys to allow restricted callback commands."""
    pub_path, _ = ensure_keys()
    auth_path = Path.home() / ".ssh" / "authorized_keys"
    
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()
    
    # Locate where this script is installed to use in the command= restriction
    script_exe = shutil.which("ssh-backchannel") or f"{Path.home()}/.local/bin/ssh-backchannel"
    
    # The entry limits the key to ONLY running this script with the 'connect' argument
    entry = f'command="{script_exe} connect",no-pty,no-port-forwarding {pub_key} {TAG}\n'
    
    lines = []
    if auth_path.exists():
        with open(auth_path, "r") as f:
            lines = f.readlines()
            
    # Clean out old entries with our tag
    new_lines = [l for l in lines if TAG not in l and l.strip()]
    new_lines.append(entry)
    
    auth_path.parent.mkdir(mode=0o700, exist_ok=True)
    with open(auth_path, "w") as f:
        f.writelines(new_lines)
    auth_path.chmod(0o600)
    print(f"Local access configured in {auth_path}")

def setup_remote(remote_target):
    """Pushes the private key and config to a remote server, ensuring directories exist."""
    pub_path, _ = ensure_keys()
    local_host = socket.gethostname()
    local_user = os.getlogin()
    
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()
    
    mapping_line = f"{local_host}:{local_user}\n"
    
    print(f"Provisioning {remote_target}...")
    try:
        # Step 1: Ensure the remote environment is ready for the config file
        # This handles cases where the home directory might be non-standard
        subprocess.run(["ssh", remote_target, "touch .ssh_backchannel_config && chmod 600 .ssh_backchannel_config"], check=True)
        
        # Step 2: Append the mapping
        subprocess.run(["ssh", remote_target, f"cat >> {REMOTE_CONFIG_PATH}"], 
                       input=mapping_line, text=True, check=True)
        
        # Step 3: Setup .ssh directory and copy the backchannel identity
        subprocess.run(["ssh", remote_target, "mkdir -p ~/.ssh && chmod 700 ~/.ssh"], check=True)
        subprocess.run(["scp", str(PRIVATE_KEY), f"{remote_target}:~/.ssh/id_backchannel"], check=True)
        subprocess.run(["ssh", remote_target, "chmod 600 ~/.ssh/id_backchannel"], check=True)
        
        print(f"Success! {remote_target} is now ready for backchannel commands.")
    except subprocess.CalledProcessError as e:
        print(f"\nError: Could not provision remote. This usually means the path is read-only or SSH failed.")
        print(f"Technical details: {e}")
        sys.exit(1)

def run_callback(command_str):
    """Triggered from the remote to execute a command on the local machine."""
    ssh_client = os.environ.get("SSH_CLIENT")
    if not ssh_client:
        sys.exit("Error: No SSH_CLIENT detected. Are you running this inside an SSH session?")
    
    # Extract the IP of the local machine from the environment
    current_ip = ssh_client.split()[0]
    target_user = None
    
    # Try to find the correct local username for this host
    remote_conf = Path.home() / REMOTE_CONFIG_PATH
    if remote_conf.exists():
        with open(remote_conf, "r") as f:
            for line in f:
                if ":" in line:
                    _, user = line.strip().split(":", 1)
                    target_user = user
                    
    if not target_user:
        target_user = os.getlogin()
        
    private_key = Path.home() / ".ssh" / "id_backchannel"
    
    # Call back to the local machine
    ssh_cmd = [
        "ssh", "-i", str(private_key), 
        "-o", "StrictHostKeyChecking=no", 
        f"{target_user}@{current_ip}", 
        command_str
    ]
    subprocess.run(ssh_cmd)

def handle_connect():
    """The entry point for incoming backchannel connections (restricted by authorized_keys)."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "echo 'No command provided.'")
    
    # Prompt for permission if Zenity is installed
    if shutil.which("zenity"):
        res = subprocess.run([
            "zenity", "--question", "--title=SSH Backchannel", 
            f"--text=A remote server wants to run:\n\n{payload}", "--width=400"
        ])
        if res.returncode != 0:
            print("Access denied.")
            return
            
    # Execute the command locally
    subprocess.run(payload, shell=True)

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel: Command callbacks over SSH.")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("configure", help="Setup local authorized_keys for callbacks")
    
    sr = subparsers.add_parser("setup-remote", help="Provision a remote server to allow callbacks")
    sr.add_argument("remote", help="Remote target (e.g., user@router.local)")
    
    run = subparsers.add_parser("run", help="Initiate a command callback to your local machine")
    run.add_argument("cmd_str", help="The shell command to run locally")
    
    subparsers.add_parser("connect", help="Internal use: handle incoming backchannel requests")
    
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