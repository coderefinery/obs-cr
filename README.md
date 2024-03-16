# Control for livestream

This provides two control services for OBS:
* A control panel that allows switching scenes, muting/unmuting audio,
  and so on.
* A live preview.

These are local applications running in Python Tkinter, so should work
on any operating system (if not, that's a bug).



## Installation

Install the requirements.txt dependencies in a virtual environment (or
similar).  The package isn't currently installable.  Note that
obsws-python unfortunately requires Python 3.9+.



## Usage

If you are just using this: The broadcaster should give you the
respective commands to run and you don't need to worry.

There is `control.py` to make a control panel, and `preview.py` to
give a preview.

```
python3 control.py HOSTNAME:PORT PASSWORD
python3 preview.py HOSTNAME:PORT PASSWORD [--delay S]
```

* `control.py --small` starts a small panel, designed for the most
  critical indicators and buttons on a crowded teacher's screen.  It
  doesn't replace or have everything of the full panel (you need the
  full panel open somewhere else, or a separate director).
* `control.py --test` will run without connecting to OBS.  Not
  everything works and there might be visible tracebacks,  but you can
  test the general things out.


### control.py

This is a streaming control panel.  There are tooltips that explain
most things, but just open it up and see.

This is synced with OBS (it uses OBS as the synchronization server
itself, which is cool).  Anything RED indicates something may be
live.  "Indicators" are synced lights: click a light on any control
panel, and it's synced across all of them.


### preview.py

This shows a live preview with less latency than the stream shows.
Use `--delay S` to set the delay to S seconds, the default is 1 which
might be a bit too slow.  This is an relatively space-inefficient
screenshot, so try not to make it too close to realtime.  0.2 is
probably fine, even 0.1.



## Status

In development, not recommended for general use unless you want to go
into the code.
