// Functions for control panel.

//
// Live indicator
//
LIVE_STATUS = { }
// Call this function each time there is some update that might possibly affect
// if the instructors are live.  This combines current + past info and
// updates the "live" indicator accordingly.
function liveUpdate(name, value) {
    // name: persistent key for the value (examples: gallerysize, instructormute, etc)
    // value: truthy if people are visible
    LIVE_STATUS[name] = value;
    anyTrue = false;
    for (v in LIVE_STATUS) {
        if (LIVE_STATUS[v]) {
            anyTrue = true
        }
    }
    forEach('.live', cell => {
        if (anyTrue) {
            cell.style.backgroundColor = 'red'
            cell.title = "Some sound or video is probably visible on stream now\n" + JSON.stringify(LIVE_STATUS)
        } else {
            cell.style.backgroundColor = ''
            cell.title = "You are probably not visible on stream"
        }
    })
}
function init_live(obs) {
    // No action currently needed: each live thing should call
    // liveUpdate itself when it initializes.
}



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
    liveUpdate('scene', SCENES_SAFE.includes(name) ? false : name)
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
        x.switchto = () => {obs_set(x.id)}
    })
}


//
// Audio stuff
//
function muteUpdate(name, state) {
    document.querySelectorAll(`.mute#${name}`).forEach(x => {
        x.style.backgroundColor = state ? '' : 'red';
    })
    liveUpdate('mute-'+name, !state)
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
        forEach('.gallerysize', x => {
            x.value = state;
            x.parentElement.style.backgroundColor = (state > 0) ? "red" : "";
            liveUpdate('gallery-size', state)
        })
        forEach('.gallerysize-state', x => {
                x.textContent = `${state.toFixed(2)}`;
        })
    })
    forEach('.gallerysize', slider => {
        slider.addEventListener('input', event => {
            console.log("E", event.target.value)
            obs_set("gallerysize", Number(event.target.value))
        })
    })

    forEach('.gallerycrop', cell => {
        cell.addEventListener('click', event => {
            // IDs are `n0` with 0 being the size.  0=set null crop.
            // Integers aren't valid IDs thus the `n` prefix.
            let id = event.target.id.slice(1)
            obs_set('gallerycrop', Number(id))
        })
    })
    obs_watch_init('gallerycrop', crop => {
        forEach(`.gallerycrop`, cell => {
            cell.style.backgroundColor = ''
        })
        // Ids are `n0` and so on (see above)
        forEach(`.gallerycrop#n${crop}`, cell => {
            cell.style.backgroundColor = 'orange'
        })
    })
}


//
// Scene presets
//
async function presetSwitch(preset) {
    scene = document.querySelector(`.preset-sbox#${preset}`).value
    resolution = document.querySelector(`.preset-rbox#${preset}`).value
    if (resolution != '-')
       await obs_set('ss_resolution', resolution)
    await obs_set('scene', scene)
    //console.log("Click preset", preset, scene)
}
// Called each time anything changes that might possibly update the
// current selected preset.  This updates the preset button color.
async function presetUpdate() {
    //console.log('presetUpdate')
    PRESETS = new Set;
    forEach('.preset-label', x => PRESETS.add(x.id));
    for (let preset of PRESETS) {
        await presetUpdateOne(preset)
    }
}
async function presetUpdateOne(preset) {
    //console.log('presetUpdate', preset)
    preset_scene = document.querySelector(`.preset-sbox#${preset}`).value
    preset_resolution = document.querySelector(`.preset-rbox#${preset}`).value
    current_scene = await obs_get('scene')
    current_resolution = await obs_get('ss_resolution')
    state = (current_scene == preset_scene &&
             current_resolution == preset_resolution)
    //console.log("Update preset state", preset, preset_scene, preset_resolution, state, "detected:", current_scene, current_resolution)

    forEach(`.preset-label#${preset}`, label => {
        color = SCENES_SAFE.includes(preset_scene) ? 'orange' : 'red'
        label.style.backgroundColor = state ? color : ''
    })
}

async function init_preset(obs) {
    PRESETS = new Set;
    forEach('.preset-label', x => PRESETS.add(x.id));
    //console.log(PRESETS)

    // Preset labels updates (update the quick action list)
    for (let preset of PRESETS) {
        obs_watch(`preset-${preset}-label`, quickUpdate)
    }

    // Preset label clicks
    forEach('.preset-label', button => {
        button.addEventListener('click', event => {
            switch_to(event.target.id)
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
        obs_watch(`preset-${select.id}-sbox`, _ => {presetUpdate(select.id)})
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
        obs_watch(`preset-${select.id}-rbox`, _ => {presetUpdate(select.id)})
    })

    //General watchers
    await obs_watch_init(`scene`, _ => {presetUpdate()})
    quickUpdate()

}


//
// Quick action functions
//
// Update current status of the quick back list
function quickUpdate() {
    ScenesAndPresets = new Set;
    ScenesAndPresets.add('-')

    // Note that preset-labels may not be defined yet.  This will
    // be updated later once presets are loaded
    forEach('.preset-label', x => {
        ScenesAndPresets.add(x.textContent)
    });
    // Regular scenes
    for (scene of ['-', ...SCENES]) {
        //console.log(scene)
        ScenesAndPresets.add(scene)
    }
    ScenesAndPresets = [...ScenesAndPresets]

    options = ScenesAndPresets.map(scene => {
        opt = document.createElement('option')
        opt.text = scene
        opt.value = scene
        return opt
    })

    forEach('.quick-back-scene', select => {
        // Remove all options
        select.options.length = 0
        for (scene of options) {
            select.options.add(scene)
        }
    })
}
// Go to a break
async function quickBreak(event) {
    await switch_to(CONFIG.NOTES)
    await obs_set('gallery_last_state', await obs_get('gallerysize'))
    await obs_set('gallerysize', 0)
    // mute brcd
    // Beep for going offline
    await obs_set_mute(CONFIG.AUDIO_INPUT, true)
    await obs_set_mute(CONFIG.AUDIO_INPUT_BRCD, true)
    await obs_broadcast('playsound', 'high')
    setTimeout(obs_broadcast, 200, 'playsound', 'low')
    // mute instr
}
// Come back from a break.  Countdown to 3 and resume.
async function quickBack(event, round=0) {
    // TODO: play jingle if requested
    // Count down to going online
    if (round < 3) {
        obs_broadcast('playsound', 'low')
        setTimeout(quickBack, 1000, event, round+1)
        return
    }
    if (round == 3) {
        await obs_broadcast('playsound', 'low')
        setTimeout(quickBack, 200, event, round+1)
        return
    }
    // Unmute audios (instructor, and brcd if it's checked)
    await obs_broadcast('playsound', 'high')
    await obs_set_mute(CONFIG.AUDIO_INPUT, false)
    if (document.querySelector('.quick-back-audio-brcd').checked) {
        await obs_set_mute(CONFIG.AUDIO_INPUT_BRCD, false)
        document.querySelector('.quick-back-audio-brcd').checked = false
    }
    // Find and change to our scene
    to_scene = document.querySelector('.quick-back-scene').value
    await switch_to(to_scene)
    // Restore the gallery size
    await obs_set('gallerysize', await obs_get('gallery_last_state'))
}
function init_quick(obs) {
    // Quick break button clicking
    forEach('.quick-break', button => {
        button.addEventListener('click', quickBreak)
    })
    // Quick back button clicking
    forEach('.quick-back', button => {
        button.addEventListener('click', quickBack)
    })
    quickUpdate()

}