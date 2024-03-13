from functools import partial
import math
import time

from tkinter import *
from tkinter import ttk
from tktooltip import ToolTip

# pylint: disable=redefined-outer-name


ACTIVE = 'red'
ACTIVE_SAFE = 'orange'
AUDIO_INPUT = 'Instructors'
AUDIO_INPUT_BRCD = 'BroadcasterMic'
NOTES = 'Notes'
SCENE_NAMES = {
    # obs_name: (label, tooltip),
    'Title': ('Title', 'Title screen with logo', True),
    'Gallery': ('Gallery', 'All instructors gallery', True),
    'Screenshare': ('Screen', 'Screenshare, normal portrait mode', True),
    'ScreenshareCrop': ('ScrLSCrp', 'Screenshare, landscape share but crop portrait out of the left 840 pixels (requires local setup)', True),
    'ScreenshareLandscape': ('ScreenLS', 'Screenshare, landscape mode (requires local setup)', True),
    'Broadcaster-Screen': ('BrdScr', 'Broadcaster local screen (only broadcaster may select)', False),
    NOTES: ('Notes', 'Notes', True),
    'Empty': ('Empty', 'Empty black screen', True),
    }
SCENES_WITH_PIP = ['Screenshare', 'ScreenshareCrop', 'ScreenshareLandscape', 'Broadcaster-Screen', NOTES]
SCENES_SAFE = ['Title', NOTES, 'Empty'] # scenes suitable for breaks
PIP = '_GalleryCapture[hidden]'
PLAYBACK_INPUT = 'CRaudio'  # for playing transitions sounds, etc.

root = Tk()
root.title("OBS CodeRefinery control")
frm = ttk.Frame(root)
frm.columnconfigure(tuple(range(10)), weight=1)
frm.rowconfigure(tuple(range(10)), weight=1)
frm.grid()
frm.pack()
#ttk.Label(frm, text="Hello World!").grid(column=0, row=0)
default_color = root.cget("background")
t = ttk.Label(frm, text=time.strftime('%H:%M:%S'))
t.grid(row=0, column=0)
def update_time():
    t.config(text=time.strftime('%H:%M:%S'))
    t.after(1000, update_time)
update_time()
ttk.Button(frm, text="Quit", command=root.destroy).grid(column=1, row=0)




# Quick actions
#def quick_break():
#    mute_toggle(True)
#    switch(NOTES)
#    pip_size.update(0, save=True)
#def quick_back(scene=NOTES):
#    print(scene)
#    mute_toggle(False)
#    switch(scene)
#    pip_size.update(pip_size.last_state)
#    playback_buttons['short'].play()
class QuickBreak(ttk.Button):
    def __init__(self, frm, text, tooltip=None, grid=None):
        super().__init__(frm, command=self.click, text=text)
        if grid:
            self.grid(row=grid[0], column=grid[1])
        ToolTip(self, f"Switch to {NOTES}, mute all audio, pip size to 0.")
    def click(self):
        mute[AUDIO_INPUT].click(True)
        mute[AUDIO_INPUT_BRCD].click(True)
        switch(NOTES)
        pip_size.update(0, save=True)
        if tooltip:
            ToolTip(self, tooltip, delay=1)
class QuickBack(ttk.Button):
    def __init__(self, frm, scene, text, tooltip=None, grid=None):
        self.scene = scene
        super().__init__(frm, command=self.click, text=text)
        if tooltip:
            ToolTip(self, tooltip, delay=1)
        if grid:
            self.grid(row=grid[0], column=grid[1])
    def click(self):
        import threading
        threading.Thread(target=self.run).start()
    def run(self):
        mute[AUDIO_INPUT].click(False)
        if quick_sound.state() == ('selected', ):
            playback_buttons['short'].play()
            time.sleep(3)
        switch(self.scene)
        pip_size.update(pip_size.last_state)
        print('sound state: ', quick_sound.state())
ttk.Label(frm, text="Quick actions:").grid(row=1, column=0)
QuickBreak(frm, 'BREAK', tooltip='Go to break.  Mute audio, hide PIP, and swich to Notes', grid=(1,1))
QuickBack(frm, 'Screenshare',       'BACK(ss) ',     tooltip='Back from break (screenshare), \ntry to restore settings', grid=(1,2))
QuickBack(frm, 'ScreenshareLandscape',   'BACK(ss-ls)',  tooltip='Back from break (notes), \ntry to restore settings',  grid=(1,3))
QuickBack(frm, 'ScreenshareCrop', 'BACK(ss-c)', tooltip='Back from break (screenshare, cropped landscape mode), \ntry to restore settings',grid=(1,4))
QuickBack(frm, NOTES,         'BACK(n)',       tooltip='Back from break (notes),\ntry to restore settings',                grid=(1,5))
quick_sound = ttk.Checkbutton(frm, text="Jingle?", onvalue=True, offvalue=False)
quick_sound.grid(row=1, column=7)
ToolTip(quick_sound, "Play short sound when coming back from break?\nIf yes, then unmute, play jingle for 3s, then switch scene and increase PIP size.")


# Scenes
def switch(name, from_obs=False):
    print(f'switching to {name}')
    # Disable currently active buttons
    for n, b in SCENES.items():
        if name != n:
            b.configure(background=default_color, activebackground=default_color)
    if name not in SCENES:
        print(f"Unknown scene {name}")
        return
    # Set new button
    if not from_obs:
        cl1.set_current_program_scene(name)
    color = ACTIVE
    if name in SCENES_SAFE:
        color = ACTIVE_SAFE
    SCENES[name].configure(background=color, activebackground=color)
    #SCENES[name].configure()
SCENES = { }
for i, (scene, (label, tooltip, selectable)) in enumerate(SCENE_NAMES.items()):
    b = SCENES[scene] = Button(frm, text=label, command=partial(switch, scene),
                               state='normal' if selectable else 'disabled')
    b.grid(column=i, row=2)
    if tooltip:
        ToolTip(b, tooltip, delay=1)



# Audio
class Mute(Button):
    def __init__(self, frm, input_, text, enabled=True, tooltip=None, grid=None):
        self.state = None
        self.input = input_
        super().__init__(frm, text=text, command=self.click, state='normal' if enabled else 'disabled')
        if tooltip:
            ToolTip(self, tooltip, delay=1)
        if grid:
            self.grid(row=grid[0], column=grid[1])
    def click(self, state=None):
        if state is None:
            state = not self.state
        self.obs_update(state)  # update colors
        cl1.set_input_mute(AUDIO_INPUT, state)
    def obs_update(self, state):
        self.state = state
        if state: # mute on
            self.configure(background=default_color, activebackground=default_color)
        else:    # mute off
            self.configure(background=ACTIVE, activebackground=ACTIVE)
class Volume(ttk.Frame):
    def __init__(self, frame, input_):
        self.input = input_
        super().__init__(frame)
        self.value = DoubleVar()
        self.scale = Scale(self, from_=-2, to=0, orient=HORIZONTAL, command=self.update, showvalue=0, resolution=.05, variable=self.value)
        self.scale.grid(row=0, column=0, columnspan=5, sticky=E+W)
        ToolTip(self.scale, "Current instructor audio gain", delay=1)
        self.label = ttk.Label(self, text="x");
        self.label.grid(row=0, column=5)
        self.columnconfigure(tuple(range(6)), weight=1)
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
        cl1.set_input_volume(self.input, vol_db=dB)
    def obs_update(self, dB):
        print('<=')
        state = self.to_state(dB)
        print(f'<= Setting volume: {state}    <- {dB}')
        self.label.config(text=f"{dB:.1f} dB")
        self.value.set(state)

mute = { }
mute[AUDIO_INPUT_BRCD] = mute_inst = Mute(frm, AUDIO_INPUT_BRCD, " Brcd", tooltip="Broadcaster microphone, red=ON.  Only broadcaster can control", enabled=False, grid=(3, 0))
mute[AUDIO_INPUT] = Mute(frm, AUDIO_INPUT, " Instr", tooltip="Mute/unbute instructor capture, red=ON", grid=(3, 1))
volume = Volume(frm, AUDIO_INPUT)
volume.grid(row=3, column=2, columnspan=5, sticky=E+W)


# PIP
CROP_FACTORS = {
    None: {'top':  0, 'bottom':  0, 'left':  0, 'right':  0, },
    1:    {'top':  0, 'bottom':  0, 'left': 59, 'right':  59, },
    2:    {'top': 90, 'bottom':  0, 'left': 12, 'right': 12, },  # checked
    3:    {'top':  4, 'bottom':  0, 'left': 60, 'right': 60, },  # checked
    5:    {'top': 50, 'bottom':  0, 'left': 11, 'right': 11, },  # checked
    }
#def pip_size(scale, from_obs=False, save=False):
#    scale = float(scale)
#    if save:
#        pip.last_scale = pip.scale
#    #print(f'PIP size: {scale}')
#    pip_value.config(text=f"{scale:0.2f}")
#    pip.scale = scale
#    if scale == 0:
#        color = default_color
#    else:
#        color = ACTIVE
#    if from_obs:
#        pip.set(scale)
#    for scene in SCENES_WITH_PIP:
#        pip.configure(background=color, activebackground=color)
#        if not from_obs:
#            id_ = cl1.get_scene_item_id(scene, PIP).scene_item_id
#            transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
#            transform['scaleX'] = scale
#            transform['scaleY'] = scale
#            cl1.set_scene_item_transform(scene, id_, transform)
class PipSize(ttk.Frame):
    def __init__(self, frame):
        self.last_state = 0.25
        super().__init__(frame)
        self.value = DoubleVar()
        self.scale = Scale(self, from_=0, to=1, orient=HORIZONTAL, command=self.update, showvalue=0, resolution=.01, variable=self.value)
        self.scale.grid(row=0, column=0, columnspan=5, sticky=E+W)
        ToolTip(self.scale, "Cchange the size of the instructor picture-in-picture", delay=1)
        self.label = ttk.Label(self, text="?");
        self.label.grid(row=0, column=5)
        self.columnconfigure(tuple(range(6)), weight=1)
    def update(self, state, save=False):
        state = float(state)
        if save:
            self.last_state = self.value.get()
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        self.scale.configure(background=color, activebackground=color)
        for scene in SCENES_WITH_PIP:
            id_ = cl1.get_scene_item_id(scene, PIP).scene_item_id
            transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
            transform['scaleX'] = state
            transform['scaleY'] = state
            cl1.set_scene_item_transform(scene, id_, transform)
    def obs_update(self, state):
        self.value.set(state)
        self.label.configure(text=f"{state:0.2f}")
        if state == 0:   color = default_color
        else:            color = ACTIVE
        self.scale.configure(background=color, activebackground=color)

b_pip = ttk.Label(frm, text="PIP size:")
b_pip.grid(row=4, column=0)
pip_size = PipSize(frm)
pip_size.grid(row=4, column=1, columnspan=6, sticky=E+W)
# PIP crop selection
def pip_crop(n):
    print(f"PIP crop → {n} people")

    for scene in SCENES_WITH_PIP:
        id_ = cl1.get_scene_item_id(scene, PIP).scene_item_id
        transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
        #print('====old', transform)
        for (k,v) in CROP_FACTORS[n].items():
            transform['crop'+k.title()] = v
        #print('====new:', transform)
        cl1.set_scene_item_transform(scene, id_, transform)
ttk.Label(frm, text="PIP crop:").grid(row=5, column=0)
crop_buttons = ttk.Frame(frm)
crop_buttons.columnconfigure(tuple(range(5)), weight=1)
crop_buttons.grid(row=5, column=1, columnspan=5)
for i, (n, label) in enumerate([(None, 'None'), (1, 'n=1'), (2, 'n=2'), (3, 'n=3-4'), (5, 'n=5-6')]):
    b = ttk.Button(crop_buttons, text=label, command=partial(pip_crop, n))
    b.grid(row=0, column=i)
    ToolTip(b, 'Set PIP to be cropped for this many people.  None=no crop', delay=1)


# Playback
playback_label = ttk.Label(frm, text="Jingle:")
playback_label.grid(row=6, column=0)
ToolTip(playback_label, f"Row deals with playing transition sounds", delay=1)
class PlaybackTimer(ttk.Label):
    def __init__(self, frm, input_name, *args):
        self.input_name = input_name
        super().__init__(frm, *args)
        self.configure(text='x')
    def update_timer(self):
        event = cl1.get_media_input_status(self.input_name)
        duration = event.media_duration
        cursor = event.media_cursor
        state = event.media_state  # 'OBS_MEDIA_STATE_PAUSED', 'OBS_MEDIA_STATE_PLAYING'
        if state != 'OBS_MEDIA_STATE_PLAYING':
            self.configure(text='-', background=default_color)
            return
        if duration < 0:
            self.after(500, self.update_timer)
            return
        def s_to_mmss(s):
            return f'{s//60}:{s%60:02}'
        self.configure(text=f'-{s_to_mmss((duration-cursor)//1000)}/{s_to_mmss(duration//1000)}',
                       background=ACTIVE)
        self.after(500, self.update_timer)
playback = PlaybackTimer(frm, PLAYBACK_INPUT)
playback.grid(row=6, column=1)
ToolTip(playback, f"Countdown time for current file playing", delay=1)
class PlayFile(ttk.Button):
    def __init__(self, frm, filename, label, tooltip):
        self.filename = filename
        super().__init__(frm, text=label, command=self.play)
        ToolTip(self, tooltip, delay=1)
    def play(self):
        print(f'setting input to {self.filename}')
        cl1.set_input_settings(PLAYBACK_INPUT, {'local_file': self.filename}, overlay=True)
playback_files = [
    {'filename': '/home/rkdarst/git/coderefinery-artwork/audiologo/CR_LOGO_Jingle_long.mp3',
     'label': 'long',
     'tooltip': 'Long theme song for starting/ending day, 1:23 duration'},
    {'filename': '/home/rkdarst/git/coderefinery-artwork/audiologo/CR_LOGO_sound_short.mp3',
     'label': 'short',
     'tooltip': 'Short audio for coming back from breaks, 0:03 duration'},
    ]
playback_buttons = { }
for i, file_ in enumerate(playback_files, start=2):
    pf = playback_buttons[file_['label']] = PlayFile(frm, **file_)
    pf.grid(row=6, column=i)
    ToolTip(pf, f"Play the audio file {file_['label']}", delay=1)
class PlayStop(ttk.Button):
    def __init__(self, frm):
        super().__init__(frm, text='StopPlay', command=self.stop)
    def stop(self):
        print("stopping playback")
        cl1.trigger_media_input_action(PLAYBACK_INPUT, 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP')
ps = PlayStop(frm)
ps.grid(row=6, column=6)
ToolTip(ps, "Stop all playbacks", delay=1)

# Announcement text
#def ann_toggle():
#    if ann_toggle = False
#    for scene in SCENES:
#        id_ = cl1.get_scene_item_id(scene, 'Announcement'.scene_item_id
#        transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
#
#def ann_update(text=None, from_obs=False):
#    if from_obs: # set value
#        ann.set(text)
#    text = ann.get()
#    print(text)
#    cl1.set_input_settings('Announcement', {'text': text}, True)
#ann_toggle = Button(frm, text="Ann text", command=ann_toggle) ; ann_toggle.grid(row=6, column=0)
#ann_toggle.state = False
#ToolTip(ann_toggle, 'Toggle anouncement text visibility.', delay=1)
#ann = Entry(frm) ; ann.grid(row=6, column=1, columnspan=6, sticky=W+E)
#b = Button(frm, text="Update", command=ann_update) ; b.grid(row=6, column=5)
#ToolTip(b, 'Update the announcement text in OBS', delay=1)

import argparse
import os
parser = argparse.ArgumentParser()
parser.add_argument('hostname_port')
parser.add_argument('password', default=os.environ.get('OBS_PASSWORD'),
                  help='or set env var OBS_PASSWORD')
args = parser.parse_args()
hostname = args.hostname_port.split(':')[0]
port = args.hostname_port.split(':')[1]
password = args.password

# OBS websocket
import obsws_python as obs
cl1 = obs.ReqClient(host=hostname, port=port, password=password, timeout=3)
cl = obs.EventClient(host=hostname, port=port, password=password, timeout=3)

# Initialize with our current state
# scene
switch(cl1.get_current_program_scene().current_program_scene_name, from_obs=True)
# audio mute
for input_ in mute:
    mute[input_].obs_update(cl1.get_input_mute(input_).input_muted)
# audio volume
dB = cl1.get_input_volume(volume.input).input_volume_db
print(f"from OBS: {dB} (volume_state)")
volume.obs_update(dB)
# pip size
pip_id = cl1.get_scene_item_id(NOTES, PIP).scene_item_id
def update_pip_size():
    """The on_scene_item_transform_changed doesn't seem to work, so we have to poll here... unfortunately."""
    pip_size.obs_update(cl1.get_scene_item_transform(NOTES, pip_id).scene_item_transform['scaleX'])
    pip_size.after(1000, update_pip_size)
update_pip_size()


def on_current_program_scene_changed(data):
    """Scene changing"""
    #print(data.attrs())
    print(f"OBS: scene to {data.scene_name}")
    switch(data.scene_name, from_obs=True)
def on_input_volume_changed(data):
    """Volume change"""
    #print(data.attrs())
    #print(data.input_name, data.input_volume_db)
    if data.input_name == volume.input:
        print(f"OBS: Volume {data.input_name} to {data.input_volume_db}")
        volume.obs_update(data.input_volume_db)
def on_input_mute_state_changed(data):
    """Muting/unmuting"""
    #print(data.attrs())
    if data.input_name in mute:
        print(f"OBS: mute {data.input_name} to {data.input_muted}")
        mute[data.input_name].obs_update(state=data.input_muted)
def on_media_input_playback_started(data):
    """Playing media"""
    print("OBS: media playback started")
    playback.update_timer()
def on_scene_item_transform_changed(data):
    """PIP size change"""
    print(f"OBS: transform change of {data.scene_item_id}")
    if data.scene_item_id == pip_id:
        pip_size.obs_update(data.scene_item_transform['scaleX'])


cl.callback.register([
    on_current_program_scene_changed,
    on_input_volume_changed,
    on_input_mute_state_changed,
    on_media_input_playback_started,
    #on_scene_item_transform_changed,
    ])

import logging
#logging.basicConfig(level=logging.DEBUG)

#import IPython ; IPython.embed()

print('starting...')
root.mainloop()
