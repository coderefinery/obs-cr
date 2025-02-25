import argparse
from functools import partial
import logging
import os
import pathlib
import subprocess
import sys
import time

import obsws_python
import yaml


from obsdict import ObsState

CONFIG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), 'config.yaml')))

LOG = logging.getLogger(__name__)


def main():
    # pylint: disable=unused-variable
    global cli_args

    parser = argparse.ArgumentParser()
    parser.add_argument('hostname_port',
                        help="HOSTNAME:PORT of the OBS to connect to")
    parser.add_argument('password', default=os.environ.get('OBS_PASSWORD'),
                      help='Websocket password, or pass "-" and set env var OBS_PASSWORD')
    parser.add_argument('--notes-window',
                        help="window name regex for notes document (for scrolling), get via xwininfo -tree -root | less.  Example: '^Collaborative document.*Privat()e' (the parentheses prevent the regex from matching itself in the process listing)")
    parser.add_argument('--small', action='store_true',
                        help="Start a smaller, more limited, control panel for instructors.")
    parser.add_argument('--test', action='store_true', help="Don't connect to OBS, just show the panel in a test mode.  Some things may not work.")
    parser.add_argument('--no-sound', action='store_true', help="Don't play the sound effects that come with certain actions.")
    parser.add_argument('--resolution-command',
                        help="Command to run when setting resolution.  WIDTH and HEIGHT will be replaced with integers.  Example: \"xdotool search --onlyvisible --name '^Zoom$' windowsize WIDTH HEIGHT;\" (mind the nested quotes)")
    parser.add_argument('--no-gallery-poll', action='store_true', help="Don't poll for gallery size (for less verbosity when testing)")
    parser.add_argument('--broadcaster', action='store_true', help="This is running on broadcaster's computer.  Enable extra broadcaster functionality like unmuting and controlling Zoom.")
    parser.add_argument('--verbose', '-v', action='count', default=0)
    args = cli_args = parser.parse_args()
    if args.verbose >= 3:
        logging.basicConfig(level=9)
    elif args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger('obsws_python').setLevel(logging.INFO)
    elif args.verbose >= 1:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('obsws_python').setLevel(logging.INFO)
    LOG.debug("Arguments: %s", cli_args)


    # OBS websocket
    global obs
    if not cli_args.test:
        hostname = cli_args.hostname_port.split(':')[0]
        port = cli_args.hostname_port.split(':')[1]
        password = cli_args.password

        import obsws_python
        obsreq = obsws_python.ReqClient(host=hostname, port=port, password=password, timeout=3)
        cl = obsws_python.EventClient(host=hostname, port=port, password=password, timeout=3)
        obssubscribe = cl.callback.register
    else:
        class Request():
            def __call(self, _method, *args, **kwargs):
                print(f'[test] OBS request: {_method}({args}, {kwargs})')
            def __getattr__(self, name):
                return partial(self.__call, name)
        obsreq = Request()
        obssubscribe = getattr(obsreq, 'callback.register')
        cl = type('null', (), {'callback':type('null', (), {'register': lambda *args, **kwargs: None})})

    obs = ObsState(obsreq, cl, config=CONFIG, test=args.test)


    # Other watchers (not displayed on the control panel)
    if cli_args.notes_window:
        obs._watch('notes_scroll', notes_scroll)
    obs._watch('playsound', play)

    if cli_args.broadcaster:
        obs._watch('ss_resolution', change_resolution)
        obs._watch('mainwindow_resolution', change_resolution)

    print('connected, waiting...')
    while True:
        time.sleep(3600)


def notes_scroll(value):
    """Scroll notes up/down"""
    # xdotool search --onlyvisible --name '^Collaborative document.*Private' windowfocus key Down windowfocus $(xdotool getwindowfocus)
    if not cli_args.broadcaster:
        return
    if not cli_args.notes_window:
        LOG.error(f"No notes_window defined for scrolling {value!r}")
        return
    cmd = ['xdotool', 'search', '--name', cli_args.notes_window,
           'windowfocus',
           'key', 'KEY',
           'windowfocus', subprocess.getoutput('xdotool getwindowfocus')
           ]
    if value in {'Up', 'Down', 'Prior', 'Next', 'End'}:
        cmd[cmd.index('KEY')] = value
        LOG.info('Scrolling notes: %r', value)
        print(f"Scrolling notes {value}")
        subprocess.call(cmd)



def set_resolution(w, h):
    """Do the actual resolution switching"""
    if not cli_args.broadcaster:
        return
    if not cli_args.resolution_command:
        LOG.error("No resolution command to set %d, %d", w, h)
        return
    cmd = cli_args.resolution_command
    w = int(w)
    h = int(h)
    if cmd in CONFIG['SS_RESOLUTION']:
        w += CONFIG['SS_RESOLUTION'][cmd]['border_pixels'][1]
        h += CONFIG['SS_RESOLUTION'][cmd]['border_pixels'][0]
        cmd = CONFIG['SS_RESOLUTION'][cmd]['command']
    # Are we in the "zoom top gallery" view?
    if obs['topgallery-mode']:
        w += CONFIG['SCREENSHARE_TOPGALLERY_BORDER']['left'] + CONFIG['SCREENSHARE_TOPGALLERY_BORDER']['right']
        h += CONFIG['SCREENSHARE_TOPGALLERY_BORDER']['top'] + CONFIG['SCREENSHARE_TOPGALLERY_BORDER']['bottom']

    if not  200 < w < 5000:
        raise ValueError(f"invalid width: {w!r}")
    if not 200 < h < 3000:
        raise ValueError(f"invalid height: {h!r}")
    cmd = cmd.replace('WIDTH', str(w)).replace('HEIGHT', str(h))
    print(f"Change resolution to {w}x{h}")
    print(cmd)
    subprocess.call(cmd, shell=True)

def change_resolution(resolution):
    """Watching function to wait for resolutoin switching signals"""
    if resolution == '-':
        LOG.info("Ignoring resolution change to null value '-'")
        return
    w, h = resolution.split('x')
    if w.isdigit and h.isdigit():
        w = int(w)
        h = int(h)
        set_resolution(w, h)
    else:
        LOG.warning("Invalid resolution: %s", resolution)

def change_resolution_mainwindow(_):
    """Watching function to wait for resolutoin switching signals"""
    cmd = cli_args.resolution_command
    subprocess.call(CONFIG['SS_RESOLUTION'][cmd]['command_resetmainwindow'])




import simpleaudio
SOUNDFILES = { name: simpleaudio.WaveObject.from_wave_file(str(pathlib.Path(__file__).parent/f'sound'/name))
          for name in CONFIG['SOUNDS'].values()
    }


def play(name):
    """Play sound.  There is an OBS listener to trigger this an the right times"""
    muted = cli_args.no_sound
    print(f"Play {name} {'(muted)' if muted else ''}")
    if 'SOUNDS' not in CONFIG is None:
        LOG.warning("Sounds are not loaded")
        return
    if name not in CONFIG['SOUNDS']:
        LOG.warning("Sound effect mapping %s not found", name)
        return
    soundfile = CONFIG['SOUNDS'][name]
    #snd = simpleaudio.WaveObject.from_wave_file(str(path))
    if not muted:
        SOUNDFILES[soundfile].play()



if __name__ == "__main__":
    main()

