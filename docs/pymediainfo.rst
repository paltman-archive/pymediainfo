API reference
=============

.. automodule:: pymediainfo
    :members:
    :undoc-members:

.. _library_autodetection:

Library autodetection
=====================

Whenever a method is called with `library_file=None` (the default), the
following logic is used.

Filename Determination
-----------------------

First, the library filename is automatically determined based on the operating
system:

- On **Linux**, `libmediainfo.so.0` is used.
- On **macOS**, the first available file among `libmediainfo.0.dylib` and
    `libmediainfo.dylib` is used, in that order.
- On **Windows**, `MediaInfo.dll` is used.

Paths Searched
--------------

Next, the code checks if a matching library file exists in the same directory
as pymediainfo's ``__init__.py`` and attempts to load it.
If pymediainfo was installed from a wheel, the bundled library is placed in
this location.

Last, if no matching file could be loaded from the previous location, the code
attempts to load the previously determined filename(s) from standard system
paths, using :class:`ctypes.CDLL` for Linux and macOS, or
:class:`ctypes.WinDLL` for Windows.
