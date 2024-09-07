# Control for livestream

This provides two control services for OBS:
* A control panel that allows switching scenes, muting/unmuting audio,
  and so on.
* A live preview.

These are local applications running in Python Tkinter, so should work
on any operating system (if not, that's a bug).



## Installation

### zipapp

This doesn't work anymore since there are compiled modules needed to
play sound.


### Local install

Create a virtual environment.  Note that obsws-python unfortunately
requires Python 3.9+.  On Linux with pip, sound output requires a
compiler, libasound2-dev, and python3-dev (on other platforms, a
pre-built package has what you need).

```
$ pip install https://github.com/coderefinery/obs-cr/archive/master.zip
```



## Usage

If you are just using this: The broadcaster should give you the
respective commands to run and you don't need to worry.

There is `control.py` to make a control panel, and `preview.py` to
give a preview.

```
obs-cr-control HOSTNAME:PORT PASSWORD
obs-cr-preview HOSTNAME:PORT PASSWORD [--delay S]
```

* `obs-cr-control --small` starts a small panel, designed for the most
  critical indicators and buttons on a crowded teacher's screen.  It
  doesn't replace or have everything of the full panel (you need the
  full panel open somewhere else, or a separate director).
* `obs-cr-control --test` will run without connecting to OBS.  Not
  everything works and there might be visible tracebacks,  but you can
  test the general things out.


### obs-cr-control

This is a streaming control panel.  There are tooltips that explain
most things, but just open it up and see.

This is synced with OBS (it uses OBS as the synchronization server
itself, which is cool).  Anything RED indicates something may be
live.  "Indicators" are synced lights: click a light on any control
panel, and it's synced across all of them.

* `--small` shows a smaller window, suitable for instructors who don't
  want to do a lot of control.
* `--broadcaster` enables extra options that only make sense on the
  broadcaster's computer (like sharing the broadcaster's screen)
* `--resolution-command` is a command that resizes the Zoom
  screenshare window.  `WIDTH` and `HEIGHT` get replaced by the
  desired window size.
* `--notes-window` is a regex which matches a window title.  This is
  taken to be the "notes window" and enables the buttons that scroll
  the notes up/down.  Linux only for now.

### obs-cr-preview

This shows a live preview with less latency than the stream shows.
Use `--delay S` to set the delay to S seconds, the default is 1 which
might be a bit too slow.  This is an relatively space-inefficient
screenshot, so try not to make it too close to realtime.  0.2 is
probably fine, even 0.1.


## Cheatsheet

Commands for copying and pasting

* Linux, Firefox: `obs-cr-control localhost:4445 TOKEN --notes-window='^TTT4HPC 07/05/2024.*Privat()e' --resolution-command="xdotool search --onlyvisible --name '^Zoom$' windowsize WIDTH HEIGHT;" --broadcaster`


## Status

In development, not recommended for general use unless you want to go
into the code.
