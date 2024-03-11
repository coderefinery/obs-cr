# Control for livestream

This provides two control services for OBS:
* A control panel that allows switching scenes, muting/unmuting audio,
  and so on.
* A live preview.

These are local applications running in Python Tkinter, so should work
on any operating system.

## Installation

Install the requirements.txt dependencies in a virtual environment (or
similar).

## Usage:

The broadcaster should give you the respective commands to run.

```
python3 control.py HOSTNAME:PORT PASSWORD
python3 preview.py HOSTNAME:PORT PASSWORD [--delay S]
```
