rm -r zipapp
mkdir zipapp
rsync -a venv/lib/python3.11/site-packages/obsws_python/ zipapp/obsws_python/
rsync -a venv/lib/python3.11/site-packages/tktooltip/ zipapp/tktooltip/
rsync -a obs_cr/ zipapp/obs_cr/


python -m zipapp zipapp --main=obs_cr.__main__:main --python="/usr/bin/env python3" --output obs-cr.pyz
