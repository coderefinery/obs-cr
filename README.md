# Control panel for CodeRefinery livestream teaching

This provides control panels for OBS, optimized for automation useful
for the CodeRefinery teaching style.  Since 2025, this is all done by
the web and there is no local installation.  The main entry point is
`web/index.html`.

The usage of these is taught as part of CodeRefinery instructor
training, unfortunately there aren't good examples here.

The general architecture is that it uses OBS as the main
synchorization server.  There are three main operations: get
persistent value, set persistent value, and watch for changes of
persistent value (with a callback).  Together, this allows us to build
almost anything.  (Some values are managed the same way but the
backend but control other controls, such as scene selection or
volume).

## OLD - Local app installation


### Local install

Create a virtual environment.  Note that obsws-python unfortunately
requires Python 3.9+.  On Linux with pip, sound output requires a
compiler, libasound2-dev, and python3-dev (on other platforms, a
pre-built package has what you need).

```
$ pip install https://github.com/coderefinery/obs-cr/archive/master.zip
```



## Cheatsheet

Commands for copying and pasting

* `python obs_cr/headless.py localhost:4445 PASSWORD --no-sound --resolution-command=zoomw -v --broadcaster --notes-window='Notes - CodeRefinery.*March 2025.*Privat()e'`

* `python3 obs_cr/websocket_proxy.py --ssl-domain=DOMAIN` - finds
  certs made by acme.sh in `~/.acme.sh/`.

* Linux, Firefox: `obs-cr-control localhost:4445 TOKEN --notes-window='^TTT4HPC 07/05/2024.*Privat()e' --resolution-command="xdotool search --onlyvisible --name '^Zoom$' windowsize WIDTH HEIGHT;" --broadcaster`


## Status

In development, not recommended for general use unless you want to go
into the code.
