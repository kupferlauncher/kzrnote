=======
kzrnote
=======

:Licence:   GNU General Public License v3 (or any later version)
:Credits:   Copyright 2011 kaizer.se

kzrnote the beginnings of a clone of Gnote (a note taking application like
Tomboy). Except, of course, in each small window there is all of Vim inside.

This is just the beginnings after some hours of hacking. It supports much of
the same D-Bus API, so that it already can be used by Kupfer's Notes plugin,
which normally works with Gnote or Tomboy.

Invoke it using::

    python kzrnote.py

It remembers the size and position of each individual note window. Vim
itself gives us a couple of incredible features, including persistent undo
across restarts.

It's not yet decided if kzrnote should try to communicate via a fake XML
note format in the D-Bus api. Our file format on disk is locale-encoded
plain text.

The user can put kzrnote-specific Vim settings in the file
``~/.config/kzrnote/user.vim``. At the moment, kzrnote is a pure shell
around Vim and I think that works very well—the user can then configure
Vim as wanted. However, there exists a lot of good note-taking plugins and I
am looking to maybe integrate one of them. At least we will manage Vim
commands for opening notes with tab completion and highlighting of Note
names like hyperlinks that will open with ``gf``.  If you want to use a
good-looking and smart note filetype you can use the notes filetype of
https://github.com/xolox/vim-notes  very well with kzrnote already now.

The default Vim setup right now enables persistent undo by default, and it
autosaves the notes vigorously. The commands ``:Note`` and ``:DeleteNote``
work to create new and remove notes respectively, but as mentioned above the
Vim integration is minimal so far.

Install it using::

    ./install

The install script uses the environment variables PYTHON, PREFIX, DESTDIR
if they need to be set to non-default values.

Other remarks

* Notes deleted in the interface are not deleted, they are moved into
  ``~/.local/share/kzrnote/attic``.
* The full-text search (via grep) is only available from the D-Bus API or in
  the development version of Kupfer that uses it.

.. vim: ft=rst tw=76 sts=4
