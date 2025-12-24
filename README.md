# ssh-backchannel
WARNING. This is vibe coded. Review before use.

Sometimes I want to do things on my local machine from a remote machine I am ssh'd into. ssh-backchannel provides a means to do so - in a moderately secure way. It allows you to run a local command from a remote machine, while asking for confirmation from your local machine.

You must have ssh running on your machine and have an IP address addressable from another machine. This can work well if you are using a VPN or a local networing.

## Architecture
A limited ssh key is created and passed to other machines when you log in. This key can only run a command which asks you for permission before running commands. 

## Installation
You can install ssh-backchannel with pipx.

```
pipx install ssh-backchannel
```

The set up your machine and the remote machine run.

`ssh-backchannel configure`
`ssh-backchannel setup-remote user@server`

Also install backchannel on the remote macine.

## Usage
Once you have setup you macine and the remote machine you can run:

`ssh-backchannel run ls`

To run ls on your home machine.

## Alternatives and prior work
If you are happy with it you could use ssh auth forwarding and just ssh into your machine. This adds a little more security since you must approve each command.

If you just want to write to your clipboard there are tools which use OSC escape codes to send data via your terminal. The only downside is that you need to set up terminal to handle deal with this. I do not like debugging this sort of stuff.

## Caveat
This only works if your host can be reached from the remote machine and may involve openning your machine ot the internet or using a VPN / being on the same subnet. Reverse proxying would probably be the easiest fix.

It is assumed that there is only one user who consistently uses a machine.

This only with X11.

Alternatively, you could use reverse proxying in your ssh config.


