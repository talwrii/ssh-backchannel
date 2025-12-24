#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import socket
import shutil
import shlex
from pathlib import Path

# Configuration
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
    
    # Use the new entrypoint without arguments to avoid shell invocation
    connect_exe = shutil.which("ssh-backchannel-connect")
    if not connect_exe:
        # Fallback: assume it's in the same directory as this script
        script_dir = Path(sys.argv[0]).parent
        connect_exe = script_dir / "ssh-backchannel-connect"
        if not connect_exe.exists():
            print("[-] Error: ssh-backchannel-connect not found. Make sure it's installed or in PATH.")
            sys.exit(1)
    
    entry = f'command="{connect_exe}",no-pty,no-port-forwarding,restrict {pub_key} {TAG}\n'
    
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
    
    print(f"[*] Local access configured. Entry point: {connect_exe}")

def setup_remote(remote_target):
    pub_path, _ = ensure_keys()
    local_host = socket.gethostname()
    local_user = os.getlogin()
    
    with open(pub_path, "r") as f:
        pub_key = f.read().strip()
    
    mapping_line = f"{local_host}:{local_user}\n"
    
    try:
        subprocess.run(["ssh", remote_target, f"touch {REMOTE_CONFIG_PATH} && chmod 600 {REMOTE_CONFIG_PATH}"], check=True)
        subprocess.run(["ssh", remote_target, f"cat >> {REMOTE_CONFIG_PATH}"], input=mapping_line, text=True, check=True)
        subprocess.run(["ssh", remote_target, "mkdir -p ~/.ssh && chmod 700 ~/.ssh"], check=True)
        subprocess.run(["scp", str(PRIVATE_KEY), f"{remote_target}:~/.ssh/id_backchannel"], check=True)
        subprocess.run(["ssh", remote_target, "chmod 600 ~/.ssh/id_backchannel"], check=True)
        print(f"[+] Success! {remote_target} is provisioned.")
    except subprocess.CalledProcessError as e:
        print(f"[-] Error: {e}")
        sys.exit(1)

def run_callback(command_str):
    ssh_client = os.environ.get("SSH_CLIENT")
    if not ssh_client:
        sys.exit("[-] Error: No SSH_CLIENT detected. Run this from an SSH session.")
    
    current_ip = ssh_client.split()[0]
    
    target_user = None
    remote_conf = Path.home() / REMOTE_CONFIG_PATH
    if remote_conf.exists():
        with open(remote_conf, "r") as f:
            for line in f:
                if ":" in line:
                    _, user = line.strip().split(":", 1)
                    target_user = user
    
    target_user = target_user or os.getlogin()
    private_key = Path.home() / ".ssh" / "id_backchannel"
    
    ssh_cmd = ["ssh", "-i", str(private_key), "-o", "StrictHostKeyChecking=no", f"{target_user}@{current_ip}", command_str]
    
    # Pipes the local stdin into the SSH command
    if not sys.stdin.isatty():
        subprocess.run(ssh_cmd, stdin=sys.stdin)
    else:
        subprocess.run(ssh_cmd)

def handle_connect():
    """Handles incoming callback, managing STDIN and EOF for the workstation process."""
    payload = os.environ.get("SSH_ORIGINAL_COMMAND", "echo 'No command received'")
    uid = os.getuid()
    
    # X11 Bridging Setup
    os.environ.setdefault("DISPLAY", ":0")
    if "XAUTHORITY" not in os.environ:
        xauth = Path.home() / ".Xauthority"
        if xauth.exists():
            os.environ["XAUTHORITY"] = str(xauth)
        else:
            try:
                matches = list(Path(f"/run/user/{uid}/").glob("gdm/Xauthority"))
                if matches: os.environ["XAUTHORITY"] = str(matches[0])
            except: pass
    
    # Use Zenity for GUI confirmation
    if shutil.which("zenity"):
        res = subprocess.run([
            "zenity", "--question", "--title=SSH Backchannel", 
            f"--text=A remote server wants to run:\n\n$ {payload}", 
            "--timeout=30", "--width=450"
        ])
        
        if res.returncode == 0:
            # Popen allows us to explicitly manage stdin to ensure tools like xclip get an EOF
            proc = subprocess.Popen(payload, shell=True, stdin=subprocess.PIPE)
            try:
                if not sys.stdin.isatty():
                    # Stream data from the SSH tunnel into the local process stdin
                    shutil.copyfileobj(sys.stdin.buffer, proc.stdin)
                
                # Crucial: Close stdin to signal EOF so the process can finish
                proc.stdin.close() 
                proc.wait()
            except Exception as e:
                print(f"[*] Command Error: {e}")
                proc.kill()
        else:
            print("[*] Action denied by user.")
    else:
        print("[!] Error: Zenity not found. Closing.")

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel Utility")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("configure")
    
    sr = subparsers.add_parser("setup-remote")
    sr.add_argument("remote")
    
    run = subparsers.add_parser("run")
    run.add_argument("cmd_words", nargs="+")
    
    subparsers.add_parser("connect")
    
    args = parser.parse_args()
    
    if args.command == "configure":
        configure()
    elif args.command == "setup-remote":
        setup_remote(args.remote)
    elif args.command == "run":
        # shlex.join ensures the command is properly escaped for the shell
        run_callback(shlex.join(args.cmd_words))
    elif args.command == "connect":
        handle_connect()

if __name__ == "__main__":
    main()