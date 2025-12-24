# ssh-backchannel

WARNING. This is vibe coded. Review before use.

Sometimes I want to do things on my local machine from a remotes machine I am ssh'd into. ssh-backchannel provides a means to do so - in a moderately secure way. It allows you to run a local command from a remote machine, while asking for confirmation from your local machine.

## Architecture
A limited ssh key is created and passed to other machines when you log in. This key can only run a command which asks you for permission before running commands.

## Alternatives and prior work
If you are happy with it you could use ssh auth forwarding and just ssh into your machine. This adds a little more security since you must approve each command.

If you just want to write to your clipboard there are tools which use OSC escape codes to send data via your terminal. The only downside is that you need to set up terminal to handle deal with this. I do not like debugging this sort of stuff.

## Caveat
This only works if your host can be reached from the remote machine and may involve openning your machine ot the internet or using a VPN / being on the same subnet.

Alternatively, you could use reverse proxying in your ssh config.






