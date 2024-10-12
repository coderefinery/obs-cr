// Functions for control panel.


//
// Indicators
//
function indicatorUpdate(name, state) {
    cells = document.getElementsByClassName(name);
    for (c of cells) {
        c.style.backgroundColor = state ? INDICATORS[name] : '';
    }
}
function indicatorClick(event) {
    cell = event.target;
    class_ = cell.classList[cell.classList.length-1];
    console.log('a', "Click on", cell, class_, "newstate=", !cell.style.backgroundColor);
    new_state = !cell.style.backgroundColor
    obs_set(class_, new_state);
    if (new_state) {
        if (INDICATORS[class_] === 'red')    {obs_broadcast('playsound', 'alert-high')};
        if (INDICATORS[class_] === 'yellow') {obs_broadcast('playsound', 'alert-medium')};
        if (INDICATORS[class_] === 'cyan')   {obs_broadcast('playsound', 'alert-low')};
    }
}
function init_indicators(obs) {
	cells = document.querySelectorAll('.indicator');
    cells.forEach(cell => {
        let class_ = cell.classList[cell.classList.length-1];
        cell.addEventListener('click', indicatorClick);
        obs_watch_init(class_, function(state) {indicatorUpdate(class_, state);});
        }
    );

}

//
// Live indicator
//
function init_live(obs) {
    // Update and watch the "live" button
    document.querySelectorAll('.live').forEach(cell => {
        obs_watch_init('mirror-live', state => {
            cell.style.backgroundColor = state?"red":"";
            cell.title = state?JSON.stringify(state):"You are probably not visible on stream"
        })
    })
}

//
// Scene button
//
function sceneUpdate(name) {
    //console.log(name)
    document.querySelectorAll('.scene').forEach(x => {
        x.style.backgroundColor = ''
    })
    document.querySelectorAll(`.scene#${name}`).forEach(x => {
        x.style.backgroundColor = x.getAttribute('livecolor') || 'red'
    })
}
function sceneClick(event) {
    cell = event.target;
    obs_set("scene", cell.id)

}
function init_scene(obs) {
    //console.log('init_scene')
    obs_watch_init("scene", sceneUpdate)
    document.querySelectorAll('.scene').forEach(x => {
        x.addEventListener('click', sceneClick);
    })
}


//
// Audio stuff
//
function muteUpdate(name, state) {
    document.querySelectorAll(`.mute#${name}`).forEach(x => {
        x.style.backgroundColor = state ? '' : 'red';
    })
}
function muteClick(event) {
    //console.log('muteClick', event, event.target.style.backgroundColor)
    obs_set_mute(event.target.id, event.target.style.backgroundColor);
}
function init_mute(obs) {
    allAudioDevs = new Set;
    document.querySelectorAll('.mute').forEach(x => allAudioDevs.add(x.id));

    allAudioDevs.forEach(x => {
        obs_get_mute(x).then( state => {muteUpdate(x, state)});
        obs_watch('mute-'+x, state => {muteUpdate(x, state)});
    })

    document.querySelectorAll('.mute').forEach(cell => {
        cell.addEventListener('click', muteClick);
    })
}
function vol_to_dB(state) {
    return - (10**(-state)) + 1;
}
function vol_to_state(dB) {
    return -Math.log10(-(dB-1));
}
function volumeUpdate(name, dB) {
    document.querySelectorAll(`.volume#${name}`).forEach(x => {
        x.value = vol_to_state(dB);
    })
    document.querySelectorAll(`.volume-dB#${name}`).forEach(x => {
        x.textContent = `${dB.toFixed(1)} dB`
    })
}
function volumeClick(event) {
    obs_set_volume(event.target.id, vol_to_dB(event.target.value))
}
function init_volume(obs) {
    allAudioDevs = new Set;
    document.querySelectorAll('.volume').forEach(x => allAudioDevs.add(x.id));

    allAudioDevs.forEach(x => {
        obs_get_volume(x).then( state => {volumeUpdate(x, state)});
        obs_watch('volume-'+x, state => {volumeUpdate(x, state)});
    })

    document.querySelectorAll('.volume').forEach(cell => {
        cell.addEventListener('input', volumeClick);
    })
}


//
// Gallery crop
//
function init_gallery(obs) {
    obs_watch_init("gallerysize", state => {
        document.querySelectorAll('.gallerysize').forEach(x => {
            x.value = state;
        })
        document.querySelectorAll('.gallerysize-state').forEach(x => {
                x.textContent = `${state.toFixed(2)}`;
        })
    })
    document.querySelectorAll('.gallerysize').forEach(slider => {
        slider.addEventListener('input', event => {
            obs_set("gallerysize", Number(event.target.value))
        })
    })

    document.querySelectorAll('.gallerycrop').forEach(cell => {
        cell.addEventListener('click', event => {
            let id = event.target.id
            obs_set('gallerycrop', Number(id))
        })
    })
}


//
// Scene presets
//
function presetClick(preset) {
    scene = document.querySelector(`.preset-sbox#${preset}`).value
    resolution = document.querySelector(`.preset-sbox#${preset}`).value
    obs_set('scene', scene)
    console.log("Click preset", preset, scene)
}
// Called each time anything changes that might possibly update the
// current selected preset.  This updates the preset button color.
async function presetUpdate(preset) {
    scene = document.querySelector(`.preset-sbox#${preset}`).value
    resolution = document.querySelector(`.preset-rbox#${preset}`).value
    current_scene = await obs_get('scene')
    current_resolution = await obs_get('ss_resolution')
    state = (current_scene == scene &&
             current_resolution == resolution)
    console.log("Update preset state", preset, scene, state, "detected:", current_scene, current_resolution)

    forEach(`.preset-label#${preset}`, label => {
        color = SCENES_SAFE.includes(scene) ? 'orange' : 'red'
        label.style.backgroundColor = state ? color : ''
    })
}

function init_preset(obs) {
    PRESETS = new Set;
    forEach('.preset-label', x => PRESETS.add(x.id));
    console.log(PRESETS)

    // Preset labels updates
    for (let preset of PRESETS) {
        obs_watch_init(`preset-${preset}-label`, label => {
            forEach(`.preset-label#${preset}`, button => {
                button.textContent = label
            })
        })
        // General watchers
        obs_watch(`preset-label`, _ => {presetUpdate(preset)})
        obs_watch_init(`scene`, _ => {presetUpdate(preset)})
    }

    // Preset label clicks
    forEach('.preset-label', button => {
        id = button.id
        button.addEventListener('click', event => {
            presetClick(event.target.id)
        })
    })

    // Preset scene choices
    forEach(`.preset-sbox`, select => {
        // Set sbox choices
        ["-", ...SCENES].forEach(scene => {
            opt = document.createElement('option')
            opt.text = scene
            opt.value = scene
            select.options.add(opt)
        })
        // Watch for sbox changes
        obs_watch_init(`preset-${select.id}-sbox`, choice => {
            select.value = choice
        })
        obs_watch_init(`preset-${select.id}-sbox`, _ => {presetUpdate(select.id)})
        // Handle sbox clicks
        select.addEventListener('input', event => {
            obs_set(`preset-${select.id}-sbox`, event.target.value)
            console.log(event, event.target.value);
        })
    })

    // Preset resolution choices
    forEach(`.preset-rbox`, select => {
        // Set rbox choices
        ["-", ...CONFIG.SCREENSHARE_SIZES].forEach(resolution => {
            opt = document.createElement('option')
            opt.text = resolution
            opt.value = resolution
            select.options.add(opt)
        })
        // Watch for rbox changes
        obs_watch_init(`preset-${select.id}-rbox`, choice => {
            select.value = choice
        })
        obs_watch_init(`preset-${select.id}-rbox`, _ => {presetUpdate(select.id)})
        // Handle rbox clicks
        select.addEventListener('input', event => {
            obs_set(`preset-${select.id}-rbox`, event.target.value)
            console.log(event, event.target.value);
        })
    })

}