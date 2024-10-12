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
    console.log(name)
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