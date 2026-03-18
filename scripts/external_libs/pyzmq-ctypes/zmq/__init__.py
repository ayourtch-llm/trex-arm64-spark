'''
Based on pyzmq-ctypes and pyzmq
Updated to work with latest ZMQ shared object

https://github.com/zeromq/pyzmq
https://github.com/svpcom/pyzmq-ctypes

Falls back to system pyzmq if ctypes bindings fail (e.g., missing
platform-specific libzmq.so when running outside Docker).
'''

try:
    from zmq import error
    from zmq.bindings import *
    from zmq.error import *
    from zmq.context import *
    from zmq.socket import *

    major = c_int()
    minor = c_int()
    patch = c_int()

    zmq_version(byref(major), byref(minor), byref(patch))

    __zmq_version__ = tuple((x.value for x in (major, minor, patch)))

    def zmq_version():
        return '.'.join(map(str, __zmq_version__))

except (OSError, ImportError):
    # ctypes bindings failed (e.g., no arm/64bit/libzmq.so outside Docker)
    # Fall back to system pyzmq package (pip install pyzmq / uv add pyzmq)
    import importlib as _il, sys as _sys

    # Remove ourselves from sys.modules so the real pyzmq can load
    _this_path = __path__[0] if hasattr(__path__, '__iter__') else __path__
    _parent = _this_path.rsplit('/', 1)[0] if '/' in _this_path else _this_path.rsplit('\\', 1)[0]

    # Temporarily remove our parent from sys.path
    _saved = [p for p in _sys.path if p == _parent]
    _sys.path = [p for p in _sys.path if p != _parent]

    # Remove our partially-loaded module
    for _k in list(_sys.modules.keys()):
        if _k == 'zmq' or _k.startswith('zmq.'):
            del _sys.modules[_k]

    # Import the real pyzmq
    _real_zmq = _il.import_module('zmq')

    # Restore path
    for _p in _saved:
        _sys.path.insert(1, _p)

    # Re-export everything from real pyzmq
    from zmq import *

