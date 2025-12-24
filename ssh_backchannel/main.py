import os
import sys
import subprocess
import argparse

def configure(public_key_path):
    """
    Adds the forced-command authorized_keys entry.
    Removes any existing entries marked with our backchannel tag.
    """
    auth_path = os.path.expanduser("~/.ssh/authorized_keys")
    
    if not os.path.exists(public_key_path):
        print(f"Error: Public key not found at {public_key_path}")
        return

    with open(public_key_path, "r") as f:
        pub_key = f.read().strip()

    # The tag we use to identify our specific key in the file
    tag = "# backchannel-key"
    
    # Construct the forced-command line
    # We use the full path to ensure it works regardless of the user's current PATH
    script_path = os.path.expanduser("~/.local/bin/ssh-backchannel")
    entry = f'command="{script_path} connect",no-pty,no-port-forwarding {pub_key} {tag}\n'

    lines = []
    if os.path.exists(auth_path):
        with open(auth_path, "r") as f:
            lines = f.readlines()

    # Effective Intervention: Remove any line containing our tag to prevent duplicates
    new_lines = [line for line in lines if tag not in line and line.strip()]
    new_lines.append(entry)

    # Ensure .ssh directory exists with correct permissions
    os.makedirs(os.path.dirname(auth_path), mode=0o700, exist_ok=True)

    with open(auth_path, "w") as f:
        f.writelines(new_lines)
    
    os.chmod(auth_path, 0o600)
    print(f"Configuration successful. Authorized keys updated at {auth_path}")

def handle_connect():
    payload = os.environ.get("SSH_ORIGINAL_COMMAND")
    if payload:
        subprocess.run(["notify-send", "SSH Backchannel", f"Action: {payload}"])

def main():
    parser = argparse.ArgumentParser(description="SSH Backchannel Tool")
    subparsers = parser.add_subparsers(dest="command")

    # The configure command
    conf_parser = subparsers.add_parser("configure")
    conf_parser.add_argument("pubkey", help="Path to the public key to authorize")

    # The connect command (for SSH)
    subparsers.add_parser("connect")

    args = parser.parse_args()

    if args.command == "configure":
        configure(args.pubkey)
    elif args.command == "connect":
        handle_connect()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()