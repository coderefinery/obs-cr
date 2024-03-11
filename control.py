from functools import partial
from math import log10
import time

from tkinter import *
from tkinter import ttk
from tktooltip import ToolTip


ACTIVE = 'red'
AUDIO_INPUT = 'Instructors'
NOTES = 'Notes'
SCENE_NAMES = {
    # obs_name: (label, tooltip),
    'Title': ('Title', 'Title screen with logo', True),
    'Gallery': ('Gallery', 'All instructors gallery', True),
    'Screenshare': ('Screen', 'Screenshare, normal portrait mode', True),
    'ScreenshareLandscape': ('ScreenLS', 'Screenshare, landscape mode (requires local setup)', True),
    'Broadcaster-Screen': ('BrdScr', 'Broadcaster local screen (only broadcaster may select)', False),
    NOTES: ('Notes', 'Notes', True),
    'Empty': ('Empty', 'Empty black screen', True),
     }
SCENES_WITH_PIP = ['Screenshare', 'ScreenshareLandscape', 'Notes']
PIP = '_GalleryCapture[hidden]'

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
def quick_break():
    mute_toggle(True)
    switch(NOTES)
    pip_size(0, save=True)
def quick_back(scene=NOTES):
    print(scene)
    mute_toggle(False)
    switch(scene)
    pip_size(pip.last_scale)
ttk.Label(frm, text="Quick actions:").grid(row=1, column=0)
b = ttk.Button(frm, text="BREAK", command=quick_break); b.grid(row=1, column=1)
ToolTip(b, 'Go to break.  Mute audio, hide PIP, and swich to Notes', delay=1)
b = ttk.Button(frm, text="BACK(ss)", command=partial(quick_back, 'Screenshare')); b.grid(row=1, column=2)
ToolTip(b, 'Back from break, try to restore settings', delay=1)
b = ttk.Button(frm, text="BACK(n)", command=quick_back); b.grid(row=1, column=3)
ToolTip(b, 'Back from break, go to notes, try to restore settings', delay=1)


# Scenes
def switch(name):
    print(f'switching to {name}')
    if name not in SCENES:
        print(f"Unknown scene {name}")
        return
    cl1.set_current_program_scene(name)
    SCENES[name].configure(background=ACTIVE, activebackground=ACTIVE)
    SCENES[name].configure()
    for n, b in SCENES.items():
        if name != n:
            b.configure(background=default_color, activebackground=default_color)
SCENES = { }
for i, (scene, (label, tooltip, selectable)) in enumerate(SCENE_NAMES.items()):
    b = SCENES[scene] = Button(frm, text=label, command=partial(switch, scene),
                               state='normal' if selectable else 'disabled')
    b.grid(column=i, row=2)
    if tooltip:
        ToolTip(b, tooltip, delay=1)



# Audio
def mute_toggle(state=None, from_obs=False):
    if state is None: # toggle
        state = not b_audio.state
    if state == b_audio.state:
        return
    if not state: # turn on
        b_audio.configure(background=ACTIVE, activebackground=ACTIVE)
        b_audio.state = state
        if not from_obs:
            cl1.set_input_mute(AUDIO_INPUT, state)
    else:
        b_audio.configure(background=default_color, activebackground=default_color)
        b_audio.state = state
        if not from_obs:
            cl1.set_input_mute(AUDIO_INPUT, state)
def volume(state, from_obs=False, dB=None):
    print(f'Setting volumes: {state} {dB}')
    if state is None:
        state = -log10(-(dB-1))
    state = float(state)
    dB = - 10**(-state) + 1
    print(f'calculated dB: {dB} ({state})')
    audio_value.config(text=f"{dB:.1f} dB")
    if from_obs:
        audio.set(state)
        return
    cl1.set_input_volume(AUDIO_INPUT, vol_db=dB)

b_audio = Button(frm, text='Audio', command=mute_toggle)
b_audio.grid(row=3, column=0)
b_audio.state = True
ToolTip(b_audio, 'Mute/unmute instructor audio.  Red=ON, default=MUTED', delay=1)
audio = Scale(frm, from_=-2, to=0, orient=HORIZONTAL, command=volume, showvalue=0, resolution=.02)
audio.grid(row=3, column=1, columnspan=5, sticky=E+W)
audio_value = ttk.Label(frm, text="x"); audio_value.grid(row=3, column=6)


# PIP
CROP_FACTORS = {
    None: {'top':  0, 'bottom':  0, 'left':  0, 'right':  0, },
    1:    {'top':  0, 'bottom':  0, 'left': 59, 'right':  59, },
    2:    {'top': 90, 'bottom':  0, 'left': 12, 'right': 12, },  # checked
    3:    {'top':  4, 'bottom':  0, 'left': 60, 'right': 60, },  # checked
    5:    {'top': 50, 'bottom':  0, 'left': 11, 'right': 11, },  # checked
    }
b_pip = ttk.Label(frm, text="PIP size:").grid(row=4, column=0)
def pip_size(scale, from_obs=False, save=False):
    scale = float(scale)
    if save:
        pip.last_scale = pip.scale
    #print(f'PIP size: {scale}')
    pip_value.config(text=f"{scale:0.2f}")
    pip.scale = scale
    pip.set(scale)
    for scene in SCENES_WITH_PIP:
        id_ = cl1.get_scene_item_id(scene, PIP).scene_item_id
        transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
        transform['scaleX'] = scale
        transform['scaleY'] = scale
        if not from_obs:
            cl1.set_scene_item_transform(scene, id_, transform)
pip = Scale(frm, from_=0, to=1, orient=HORIZONTAL, command=pip_size, resolution=.01, showvalue=0)
pip.grid(row=4, column=1, columnspan=5, sticky=E+W)
pip.scale = None
pip.last_scale = .25
pip_value = ttk.Label(frm, text="?") ; pip_value.grid(row=4, column=6)
# PIP crop selection
def pip_crop(n):
    print(f"PIP crop → {n} people")

    for scene in SCENES_WITH_PIP:
        id_ = cl1.get_scene_item_id(scene, PIP).scene_item_id
        transform = cl1.get_scene_item_transform(scene, id_).scene_item_transform
        print('====old', transform)
        for (k,v) in CROP_FACTORS[n].items():
            transform['crop'+k.title()] = v
        print('====new:', transform)
        cl1.set_scene_item_transform(scene, id_, transform)
ttk.Label(frm, text="PIP crop:").grid(row=5, column=0)
crop_buttons = ttk.Frame(frm)
crop_buttons.columnconfigure(tuple(range(5)), weight=1)
crop_buttons.grid(row=5, column=1, columnspan=5)
for i, (n, label) in enumerate([(None, 'None'), (1, 'n=1'), (2, 'n=2'), (3, 'n=3-4'), (5, 'n=5-6')]):
    b = ttk.Button(crop_buttons, text=label, command=partial(pip_crop, n))
    b.pack(in_=crop_buttons, side=LEFT)
    ToolTip(b, 'Set PIP to be cropped for this many people.  None=no crop', delay=1)


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
switch(cl1.get_current_program_scene().current_program_scene_name)
# audio mute
mute_toggle(cl1.get_input_mute(AUDIO_INPUT).input_muted, from_obs=True)
# audio volume
dB = cl1.get_input_volume(AUDIO_INPUT).input_volume_db
print(f"from OBS: {dB} (volume_state)")
volume(state=None, dB=dB, from_obs=True)
# pip size
id_ = cl1.get_scene_item_id(NOTES, PIP).scene_item_id
pip_size(cl1.get_scene_item_transform(NOTES, id_).scene_item_transform['scaleX'], from_obs=True)


def on_current_program_scene_changed(data):
    #print(data.attrs())
    print(data.scene_name)
    if data.scene_name in SCENES:
        switch(data.scene_name)
    else:
        print(f'Switching to unknown scene: {data.scene_name}')
def on_input_volume_changed(data):
    print(data.attrs())
    print(data.input_name, data.input_volume_db)
    if data.input_name == AUDIO_INPUT:
        volume(state=None, dB=data.input_volume_db, from_obs=True)
def on_input_mute_state_changed(data):
    print(data.attrs())
    if data.input_name == AUDIO_INPUT:
        mute_toggle(state=data.input_muted)
cl.callback.register([
    on_current_program_scene_changed,
    on_input_volume_changed,
    on_input_mute_state_changed,
    ])

#import logging
#logging.basicConfig(level=logging.DEBUG)

print('starting...')
root.mainloop()
