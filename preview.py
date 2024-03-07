import argparse
import os
parser = argparse.ArgumentParser()
parser.add_argument('hostname_port')
parser.add_argument('password', default=os.environ.get('OBS_PASSWORD'),
                  help='or set env var OBS_PASSWORD')
parser.add_argument('--delay', '-d', type=float, default=1)
args = parser.parse_args()
hostname = args.hostname_port.split(':')[0]
port = args.hostname_port.split(':')[1]
password = args.password

# OBS websocket
import obsws_python as obs
cl1 = obs.ReqClient(host=hostname, port=port, password=password, timeout=3)

import base64
import io

from tkinter import *
from tkinter import ttk
from PIL import Image, ImageTk

def get_image(w=840//2, h=1080//2):
    w = max(w, 50)
    h = max(h, 50)
    w = min(w, 1920)
    h = min(h, 1080)
    source = cl1.get_current_program_scene().current_program_scene_name
    image = cl1.get_source_screenshot(source, 'png', w, h, -1).image_data
    image = base64.b64decode(image.split(',')[1])
    image = Image.open(io.BytesIO(image))
    return image


def update_image():
    print("Updating...")
    w, h = root.winfo_width(), root.winfo_height()
    print(w, h)
    image = get_image(w, h)
    #image_new = image.resize((w, h))
    #print(image_new)
    pi = ImageTk.PhotoImage(image)
    background.configure(image=pi)
    background.img = pi
    #background.pack(fill=BOTH, expand=YES)
    #frm.pack()
    root.after(max(100, int(args.delay*1000)), update_image)

root = Tk()
frm = ttk.Frame(root, padding=0)
frm.pack()
image = get_image(840//2, 1080//2)
print(image)
w = image.width
h = image.height
print(w, h)
root.geometry(f"{w}x{h}")

#frm.pack(fill=BOTH, expand=YES)
pi = ImageTk.PhotoImage(get_image())
background = Label(frm, image=pi)
background.pack(fill=BOTH, expand=YES)
update_image()

#ttk.Label(frm, image=pi)
#canvas = Canvas(root, width=300, height=300)
#canvas.pack()
#canvas.create_image(20, 20, anchor=NW, image=pi)
root.mainloop()

