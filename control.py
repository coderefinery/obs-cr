import collections
from functools import partial
import inspect
import logging
import math
import random
import subprocess
import time

from tkinter import *
from tkinter import ttk
from tktooltip import ToolTip

# pylint: disable=redefined-outer-name

#
# Application setup
#
import argparse
import os
class DictAction(argparse.Action):
    """Argparse action that collects x=y values into a dict."""
    def __init__(self, *args, default=None, **kwargs):
        if default is None: default = {}
        super().__init__(*args, default=default, **kwargs)
    def __call__(self, parser, namespace, values, option_string=None):
        settings = getattr(namespace, self.dest)
        for x in values:
            if '=' not in x: raise argparse.ArgumentError(x, f'Argument missing "=": "{x}"')
            settings[x.split('=', 1)[0]] = x.split('=', 1)[1]
parser = argparse.ArgumentParser()
parser.add_argument('hostname_port')
parser.add_argument('password', default=os.environ.get('OBS_PASSWORD'),
                  help='or set env var OBS_PASSWORD')
parser.add_argument('--notes-window',
                    help='window name regex for notes document (for scrolling), get via xwininfo -tree -root | less')
parser.add_argument('--small', action='store_true')
parser.add_argument('--test', action='store_true', help="Don't connect to OBS, just show the panel")
parser.add_argument('--scene-hook', action=DictAction, nargs=1,
                    help="Local command line hooks for switching to each scene, format SCENENAME=command")
parser.add_argument('--resolution-hook',
                    help="Command to run when setting resolution.  WIDTH and HEIGHT will be replaced with integers")
parser.add_argument('--no-pip-poll', action='store_true', help="Don't poll for pip size (for less verbosity when testing)")
parser.add_argument('--broadcaster', action='store_true', help="This is running on broadcaster's computer")
parser.add_argument('--verbose', '-v', action='count', default=0)
args = cli_args = parser.parse_args()
LOG = logging.getLogger(__name__)
if args.verbose >= 2:
    logging.basicConfig(level=logging.DEBUG)
elif args.verbose >= 1:
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('obsws_python').setLevel(logging.INFO)
LOG.debug("Arguments: %s", cli_args)


#
# Definitions
#
ACTIVE = 'red'
ACTIVE_SAFE = 'orange'
AUDIO_INPUT = 'Instructors'
AUDIO_INPUT_BRCD = 'BroadcasterMic'
NOTES = 'Notes'
SCENE_NAMES = {
    # obs_name: (label, tooltip),
    'Title': ('Title', 'Title screen with logo', True),
    'Gallery': ('Gallery', 'All instructors gallery', True),
    'Screenshare': ('SS Portrait', 'Screenshare, normal portrait mode', True),
    'ScreenshareCrop': ('SS Crop', 'Screenshare, landscape share but crop portrait out of the left 840 pixels (requires local setup)', True),
    'ScreenshareLandscape': ('SS Landscape', 'Screenshare, actual full landscape mode inserted into portrait mode (requires local setup)', True),
    'Broadcaster-Screen': ('BrdScr', 'Broadcaster local screen (only broadcaster may select)', args.broadcaster),
    NOTES: ('Notes', 'Notes, from the broadcaster computer', True),
    'Empty': ('Empty', 'Empty black screen', True),
    }
SCENE_NAMES_REVERSE = { v[0]: n for n,v in SCENE_NAMES.items() }
SCENES_WITH_PIP = ['Screenshare', 'ScreenshareCrop', 'ScreenshareLandscape', 'Broadcaster-Screen', NOTES]
SCENES_WITH_GALLERY = SCENES_WITH_PIP + ['Gallery']
SCENES_SAFE = ['Title', NOTES, 'Empty'] # scenes suitable for breaks
SCENE_SIZES = [
   "840x1080",
   "1920x1080",
   ]
PIP = '_GalleryCapture[hidden]'
PLAYBACK_INPUT = 'CRaudio'  # for playing transitions sounds, etc.
TOOLTIP_DELAY = 0.5
PLAYBACK_FILES = [
    {'filename': '/home/rkdarst/git/coderefinery-artwork/audiologo/CR_LOGO_sound_short.mp3',
     'label': 'short',
     'tooltip': 'Short audio for coming back from breaks, 0:03 duration'},
    {'filename': '/home/rkdarst/git/coderefinery-artwork/audiologo/CR_LOGO_Jingle_long.mp3',
     'label': 'long',
     'tooltip': 'Long theme song for starting/ending day, 1:23 duration'},
    ]
PIP_CROP_FACTORS = {
    None: {'top':  0, 'bottom':  0, 'left':  0, 'right':  0, },
    1:    {'top':  0, 'bottom':  0, 'left': 59, 'right':  59, },
    2:    {'top': 90, 'bottom':  0, 'left': 12, 'right': 12, },  # checked
    3:    {'top':  4, 'bottom':  0, 'left': 60, 'right': 60, },  # checked
    5:    {'top': 50, 'bottom':  0, 'left': 11, 'right': 11, },  # checked
    }


class ObsState:
    """Manager class for all OBS state
    """
    ATTRS = {
        ''
        }
    _LOG = logging.getLogger('ObsState')
    def __init__(self, obsreq, obsev):
        super().__setattr__('_req', obsreq)
        super().__setattr__('_ev', obsev)
        super().__setattr__('_watchers', collections.defaultdict(set))
        super().__setattr__('_dir', set(dir(self)))

        watching_funcs = [func
                          for (name, func) in inspect.getmembers(self, predicate=inspect.ismethod)
                          if name.startswith('on_')
                          ]
        self._LOG.debug('Registering functions: %s', watching_funcs)
        self._ev.callback.register(watching_funcs)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name}')
        value = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name).slot_value
        self._LOG.debug('obs.getattr {name}={value}')
        return value
    __getitem__ = __getattr__

    def __setattr__(self, name, value):
        if name in self._dir:
            super().__setattr__(name, value)
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name}')
        self._LOG.debug('obs.setattr %s=%s', name, value)
        self._req.set_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name, value)
        self._req.broadcast_custom_event({'eventData': {name: value}})
        if args.test:
            self.on_custom_event(type('dummy', (), {name: value, 'attrs': lambda: [name]}))
    __setitem__ = __setattr__

    def __hasattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name}')
        value = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name)
        self._LOG.debug('obs.hasattr {name}')

    def on_custom_event(self, event):
        """Watcher for custom events"""
        self._LOG.debug('custom event %s (%s)', event, event.attrs())
        for attr in event.attrs():
            if attr in self._watchers:
                for func in self._watchers[attr]:
                    self._LOG.debug('custom event attr=%s func=%s', attr, func)
                    func(getattr(event, attr))

    def _watch(self, name, func):
        self._LOG.debug('obs._watch add %s=%s', name, func)
        self._watchers[name].add(func)

    # Custom properties
    @property
    def scene(self):
        value = self._req.get_current_program_scene().current_program_scene_name
        self._LOG.debug('obs.scene get scene=%s', value)
        return value
    @scene.setter
    def scene(self, value):
        self._LOG.debug('obs.scene set scene=%s', value)
        self._req.set_current_program_scene(value)
        if args.test:
            self.on_current_program_scene_changed(type('dummy', (), {'scene_name': value}))
    def on_current_program_scene_changed(self, data):
        print('z'*50)
        for func in self._watchers['scene']:
            self._LOG.debug('obs.scene watch scene %s', func)
            func(data.scene_name)

    @property
    def muted(self):
        return self._req.get_input_mute(AUDIO_INPUT).input_muted
    @muted.setter
    def muted(self, value):
        self._req.set_input_mute(AUDIO_INPUT, value)
        if args.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    @property
    def muted_brcd(self):
        return self._req.get_input_mute(AUDIO_INPUT).input_muted
    @muted_brcd.setter
    def muted_brcd(self, value):
        self._req.set_input_mute(AUDIO_INPUT, value)
        if args.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    def on_input_mute_state_changed(self, data):
        print(f"OBS: mute {data.input_name} to {data.input_muted}")
        for ctrl, name in [
            (AUDIO_INPUT, 'muted'),
            (AUDIO_INPUT_BRCD, 'muted_brcd'),
            ]:
            if data.input_name == ctrl:
                for func in self._watchers[name]:
                    func(data.input_muted)


# OBS websocket
if not args.test:
    hostname = args.hostname_port.split(':')[0]
    port = args.hostname_port.split(':')[1]
    password = args.password

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

obs = ObsState(obsreq, cl)


class Helper:
    grid_pos = None
    grid_s_pos = None
    tt = None   # tooltip object
    def __init__(self, *args, tooltip=None, grid=None, grid_s=None, **kwargs):
        #print("Helper init", grid, tooltip if isinstance(tooltip, str) else '[non-string tooltip]')
        #print(self)
        super().__init__(*args, **kwargs)
        if tooltip is None and hasattr(self, 'tooltip'):
            tooltip = self.tooltip
        if tooltip:
            self.tt = ToolTip(self, tooltip, delay=TOOLTIP_DELAY)

        if not grid and self.grid_pos:
            grid = self.grid_pos
        if not grid_s and self.grid_s_pos:
            grid_s = self.grid_s_pos

        if grid_s and cli_args.small:
            self.grid(grid_s)
        if grid and not cli_args.small:
            self.grid(grid)
class Label2(Helper, Label):
    def __init__(self, *args, **kwargs):
        print('init'*10, kwargs['text'])
        super().__init__(*args, **kwargs)
    pass

def g(*args, **kwargs):
    grid_ = { }
    if args:
        grid_['row'] = args[0]
        grid_['column'] = args[1]
    grid_.update(kwargs)
    return grid_

def scene_to_label(name):
    return SCENE_NAMES.get(name, [('-')])[0]

def label_to_scene(name):
    return SCENE_NAMES_REVERSE.get(name, name)



#
# GUI setup
#
root = Tk()
root.title("OBS CodeRefinery control")
frm = ttk.Frame(root)
frm.columnconfigure(tuple(range(10)), weight=1)
frm.rowconfigure(tuple(range(10)), weight=1)
frm.grid()
frm.pack()
#ttk.Label(frm, text="Hello World!").grid(column=0, row=0)
class Time(Helper, ttk.Label):
    grid_pos = grid_s_pos = g(0, 7)
    tooltip = "Current time"
    def __init__(self, frame):
        super().__init__(frm, text=time.strftime('%H:%M:%S'))
        self.after(1000, self.update_)
    def update_(self):
        self.config(text=time.strftime('%H:%M:%S'))
        self.after(1000, self.update_)
class Quit(Helper, ttk.Button):
    tooltip = "Quit the control panel (does not affect the stream)"
    #grid_pos = g(0, 8)
    def __init__(self, frame):
        super().__init__(frame, text='Quit', command=root.destroy)
time_l = Time(frm)
quit_b = Quit(frm)

default_color = root.cget("background")
default_activecolor = default_color
color_default = {'background': default_color, 'activebackground': default_color}



class IndicatorLight(Helper, Button):
    def __init__(self, frm, event_name, label, color='cyan', blink=None, **kwargs):
        self.event_name = event_name
        self.color = color
        self.blink = blink
        super().__init__(frm, text=label, command=self.click, **kwargs)
        saved_state = getattr(obs, event_name)
        self.state = None
        self.blink_id = None
        if saved_state:
            self.state = saved_state.slot_value
        self.update_(self.state)
        obs._watch(event_name, self.update_)
    def click(self):
        self.state = not self.state
        setattr(obs, self.event_name, self.state)
    def update_(self, state):
        """Callback anytime state is updated."""
        self.state = state
        if self.state:
            self.configure(background=self.color, activebackground=self.color)
            if self.blink:
                blink_id = self.blink_id = random.randint(0, 2**64-1)
                self.after(self.blink, self.do_blink, blink_id, False)
        else:
            self.configure(background=default_color, activebackground=default_color)
    def do_blink(self, blink_id, next_state):
        """Callback to blink.  Each time flips blink on/off until self.state is not true."""
        if self.blink_id != blink_id or not self.state:
            return
        if next_state:
            self.configure(background=self.color, activebackground=self.color)
        else:
            self.configure(background=default_color, activebackground=default_color)
        self.after(self.blink, self.do_blink, blink_id, not next_state)

class IndicatorMasterLive(Helper, Button):
    def __init__(self, frm, event_name, label, color='cyan', tooltip=None, **kwargs):
        self.event_name = event_name
        self.color = color
        if tooltip:
            self.tt_default = tooltip
            tooltip = self.tt_msg
        self.state = { }
        super().__init__(frm, text=label, state='disabled', tooltip=tooltip, **kwargs)
    def update_(self, name, value):
        self.state[name] = value
        if any(self.state.values()):
            self.configure(background=self.color, activebackground=self.color)
        else:
            self.configure(background=default_color, activebackground=default_color)
    def tt_msg(self):
        return '\n'.join([self.tt_default] + [f'RED: {k} ({v})' for k,v in self.state.items() if v])
    def on_custom_event(self, event):
        pass
il = Label(frm, text="Indicator:")
il.grid(row=0, column=0)
ToolTip(il, "Synced indicator lights.  Pushing a button illuminates it on all other panels, but has no other effect.")
#il = Label2(frm, text="Indicator:", grid=g(0,0), tooltip="Synced indicator lights.  Pushing a button illuminates it on all other panels, but has no other effect.")
indicator_frame = ttk.Frame(frm)
indicator_frame.grid(row=0, column=1, columnspan=6, sticky=W)
indicator_frame.columnconfigure(tuple(range(10)), weight=1)
indicators = { }
indicators['live'] = IndicatorMasterLive(indicator_frame, 'indicator-live', label="Live", color='red', grid=g(0,0), grid_s=g(0,0), tooltip="Master live warning.  RED if anything is live on stream (tooltip will indicate what is on).")
for i, (name, label, color, tt, kwargs) in enumerate([
    ('warning',  'Warn',     'red',    'Master warning: some urgent issue, please check.', {'blink': 500}),
    ('caution',  'Caution',  'yellow', 'Master caution: some issue, please check.', {}),
    ('time',     'Time',     'yellow', 'General "check time" indicator.', {}),
    ('notes',    'Notes',    'cyan',   'General "check shared notes" indicator.', {}),
    ('question', 'Question', 'cyan',   'Important question, check chat or notes', {}),
    ('chat',     'Chat',     'cyan',   'Check chat indicator', {}),
    ('slower',     '<',      'yellow', 'Slower', {}),
    ('faster',     '>',      'yellow', 'Faster', {}),
    ]):
    indicators[name] = IndicatorLight(indicator_frame, 'indicator-'+name, label, color=color,
                                      grid  =g(row=0, column=i+1),
                                      grid_s=g(row=0, column=i+1),
                                      tooltip=tt, **kwargs)





# Quick actions
class QuickBreak(Helper, ttk.Button):
    def __init__(self, frm, text, **kwargs):
        super().__init__(frm, command=self.click, text=text, **kwargs)
    def click(self):
        mute[AUDIO_INPUT].click(True)
        mute[AUDIO_INPUT_BRCD].click(True)
        SceneButton.switch(NOTES)
        pip_size.save_last()
        pip_size.update(0)
class QuickBack(Helper, ttk.Button):
    def __init__(self, frm, scene, text, **kwargs):
        self.scene = scene
        super().__init__(frm, command=self.click, text=text, **kwargs)
    def click(self):
        import threading
        threading.Thread(target=self.run).start()
    def run(self):
        mute[AUDIO_INPUT].click(False)
        if quick_sound.instate(('selected', )):
            playback_buttons['short'].play()
            time.sleep(3)
            quick_sound.state(('!selected',))
        SceneButton.switch(self.scene)
        pip_size.restore_last()
        print('sound state: ', quick_sound.state())
if not args.small:
    qa_label = ttk.Label(frm, text="Presets:")
    qa_label.grid(row=1, column=0)
    ToolTip(qa_label, "Quick actions.  Clicking button does something for you.", delay=TOOLTIP_DELAY)
#l2 = Label2(frm, text="Presets:", grid=g(1, 0))
QuickBreak(frm, 'BREAK', tooltip='Go to break.\nMute audio, hide PIP, and swich to Notes',
           grid=g(1,1), grid_s=g(1,1))

if not args.small:
    QuickBack(frm, 'Screenshare',         'BACK(SS-P) ',  grid=g(1,2), tooltip='Back from break\nSwitch to Screenshare, \ntry to restore settings')
    QuickBack(frm, 'ScreenshareCrop',     'BACK(SS-C)', grid=g(1,3), tooltip='Back from break\nSwitch to Screenshare, cropped landscape mode, \ntry to restore settings')
    QuickBack(frm, 'ScreenshareLandscape','BACK(SS-LS)',grid=g(1,4), tooltip='Back from break\nSwitch to Screenshare-Landscape\nNotes, \ntry to restore settings')
    QuickBack(frm, NOTES,                 'BACK(n)',    grid=g(1,6), tooltip='Back from break\nSwitch to Notes,\ntry to restore settings')
    quick_sound = ttk.Checkbutton(frm, text="Jingle?", onvalue=True, offvalue=False)
    quick_sound.grid(row=1, column=7)
    quick_sound.state(('!selected', '!alternate',))

    ToolTip(quick_sound,
            "Play short sound when coming back from break?\n"
            "If yes, then unmute, play jingle for 3s, then switch scene and increase PIP size.\n"
            "if no, immediately restore the settings.", delay=TOOLTIP_DELAY)


# Scenes
class SceneButton(Helper, Button):
    _instances = [ ]
    def __init__(self, frame, scene_name, label, selectable=True, **kwargs):
        self.scene_name = scene_name
        super().__init__(frame, text=label,
                         command=partial(self.switch, scene_name),
                         state='normal' if selectable else 'disabled',
                         **kwargs)
        self._instances.append(self)
        if not args.test:
            current_scene = obs.scene
            if current_scene == scene_name:
                self.update_(True)
                indicators['live'].update_('scene-visible', scene_name if (scene_name not in SCENES_SAFE) else '')
                print(f"Init: Current scene {current_scene}")
        obs._watch('scene', self.switched)
    @classmethod
    def switch(self, name):
        """Trigger a switch"""
        print(f'Remote: triggered scene {name}')
        obs.scene = name
        self.switched(name)
    @classmethod
    def switched(self, name):
        """Handle a switch triggered externally"""
        indicators['live'].update_('scene-visible', name if (name not in SCENES_SAFE) else '')
        for instance in self._instances:
            instance.update_(instance.scene_name == name)
        if name in cli_args.scene_hook:
            subprocess.call(cli_args.scene_hook[name], shell=True)
    def update_(self, state):
        """Update button's apperance if clicked"""
        if state and self.scene_name in SCENES_SAFE:
            color = ACTIVE_SAFE
        elif state:
            color = ACTIVE
        else:
            color = default_color
        self.configure(background=color, activebackground=color)

class SceneLabel(Helper, Label):
    label = ''
    scene_name = ''
    def __init__(self, frm, *args, tooltip=None, **kwargs):
        self.tt_default = tooltip or 'Current scene'
        super().__init__(frm, *args, tooltip=self.tt_msg, **kwargs)
        self.configure(text='[scene]')
        obs._watch('scene', self.update_)
        if not cli_args.test:
            self.update_(obs.scene)
    def update_(self, scene_name):
        self.scene_name = scene_name
        label = self.label = SCENE_NAMES.get(scene_name, (scene_name,))[0]
        self.configure(text=label)
        if scene_name in SCENES_SAFE:
            color = default_color
        else:
            color = ACTIVE
        self.configure(background=color, activebackground=color)
    def tt_msg(self):
        return '\n'.join([self.tt_default, f'{self.label} ({self.scene_name})'])

for i, (scene, (label, tooltip, selectable)) in enumerate(SCENE_NAMES.items()):
    b = SceneButton(frm, scene_name=scene, label=label, selectable=selectable,
                    tooltip=tooltip,
                    grid=g(2, i))
if args.small:
    SceneLabel(frm, grid_s=g(1,0), tooltip="Current scene")

# Audio
class Mute(Helper, Button):
    def __init__(self, frm, input_, text, enabled=True, **kwargs):
        self.state = None  # True = Muted, False = unmuted (LIVE)
        self.input = input_
        super().__init__(frm, text=text, command=self.click, state='normal' if enabled else 'disabled', **kwargs)
        if not args.test:
            self.obs_update(obsreq.get_input_mute(input_).input_muted)
        obssubscribe(self.on_input_mute_state_changed)
    def click(self, state=None):
        """True = muted"""
        if state is None:
            state = not self.state
        self.obs_update(state)  # update colors
        obsreq.set_input_mute(self.input, state)
    def obs_update(self, state):
        self.state = state
        if state: # mute on
            self.configure(background=default_color, activebackground=default_color)
        else:    # mute off
            self.configure(background=ACTIVE, activebackground=ACTIVE)
        indicators['live'].update_('mute-'+self.input, 'unmuted' if not state else None)
    def on_input_mute_state_changed(self, data):
        """Muting/unmuting"""
        if data.input_name == self.input:
            print(f"OBS: mute {data.input_name} to {data.input_muted}")
            self.obs_update(state=data.input_muted)
class Volume(Helper, ttk.Frame):
    def __init__(self, frame, input_, **kwargs):
        self.input = input_
        super().__init__(frame, **kwargs)
        self.value = DoubleVar()
        self.scale = Scale(self, from_=-2, to=0, orient=HORIZONTAL, command=self.update, showvalue=0, resolution=.05, variable=self.value)
        self.scale.grid(row=0, column=0, columnspan=5, sticky=E+W)
        ToolTip(self.scale, "Current instructor audio gain", delay=TOOLTIP_DELAY)
        self.label = ttk.Label(self, text="x");
        self.label.grid(row=0, column=5)
        self.columnconfigure(tuple(range(6)), weight=1)
        # Initial update
        if not args.test:
            dB = obsreq.get_input_volume(input_).input_volume_db
            print(f"from OBS: {input_} {dB} (volume_state)")
            self.obs_update(dB)
        # Callback update
        obssubscribe(self.on_input_volume_changed)
    def to_dB(self, state):
        return - 10**(-state) + 1
    def to_state(self, dB):
        return -math.log10(-(dB-1))

    def update(self, state):
        print('->')
        state = float(state)
        dB = self.to_dB(state)
        print(f'-> Setting volume: {state}     ->  {dB}')
        self.label.config(text=f"{dB:.1f} dB")
        self.last_dB = dB
        obsreq.set_input_volume(self.input, vol_db=dB)
    def obs_update(self, dB):
        print('<=')
        state = self.to_state(dB)
        print(f'<= Setting volume: {state}    <- {dB}')
        self.label.config(text=f"{dB:.1f} dB")
        self.value.set(state)
    def on_input_volume_changed(self, data):
        """Volume change callback"""
        if data.input_name == self.input:
            print(f"OBS: Volume {data.input_name} to {data.input_volume_db}")
            self.obs_update(data.input_volume_db)

if not args.small:
    audio_l = ttk.Label(frm, text="Audio:")
    audio_l.grid(row=3, column=0)
    ToolTip(audio_l, "Audio controls (mute/unmute/level)", delay=TOOLTIP_DELAY)
mute = { }
mute[AUDIO_INPUT_BRCD] = Mute(frm, AUDIO_INPUT_BRCD, "Brcd", grid=g(3, 1), tooltip="Broadcaster microphone, red=ON.  Only broadcaster can control", enabled=args.broadcaster)
mute[AUDIO_INPUT]      = Mute(frm, AUDIO_INPUT,     "Instr", grid=g(3, 2), tooltip="Mute/unmute instructor capture, red=ON", )
volume = Volume(frm, AUDIO_INPUT, grid=g(row=3, column=3, columnspan=4, sticky=E+W))


# PIP
class PipSize(Helper, ttk.Frame):
    def __init__(self, frame, **kwargs):
        self.last_state = 0.25
        super().__init__(frame, **kwargs)
        self.value = DoubleVar()
        self.scale = Scale(self, from_=0, to=1, orient=HORIZONTAL, command=self.update, showvalue=0, resolution=.01, variable=self.value)
        self.scale.grid(row=0, column=0, columnspan=5, sticky=E+W)
        ToolTip(self.scale, "Change the size of the instructor picture-in-picture, 0=invisible", delay=TOOLTIP_DELAY)
        self.label = ttk.Label(self, text="?")
        self.label.grid(row=0, column=5)
        self.columnconfigure(tuple(range(6)), weight=1)
        # update polling
        if not args.test:
            self.pip_id = obsreq.get_scene_item_id(NOTES, PIP).scene_item_id
            obssubscribe(self.on_custom_event)
            if not cli_args.no_pip_poll:
                self.update_pip_size()
    def update(self, state):
        """Update callback of slider"""
        state = float(state)
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        indicators['live'].update_('pip-size', 'visible' if state != 0 else None)

        self.scale.configure(background=color, activebackground=color)
        for scene in SCENES_WITH_PIP:
            id_ = obsreq.get_scene_item_id(scene, PIP).scene_item_id
            transform = obsreq.get_scene_item_transform(scene, id_).scene_item_transform
            transform['scaleX'] = state
            transform['scaleY'] = state
            obsreq.set_scene_item_transform(scene, id_, transform)
    def save_last(self):
        """Save pip size for future restoring"""
        self.last_state = self.value.get()
        # The custom event doesn't seem to work - somehow
        obsreq.broadcast_custom_event({'eventData': {'pip_last_state': self.last_state}})
        obsreq.set_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', 'pip_last_state', self.last_state)
        print('setting')
    def restore_last(self):
        """Restore last pip size"""
        self.update(self.last_state)
    def obs_update(self, state):
        """"Callabck for scale update from OBS"""
        self.value.set(state)
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        self.scale.configure(background=color, activebackground=color)
        indicators['live'].update_('pip-size', 'visible' if state != 0 else None)
    def on_custom_event(self, data):
        """Custom event listener callback from OBS."""
        #print(f'OBS custom event: {vars(data)}')
        if hasattr(data, 'pip_last_state'):
            self.last_state = data.pip_last_state
            print(f"Saving last pip size: {self.last_state}")
    def update_pip_size(self):
        """The on_scene_item_transform_changed doesn't seem to work, so we have to poll here... unfortunately."""
        self.obs_update(obsreq.get_scene_item_transform(NOTES, self.pip_id).scene_item_transform['scaleX'])
        self.after(1000, self.update_pip_size)

if not args.small:
    b_pip = ttk.Label(frm, text="PIP size:")
    b_pip.grid(row=4, column=0)
    ToolTip(b_pip, "Change size of instuctor picture-in-picture.", delay=TOOLTIP_DELAY)
pip_size = PipSize(frm, grid=g(row=4, column=1, columnspan=6, sticky=E+W))
# PIP crop selection
def pip_crop(n):
    print(f"PIP crop → {n} people")

    for scene in SCENES_WITH_PIP:  # TODO: with gallery
        id_ = obsreq.get_scene_item_id(scene, PIP).scene_item_id
        transform = obsreq.get_scene_item_transform(scene, id_).scene_item_transform
        #print('====old', transform)
        for (k,v) in PIP_CROP_FACTORS[n].items():
            transform['crop'+k.title()] = v
        #print('====new:', transform)
        obsreq.set_scene_item_transform(scene, id_, transform)
if not args.small:
    b_cropbuttons = ttk.Label(frm, text="PIP crop:")
    b_cropbuttons.grid(row=5, column=0)
    ToolTip(b_cropbuttons,
        "PIP insert can be cropped to suit different numbers of people (this comes from "
        "how Zoom lays it out for different numbers of people.  Click a button if "
        "it doesn't fit right into the corner.", delay=TOOLTIP_DELAY)
crop_buttons = ttk.Frame(frm)
crop_buttons.columnconfigure(tuple(range(5)), weight=1)
crop_buttons.grid(row=5, column=1, columnspan=5)
for i, (n, label) in enumerate([(None, 'None'), (1, 'n=1'), (2, 'n=2'), (3, 'n=3-4'), (5, 'n=5-6')]):
    b = ttk.Button(crop_buttons, text=label, command=partial(pip_crop, n))
    if not args.small:
        b.grid(row=0, column=i)
    ToolTip(b, 'Set PIP to be cropped for this many people.  None=no crop', delay=TOOLTIP_DELAY)

# Playback
class PlaybackTimer(Helper, ttk.Label):
    def __init__(self, frm, input_name, *args, **kwargs):
        self.input_name = input_name
        super().__init__(frm, *args, **kwargs)
        self.configure(text='-')
        obssubscribe(self.on_media_input_playback_started)
    def update_timer(self):
        event = obsreq.get_media_input_status(self.input_name)
        state = event.media_state  # 'OBS_MEDIA_STATE_PAUSED', 'OBS_MEDIA_STATE_PLAYING'
        if state in {'OBS_MEDIA_STATE_OPENING', 'OBS_MEDIA_STATE_BUFFERING', 'OBS_MEDIA_STATE_PAUSED', }:
            print(f"OBS media state: {state}")
            self.after(500, self.update_timer)
            return
        if state != 'OBS_MEDIA_STATE_PLAYING':
            self.configure(text='-', background=default_color)
            print(f"OBS media state: {state}")
            return
        duration = event.media_duration
        cursor = event.media_cursor
        if duration < 0:
            self.after(500, self.update_timer)
            return
        def s_to_mmss(s):
            return f'{s//60}:{s%60:02}'
        self.configure(text=f'-{s_to_mmss((duration-cursor)//1000)}/{s_to_mmss(duration//1000)}',
                       background=ACTIVE)
        self.after(500, self.update_timer)
    def on_media_input_playback_started(self, data):
        """Playing media"""
        print("OBS: media playback started")
        self.update_timer()
class PlayFile(Helper, ttk.Button):
    def __init__(self, frm, filename, label, **kwargs):
        self.filename = filename
        super().__init__(frm, text=label, command=self.play, **kwargs)
    def play(self):
        print(f'setting input to {self.filename}')
        obsreq.set_input_settings(PLAYBACK_INPUT, {'local_file': self.filename}, overlay=True)
class PlayStop(Helper, ttk.Button):
    def __init__(self, frm, **kwargs):
        super().__init__(frm, text='StopPlay', command=self.stop, **kwargs)
    def stop(self):
        print("stopping playback")
        obsreq.trigger_media_input_action(PLAYBACK_INPUT, 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP')
if not args.small:
    playback_label = ttk.Label(frm, text="Jingle:")
    playback_label.grid(row=6, column=0)
    ToolTip(playback_label, "Row deals with playing transition sounds", delay=TOOLTIP_DELAY)
playback = PlaybackTimer(frm, PLAYBACK_INPUT, grid=g(6, 1), grid_s=g(1, 2), tooltip="Countdown time for current file playing")
playback_buttons = { }
for i, file_ in enumerate(PLAYBACK_FILES, start=2):
    pf = playback_buttons[file_['label']] = PlayFile(frm, **file_, grid=g(6, i))
ps = PlayStop(frm, grid=g(6, 2+len(PLAYBACK_FILES)), tooltip="Stop all playbacks")



class ScrollNotes(Helper, ttk.Button):
    def __init__(self, frm, label, event, **kwargs):
        self.event = event
        super().__init__(frm, text=label, command=self.click, **kwargs)
    def click(self):
        obsreq.broadcast_custom_event({'eventData': {self.event: True}})
    def on_custom_event(self, event):
        pass
sn_frame= ttk.Frame(frm)
sn_frame.columnconfigure(tuple(range(3)), weight=1)
if args.small:
    sn_frame.grid(row=1, column=3, columnspan=4)
else:
    sn_frame.grid(row=8, column=0, columnspan=3)

sn_label = Label(sn_frame, text="Notes scroll:")
sn_label.grid(row=0, column=0)
ToolTip(sn_label, "Tools for scrolling notes up and down (on the broadcaster computer), in the Notes view.", delay=TOOLTIP_DELAY)
b = ScrollNotes(sn_frame, "Up",   event='notes_scroll_up',   grid=g(0,1), grid_s=g(0,1), tooltip="Scroll notes up")
b = ScrollNotes(sn_frame, "Down", event='notes_scroll_down', grid=g(0,2), grid_s=g(0,2), tooltip="Scroll notes down")




# Announcement text
class AnnouncementButton(Helper, Button):
    def __init__(self, frame, name, label, **kwargs):
        self.name = name
        self.state = False
        super().__init__(frame, command=self.click_, *kwargs)
    def click_(self):
        pass
class AnnouncementLabel(Helper, Frame):
    pass

    #def ann_toggle():
#    if ann_toggle = False
#    for scene in SCENES:
#        id_ = obsreq.get_scene_item_id(scene, 'Announcement'.scene_item_id
#        transform = obsreq.get_scene_item_transform(scene, id_).scene_item_transform
#
#def ann_update(text=None, from_obs=False):
#    if from_obs: # set value
#        ann.set(text)
#    text = ann.get()
#    print(text)
#    obsreq.set_input_settings('Announcement', {'text': text}, True)
#ann_toggle = Button(frm, text="Ann text", command=ann_toggle) ; ann_toggle.grid(row=6, column=0)
#ann_toggle.state = False
#ToolTip(ann_toggle, 'Toggle anouncement text visibility.', delay=TOOLTIP_DELAY)
#ann = Entry(frm) ; ann.grid(row=6, column=1, columnspan=6, sticky=W+E)
#b = Button(frm, text="Update", command=ann_update) ; b.grid(row=6, column=5)
#ToolTip(b, 'Update the announcement text in OBS', delay=TOOLTIP_DELAY)


class Preset(Helper, ttk.Frame):
    def __init__(self, frame, name, label, **kwargs):
        super().__init__(frame, **kwargs)
        self.name = name

        self.button = Button(self, text=label, command=self.click)
        self.button.grid(row=0, column=0)

        # Scene choices
        self.sbox_value = StringVar()
        self.sbox_value.set(scene_to_label(obs[f'preset-{self.name}-sbox'] or '-'))
        self.sbox = OptionMenu(self, self.sbox_value,
                               '-', *[scene_to_label(x) for x in SCENE_NAMES],
                               command=self.click_sbox)
        self.sbox.grid(row=0, column=1)
        self._last_scene = obs.scene

        # Resolution choices
        self.rbox_value = StringVar()
        self.rbox_value.set(obs[f'preset-{self.name}-rbox'] or '-')
        self.rbox = OptionMenu(self, self.rbox_value, '-', *SCENE_SIZES,
                               command=self.click_rbox)
        self.rbox.grid(row=0, column=2)
        self._last_res = obs.ss_resolution

        self.watch_scene(obs.scene)
        self.watch_resolution(obs.ss_resolution)
        obs._watch('scene', self.watch_scene)
        obs._watch('ss_resolution', self.watch_resolution)
        obs._watch(f'preset-{self.name}-sbox', self.watch_sbox)
        obs._watch(f'preset-{self.name}-rbox', self.watch_rbox)

    def click(self):
        """Button is clicked.  Switch to this preset"""
        scene_name = label_to_scene(self.sbox_value.get())
        resolution = self.rbox_value.get()
        print(f'Setting to preset {scene_name} at {resolution}')
        obs.scene = scene_name
        obs.ss_resolution = resolution
        w, h = resolution.split('x')
        w = int(w)
        h = int(h)
        set_resolution(w, h)

    def click_sbox(self, name):
        name = label_to_scene(name)
        obs[f'preset-{self.name}-sbox'] = name
        #self.update_()
    def click_rbox(self, name):
        obs[f'preset-{self.name}-rbox'] = name
        #self.update_()

    def watch_scene(self, name):
        self._last_scene = name
        self.update_()
    def watch_resolution(self, res):
        self._last_res = res
        self.update_()

    def watch_sbox(self, value):
        LOG.debug('watch sbox')
        self.sbox_value.set(scene_to_label(value))
        self.update_()
    def watch_rbox(self, value):
        LOG.debug('watch rbox')
        self.rbox_value.set(value)
        self.update_()

    def update_(self):
        """Update coloring"""
        LOG.debug('preset-%s: %s = %s', self.name, self._last_scene, self.sbox_value.get())
        LOG.debug('preset-%s: %s = %s', self.name, self._last_res, self.rbox_value.get())
        state = (self._last_scene == label_to_scene(self.sbox_value.get())
                 and self._last_res == self.rbox_value.get() )
        if state and self._last_scene in SCENES_SAFE:
            color = ACTIVE_SAFE
        elif state:
            color = ACTIVE
        else:
            color = default_color
        self.button.configure(background=color, activebackground=color)


l_presets = ttk.Label(frm, text="Scene presets:")
l_presets.grid(row=9, column=0)
a = Preset(frm, 'a', "A", grid=g(9,1, columnspan=3, sticky=E+W))




def set_resolution(w, h):
    if not args.resolution_hook:
        LOG.warning("No resolution hook to set %d, %d", w, h)
        return
    cmd = args.resolution_hook
    w = int(w)
    h = int(h)
    if not  200 < w < 5000:
        raise ValueError(f"invalid width: {w}")
    if not 200 < h < 3000:
        raise ValueError(f"invalid height: {w}")
    cmd = cmd.replace('WIDTH', str(w)).replace('HEIGHT', str(h))
    subprocess.call(cmd, shell=True)





# Initialize with our current state
if not args.test:
    pass
    # scene
    #switch(obsreq.get_current_program_scene().current_program_scene_name, from_obs=True)
    # audio mute
    #for input_ in mute:
    #    mute[input_].obs_update(obsreq.get_input_mute(input_).input_muted)
    # audio volume
    #dB = obsreq.get_input_volume(volume.input).input_volume_db
    #print(f"from OBS: {dB} (volume_state)")
    #volume.obs_update(dB)
    # pip size
    #pip_id = obsreq.get_scene_item_id(NOTES, PIP).scene_item_id
    #def update_pip_size():
    #    """The on_scene_item_transform_changed doesn't seem to work, so we have to poll here... unfortunately."""
    #    pip_size.obs_update(obsreq.get_scene_item_transform(NOTES, pip_id).scene_item_transform['scaleX'])
    #    pip_size.after(1000, update_pip_size)
    #update_pip_size()

#def on_current_program_scene_changed(data):
#    """Scene changing"""
#    #print(data.attrs())
#    print(f"OBS: scene to {data.scene_name}")
#    switch(data.scene_name, from_obs=True)
#def on_input_volume_changed(data):
#    """Volume change"""
#    #print(data.attrs())
#    #print(data.input_name, data.input_volume_db)
#    if data.input_name == volume.input:
#        print(f"OBS: Volume {data.input_name} to {data.input_volume_db}")
#        volume.obs_update(data.input_volume_db)
#def on_input_mute_state_changed(data):
#    """Muting/unmuting"""
#    #print(data.attrs())
#    if data.input_name in mute:
#        print(f"OBS: mute {data.input_name} to {data.input_muted}")
#        mute[data.input_name].obs_update(state=data.input_muted)
#def on_media_input_playback_started(data):
#    """Playing media"""
#    print("OBS: media playback started")
#    playback.update_timer()
#def on_scene_item_transform_changed(data):
#    """PIP size change.  This doesnt' work."""
#    print(f"OBS: transform change of {data.scene_item_id}")
#    if data.scene_item_id == pip_id:
#        pip_size.obs_update(data.scene_item_transform['scaleX'])

def on_custom_event(data):
    if not args.notes_window:
        return
    cmd = ['xdotool', 'search', '--name', args.notes_window,
           'windowfocus',
           'key', 'KEY',
           'windowfocus', subprocess.getoutput('xdotool getwindowfocus')
           ]
    if hasattr(data, 'notes_scroll_down'):
        cmd[cmd.index('KEY')] = 'Down'
        subprocess.call(cmd)
    if hasattr(data, 'notes_scroll_up'):
        cmd[cmd.index('KEY')] = 'Up'
        subprocess.call(cmd)

# xdotool search --onlyvisible --name '^Collaborative document.*Private' windowfocus key Down windowfocus $(xdotool getwindowfocus)


obssubscribe([
    #on_current_program_scene_changed,
    #on_input_volume_changed,
    #on_input_mute_state_changed,
    #on_media_input_playback_started,
    #on_scene_item_transform_changed,
    #pip_size.on_custom_event,
    *([on_custom_event] if args.notes_window else []),
    #*[x.on_custom_event for x in indicators.values()],
    ])

#import IPython ; IPython.embed()

print('starting...')
root.mainloop()
