import collections
import inspect
import logging


class ObsState:
    """Manager class for all OBS state.

    This dictonary-like object (which also can be used as attribute
    lookups) serves as a way to sync OBS state and broadcast it.  It
    does:

    - Setting an attribute
      - broadcasts it as a custom event (which every other dict gets)
      - saves it as OBS persistent state
    - Getting an attribute
      - Gets it from persistent state
    - Watching an attribute
      - Watches for those custom events and will trigger the callback
        each time the attribute is updated
    - The _watch_init() method installs a callback, and calls it once
      with the saved value.

    The combination of OBS persistent state and OBS custom events allows
    clients to get updates as soon as a value is changed, but also sync
    to the last-set value each time the program starts.
    """
    ATTRS = {
        ''
        }
    _LOG = logging.getLogger('ObsState')
    def __init__(self, obsreq, obsev, config, test=False):
        super().__setattr__('_req', obsreq)
        super().__setattr__('_ev', obsev)
        super().__setattr__('_watchers', collections.defaultdict(set))
        super().__setattr__('config', config)
        super().__setattr__('test', test)
        # Record what are class attributes and not auto-sent
        super().__setattr__('_dir', set(dir(self)))

        watching_funcs = [func
                          for (name, func) in inspect.getmembers(self, predicate=inspect.ismethod)
                          if name.startswith('on_')
                          ]
        self._LOG.debug('Registering functions: %s', watching_funcs)
        self._ev.callback.register(watching_funcs)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name!r}')
        data = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name)
        value = getattr(data, 'slot_value', None)
        self._LOG.debug('obs.getattr {name!r}={value!r}')
        return value
    __getitem__ = __getattr__

    def __setattr__(self, name, value):
        if name in self._dir:
            super().__setattr__(name, value)
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name!r}')
        self._LOG.debug('obs.setattr %r=%r', name, value)
        self._req.set_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name, value)
        self._req.broadcast_custom_event({'eventData': {name: value}})
        if self.test:
            self.on_custom_event(type('dummy', (), {name: value, 'attrs': lambda: [name]}))
    __setitem__ = __setattr__

    def broadcast(self, name, value):
        """Like __setattr__, but only broadcasts, doesn't save persistent data"""
        self._LOG.debug('obs.broadcast %r=%r', name, value)
        self._req.broadcast_custom_event({'eventData': {name: value}})
        if self.test:
            self.on_custom_event(type('dummy', (), {name: value, 'attrs': lambda: [name]}))

    def __hasattr__(self, name):
        self._LOG.debug('obs.hasattr %r', name)
        if name.startswith('_'):
            raise AttributeError(f'Invalid attribute {name!r}')
        data = self._req.get_persistent_data('OBS_WEBSOCKET_DATA_REALM_PROFILE', name)
        value = getattr(data, 'slot_value', None)
        if value is None:
            return False
        return True

    def on_custom_event(self, event):
        """Watcher for custom events"""
        self._LOG.debug('custom event %r (%r)', event, event.attrs())
        for attr in event.attrs():
            if attr in self._watchers:
                for func in self._watchers[attr]:
                    self._LOG.debug('custom event attr=%r func=%s', attr, func)
                    func(getattr(event, attr))

    def _watch(self, name, func):
        """Set a watcher for updates of this key"""
        self._LOG.debug('obs._watch add %r=%s', name, func)
        self._watchers[name].add(func)

    def _watch_init(self, name, func):
        """Set a watcher for this key.  Also run the callback once with the current value."""
        self._LOG.debug('obs._watch_init add %r=%s', name, func)
        self._watchers[name].add(func)
        func(getattr(self, name))

    # Custom properties
    @property
    def scene(self):
        value = self._req.get_current_program_scene().current_program_scene_name
        self._LOG.debug('obs.scene get scene=%r', value)
        return value
    @scene.setter
    def scene(self, value):
        self._LOG.debug('obs.scene set scene=%r', value)
        self._req.set_current_program_scene(value)
        if self.test:
            self.on_current_program_scene_changed(type('dummy', (), {'scene_name': value}))
    def on_current_program_scene_changed(self, data):
        for func in self._watchers['scene']:
            self._LOG.debug('obs.scene watch scene %r', func)
            func(data.scene_name)

    @property
    def muted(self):
        return self._req.get_input_mute(self.config['AUDIO_INPUT']).input_muted
    @muted.setter
    def muted(self, value):
        self._req.set_input_mute(self.config['AUDIO_INPUT'], value)
        if self.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    @property
    def muted_brcd(self):
        return self._req.get_input_mute(self.config['AUDIO_INPUT']).input_muted
    @muted_brcd.setter
    def muted_brcd(self, value):
        self._req.set_input_mute(self.config['AUDIO_INPUT'], value)
        if self.test:
            self.on_input_mute_state_changed(type('dummy', (), {'input_muted': value}))
    def on_input_mute_state_changed(self, data):
        print(f"Mute {data.input_name!r} to {data.input_muted!r}")
        for ctrl, name in [
            (self.config['AUDIO_INPUT'], 'muted'),
            (self.config['AUDIO_INPUT_BRCD'], 'muted_brcd'),
            ]:
            if data.input_name == ctrl:
                for func in self._watchers[name]:
                    func(data.input_muted)
