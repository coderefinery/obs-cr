OBS_DEBUG = true;

//
// Basic utility functions
//

// Shortcut to select all elements with a given selector, and run
// the anonymous function on all of them.  Used for updating all
// elements of a given class at the same time.
function forEach(querySelector, func) {
    return document.querySelectorAll(querySelector).forEach(x => {
        func(x);
    })
}

// If this is SSL, show the warning
if (window.location.protocol === 'https:') {
    forEach('.ssl-warning', x => {x.style.display = 'block'});
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

// Convert a stable ID to a human name for a scene/preset
function scene_to_name(scene) {
    if (scene == '-') return '-'
    // Human names of named scenes
    if (scene in CONFIG.SCENES) {
        return CONFIG.SCENES[scene].name
    }
    // Human names of named presets
    label = document.querySelector(`.preset-label#${scene}`)
    if (label) {
        return label.textContent
    }
    return scene
}
// Convert a scene's human name to its stable ID
function name_to_scene(name) {
    if (scene == '-') return '-'
    if (name in CONFIG.SCENES_REVERSE) {
        return CONFIG.SCENES_REVERSE[name]
    }
    for (label of document.querySelectorAll('.preset-label')) {
        if (label.textContent == name) {
            return label.id
        }
    }
    return name
}
async function switch_to(scene) {
    scene = name_to_scene(scene)
    // It's a normal scene
    if (scene in CONFIG.SCENES) {
        await obs_set('scene', scene)
        return
    }
    // It's a preset
    await presetClick(scene)
}



//
// Main OBS relay functions.
//

// Set a value (and broadcast an event that represents it)
async function obs_set(name, value) {
    if (window["obs_set_"+name]) {
        if (OBS_DEBUG) {console.debug("obs_set", name, value)}
        return await(window["obs_set_"+name](name, value));
    }
    await _obs_set(name, value);
};
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

// Handler for watching things.
function _obs_trigger(name, value) {
    (WATCHERS[name] || []).forEach( x => {
        x(value)
    })
}
function _obs_on_custom_event (data) {
    for (name in data) {
        //console.log("C", name, data[name])
        _obs_trigger(name, data[name])
    }
};

// Initialize all the different watchers
function _obs_init_watchers(obs) {
    obs.on('CustomEvent', _obs_on_custom_event);
    obs.on('CurrentProgramSceneChanged', event => {_obs_trigger('scene', event.sceneName)});
    obs.on('InputMuteStateChanged', event =>{_obs_trigger('mute-'+event.inputName, event.inputMuted)});
    obs.on('InputVolumeChanged', event =>{_obs_trigger('volume-'+event.inputName, event.inputVolumeDb)});
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

// Gallery size
GALLERYSIZE_LASTTRIGGER = [0];
async function obs_set_gallerysize(_, state) {
    // Try to prevent race conditions by allowing only one call at a time
    // TODO: this doesn't work yet (but does make it better).
    let calltime = GALLERYSIZE_LASTTRIGGER[0] + 1;
    GALLERYSIZE_LASTTRIGGER[0] = calltime;
    //console.log("Setting gallery size at", calltime)
    //
    for (let scene of SCENES_WITH_RESIZEABLE_GALLERY) {
        let ret = await obs.call("GetSceneItemId", {sceneName: scene, sourceName: GALLERY});
        let sid = ret.sceneItemId;
        ret = await obs.call("GetSceneItemTransform", {sceneName: scene, sceneItemId: sid})
        let transform = ret.sceneItemTransform
        transform.scaleX = state;
        transform.scaleY = state;
        //console.log(transform)
        //console.log(GALLERYSIZE_LASTTRIGGER[0], calltime, GALLERYSIZE_LASTTRIGGER[0] > calltime)
        if (GALLERYSIZE_LASTTRIGGER[0] > calltime) {
            console.log("Aborting gallery update, new one started")
            return;
        }
        await obs.call("SetSceneItemTransform", {sceneName: scene, sceneItemId: sid, sceneItemTransform: transform})
    }
    if (GALLERYSIZE_LASTTRIGGER[0] > calltime) {
        console.log("Aborting gallery update, new one started")
        return;
    }
    _obs_set("gallerysize", state)
}
async function obs_get_gallerysize(_) {
    let ret = await obs.call("GetSceneItemId", {sceneName: NOTES, sourceName: GALLERY});
    let sid = ret.sceneItemId;
    ret = await obs.call("GetSceneItemTransform", {sceneName: NOTES, sceneItemId: sid})
    let transform = ret.sceneItemTransform
    return transform.scaleX;
}
async function obs_set_gallerycrop(_, state) {
    for (let scene of SCENES_WITH_RESIZEABLE_GALLERY) {
        let ret = await obs.call("GetSceneItemId", {sceneName: scene, sourceName: GALLERY});
        let sid = ret.sceneItemId;
        ret = await obs.call("GetSceneItemTransform", {sceneName: scene, sceneItemId: sid})
        let transform = ret.sceneItemTransform
        transform = { ...transform, ...CONFIG.GALLERY_CROP_FACTORS[state]}
        //console.log(transform)
        await obs.call("SetSceneItemTransform", {sceneName: scene, sceneItemId: sid, sceneItemTransform: transform})
    }
    _obs_set("gallerycrop", state)
}
