set -e

BASE=$(python3 -c 'import obsws_python; from os.path import dirname; print(dirname(dirname(obsws_python.__file__)))')

rm -rf zipapp
mkdir zipapp
rsync -a -L ${BASE}/obsws_python*                   zipapp/
rsync -a -L ${BASE}/websocket*                      zipapp/
rsync -a -L ${BASE}/tktooltip                       zipapp/
rsync -a -L ${BASE}/tkinter_tooltip-3.1.0.dist-info zipapp/
rsync -a -L obs_cr                                  zipapp/

python -m zipapp zipapp --main=obs_cr.__main__:main --python="/usr/bin/env python3" --output obs-cr.pyz
