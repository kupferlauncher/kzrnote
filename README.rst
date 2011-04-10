=======
vimnote
=======

:Licence:   GNU General Public License v3 (or any later version)
:Credits:   Copyright 2011 Ulrik Sverdrup

vimnote the beginnings of a clone of Gnote (a note taking application like
Tomboy). Except, of course, in each small window there is all of Vim inside.

This is just the beginnings after some hours of hacking. It supports much of
the same D-Bus API, so that it already can be used by Kupfer's Notes plugin,
which normally works with Gnote or Tomboy.

Invoke it using::

    python vimnote.py

It remembers the size and position of each individual note window. Vim
itself gives us a couple of incredible features, including persistent undo
across restarts.

It's not yet decided if vimnote should try to communicate via a fake XML
note format in the D-Bus api. Our file format on disk is locale-encoded
plain text.

The user can put vimnote-specific vim settings in the file
``~/.config/vimnote/user.vim``.

Install it using::

    ./install

The install script uses the environment variables PYTHON, PREFIX, DESTDIR
if they need to be set to non-default values.

.. vim: ft=rst tw=76 sts=4
