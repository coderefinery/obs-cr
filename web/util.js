OBS_DEBUG = false;

//
// Basic utility functions
//

// Shortcut to select all elements with a given selector, and run
// the anonymous function on all of them.  Used for updating all
// elements of a given class at the same time.
function forEach(querySelector, func) {
    let n = 0
    for (let x of document.querySelectorAll(querySelector)) {
        func(x);
        n += 1
    }
    return n
}
async function forEachAsync(querySelector, func) {
    let n = 0
    for (let x of document.querySelectorAll(querySelector)) {
        await func(x);
        n += 1
    }
    return n
}

// Load global configuration
async function load_config () {
    response = await fetch("config.yaml").catch(update_status("Can not load config.yaml"))
    text = await response.text().catch(update_status("config.yaml data not loaded"))
    CONFIG = jsyaml.load(text)
    globalThis.CONFIG = CONFIG
    // Make mapping human name -> scene names
    CONFIG.SCENES_REVERSE = { }
    for (scene in CONFIG.SCENES) {
        CONFIG.SCENES_REVERSE[CONFIG.SCENES[scene].name]= scene
    }
    return globalThis.CONFIG
  }


// If this is SSL, show the warning
async function init_ssl_warning () {
    if (window.location.protocol === 'https:') {
        forEach('.ssl-warning', x => {x.style.display = 'block'});
    }
}


function replace_url_path(href, page) {
    // Replace the path component (xxx.html) with page (page.html)
    purl = new URL(href);
    purl.pathname = purl.pathname.replace(/\/[^\/]*?$/, `/${page}.html`);
    return purl.toString();
}

function init_rellinks() {
    // For each <a> element with classname PAGE-href, replace link target path with PAGE.html
    purl = new URL(window.location.href);
    for (page of ["preview", "index", "control", "small", "director", "annunciators", "tablet"]) {
        purl.pathname = purl.pathname.replace(/\/[^\/]*?$/, `/${page}.html`)
        forEach(`.${page}-href`, x => {x.href = purl.toString()});
    }
}

function init_hide_popoutbutton () {
    if (! window.toolbar.visible) {
        forEach('button.popout', button => {button.style.display = 'none'})
    }
}

// Convert key=value&key2=value2 in URL fragment to dict
function getFragmentParams() {
    const params = {};
    const fragment = window.location.hash.substring(1);
    const pairs = fragment.split('&');
    pairs.forEach(pair => {
        const [key, value] = pair.split('=');
        if (key) {
            params[decodeURIComponent(key)] = decodeURIComponent(value || '');
        }
    });
    return params;
}

async function checkSrv (domain, service="_obs", protocol="_tcp") {
    const srvRecord = `${service}.${protocol}.${domain}`
    const dnsApi = `https://dns.google/resolve?name=${srvRecord}&type=SRV`;
    res = await fetch(dnsApi);
    if (!res.ok) {
        msg = "DNS query to dns.google failed (to look up SRV records)"
        update_status(msg);
        console.error(msg);
        return {domain: null, port: null, ok: false};
    }
    data = await res.json();
    if (!res.ok || !data.Answer) {
        msg = `DNS lookup of SRV record ${srvRecord} failed`
        update_status(msg);
        console.error(msg);
    }
    record = data.Answer[0].data.split(" ");
    srvDomain = record[3]
    srvPort = parseInt(record[2]);
    console.log(`Looked up SRV record ${service}.${protocol}.${domain} -> ${srvDomain} ${srvPort}`)
    return {domain: srvDomain, port: srvPort, ok: true}
}

// async function getParams() {
//     console.log('x');
//     // Like get fragment params but do more
//     params = getFragmentParams();
//     try {
//         if (params.url.indexOf(":") == -1) {
//             // There is no colon, so do a SRV lookup
//             srvRecord = await checkSrv(params.url);
//             if (srvRecord.ok === true) {
//                 params.url = `${srvRecord.domain}:${srvRecord.port}`
//             }
//         }
//     } catch (error) {
//         console.log("Error in SRV lookup", error)
//     }
//     return params;
// }


function update_status(text) {
    forEach('.status', x => {x.innerText = text});
}

const delay = ms => new Promise(res => setTimeout(res, ms));

// Convert a stable ID to a human name for a scene/preset
function scene_to_name(scene) {
    if (scene == '-') return '-'
    // Human names of named scenes
    if (scene in CONFIG.SCENES) {
        return CONFIG.SCENES[scene].name
    }
    // Human names of named presets
    label = document.querySelector(`.preset-label[id="${scene}"]`)
    if (label) {
        return label.value
    }
    return scene
}
// Convert a scene's human name to its stable ID
function name_to_scene(name) {
    if (name == '-' || !name) return '-'
    if (name in CONFIG.SCENES_REVERSE) {
        return CONFIG.SCENES_REVERSE[name]
    }
    for (label of document.querySelectorAll('.preset-label')) {
        //console.log(label.id, label.textContent)
        if (label.value == name) {
            return label.id
        }
    }
    return name
}
async function switch_to(scene) {
    console.log("switch_to: (raw)", scene)
    scene = name_to_scene(scene)
    console.log("switch_to:", scene)
    // It's a normal scene
    if (scene in CONFIG.SCENES) {
        await obs_set('scene', scene)
        return
    }
    // It's a preset
    await presetSwitch(scene)
}


// Play sound events locally (indicators, going back live, etc)
SOUNDFILES = { }
async function init_soundfiles() {
    for (effectname in CONFIG.SOUNDS) {
        filename = CONFIG.SOUNDS[effectname]
        //console.log(`Loading ./sound/${filename}`)
        audio = new Audio(`./sound/${filename}`);
        SOUNDFILES[effectname] = audio;
    }
}
async function soundEvent(value) {
    nosound = document.querySelector("input.no-local-sound")
    if (nosound != null && nosound.checked) {
        console.debug(`Not playing sound ${value} due to no-local-sound=true`)
        return;
    }
    if (getFragmentParams()["nosound"]) {
        console.debug(`Not playing sound ${value} due to url fragment #nosound=1`)
        return;

    }
    //console.log(`sound event: ${value}`);
    update_status(`Sound event: ${value}`);
    audio = SOUNDFILES[value];
    audio.play().catch((error) => {
        // Handle the error
        console.error('Error playing audio:', error);
        forEach('.audio-warning', x => {x.style.display = 'block'});
    });
}


// Wakelock to keep screen on
// This does NOT currently work on non-SSL sites.
async function init_wakelock() {
    const params = getFragmentParams();
    if (params['wakelock']) {
        console.error('wakelock trying to activate')
         wakeLock = await navigator.wakeLock.request('screen');
    }
}

//let wakeLock = null;
async function fullscreen_toggle() {
    main=document.querySelector('#main')
    if (main.fs == 1) {
        document.exitFullscreen()
        main.fs = 0
        // Wakelock doesn't work in non-SSL
        //wakeLock.release().then(() => {
        //    wakeLock = null;
        //});
    } else {
        main.requestFullscreen()
        //wakeLock = await navigator.wakeLock.request("screen");
        main.fs = 1
    }
}


//
// Synced Buttons
//

async function init_sync_checkboxes() {
    await forEachAsync('input[type="checkbox"].synced', async checkbox => {
        await obs_watch_init(checkbox.attributes.syncwith.value, newvalue => {
            if (newvalue != null)
                checkbox.checked = newvalue
        })
        checkbox.addEventListener('click', async event => {
            await obs_set(checkbox.attributes.syncwith.value, event.target.checked)
        })
    })
}

async function init_sync_buttons() {
    await forEachAsync('button.synced', async button => {
        button.addEventListener('click', async event => {
            console.log(button, event.target)
            await obs_set(event.target.attributes.syncwith.value, event.target.innerText)
        })
    })
}

async function init_sync_selects() {
    await forEachAsync('select.synced', async select => {
        await obs_watch_init(select.attributes.syncwith.value, newvalue => {
            if (newvalue != null)
                select.value = newvalue
            })
        select.addEventListener('input', async event => {
            await obs_set(select.attributes.syncwith.value, event.target.value)
        })
    })
}

async function init_sync_textcontent() {
    await forEachAsync('span.synced, button.synced', async span => {
        await obs_watch_init(span.attributes.syncwith.value, newvalue => {
            if (newvalue != null)
                span.textContent = newvalue
        })
    })
}
async function init_sync_input() {
    await forEachAsync('input.synced[type="text"]', async input => {
        await obs_watch_init(input.attributes.syncwith.value, newvalue => {
            if (newvalue != null)
                input.value = newvalue
        })
        input.addEventListener('change', async event => {
            await obs_set(input.attributes.syncwith.value, event.target.value)
        })
    })
}



//
// Main OBS relay functions.
//

// Connect to OBS
async function obs_init () {
    const params = getFragmentParams();
    const url = params.url || 'localhost:4455';
    const password = params.password || '';

    // Create a new OBS WebSocket instance
    globalThis.obs = new OBSWebSocket();
    update_status(`Trying to connect to ws://${url}`)

    try {
	await obs.connect(`ws://${url}`, password)
    } catch (err) {
	console.log(err)
	update_status(`Connection failed: ${err.message}`)
	return
    }
    update_status(`Connected to OBS at ws://${url}.`);
    // Poll to keep the connection alive
    setInterval(async function() {console.log("Connection ping: ", (await obs.call('GetVersion')).obsVersion)},
                60000);
    obs.on('ConnectionClosed', e => { update_status(`OBS Disconnected (closed)!: ${e}`); } )
    obs.on('ConnectionError', e => { update_status(`OBS Disconnected (error)!: ${e}`); } )
}


// Set a value (and broadcast an event that represents it).  Handles
// special cases
async function obs_set(name, value) {
    if (window["obs_set_"+name]) {
        if (OBS_DEBUG) {console.debug("obs_set", name, value)}
        return await(window["obs_set_"+name](name, value));
    }
    await _obs_set(name, value);
};
// Raw setting: no special cases.
async function _obs_set(name, value) {
    if (OBS_DEBUG) {console.debug("_obs_set      ", name, value)}
    x = await obs.call("SetPersistentData", {
        realm: "OBS_WEBSOCKET_DATA_REALM_PROFILE", 
        slotName: name,
        slotValue: value});
    await obs.call('BroadcastCustomEvent', {eventData: {[name]: value}});
}

// Broadcast a value (like obs_set, but doesn't permanently store it)
async function obs_broadcast(name, value) {
    if (OBS_DEBUG) {console.debug("obs_broadcast", name, value)}
    await obs.call('BroadcastCustomEvent', {eventData: {[name]: value}});
};

// Get a value
async function obs_get(name) {
    if (window["obs_get_"+name]) {
        if (OBS_DEBUG) {console.debug("obs_get       ", name)}
        return await(window["obs_get_"+name](name));
    }
    return await _obs_get(name)
}
async function _obs_get(name) {
    if (OBS_DEBUG) {console.debug("_obs_get      ", name)}
    x = await obs.call("GetPersistentData", {
        realm: "OBS_WEBSOCKET_DATA_REALM_PROFILE", 
        slotName: name});
    return(x.slotValue);
};

// Run the callback each time 'name' gets an update, in addition to the
// once when it is set.  This is obs_watch + calling it once with the
// value from obs_init.
async function obs_watch_init(name, callback) {
    if (OBS_DEBUG) {console.debug("obs_watch_init", name, callback)}
    obs_watch(name, callback);
    await callback(await obs_get(name));
}

WATCHERS = { };
// Run the callback each time 'name' gets an update
function obs_watch(name, callback) {
    if (OBS_DEBUG) {console.debug("obs_watch     ", name, callback)}
    if (WATCHERS[name] === undefined) {
        WATCHERS[name] = [];
    }
    WATCHERS[name].push(callback);
};

async function obs_force(name) {
    value = await obs_get(name)
    await _obs_trigger(name, value)
}
// Handler for watching things.
async function _obs_trigger(name, value) {
    for (x of (WATCHERS[name] || [])) {
        await x(value)
    }
}
async function _obs_on_custom_event (data) {
    for (name in data) {
        //console.log("C", name, data[name])
        await _obs_trigger(name, data[name])
    }
};

// Initialize all the different watchers
async function _obs_init_watchers() {
    await obs.on('CustomEvent', _obs_on_custom_event);
    await obs.on('CurrentProgramSceneChanged', event => {_obs_trigger('scene', event.sceneName)});
    await obs.on('InputMuteStateChanged', event =>{_obs_trigger('mute-'+event.inputName, event.inputMuted)});
    await obs.on('InputVolumeChanged', event =>{_obs_trigger('volume-'+event.inputName, event.inputVolumeDb)});
}



//
// Special-case OBS relay functions.
//

// Scene setting
async function obs_get_scene(_) {
    ret = await obs.call("GetCurrentProgramScene", {})
    return ret.sceneName || ret.currentProgramSceneName;
}
async function obs_set_scene(_, value) {
    return await obs.call("SetCurrentProgramScene", {sceneName: value})
}


// Audio and volume
async function obs_set_mute(name, state) {
    await obs.call("SetInputMute", {inputName: name, inputMuted: Boolean(state)})
}
async function obs_get_mute(name) {
    ret = await obs.call("GetInputMute", {inputName: name});
    //console.log(name, ret.inputMuted);
    return ret.inputMuted;
}
async function obs_set_volume(name, dB) {
    await obs.call("SetInputVolume", {inputName: name, inputVolumeDb: dB})
}
async function obs_get_volume(name) {
    ret = await obs.call("GetInputVolume", {inputName: name});
    //console.log(name, ret.inputVolumeDb);
    return ret.inputVolumeDb;
}


// File playback
async function obs_playfile(filename) {
    await obs.call("SetInputSettings", {
        inputName: CONFIG.PLAYBACK_INPUT,
        inputSettings: {'local_file': filename},
        overlay: true})
}
async function obs_playfile_stop() {
    await obs.call("TriggerMediaInputAction", {inputName: CONFIG.PLAYBACK_INPUT,
                                               mediaAction: 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP'})
}


// Gallery size
GALLERYSIZE_LASTTRIGGER = [0];
async function obs_set_gallerysize(_, state) {
    // Try to prevent race conditions by allowing only one call at a time
    // TODO: this doesn't work yet (but does make it better).
    let calltime = GALLERYSIZE_LASTTRIGGER[0] + 1;
    GALLERYSIZE_LASTTRIGGER[0] = calltime;
    //console.log("Setting gallery size at", calltime)
    //
    for (let scene of CONFIG.SCENES_WITH_RESIZEABLE_GALLERY) {
        let ret = await obs.call("GetSceneItemId", {sceneName: scene, sourceName: CONFIG.GALLERY});
        let sid = ret.sceneItemId;
        ret = await obs.call("GetSceneItemTransform", {sceneName: scene, sceneItemId: sid})
        let transform = ret.sceneItemTransform
        transform.scaleX = state;
        transform.scaleY = state;
        //console.log(transform)
        //console.log(GALLERYSIZE_LASTTRIGGER[0], calltime, GALLERYSIZE_LASTTRIGGER[0] > calltime)
        if (GALLERYSIZE_LASTTRIGGER[0] > calltime) {
            //console.log("Aborting gallery update, new one started")
            return;
        }
        await obs.call("SetSceneItemTransform", {sceneName: scene, sceneItemId: sid, sceneItemTransform: transform})
    }
    if (GALLERYSIZE_LASTTRIGGER[0] > calltime) {
        //console.log("Aborting gallery update, new one started")
        return;
    }
    // Don't use the gallerysize setter.  It can lead to race conditions and
    // lose all the settings. We poll instead.
    //_obs_set("gallerysize", state)
}
async function obs_get_gallerysize(_) {
    let ret = await obs.call("GetSceneItemId", {sceneName: CONFIG.NOTES, sourceName: CONFIG.GALLERY});
    let sid = ret.sceneItemId;
    ret = await obs.call("GetSceneItemTransform", {sceneName: CONFIG.NOTES, sceneItemId: sid})
    let transform = ret.sceneItemTransform
    return transform.scaleX;
}
async function obs_set_gallerycrop(_, state) {
    ss_resolution = await obs_get('ss_resolution')
    ss_width = parseInt(ss_resolution.split('x')[0])
    ss_height = parseInt(ss_resolution.split('x')[1])
    if (await obs_get('topgallery-mode')) {
        ss_width  = CONFIG.SS_RESOLUTION.zoomw.mainwindow_forcesize[0]
        ss_height = CONFIG.SS_RESOLUTION.zoomw.mainwindow_forcesize[1] - CONFIG.SCREENSHARE_TOPGALLERY_BORDER['top'] - CONFIG.SCREENSHARE_TOPGALLERY_BORDER['bottom']
    }
    console.log("ss_width, ss_height", ss_width, ss_height)
    if (state === undefined) {
        state = await obs_get('gallerycrop')
    }
    topgallery_mode = await obs_get('topgallery-mode')

    // For every scene
    for (let scene of ["Gallery", "GalleryTop", ...CONFIG.SCENES_WITH_RESIZEABLE_GALLERY]) {
        // These are the "normal" galleries
        var ret;
        // Find the "normal" galleries that are full screen
        try {
            ret = await obs.call("GetSceneItemId", {sceneName: scene, sourceName: CONFIG.GALLERY});
        } catch (err) {
            console.log(`Gallery crop: scene ${scene} did not have ${CONFIG.GALLERY}`)
            ret = false;
        }
        if (ret) {
            console.log(`GalleryCrop: ${scene}->${CONFIG.GALLERY}`)
            let sid = ret.sceneItemId;
            ret = await obs.call("GetSceneItemTransform", {sceneName: scene, sceneItemId: sid})
            let transform = ret.sceneItemTransform
            if (!topgallery_mode) {
                let factors = CONFIG.GALLERY_CROP_FACTORS[state]
                console.log(`GT-old, ${scene}, Gallery, ${sid}:`, transform)
                transform = { ...transform, ...factors}
                console.log(`GT-new, ${scene}, Gallery, ${sid}:`, transform)
            } else {
                let factors = CONFIG.TOPGALLERY_CROP_FACTORS[state];
                transform = {...factors}
                console.log(`GT-old[top], ${scene}, Gallery, ${sid}:`, transform)
                transform.cropBottom += ss_height
                if (state > 0) {
                    // Take 200× + 96.  Divide that to the two sides, then add 96 to the right side.
                    picturewidths = 202*state + 94 //200 * state + 96
                    width_onsides = ((ss_width+4) - picturewidths) / 2
                    transform.cropLeft = Math.max(0, width_onsides)
                    transform.cropRight = Math.max(0, width_onsides + 96)
                }
                console.log(`GT-new[top], ${scene}, Gallery, ${sid}:`, transform)
            }
            //console.log(transform)
            await obs.call("SetSceneItemTransform", {sceneName: scene, sceneItemId: sid, sceneItemTransform: transform})
        }
        // Find the galleries that are the top bar
        // try {
        //     ret = await obs.call("GetSceneItemId", {sceneName: scene, sourceName: CONFIG.GALLERYTOP});
        // } catch (err) {
        //     console.log(`Gallery (top) crop: scene ${scene} did not have ${CONFIG.GALLERYTOP}`)
        //     ret = false;
        // }
        // if (ret) {
        //     console.log(`GalleryCrop: ${scene}->${CONFIG.GALLERYTOP}`)
        //     let sid = ret.sceneItemId;
        //     //ret = await obs.call("GetSceneItemTransform", {sceneName: scene, sceneItemId: sid})
        //     //let transform = ret.sceneItemTransform
        //     let factors = CONFIG.TOPGALLERY_CROP_FACTORS[state];
        //     //console.log(`GT-old, top, ${scene}, GalleryTop, ${sid}:`, transform)
        //     //transform = { ...transform, ...factors}
        //     transform = {...factors}
        //     // How to compute this?  Hm...
        //     //factors = JSON.parse(JSON.stringify(CONFIG.GALLERY_CROP_FACTORS[state]))
        //     transform.cropBottom += ss_height
        //     if (state > 0) {
        //         // Take 200× + 96.  Divide that to the two sides, then add 96 to the right side.
        //         picturewidths = 202*state + 94 //200 * state + 96
        //         width_onsides = ((ss_width+4) - picturewidths) / 2
        //         transform.cropLeft = Math.max(0, width_onsides)
        //         transform.cropRight = Math.max(0, width_onsides + 96)
        //     }
        //     console.log(`GT-new, top, state=${state}, ${scene}, GalleryTop, ${sid}:`, transform)
        //     await obs.call("SetSceneItemTransform", {sceneName: scene, sceneItemId: sid, sceneItemTransform: transform})

        // }
    }
    _obs_set("gallerycrop", state)
}
