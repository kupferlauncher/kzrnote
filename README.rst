=======
kzrnote
=======

:Licence:   GNU General Public License v3 (or any later version)
:Credits:   Copyright 2011–2017

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

The user can put kzrnote-specific Vim settings in the file
``~/.config/kzrnote/user.vim``. At the moment, kzrnote does not have a
filetype of its own and I think that works very well —the user can then
configure Vim as wanted.


The default Vim setup right now enables persistent undo by default, and it
autosaves the notes vigorously. The commands ``:Note`` and ``:DeleteNote``
work to create new and remove notes respectively. ``:Note`` can also open
other existing notes. Mentioned note titles are underlined like hyperlinks
and will open with ``gf``.

I have used code from Peter Odding's https://github.com/xolox/vim-notes to
implement linking of notes. For this reason, the file ``notemode.vim`` is of
course available to copy & modify under the original MIT license terms.
If you want to use a good-looking and smart note filetype in kzrnote, you can
use the notes filetype from Peter's ``vim-notes``.

Install it using::

    ./install

The install script uses the environment variables PYTHON, PREFIX, DESTDIR
if they need to be set to non-default values.

**Other remarks**

* Notes deleted in the interface are not deleted, they are moved into
  ``~/.local/share/kzrnote/attic``.
* The full-text search (via grep) is only available from the D-Bus API and
  in the development version of Kupfer that uses it.
* It's not yet decided if kzrnote should try to communicate via a fake XML
  note format in the D-Bus api. Our file format on disk is locale-encoded
  plain text.
* **Requirements**:

  + Python 3
  + Gtk 3, pygi
  + Vte 2.91
  + dbus-python

.. vim: ft=rst tw=76 sts=4
