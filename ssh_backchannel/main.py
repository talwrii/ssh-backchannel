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
REMOTE_CONFIG_PATH = ".ssh_backchannel_config"

def ensure_keys():
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, mode=0o700)
    if not PRIVATE_KEY.exists():
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(PRIVATE_KEY), "-N", ""], check=True)
    return PUBLIC_KEY, PRIVATE_KEY

def configure():
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
    print(f"Local access configured in {auth_path}")

def setup_remote(remote_target):
    pub_path, _ = ensure_keys()
    local_host = socket.gethostname()
    local_user = os.getlogin()
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()
    mapping_line = f"{local_host}:{local_user}\n"
    try:
        subprocess.run(["ssh", remote_target, "touch .ssh_backchannel_config && chmod 600 .ssh_backchannel_config"], check=True)
        subprocess.run(["ssh", remote_target, f"cat >> {REMOTE_CONFIG_PATH}"], input=mapping_line, text=True, check=True)
        subprocess.run(["ssh", remote_target, "mkdir -p ~/.ssh && chmod 700 ~/.ssh"], check=True)
        subprocess.run(["scp", str(PRIVATE_KEY), f"{remote_target}:~/.ssh/id_backchannel"], check=True)
        subprocess.run(["ssh", remote_target, "chmod 600 ~/.ssh/id_backchannel"], check=True)
        print(f"Success! {remote_target} is provisioned.")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        sys.exit(1)

def run_callback(command_str):
    ssh_client = os.environ.get("SSH_CLIENT")
    if not ssh_client:
        sys.exit("Error: No SSH_CLIENT detected.")
    current_ip = ssh_client.split()[0]
    target_user = None
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
    ssh_cmd = ["ssh", "-i", str(private_key), "-o", "StrictHostKeyChecking=no", f"{target_user}@{current_ip}", command_str]
    subprocess.run(ssh_cmd)

def handle_connect():
    """Bridges the SSH session to the local X11 display session."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "echo 'No command received'")
    uid = os.getuid()

    # --- X11 Environment Bridging ---
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
    
    if "XAUTHORITY" not in os.environ:
        # Standard location for most desktop environments
        xauth = Path.home() / ".Xauthority"
        if xauth.exists():
            os.environ["XAUTHORITY"] = str(xauth)
        else:
            # Fallback for display managers like GDM that store auth in /run
            try:
                matches = list(Path(f"/run/user/{uid}/").glob("gdm/Xauthority"))
                if matches:
                    os.environ["XAUTHORITY"] = str(matches[0])
            except Exception:
                pass

    # Ensure DBUS is available for Zenity notification system
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
        dbus_path = Path(f"/run/user/{uid}/bus")
        if dbus_path.exists():
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={dbus_path}"

    if shutil.which("zenity"):
        try:
            # timeout ensures the SSH process doesn't hang forever if display is dead
            res = subprocess.run([
                "zenity", "--question", "--title=SSH Backchannel", 
                f"--text=A remote server wants to run:\n\n{payload}", 
                "--timeout=30", "--width=450"
            ], capture_output=True)
            
            if res.returncode == 0:
                subprocess.run(payload, shell=True)
            else:
                print("Action declined or timed out.")
        except Exception as e:
            print(f"X11 Display Error: {e}")
    else:
        print("Error: zenity not found. X11 callback failed.")

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("configure")
    sr = subparsers.add_parser("setup-remote")
    sr.add_argument("remote")
    run = subparsers.add_parser("run")
    run.add_argument("cmd_str")
    subparsers.add_parser("connect")
    args = parser.parse_args()
    if args.command == "configure": configure()
    elif args.command == "setup-remote": setup_remote(args.remote)
    elif args.command == "run": run_callback(args.cmd_str)
    elif args.command == "connect": handle_connect()

if __name__ == "__main__":
    main()