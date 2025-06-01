// Functions for control panel.

//
// Primary initialization setup
//
INIT_FUNCTIONS = [
    load_config,
    init_ssl_warning,
    init_rellinks,
    init_hide_popoutbutton,
    init_soundfiles,
    init_audio,
    obs_init,
    _obs_init_watchers,
    init_misc,
    init_sync_checkboxes,
    init_sync_buttons,
    init_sync_selects,
    init_sync_textcontent,
    init_sync_input,
    init_live,
    init_indicators,
    init_scene,
    init_mute,
    init_volume,
    init_gallery,
    init_preset,
    init_quick,
    init_scrollnotes,
    init_playfile,
    init_ss_resolution,
    init_announcement,
    init_reset_mainwindow,
    init_reset_secondwindow,
    init_preview,
    init_timers,
    //init_wakelock,
]
// Run all initialization in sequence (one after another - no parallel)
async function init_all() {
    for (func of INIT_FUNCTIONS) {
        await func()
    }
}

//
// Misc elements
//
function updateTime() {
    return forEach('.time', element => {
        date = new Date
        time = `${date.getHours()}:${String(date.getMinutes()).padStart(2, "0")}:${String(date.getSeconds()).padStart(2, "0")}`
        element.textContent = time
    })
}
async function init_misc() {
    n = updateTime()
    if (n) {
        setInterval(updateTime, 500)
    }
}

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
function indicatorBlink(id,) {
    forEach(`.indicator#${id}`, cell => {
        // Disable it
        if (!cell.state) {
            cell.style.backgroundColor = ''
            return
        }
        cell.style.backgroundColor = !cell.style.backgroundColor ? CONFIG.INDICATORS[id]['color'] : '';
    })
    console.log("setting timeout")
    // Get one cell to see if if timer needs to continue
    if (!document.querySelector(`.indicator#${id}`).state) {
        return
    }
    setTimeout(indicatorBlink, CONFIG.INDICATORS[id]['blink'], id)
}
function indicatorUpdate(id, state) {
    forEach(`.indicator#${id}`, cell => {
        cell.state = state
        cell.style.backgroundColor = state ? CONFIG.INDICATORS[id]['color'] : '';
        if (state && CONFIG.INDICATORS[id]['blink']) {
            setTimeout(indicatorBlink, CONFIG.INDICATORS[id]['blink'], id)
        }
    });
}
async function indicatorClick(event) {
    cell = event.target;
    id = cell.id;
    console.log('a', "Click on", cell, id, "newstate=", !cell.state);
    new_state = !cell.state
    await obs_set('indicator-'+id, new_state);
    if (new_state) {
        await obs_broadcast('playsound', CONFIG.INDICATORS[id]['sound'])
    }
}
async function init_indicators() {
    await forEachAsync('.indicator', async cell => {
        let id = cell.id;
        cell.addEventListener('click', indicatorClick);
        await obs_watch_init('indicator-'+id, state => {
            indicatorUpdate(id, state);
        });
        }
    );
    obs_watch('playsound', soundEvent);
}

//
// Scene button
//
function sceneUpdate(name) {
    //console.log(name)
    forEach('.scene', x => {
        x.style.backgroundColor = ''
    })
    forEach(`.scene#${name}`, x => {
        x.style.backgroundColor = x.getAttribute('livecolor') || 'red'
    })
    liveUpdate('scene', CONFIG.SCENES_SAFE.includes(name) ? false : name)
}
async function sceneClick(event) {
    cell = event.target;
    await obs_set("scene", cell.id)
}
async function init_scene(obs) {
    //console.log('init_scene')
    forEach('.scene', x => {
        x.addEventListener('click', sceneClick);
        x.title = CONFIG.SCENES[x.id].description
    })
    // This must always run because it updates the live annunciator
    await obs_watch_init("scene", sceneUpdate)
}


//
// Audio stuff
//
function muteUpdate(name, state) {
    // Update local state to match the remote state
    forEach(`.mute#${name}`, x => {
        x.style.backgroundColor = state ? '' : 'red';
    })
    liveUpdate('mute-'+name, !state)
}
async function muteClick(event) {
    // Trigger local change to OBS/other clients.
    //console.log('muteClick', event, event.target.style.backgroundColor)
    await obs_set_mute(event.target.id, event.target.style.backgroundColor);
}
async function init_mute() {
    // These watchers must always run to update the "live" annunciator
    for (let x of CONFIG.AUDIO_INPUTS) {
        await obs_get_mute(x).then( state => {muteUpdate(x, state)});
        obs_watch('mute-'+x, state => {muteUpdate(x, state)});
    }

    forEach('.mute', cell => {
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
    // Trigger local update to match global state
    forEach(`.volume#${name}`, x => {
        x.value = vol_to_state(dB);
    })
    forEach(`.volume-dB#${name}`, x => {
        x.textContent = `${dB.toFixed(1)} dB`
    })
}
async function volumeClick(event) {
    // Propagate local change to OBS/global clients
    await obs_set_volume(event.target.id, vol_to_dB(event.target.value))
}
async function init_volume() {
    n = forEach('.volume', cell => {
        cell.addEventListener('input', volumeClick);
    })
    if (n) {
        for (let x of CONFIG.AUDIO_INPUTS) {
            await obs_get_volume(x).then( state => {volumeUpdate(x, state)});
            obs_watch('volume-'+x, state => {volumeUpdate(x, state)});
        }
    }
}


//
// Gallery crop
//
async function updateGallerySize() {
    gallerysize = await obs_get('gallerysize')
    forEach('.gallerysize', slider => {
        slider.value = gallerysize;
        slider.parentElement.style.backgroundColor = (gallerysize > 0) ? "red" : "";
        liveUpdate('gallery-size', gallerysize)
    })

}
async function init_gallery() {
    // obs_watch_init("gallerysize", state => {
    //     forEach('.gallerysize', x => {
    //         x.value = state;
    //         x.parentElement.style.backgroundColor = (state > 0) ? "red" : "";
    //         liveUpdate('gallery-size', state)
    //     })
    //     forEach('.gallerysize-state', x => {
    //             x.textContent = `${state.toFixed(2)}`;
    //     })
    // })
    forEach('.gallerysize', slider => {
        slider.addEventListener('input', async event => {
            //console.log("E", event.target.value)
            await obs_set("gallerysize", Number(event.target.value))
        })
    })
    setInterval(updateGallerySize, 1000)

    n = forEach('.gallerycrop', cell => {
        cell.addEventListener('click', async event => {
            // IDs are `n0` with 0 being the size.  0=set null crop.
            // Integers aren't valid IDs thus the `n` prefix.
            let id = event.target.id.slice(1)
            await obs_set('gallerycrop', Number(id))
        })
    })
    if (n) {
       await obs_watch_init('gallerycrop', crop => {
            forEach(`.gallerycrop`, cell => {
                cell.style.backgroundColor = ''
            })
            // Ids are `n0` and so on (see above)
            forEach(`.gallerycrop#n${crop}`, cell => {
                cell.style.backgroundColor = 'orange'
            })
        })
    }
}


//
// Scene presets
//
async function presetSwitch(preset, round=0) {
    console.log('presetSwitch', preset, round)
    let scene = document.querySelector(`.preset-sbox#${preset}`).value
    if (round==0) {
        old_scene = await obs_get['scene']
        resolution = document.querySelector(`.preset-rbox#${preset}`).value
        if (resolution != '-')
            await obs_set('ss_resolution', resolution)
            if (!CONFIG.SCENES_REMOTE.includes(old_scene) && CONFIG.SCENES_REMOTE.includes(scene)) {
                // TODO: wait 0.1 second if old scene is not same as
                // current scene.  This gives it time to change resolution before changing.
                setTimeout(presetSwitch, 0.1*1000, preset, 1)
                return
            }
    }
    console.warn(preset, scene)
    await obs_set('scene', scene)
    //console.log("Click preset", preset, scene)
}
// Called each time anything changes that might possibly update the
// current selected preset.  This updates the preset button color.
async function presetUpdate() {
    //console.log('presetUpdate')
    for (preset of PRESETS) {
        await presetUpdateOne(preset)
    };
}
async function presetUpdateOne(preset) {
    //console.log('presetUpdate', preset)
    preset_scene = document.querySelector(`.preset-sbox#${preset}`).value
    preset_resolution = document.querySelector(`.preset-rbox#${preset}`).value
    current_scene = await obs_get('scene')
    current_resolution = await obs_get('ss_resolution')
    state = (current_scene == preset_scene &&
             ((current_resolution == preset_resolution) || preset_resolution == "-"))
    //console.log("Update preset state", preset, state, 'setting:', preset_scene, preset_resolution, "detected:", current_scene, current_resolution)

    forEach(`.preset-label#${preset}, .preset-active#${preset}`, label => {
        color = CONFIG.SCENES_SAFE.includes(preset_scene) ? 'orange' : 'red'
        label.style.backgroundColor = state ? color : ''
    })
    forEach(`.preset-go#${preset}`, button => {
        //console.log(preset_scene, preset_scene == '-')
        enabled = (preset_scene != '-')// && (preset_resolution != '-')
        button.disabled = enabled ? false : true
    })
}
PRESETS = new Set;
async function init_preset() {
    forEach('.preset-label', x => PRESETS.add(x.id));
    //console.log(PRESETS)

    // Preset labels updates (update the quick action list)
    for (let preset of PRESETS) {
        obs_watch(`preset-${preset}-label`, quickUpdate)
        // We don't need to watch_init - we do it below.
    }

    // Preset label clicks
    forEach('button.preset-label, button.preset-go', button => {
        button.addEventListener('click', async event => {
            await switch_to(event.target.id)
            await presetUpdateOne(event.target.id)
        })
    })

    // Preset scene choices
    await forEachAsync(`.preset-sbox`, async select => {
        // Set sbox choices
        ["-", ...Object.keys(CONFIG.SCENES)].forEach(scene => {
            opt = document.createElement('option')
            opt.text = scene_to_name(scene)
            opt.value = scene
            select.options.add(opt)
        })
        // We have to re-init here, since the previous init
        // didn't have the values to select
        await obs_force(`preset-${select.id}-sbox`)
        obs_watch(`preset-${select.id}-sbox`, _ => {presetUpdate(select.id)})
    })

    // Preset resolution choices
    await forEachAsync(`.preset-rbox`, async select => {
        // Set rbox choices
        ["-", ...CONFIG.SCREENSHARE_SIZES].forEach(resolution => {
            opt = document.createElement('option')
            opt.text = resolution
            opt.value = resolution
            select.options.add(opt)
        })
        await obs_force(`preset-${select.id}-rbox`)
        obs_watch(`preset-${select.id}-rbox`, _ => {presetUpdate(select.id)})

    })

    //General watchers
    await obs_watch_init(`scene`, async _ => {await presetUpdate()})
    quickUpdate()

}


//
// Quick action functions
//
// Update current status of the quick back list
async function quickUpdate() {
    ScenesAndPresets = new Set;
    ScenesAndPresets.add('-')

    // Note that preset-labels may not be defined yet.  This will
    // be updated later once presets are loaded
    forEach('.preset-go', x => {
        //console.log(x, x.id, scene_to_name(x.id))
        if (x.disabled) {
            return
        }
        ScenesAndPresets.add(scene_to_name(x.id))
    });
    // Regular scenes
    for (scene of ['-', ...Object.keys(CONFIG.SCENES)]) {
        //console.log(scene)
        ScenesAndPresets.add(scene)
    }
    ScenesAndPresets = [...ScenesAndPresets]

    options = ScenesAndPresets.map(scene => {
        opt = document.createElement('option')
        opt.text = scene_to_name(scene)
        opt.value = scene
        return opt
    })

    await forEachAsync('.quick-back-scene', async select => {
        // Remove all options
        select.options.length = 0
        for (scene of options) {
            select.options.add(scene)
        }
        await obs_force(select.attributes.syncwith.value)
    })
}
// Go to a break
async function quickBreak(event) {
    await switch_to(CONFIG.NOTES)
    old_gallery_size = await obs_get('gallerysize')
    if (old_gallery_size != 0) {
        await obs_set('gallery_last_state', old_gallery_size)
        await obs_set('gallerysize', 0)
    }
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
    if (round == 0) {
        if (await obs_get('checkbutton-quick_jingle-value')) {
            obs_playfile(CONFIG.PLAYBACK_FILES['short']['filename'])
        }
    }
    if (round < 3) {
        obs_broadcast('playsound', 'low')  // don't await to keep time
        setTimeout(quickBack, 1000, event, round+1)
        return
    }
    if (round == 3) {
        await obs_broadcast('playsound', 'low')  // *do* await now to keep time
        setTimeout(quickBack, 200, event, round+1)
        return
    }
    // Unmute audios (instructor, and brcd if it's checked)
    await obs_broadcast('playsound', 'high')
    await obs_set_mute(CONFIG.AUDIO_INPUT, false)
    if (await obs_get('checkbutton-quick_brcd-value')) { //Todo: don't block the rest of the threads here
        await obs_set_mute(CONFIG.AUDIO_INPUT_BRCD, false)
        await obs_set('checkbutton-quick_brcd-value', false)
    }
    // Find and change to our scene
    to_scene = await obs_get('quickback-quickback-a-value')
    await switch_to(to_scene)
    // Restore the gallery size
    await obs_set('gallerysize', await obs_get('gallery_last_state'))
}
async function init_quick() {
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


//
// Scrolling notes
//
function init_scrollnotes() {
    forEach('.scrollnotes.up',   button => {button.addEventListener('click', async x=> await obs_broadcast('notes_scroll', "Up"))})
    forEach('.scrollnotes.down', button => {button.addEventListener('click', async x=> await obs_broadcast('notes_scroll', "Down"))})
    forEach('.scrollnotes.pgup', button => {button.addEventListener('click', async x=> await obs_broadcast('notes_scroll', "Prior"))})
    forEach('.scrollnotes.pgdn', button => {button.addEventListener('click', async x=> await obs_broadcast('notes_scroll', "Next"))})
    forEach('.scrollnotes.end',  button => {button.addEventListener('click', async x=> await obs_broadcast('notes_scroll', "End"))})
}



//
// Playing sound
//
async function playfileTimerUpdate(data=undefined) {
    ret = await obs.call("GetMediaInputStatus", {inputName: CONFIG.PLAYBACK_INPUT})
    state = ret.mediaState // 'OBS_MEDIA_STATE_PAUSED', 'OBS_MEDIA_STATE_PLAYING'
    if (['OBS_MEDIA_STATE_OPENING', 'OBS_MEDIA_STATE_BUFFERING', 'OBS_MEDIA_STATE_PAUSED'].includes(state)) {
        setTimeout(playfileTimerUpdate, 500)
        return
    } else if (state != "OBS_MEDIA_STATE_PLAYING") {
        // Stop condition: no longer playing, reset everything and stop the updater.
        forEach('.playfile.timer', cell => {
            cell.textContent = '-'
            cell.style.backgroundColor = ''
        })
        return
    }
    duration = Math.floor(ret.mediaDuration / 1000)
    cursor = Math.floor(ret.mediaCursor / 1000)
    if (duration < 0) {
        setTimeout(playfileTimerUpdate, 500) // Wait 0.5s and re-update timer
    }
    function s_to_mmss(s) {
        // s to mm:ss
        return `${Math.floor(s/60)}:${String(s%60).padStart(2, '0')}`
    }
    forEach('.playfile.timer', cell => {
        cell.textContent = `${s_to_mmss(cursor)}/${s_to_mmss(duration)}`
        cell.style.backgroundColor = 'orange'
    })
    setTimeout(playfileTimerUpdate, 500)
}
async function init_playfile() {
    for (let label in CONFIG.PLAYBACK_FILES) {
        let filename = CONFIG.PLAYBACK_FILES[label]['filename']
        let tooltip = CONFIG.PLAYBACK_FILES[label]['tooltip']
        forEach(`.playfile.${label}`, button => {
            button.addEventListener('click', async event => {
                console.log("Trigger playback", label)
                await obs_playfile(filename)
            })
            button.title = tooltip
        })
    }

    forEach('.playfile.stop', button => {
        button.addEventListener('click', async event => {
            await obs_playfile_stop()
        })
    })

    await obs.on('MediaInputPlaybackStarted', playfileTimerUpdate)
    await playfileTimerUpdate() // Run once to init - returns if not playing
}


//
// Screenshare resolution box
//
async function init_ss_resolution() {
    // Preset resolution choices
    await forEachAsync(`select.ss-resolution`, async select => {
        // Set resolution choices
        ["-", ...CONFIG.SCREENSHARE_SIZES].forEach(resolution => {
            opt = document.createElement('option')
            opt.text = resolution
            opt.value = resolution
            select.options.add(opt)
        })
        //await obs_force(`ss-resolution`)
        //obs_watch(`preset-${select.id}-rbox`, _ => {presetUpdate(select.id)})
    })
}

async function init_reset_mainwindow() {
    await forEachAsync(`button.reset-mainwindow-size`, async button => {
        button.addEventListener('click', async event => {
            console.log("Reset secondwindow size", event)
            await obs_set('mainwindow_resolution', true)
            await delay(500)
            await obs_set_gallerycrop()
        })
    })
}

async function init_reset_secondwindow() {
    await forEachAsync(`button.reset-secondwindow-size`, async button => {
        button.addEventListener('click', async event => {
            console.log("Reset secondwindow size", event)
            await obs_set('ss_resolution', await obs_get('ss_resolution'))
        })
    })
}

//
// Preview pane
//
let PREVIEW_UPDATE_RUNNING = false;
async function update_preview () {
    if (PREVIEW_UPDATE_RUNNING) {
         console.log('aborting, already running');
         return;
    }
    try {
        PREVIEW_UPDATE_RUNNING = true;
        res = await obs.call('GetCurrentProgramScene',);
        //console.log(res)
        sceneName = res.currentProgramSceneName;
        ret = await obs.call('GetSourceScreenshot',
                             {sourceName: sceneName,
                              imageFormat: "png",
                              //imageWidth: ,
                              //imageHeight: ,
                            })
        img = ret.imageData;
        //console.log(ret)
        //console.log(res)
        n = forEach('img.preview', element => {
            element.src = `data:img/png;base64=${img}`
            //console.log(element)
        })
    } finally {
        PREVIEW_UPDATE_RUNNING = false;
    }
    return n
}
async function init_preview () {
    const params = getFragmentParams();
    UPDATE_INTERVAL = parseFloat(params.delay)*1000 || 250;

    n = await update_preview();
    //console.log(n)
    if (n) {
        setInterval(update_preview, UPDATE_INTERVAL);
    }
}


//
// Enable audio
//
async function audioTest(event, round=0) {
    console.log(round)
    if (round == 0) {await soundEvent('low');          setTimeout(audioTest, 200, null, 1); return}
    if (round == 1) {await soundEvent('high');         setTimeout(audioTest, 200, null, 2); return}
    if (round == 2) {await soundEvent('alert-low');    setTimeout(audioTest, 200, null, 3); return}
    if (round == 3) {await soundEvent('alert-medium'); setTimeout(audioTest, 200, null, 4); return}
    if (round == 4) {await soundEvent('alert-high');   setTimeout(audioTest, 200, null, 5); return}
    forEach('.enable-audio, .audio-warning', div => {
        div.style['display'] = 'none'
    })
}
function init_audio() {
    forEach('.enable-audio-button', button => {
        button.addEventListener('click', audioTest)
    })
    if (getFragmentParams()["nosound"]) {
        forEach('.enable-audio, .audio-warning', div => {
            div.style['display'] = 'none'
        })
    }
}


//
// Announcement text sync
//
async function init_announcement() {
    forEach('input.announcement', input => {
        input.addEventListener('change', async event => {
            //await obs_set(input.attributes.syncwith.value, event.target.value)
            //console.log(await obs.call('GetInputSettings', {inputName: 'Announcement'}))
            await obs.call('SetInputSettings', {inputName: 'Announcement', inputSettings: {text: event.target.value}})
        })
    })
    forEach('input.announcement-textsize', input => {
        input.addEventListener('change', async event => {
            //await obs_set(input.attributes.syncwith.value, event.target.value)
            await obs.call('GetInputSettings', {inputName: 'Announcement'})
            await obs.call('SetInputSettings', {inputName: 'Announcement', inputSettings: {font: {size: parseInt(event.target.value, 10)}}})
        })
    })
    forEach("input.announcement-enabled", input => {
        input.addEventListener('change', async event => {
            //console.log(event)
            scenes = (await obs.call('GetSceneList', {}))['scenes']
            for(sceneData of scenes) {
                sceneName = sceneData['sceneName']
                //console.log(scene)
                sceneItems = (await obs.call('GetSceneItemList', {sceneName: sceneName}))['sceneItems']
                //console.log(sceneItems)
                for (sceneItem of sceneItems) {
                    if (sceneItem.sourceName == 'Announcement') {
                        //console.log(sceneName, sceneItem)
                        await obs.call('SetSceneItemEnabled', {sceneName: sceneName, sceneItemId: sceneItem.sceneItemId, sceneItemEnabled: event.target.checked})
                    }
                }
            }
        })
    })
}


//
// Timers
//
async function init_timers() {
    //console.log('XXXXXXX')
    IDs = [ ]
    forEach("input.timer", input => {
        // User change
        //console.log(input)
        let id = input.id
        input.addEventListener('change', async event => {
            //console.log(event)
            input = event.target

            regex_at = /@(\d\d?):(\d\d?)(\/(\d+))?/
            match_at = input.value.match(regex_at)
            if (match_at) {
                // Match format @HH:MM/DD where HH:MM is a real time and DD is duration in minutes
                endtime = new Date()
                endtime.setHours(parseInt(match_at[1]))
                endtime.setMinutes(parseInt(match_at[2]))
                duration = match_at[4]*60 || null
                endtime = Math.round(endtime.getTime()/1000)
                console.log('timer parse', match_at, endtime, duration)
            } else {
                // Simple match
                regex = /(\d\d?)(:(\d\d?))?(\/(\d\+))?/
                match = input.value.match(regex)
                minutes = match[1]
                seconds = match[3] || 0
                duration = match[5]*60 || null
                endtime = Math.round(Date.now()/1000 + 60*parseInt(minutes)  + parseInt(seconds))
                console.log('timer parse', match, minutes, seconds, duration)
            }
            if (duration === null) {
                duration = Math.round(endtime - Date.now()/1000)
            }
            timer_set(id, endtime, duration)
            obs_set('timer-'+id, `${endtime}:${duration}`)
        })
        obs_watch_init('timer-'+input.id, endtime => {
            endtime = endtime.split(/:/)
            if (endtime.length == 2) {
                duration = endtime[1]
                endtime = endtime[0]
            } else {
                endtime = endtime[0]
                duration = null
            }
            if (endtime > Date.now()/1000) {
                timer_set(id, endtime, duration)
            }
        })
    })
}
async function timer_set(id, endtime, duration) {
    console.log('timer_set', id, endtime)
    // Start a countdown timer
    input = document.querySelector('input#'+id)
    input.endtime = endtime
    setTimeout(timer_tick, 500, id, endtime, duration)
}
async function timer_tick(id, endtime, duration) {
    // If we have been updated, just exit - a new handler will have been registered
    console.log('tick', id, endtime, input.endtime, duration)
    input = document.querySelector('input#'+id)
    if (input.endtime != endtime) {
        console.log(`timer ${id} has been reset`)
        return
    }
    endtime = input.endtime
    // Abort if time expired
    if (endtime < Date.now()/1000) {
        console.log(`timer ${id} has expired`)
        input.style.backgroundColor = null
        return
    }
    if (document.activeElement !== input) {
        // Only tick if we are not focused
        remaining = Math.floor((endtime - Date.now()/1000))
        time = `${Math.floor(remaining/60)}:${String(remaining%60).padStart(2, "0")}`
        input.value = time
        fraction_remaining = remaining / duration
        if (fraction_remaining < .75) {
            fraction = fraction_remaining * 4 // 1 when started, 0 when out
            input.style.backgroundColor = `hsl(288, 100%, ${Math.max(50+50*fraction)}%)`
        }
    } else {
        console.log(`timer ${id} is focused`)
    }
    setTimeout(timer_tick, 500, id, endtime, duration)
}