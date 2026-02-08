# What is bluray?

bluray is an in-terminal, interactive path chooser and directory changer. Unlike other tools (broot, ranger, xplr, etc), bluray is written specifically for xonsh and is directly part of the prompt - not a subprocess or command.

https://github.com/uninstall-your-browser/xontrib-bluray/raw/refs/heads/master/images/demo.mp4

## Install

```xonsh
# use xuv
xuv install git+https://github.com/uninstall-your-browser/xontrib-bluray.git
# use xpip
xpip install git+https://github.com/uninstall-your-browser/xontrib-bluray.git
```

## Usage

Bluray **requires** the `prompt-toolkit` backend to be in use. 

- Press `ctrl+y` to access the path picker. If your text cursor is ontop of an argument in your prompt, it will replace it with a new path.
- Press `ctrl+k` to access the directory changer.
- Press `.` to show/hide dotfiles.
- Press `/` to use the name filter

