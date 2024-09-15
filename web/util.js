
// If this is SSL, show the warning
if (window.location.protocol === 'https:') {
    document.getElementById('ssl-warning').style.display = 'block';
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
    document.getElementById('status').innerText = text;
}


// Set a value (and broadcast an event that represents it)
async function obs_set(name, value) {
    x = await obs.call("SetPersistentData", {
        realm: "OBS_WEBSOCKET_DATA_REALM_PROFILE", 
        slotName: name,
        slotValue: value});
        await obs.call('BroadcastCustomEvent', {eventData: {[name]: value}});
    };

// Broadcast a value (like obs_set, but doesn't permanently store it)
async function obs_broadcast(name, value) {
    await obs.call('BroadcastCustomEvent', {eventData: {[name]: value}});
};

// Get a value
async function obs_get(name) {
x = await obs.call("GetPersistentData", {
    realm: "OBS_WEBSOCKET_DATA_REALM_PROFILE", 
    slotName: name});
    return(x.slotValue);
};

WATCHERS = { };
// Run the callback each time 'name' gets an update
function obs_watch(name, callback) {
    if (WATCHERS[name] === undefined) {
        WATCHERS[name] = [];
    }
    WATCHERS[name].push(callback);
};
// Run the callback each time 'name' gets an update, in addition to the
// once when it is set
        
async function obs_watch_init(name, callback) {
    obs_watch(name, callback);
    await callback(await obs_get(name));
}
// Handler for watching things.
function _obs_on_custom_event (data) {
    //console.log('a');
    for (name in data) {
        //console.log('b', name);
        if (WATCHERS[name] !== undefined) {
            //console.log('c', name, data[name]);
            for (func of WATCHERS[name].values()) {
                //console.log('d', name, data[name], func);
                func(data[name]);
            }
        }
    }
};
