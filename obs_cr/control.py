
# pylint: disable=too-many-ancestors

import argparse
import collections
from functools import partial
import inspect
import logging
import math
import os
import pathlib
import random
import subprocess
import textwrap
import time

from tkinter import *  # pylint: disable=wildcard-import,unused-wildcard-import
from tkinter import ttk
from tktooltip import ToolTip

# pylint: disable=redefined-outer-name

#
# Application setup
#
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


class IfBroadcaster:
    def __bool__(self):
        return cli_args.broadcaster
IfBroadcaster = IfBroadcaster()

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
    'Screenshare': ('SS Portrait', 'Screenshare, normal portrait mode.\nUsed when the instructor can share a portion of the screen with the right 840x1080 aspect ratio.', True),
    'ScreenshareCrop': ('SS Crop', 'Screenshare, landscape share but crop portrait out of the left 840 pixels.\nUsed when instructors can\'t share a portion of the screen, but share a full screen and we pull an 840x1080 aspect ratio chuck out of the left side of it.', True),
    'ScreenshareLandscape': ('SS Landscape', 'Screenshare, actual full landscape mode shrunk into portrait mode.\nUsed when an instructor actually is sharing landscape and you want black bars at the top/bottom to make it fit.', True),
    'BroadcasterScreen': ('BrdScr', 'Broadcaster local screen (only broadcaster may select)', IfBroadcaster),
    NOTES: ('Notes', 'Notes, from the broadcaster computer', True),
    'Empty': ('Empty', 'Empty black screen', True),
    }
SCENE_NAMES_REVERSELOOKUP = { v[0]: n for n,v in SCENE_NAMES.items() }
SCENES_WITH_RESIZEABLE_GALLERY = ['Screenshare', 'ScreenshareCrop', 'ScreenshareLandscape', 'BroadcasterScreen', NOTES]
SCENES_WITH_GALLERY = SCENES_WITH_RESIZEABLE_GALLERY + ['Gallery']
SCENES_SAFE = ['Title', NOTES, 'Empty'] # scenes suitable for breaks
SCENES_REMOTE = {'Screenshare', 'ScreenshareCrop', 'ScreenshareCrop'}
# Possible screen sizes that someone might share (used for fitting them to the view)
SCREENSHARE_SIZES = [
   "840x1080",
   "1920x1080",
   "1920x1200",
   "1680x1080",
   "3840x1080",
   ]
GALLERY = 'ZoomGalleryCapture'
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
GALLERY_CROP_FACTORS = {
    None: {'top':  0, 'bottom':  0, 'left':  0, 'right':  0, },
    1:    {'top':  0, 'bottom':  0, 'left': 59, 'right':  59, },
    2:    {'top': 90, 'bottom':  0, 'left': 12, 'right': 12, },  # checked
    3:    {'top':  4, 'bottom':  0, 'left': 60, 'right': 60, },  # checked
    5:    {'top': 50, 'bottom':  0, 'left': 11, 'right': 11, },  # checked
    }
import simpleaudio
# Mapping of sound event names to the sound files.
SOUNDS = {
    'low': '311.wav',    # low-high for going live, high-low for going off-live
    'high': '349.wav',
    'alert-high': '622.wav',    # high-priority indicator alert (master warning light)
    'alert-medium': '440.wav',  # medium-priority indicator alert (master caution, time, faster/slower, etc)
    'alert-low': '261.wav',     # low-priority indicator alert (notes, question, etc)
    }
# Pre-cache sound files in memory
SOUNDFILES = { name: simpleaudio.WaveObject.from_wave_file(str(pathlib.Path(__file__).parent/f'sound'/name))
          for name in SOUNDS.values()
    }


LOG = logging.getLogger(__name__)



class ObsState:
    """Manager class for all OBS state.

    This dictonary-like object (which also can be used as attribute
    lookups) serves as a way to sync OBS state and broadcast it.  It
    does:

    - Setting an attribute
      - broadcasts it as a custom event (which every other dict gets)
      - saves it as OBS persistent state
    - Getting an attribute
      - Gets it from persistent state
    - Watching an attribute
      - Watches for those custom events and will trigger the callback
        each time the attribute is updated
    - The _watch_init() method installs a callback, and calls it once
      with the saved value.

    The combination of OBS persistent state and OBS custom events allows
    clients to get updates as soon as a value is changed, but also sync
    to the last-set value each time the program starts.
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
            raise AttributeError(f'Invalid attribute {name!r}')
        data = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name)
        value = getattr(data, 'slot_value', None)
        self._LOG.debug('obs.getattr {name!r}={value!r}')
        return value
    __getitem__ = __getattr__

    def __setattr__(self, name, value):
        if name in self._dir:
            super().__setattr__(name, value)
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name!r}')
        self._LOG.debug('obs.setattr %r=%r', name, value)
        self._req.set_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name, value)
        self._req.broadcast_custom_event({'eventData': {name: value}})
        if cli_args.test:
            self.on_custom_event(type('dummy', (), {name: value, 'attrs': lambda: [name]}))
    __setitem__ = __setattr__

    def broadcast(self, name, value):
        """Like __setattr__, but only broadcasts, doesn't save persistent data"""
        self._LOG.debug('obs.broadcast %r=%r', name, value)
        self._req.broadcast_custom_event({'eventData': {name: value}})
        if cli_args.test:
            self.on_custom_event(type('dummy', (), {name: value, 'attrs': lambda: [name]}))

    def __hasattr__(self, name):
        self._LOG.debug('obs.hasattr %r', name)
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name!r}')
        data = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name)
        value = getattr(data, 'slot_value', None)
        if value is None:
            return False
        return True

    def on_custom_event(self, event):
        """Watcher for custom events"""
        self._LOG.debug('custom event %r (%r)', event, event.attrs())
        for attr in event.attrs():
            if attr in self._watchers:
                for func in self._watchers[attr]:
                    self._LOG.debug('custom event attr=%r func=%s', attr, func)
                    func(getattr(event, attr))

    def _watch(self, name, func):
        """Set a watcher for updates of this key"""
        self._LOG.debug('obs._watch add %r=%s', name, func)
        self._watchers[name].add(func)

    def _watch_init(self, name, func):
        """Set a watcher for this key.  Also run the callback once with the current value."""
        self._LOG.debug('obs._watch_init add %r=%s', name, func)
        self._watchers[name].add(func)
        func(getattr(self, name))

    # Custom properties
    @property
    def scene(self):
        value = self._req.get_current_program_scene().current_program_scene_name
        self._LOG.debug('obs.scene get scene=%r', value)
        return value
    @scene.setter
    def scene(self, value):
        self._LOG.debug('obs.scene set scene=%r', value)
        self._req.set_current_program_scene(value)
        if cli_args.test:
            self.on_current_program_scene_changed(type('dummy', (), {'scene_name': value}))
    def on_current_program_scene_changed(self, data):
        for func in self._watchers['scene']:
            self._LOG.debug('obs.scene watch scene %r', func)
            func(data.scene_name)

    @property
    def muted(self):
        return self._req.get_input_mute(AUDIO_INPUT).input_muted
    @muted.setter
    def muted(self, value):
        self._req.set_input_mute(AUDIO_INPUT, value)
        if cli_args.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    @property
    def muted_brcd(self):
        return self._req.get_input_mute(AUDIO_INPUT).input_muted
    @muted_brcd.setter
    def muted_brcd(self, value):
        self._req.set_input_mute(AUDIO_INPUT, value)
        if cli_args.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    def on_input_mute_state_changed(self, data):
        print(f"Mute {data.input_name!r} to {data.input_muted!r}")
        for ctrl, name in [
            (AUDIO_INPUT, 'muted'),
            (AUDIO_INPUT_BRCD, 'muted_brcd'),
            ]:
            if data.input_name == ctrl:
                for func in self._watchers[name]:
                    func(data.input_muted)




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
        super().__init__(*args, **kwargs)



class SyncedCheckbutton(Helper, ttk.Checkbutton):
    """Checkbutton synced through OBS"""
    def __init__(self, frm, name, *args, **kwargs):
        self.name = name
        super().__init__(frm, *args, command=self.click, **kwargs)
        obs._watch_init(f'checkbutton-{self.name}-value', self.update_)
    def click(self, value=None):
        """Click (or other local update)"""
        if value is None:
            value = self.instate(('selected',))
        else:
            self.state(('selected' if value else '!selected', ))
        obs[f'checkbutton-{self.name}-value'] = value
    def update_(self, value):
        """Trigger update from OBS side"""
        self.state(('!alternate',))
        self.state(('selected' if value else '!selected', ))



class SyncedLabel(Helper, Label):
    """A label that is synced via the key"""
    def __init__(self, frm, key, *args, **kwargs):
        self.key = key
        super().__init__(frm, *args, **kwargs)
        if key:
            obs._watch_init(self.key, self.watch)
    def watch(self, value):
        """Remote update"""
        self.configure(text=value)


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
    return SCENE_NAMES_REVERSELOOKUP.get(name, name)

def set_resolution(w, h):
    if not cli_args.broadcaster:
        return
    if not cli_args.resolution_command:
        LOG.error("No resolution command to set %d, %d", w, h)
        return
    cmd = cli_args.resolution_command
    w = int(w)
    h = int(h)
    if not  200 < w < 5000:
        raise ValueError(f"invalid width: {w!r}")
    if not 200 < h < 3000:
        raise ValueError(f"invalid height: {h!r}")
    cmd = cmd.replace('WIDTH', str(w)).replace('HEIGHT', str(h))
    subprocess.call(cmd, shell=True)


def switch(name):
    """Switch to preset (or scene) with this name"""
    print(f'switch: triggered switch to scene {name!r}')
    preset = Preset.by_label(name)
    if preset is not None:
        preset._switch_to()
        obs['scene_humanname'] = name
        return
    if name in SCENE_NAMES:
        SceneButton.switch(name)
        obs['scene_humanname'] = name
        return
    LOG.error("switch: could not find scene %r to switch to", name)


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
        subprocess.call(cmd)


def play(name):
    """Play sound.  There is an OBS listener to trigger this an the right times"""
    muted = cli_args.no_sound
    print(f"Play {name} {'(muted)' if muted else ''}")
    if SOUNDS is None:
        LOG.warning("Sounds are not loaded")
        return
    if name not in SOUNDS:
        LOG.warning("Sound effect mapping %s not found", name)
        return
    soundfile = SOUNDS[name]
    #snd = simpleaudio.WaveObject.from_wave_file(str(path))
    if not muted:
        SOUNDFILES[soundfile].play()




#
# GUI setup
#
root = Tk()

default_color = root.cget("background")
default_activecolor = default_color
color_default = {'background': default_color, 'activebackground': default_color}



class IndicatorLight(Helper, Button):
    def __init__(self, frm, event_name, label, color='cyan', blink=None, **kwargs):
        self.event_name = event_name
        self.color = color
        self.blink = blink
        self.label = label
        super().__init__(frm, text=label, command=self.click, **kwargs)
        saved_state = obs[event_name]
        self.state = None
        self.blink_id = None
        if saved_state:
            self.state = saved_state
        self.update_(self.state)
        obs._watch(event_name, self.update_)
    def click(self):
        self.state = not self.state
        print(f"Indicator {self.label!r} -> {self.state}")
        setattr(obs, self.event_name, self.state)
        if self.state:
            if self.color == 'red':    obs.broadcast('playsound', 'alert-high')
            if self.color == 'yellow': obs.broadcast('playsound', 'alert-medium')
            if self.color == 'cyan':   obs.broadcast('playsound', 'alert-low')
    def update_(self, state):
        """Callback anytime state is updated."""
        self.state = state
        print(f"OBS: Indicator {self.label!r} -> {self.state}")
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
            obs['mirror-live'] = self.state
        else:
            self.configure(background=default_color, activebackground=default_color)
            obs['mirror-live'] = False
    def tt_msg(self):
        return '\n'.join([self.tt_default] + [f'RED: {k!r} ({v!r})' for k,v in self.state.items() if v])
    def on_custom_event(self, event):
        pass





# Quick actions
class QuickBreak(Helper, ttk.Button):
    def __init__(self, frm, text, **kwargs):
        super().__init__(frm, command=self.click, text=text, **kwargs)
    def click(self):
        mute[AUDIO_INPUT].click(True)
        mute[AUDIO_INPUT_BRCD].click(True)
        self.after(0, self.beep)
        switch(NOTES)
        gallery_size.save_last()
        gallery_size.update(0)
    def beep(self, phase=1):
        if phase == 1:
            obs.broadcast('playsound', 'high')
            return self.after(200, self.beep, 2)
        obs.broadcast('playsound', 'low')

class QuickBack(Helper, ttk.Button):
    def __init__(self, frm, scene, text, **kwargs):
        self.scene = scene
        super().__init__(frm, command=self.click, text=text, **kwargs)
    def click(self):
        import threading
        threading.Thread(target=self.run).start()
    def run(self):
        mute[AUDIO_INPUT].click(False)
        if quick_jingle.instate(('selected', )):
            playback_buttons['short'].play()
            time.sleep(3)
            quick_jingle.state(('!selected',))
        switch(self.scene)
        gallery_size.restore_last()


# Scenes
class SceneButton(Helper, Button):
    _instances = [ ]
    def __init__(self, frame, scene_name, label, selectable=True, **kwargs):
        self.scene_name = scene_name
        super().__init__(frame, text=label,
                         command=partial(switch, scene_name),
                         state='normal' if selectable else 'disabled',
                         **kwargs)
        self._instances.append(self)
        if not cli_args.test:
            current_scene = obs.scene
            if current_scene == scene_name:
                self.update_(True)
                indicators['live'].update_('scene-visible', scene_name if (scene_name not in SCENES_SAFE) else '')
                LOG.info("Init: Current scene %r", current_scene)
        obs._watch('scene', self.switched)
    @classmethod
    def switch(self, name):
        """Trigger a switch"""
        LOG.info('SceneButton: triggered scene %r', name)
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

class SceneLabel(SyncedLabel):
    scene_label = ''
    scene_name = ''
    def __init__(self, frm, *args, **kwargs):
        super().__init__(frm, *args, key='scene_humanname', **kwargs)
        #obs._watch_init('scene_humanname', self.update_)
    def tooltip(self):
        return '\n'.join(['Current scene',
                          f'{self.scene_label!r} ({self.scene_name!r})'])
    def watch(self, value):
        # value could be a scene name, or a preset label
        LOG.debug('SceneLabel: watching %r', value)
        if value in SCENE_NAMES:
            self.scene_name = value
            self.scene_label = scene_to_label(value)
        else:
            self.scene_label = value
            preset = Preset.by_label(value)
            if preset is not None:
                self.scene_name = preset.sbox_value.get()
            else:
                self.scene_name = ''
        #label = self.label = SCENE_NAMES.get(scene_name, (scene_name,))[0]
        super().watch(self.scene_label)
        if self.scene_name in SCENES_SAFE:
            color = default_color
        else:
            color = ACTIVE
        self.configure(background=color, activebackground=color)


# Audio
class Mute(Helper, Button):
    def __init__(self, frm, input_, text, enabled=True, **kwargs):
        self.state = None  # True = Muted, False = unmuted (LIVE)
        self.input = input_
        super().__init__(frm, text=text, command=self.click, state='normal' if enabled else 'disabled', **kwargs)
        if not cli_args.test:
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
            LOG.info("OBS: Mute %r to %r", data.input_name, data.input_muted)
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
        if not cli_args.test:
            dB = obsreq.get_input_volume(input_).input_volume_db
            LOG.info("OBS: %r %r (volume_state)", input_, dB)
            self.obs_update(dB)
        # Callback update
        obssubscribe(self.on_input_volume_changed)
    def to_dB(self, state):
        return - 10**(-state) + 1
    def to_state(self, dB):
        return -math.log10(-(dB-1))

    def update(self, state):
        state = float(state)
        dB = self.to_dB(state)
        #print(f'-> Setting volume: {state!r}     ->  {dB!r}')
        self.label.config(text=f"{dB:.1f} dB")
        self.last_dB = dB
        obsreq.set_input_volume(self.input, vol_db=dB)
    def obs_update(self, dB):
        #print('<=')
        state = self.to_state(dB)
        #print(f'<= Setting volume: {state!r}    <- {dB!r}')
        self.label.config(text=f"{dB:.1f} dB")
        self.value.set(state)
    def on_input_volume_changed(self, data):
        """Volume change callback"""
        if data.input_name == self.input:
            #print(f"OBS: Volume {data.input_name!r} to {data.input_volume_db!r}")
            self.obs_update(data.input_volume_db)



# Gallery
class GallerySize(Helper, ttk.Frame):
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
        if not cli_args.test:
            self.gallery_id = obsreq.get_scene_item_id(NOTES, GALLERY).scene_item_id
            obssubscribe(self.on_custom_event)
            if not cli_args.no_gallery_poll:
                self.update_gallery_size()
    def update(self, state):
        """Update callback of slider"""
        state = float(state)
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        indicators['live'].update_('gallery-size', 'visible' if state != 0 else None)

        self.scale.configure(background=color, activebackground=color)
        for scene in SCENES_WITH_RESIZEABLE_GALLERY:
            id_ = obsreq.get_scene_item_id(scene, GALLERY).scene_item_id
            transform = obsreq.get_scene_item_transform(scene, id_).scene_item_transform
            transform['scaleX'] = state
            transform['scaleY'] = state
            obsreq.set_scene_item_transform(scene, id_, transform)
    def save_last(self):
        """Save gallery size for future restoring"""
        self.last_state = self.value.get()
        # The custom event doesn't seem to work - somehow
        obsreq.broadcast_custom_event({'eventData': {'gallery_last_state': self.last_state}})
        obsreq.set_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', 'gallery_last_state', self.last_state)
    def restore_last(self):
        """Restore last gallery size"""
        self.update(self.last_state)
    def obs_update(self, state):
        """"Callabck for scale update from OBS"""
        if not math.isclose(self.value.get(), state, rel_tol=1e-5):
            indicators['live'].update_('gallery-size', 'visible' if state != 0 else None)
        self.value.set(state)
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        self.scale.configure(background=color, activebackground=color)
    def on_custom_event(self, data):
        """Custom event listener callback from OBS."""
        #print(f'OBS custom event: {vars(data)!r}')
        if hasattr(data, 'gallery_last_state'):
            self.last_state = data.gallery_last_state
            print(f"Saving last gallery size: {self.last_state!r}")
    def update_gallery_size(self):
        """The on_scene_item_transform_changed doesn't seem to work, so we have to poll here... unfortunately."""
        self.obs_update(obsreq.get_scene_item_transform(NOTES, self.gallery_id).scene_item_transform['scaleX'])
        self.after(1000, self.update_gallery_size)

# Gallery crop selection
def gallery_crop(n):
    print(f"GALLERY crop → {n} people")

    for scene in SCENES_WITH_GALLERY:  # TODO: with gallery
        id_ = obsreq.get_scene_item_id(scene, GALLERY).scene_item_id
        transform = obsreq.get_scene_item_transform(scene, id_).scene_item_transform
        #print('====old', transform)
        for (k,v) in GALLERY_CROP_FACTORS[n].items():
            transform['crop'+k.title()] = v
        #print('====new:', transform)
        obsreq.set_scene_item_transform(scene, id_, transform)

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
            print(f"OBS media state: {state!r}")
            self.after(500, self.update_timer)
            return
        if state != 'OBS_MEDIA_STATE_PLAYING':
            self.configure(text='-', background=default_color)
            print(f"OBS media state: {state!r}")
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
        print(f'setting input to {self.filename!r}')
        obsreq.set_input_settings(PLAYBACK_INPUT, {'local_file': self.filename}, overlay=True)
class PlayStop(Helper, ttk.Button):
    def __init__(self, frm, **kwargs):
        super().__init__(frm, text='StopPlay', command=self.stop, **kwargs)
    def stop(self):
        print("stopping playback")
        obsreq.trigger_media_input_action(PLAYBACK_INPUT, 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP')



class ScrollNotes(Helper, ttk.Button):
    """Button that will emit a keyboard event to the notes window.
    """
    def __init__(self, frm, label, event, **kwargs):
        self.event = event
        super().__init__(frm, text=label, command=self.click, **kwargs)
    def click(self):
        obs['notes_scroll'] = self.event
    def on_custom_event(self, event):
        pass
class ScrollNotesAuto(SyncedCheckbutton):
    """Checkbox that, when enabled, will periodically scroll the notes to the bottom.
    """
    state_ = None
    scroll_id = None
    delay = 10000 # ms
    def __init__(self, *args, **kwargs):
        super().__init__(*args, name='notes_scroll_auto', text="Auto-scroll", **kwargs)
    def tooltip(self):
        return f"When checked, emit a PgDn event on the notes every {self.delay//1000} seconds."
    def update_(self, value):
        super().update_(value)
        self.state_ = value
        if value:
            # the scroll ID is used to prevent multiple watchers from going at
            # the same time
            scroll_id = self.scroll_id = random.randint(0, 2**64-1)
            if cli_args.broadcaster:
                self.do_scroll(scroll_id)
    def do_scroll(self, scroll_id):
        if self.scroll_id != scroll_id or not self.state_:
            return
        notes_scroll('Next')
        LOG.info("Scrolling notes (auto)...")
        self.after(self.delay, self.do_scroll, scroll_id)





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


class Preset():
    _instances = [ ]
    def __init__(self, frame, name, label, row, column, **kwargs):
        self.name = name
        self.label = label
        self._last_scene = None
        self._last_res = None
        self._instances.append(self)

        self.button = Button(frame, text=label, command=self.click)
        self.button.grid(row=row, column=column)
        ToolTip(self.button, lambda: f'Switch to preset {self.label!r}\n(Internal name: {self.name})', delay=TOOLTIP_DELAY)

        # Scene choices
        self.sbox_value = StringVar()
        self.sbox = OptionMenu(frame, self.sbox_value,
                               '-', *[scene_to_label(x) for x in SCENE_NAMES],
                               command=self.click_sbox)
        self.sbox.grid(row=row, column=column+1)
        ToolTip(self.sbox, lambda: f'Scene for preset {self.label!r}', delay=TOOLTIP_DELAY)

        # Resolution choices
        self.rbox_value = StringVar()
        self.rbox = OptionMenu(frame, self.rbox_value, '-', *SCREENSHARE_SIZES,
                               command=self.click_rbox)
        self.rbox.grid(row=row, column=column+2)
        ToolTip(self.rbox, lambda: f'Zoom capture resolution for preset {self.label!r}', delay=TOOLTIP_DELAY)

        self.rename_button = Button(frame, text='r', command=self.rename)
        self.rename_button.grid(row=row, column=column+3)
        ToolTip(self.rename_button, lambda: f"Rename {self.label!r}")

        obs._watch_init('scene', self.watch_scene)
        obs._watch_init('ss_resolution', self.watch_resolution)
        obs._watch_init(f'preset-{self.name}-sbox', self.watch_sbox)
        obs._watch_init(f'preset-{self.name}-rbox', self.watch_rbox)
        obs._watch_init(f'preset-{self.name}-label', self.watch_label)

    @classmethod
    def by_label(cls, label):
        for instance in cls._instances:
            if instance.label == label:
                return instance

    def click(self):
        """Button is clicked.  Switch to this preset"""
        switch(self.label)
    def _switch_to(self):
        old_scene_name = obs.scene
        scene_name = label_to_scene(self.sbox_value.get())
        resolution = self.rbox_value.get()
        print(f'Setting to preset {self.label!r} ({scene_name!r} at {resolution!r})')
        w, h = resolution.split('x')
        if w.isdigit and h.isdigit():
            w = int(w)
            h = int(h)
            set_resolution(w, h)
            obs.ss_resolution = resolution
            if old_scene_name not in SCENES_REMOTE and scene_name in SCENES_REMOTE:
                # We can't wait in this thread since the resolution callback
                # needs to run in the meantime while waiting.
                self.button.after(int(0.1*1000), self._switch_to_callback, scene_name)
                return
        self._switch_to_callback(scene_name)
    def _switch_to_callback(self, scene_name):
        """Callback of _switch_to, see comment there for why this is needed"""
        obs.scene = scene_name
        SceneButton.switch(scene_name)

    def click_sbox(self, name):
        name = label_to_scene(name)
        obs[f'preset-{self.name}-sbox'] = name
    def click_rbox(self, name):
        obs[f'preset-{self.name}-rbox'] = name

    def watch_scene(self, name):
        self._last_scene = name or '-'
        self.update_()
    def watch_resolution(self, res):
        self._last_res = res or '-'
        self.update_()
    def watch_label(self, label):
        if label:
            self.label = label
            self.button.configure(text=label)

    def watch_sbox(self, value):
        LOG.debug('watch sbox')
        self.sbox_value.set(scene_to_label(value) or '-')
        self.update_()
    def watch_rbox(self, value):
        LOG.debug('watch rbox')
        self.rbox_value.set(value or '-')
        self.update_()

    def update_(self):
        """Update coloring"""
        LOG.debug('preset-%s: %r = %r', self.name, self._last_scene, self.sbox_value.get())
        LOG.debug('preset-%s: %r = %r', self.name, self._last_res, self.rbox_value.get())
        state = (self._last_scene == label_to_scene(self.sbox_value.get())
                 and self._last_res == self.rbox_value.get() )
        if state and self._last_scene in SCENES_SAFE:
            color = ACTIVE_SAFE
        elif state:
            color = ACTIVE
        else:
            color = default_color
        if self.sbox_value.get() == '-':
            self.button['state'] = 'disabled'
        else:
            self.button['state'] = 'normal'
        self.button.configure(background=color, activebackground=color)

    def rename(self):
        dialog = Toplevel()
        dialog.wm_title(f"Rename {self.name!r}.")
        newname = ttk.Entry(dialog, text=self.label)
        newname.grid(row=0, column=0, columnspan=2)

        def do_rename():
            label = newname.get()
            self.label = label
            if not label:
                LOG.error("A renamed label can not be blank: %r", label)
            elif label in SCENE_NAMES:
                LOG.error("A renamed label can be the same as a scene name: %r", label)
            elif self.label in [x.label for x in Preset._instances if x is not self]:
                LOG.error("A renamed label can not be the same as an existing label: %r", label)
            else:
                obs[f'preset-{self.name}-label'] = label
            dialog.destroy()

        ok = ttk.Button(dialog, text=f"Rename {self.label!r}", command=do_rename)
        ok.grid(row=1, column=1)
        cancel = ttk.Button(dialog, text="Cancel", command=dialog.destroy)
        cancel.grid(row=1, column=0)




#
# Quick actions
#
class QuickBackSelect(Helper, ttk.OptionMenu):
    def __init__(self, frm, name, **kwargs):
        self.value = StringVar()
        self.name = name
        super().__init__(frm, self.value, '-', *self.options, command=self.click,
                         **kwargs)
        #self.value.set(obs[f'quickback-{self.name}-value'] or '-')
        obs._watch_init(f'quickback-{self.name}-value', self.update_)
        for preset in Preset._instances:
            obs._watch(f'preset-{preset.name}-label', self.update_options)
            obs._watch(f'preset-{preset.name}-sbox', self.update_options)

    @property
    def options(self):
        return ['-'] + [x.label for x in Preset._instances if x.sbox_value.get() not in {'-', None}] + list(SCENE_NAMES)
    def update_options(self, _=None):
        self.update_()
    def update_(self, name=None):
        old = self.value.get()
        options = self.options
        self.set_menu('-', *self.options)
        if old in options:
            self.value.set(name or old or '-')
        else:
            self.value.set('-')
    def click(self, name):
        obs[f'quickback-{self.name}-value'] = name


class QuickBackGo(Helper, ttk.Button):
    def __init__(self, frm, menu, *args, **kwargs):
        self.menu = menu
        super().__init__(frm,*args,
                         text="BACK" + ("" if cli_args.small else " to ->"),
                         command=self.click,
                         **kwargs)
        ToolTip(self, self._tooltip, delay=TOOLTIP_DELAY)
    def _tooltip(self):
        return textwrap.dedent(f"""\
        Go back to the program, after a three second countdown (3...2...1...0).
        Switch to {self.menu.value.get()}
        Play jingle = {quick_jingle.instate(('selected', ))}
        Unmute broadcaster audio = {quick_brcd.instate(('selected', ))}\
        """)
    i = 0
    def beep(self, counter):
        """Callback for beeping.  Trigger a counter-second countdown

        Final beep on 0.  For example beep(3) triggers: 'b ... b ... b ... B'  Each interval is 3 s for a total of 3s.  ."""
        LOG.debug('beeping for back, counter={counter}')
        if counter < 0:
            obs.broadcast('playsound', 'high')
            return
        if counter == 0:
            self.after(200, self.beep, counter-1)
        else:
            self.after(1000, self.beep, counter-1)
        obs.broadcast('playsound', 'low')


    def click(self, phase=1):
        scene = self.menu.value.get()
        if scene == '-' or not scene:
            LOG.warning("QuickBack with scene %r, doing nothing", scene)
            return
        if phase == 1:
            # Do this when the button is first clicked
            LOG.info("QuickBack phase 1: %r", scene)
            self.beep(3)
            if quick_jingle.instate(('selected', )):
                playback_buttons['short'].play()
            return self.after(3500, partial(self.click, phase=2))
        # Only go directly here if no jingle.  If jingle, go here on callback.
        LOG.info("QuickBack phase 2: %r", scene)
        # Unmute the audio
        mute[AUDIO_INPUT].click(False)
        if quick_brcd.instate(('selected', )):
            mute[AUDIO_INPUT_BRCD].click(False)
        # Reset check boxes to default
        quick_jingle.click(False)
        quick_brcd.click(False)
        switch(scene)
        gallery_size.restore_last()




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
    parser.add_argument('--scene-hook', action=DictAction, nargs=1,
                        help="Local command line hooks for switching to each scene, format SCENENAME=command")
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
    global obsreq
    global obssubscribe
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

    obs = ObsState(obsreq, cl)


    #
    # GUI setup
    #
    #root = Tk()
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
    #default_color = root.cget("background")
    #default_activecolor = default_color
    #color_default = {'background': default_color, 'activebackground': default_color}


    # Indicator lights
    global indicators
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
    global quick_jingle
    global quick_brcd
    if not cli_args.small:
        qa_label = ttk.Label(frm, text="QuickAct:")
        qa_label.grid(row=1, column=0)
        ToolTip(qa_label, "Quick actions.  Clicking quickly cuts you away from / back to the program.", delay=TOOLTIP_DELAY)
    #l2 = Label2(frm, text="Presets:", grid=g(1, 0))
    QuickBreak(frm, 'BREAK', tooltip='Go to break.\nMute audio, hide GALLERY, and swich to Notes',
               grid=g(1,1), grid_s=g(1,1))
    quick_jingle = SyncedCheckbutton(frm, grid=g(row=1, column=7), name='quick_jingle', text="Jingle?", onvalue=True, offvalue=False)
    quick_jingle.state(('!alternate',))
    quick_brcd = SyncedCheckbutton(frm, grid=g(row=1, column=6), name='quick_brcd', text="Brcd Audio?", onvalue=True, offvalue=False, tooltip="If checked, also unmute the broadcaster's microphone when returning.")
    quick_brcd.grid(row=1, column=6)
    quick_brcd.state(('!alternate', 'disabled' if not cli_args.broadcaster else ''))
    ToolTip(quick_jingle,
            "Play short sound when coming back from break?\n"
            "If yes, then unmute, play jingle for 3s, then switch scene and increase gallery size.\n"
            "if no, immediately restore the settings.", delay=TOOLTIP_DELAY)
    if not cli_args.small:
        #QuickBack(frm, 'Screenshare',         'BACK(SS-P) ',  grid=g(1,2), tooltip='Back from break\nSwitch to Screenshare, \ntry to restore settings')
        #QuickBack(frm, 'ScreenshareCrop',     'BACK(SS-C)', grid=g(1,3), tooltip='Back from break\nSwitch to Screenshare, cropped landscape mode, \ntry to restore settings')
        #QuickBack(frm, 'ScreenshareLandscape','BACK(SS-LS)',grid=g(1,4), tooltip='Back from break\nSwitch to Screenshare-Landscape\nNotes, \ntry to restore settings')
        #QuickBack(frm, NOTES,                 'BACK(n)',    grid=g(1,6), tooltip='Back from break\nSwitch to Notes,\ntry to restore settings')
        pass


    # Scene selection
    if not cli_args.small:
        scene_label = ttk.Label(frm, text='Scene:')
        scene_label.grid(row=2, column=0)
        ToolTip(scene_label, "Raw scene selection")
    scene_frame = ttk.Frame(frm)
    if not cli_args.small:
        scene_frame.grid(row=2, column=1, columnspan=7)
    for i, (scene, (label, tooltip, selectable)) in enumerate(SCENE_NAMES.items()):
        b = SceneButton(scene_frame, scene_name=scene, label=label, selectable=selectable,
                        tooltip=tooltip+f'\n(OBS scene name: {scene})',
                        grid=g(2, i))
    if cli_args.small:
        SceneLabel(frm, grid_s=g(1,0))

    # Audio
    global mute
    if not cli_args.small:
        audio_l = ttk.Label(frm, text="Audio:")
        audio_l.grid(row=6, column=0)
        ToolTip(audio_l, "Audio controls (mute/unmute/level)", delay=TOOLTIP_DELAY)
    mute = { }
    mute[AUDIO_INPUT_BRCD] = Mute(frm, AUDIO_INPUT_BRCD, "Brcd", grid=g(6, 1), tooltip="Broadcaster microphone, red=ON.  Only broadcaster can control", enabled=cli_args.broadcaster)
    mute[AUDIO_INPUT]      = Mute(frm, AUDIO_INPUT,     "Instr", grid=g(6, 2), tooltip="Mute/unmute instructor capture, red=ON", )
    volume = Volume(frm, AUDIO_INPUT, grid=g(row=6, column=3, columnspan=4, sticky=E+W))


    # gallery size
    global gallery_size
    if not cli_args.small:
        b_gallery = ttk.Label(frm, text="Gallery size:")
        b_gallery.grid(row=7, column=0)
        ToolTip(b_gallery, "Change size of instuctor picture-in-picture.", delay=TOOLTIP_DELAY)
    gallery_size = GallerySize(frm, grid=g(row=7, column=1, columnspan=6, sticky=E+W))
    if not cli_args.small:
        b_cropbuttons = ttk.Label(frm, text="Gallery crop:")
        b_cropbuttons.grid(row=8, column=0)
        ToolTip(b_cropbuttons,
            "Gallery insert can be cropped to suit different numbers of people (this comes from "
            "how Zoom lays it out for different numbers of people.  Click a button if "
            "it doesn't fit right into the corner.", delay=TOOLTIP_DELAY)
    crop_buttons = ttk.Frame(frm)
    crop_buttons.columnconfigure(tuple(range(5)), weight=1)
    crop_buttons.grid(row=8, column=1, columnspan=5)
    for i, (n, label) in enumerate([(None, 'None'), (1, 'n=1'), (2, 'n=2'), (3, 'n=3-4'), (5, 'n=5-6')]):
        b = ttk.Button(crop_buttons, text=label, command=partial(gallery_crop, n))
        if not cli_args.small:
            b.grid(row=0, column=i)
        ToolTip(b, 'Set Gallery to be cropped for this many people.  None=no crop', delay=TOOLTIP_DELAY)


    # Audo jingle playback
    global playback_buttons
    if not cli_args.small:
        playback_label = ttk.Label(frm, text="Jingle:")
        playback_label.grid(row=9, column=0)
        ToolTip(playback_label, "Row deals with playing transition sounds", delay=TOOLTIP_DELAY)
    playback = PlaybackTimer(frm, PLAYBACK_INPUT, grid=g(9, 1), grid_s=g(1, 3), tooltip="Countdown time for current file playing")
    playback_buttons = { }
    for i, file_ in enumerate(PLAYBACK_FILES, start=2):
        pf = playback_buttons[file_['label']] = PlayFile(frm, **file_, grid=g(9, i))
    ps = PlayStop(frm, grid=g(9, 2+len(PLAYBACK_FILES)), tooltip="Stop all playbacks")


    # Scroll notes
    sn_frame= ttk.Frame(frm)
    sn_frame.columnconfigure(tuple(range(3)), weight=1)
    if cli_args.small:
        sn_frame.grid(row=1, column=4, columnspan=7)
    else:
        sn_frame.grid(row=11, column=0, columnspan=6)
    sn_label = Label(sn_frame, text="Notes scroll:")
    sn_label.grid(row=0, column=0)
    ToolTip(sn_label, "Tools for scrolling notes up and down (on the broadcaster computer), in the Notes view.", delay=TOOLTIP_DELAY)
    b = ScrollNotes(sn_frame, "Up",   event='Up',   grid=g(0,1), grid_s=g(0,1), tooltip="Scroll notes up")
    b = ScrollNotes(sn_frame, "Down", event='Down', grid=g(0,2), grid_s=g(0,2), tooltip="Scroll notes down")
    b = ScrollNotes(sn_frame, "PgUp", event='Prior',grid=g(0,3),                tooltip="Scroll notes PgUp")
    b = ScrollNotes(sn_frame, "PgDn", event='Next', grid=g(0,4),                tooltip="Scroll notes PgDn")
    b = ScrollNotes(sn_frame, "End",  event='End',  grid=g(0,5),                tooltip="Scroll notes End key")
    b = ScrollNotesAuto(sn_frame, grid=g(0,6))



    # Presets
    l_presets = SyncedLabel(frm, key=None, text="Scene presets:", grid=g(row=3, column=0),
                            tooltip="Scene presets.  You can configure various presets and quickly jump to them.  Presets consist of a name, which scene, and resolution of the Zoom window.")
    l_presets_size = SyncedLabel(frm, 'ss_resolution', grid=g(row=4, column=0), tooltip="Last set Zoom resolution")
    f_presets = ttk.Frame(frm)
    if not cli_args.small:
        f_presets.grid(row=3, column=1, rowspan=3, columnspan=8, sticky=NSEW)
    ttk.Separator(f_presets, orient=VERTICAL).grid(column=4, row=0, rowspan=3, sticky=NS)
    f_presets.columnconfigure((0,1,2,5,6,7), weight=15)
    f_presets.columnconfigure((3,8), weight=5)
    f_presets.columnconfigure((4), minsize=20)
    preset_a = Preset(f_presets, 'preset-a', "A", row=0, column=0)
    preset_b = Preset(f_presets, 'preset-b', "B", row=0, column=5)
    preset_c = Preset(f_presets, 'preset-c', "C", row=1, column=0)
    preset_d = Preset(f_presets, 'preset-d', "D", row=1, column=5)
    preset_e = Preset(f_presets, 'preset-e', "E", row=2, column=0)
    preset_f = Preset(f_presets, 'preset-f', "F", row=2, column=5)

    qbs = QuickBackSelect(frm, name='quickback-a', grid=g(row=1, column=4))
    qbg = QuickBackGo(frm, qbs, grid=g(row=1, column=3), grid_s=g(row=1, column=2))



    # Other watchers (not displayed on the control panel)
    if cli_args.notes_window:
        obs._watch('notes_scroll', notes_scroll)
    obs._watch('playsound', play)

    # begin
    print('starting...')
    root.mainloop()


if __name__ == "__main__":
    main()

