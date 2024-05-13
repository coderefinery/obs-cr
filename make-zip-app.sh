set -e

BASE=$(python3 -c 'import obsws_python; from os.path import dirname; print(dirname(dirname(obsws_python.__file__)))')

rm -r zipapp
mkdir zipapp
rsync -a ${BASE}/obsws_python/ zipapp/obsws_python/
rsync -a ${BASE}/tktooltip/ zipapp/tktooltip/
rsync -a obs_cr/ zipapp/obs_cr/

python -m zipapp zipapp --main=obs_cr.__main__:main --python="/usr/bin/env python3" --output obs-cr.pyz
