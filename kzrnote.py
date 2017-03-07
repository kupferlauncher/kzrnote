# encoding: utf-8
# vim: sts=4 sw=4 et ft=python foldmethod=marker

APPNAME = "kzrnote"
VIM_DEFAULT = 'vim'
ICONNAME = 'kzrnote'
VERSION='0.2'

# Preamble {{{
import importlib
import json
import locale
import os
import signal
import sys
import time
import urllib.parse
import subprocess

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

import dbus
from dbus.gi_service import ExportedGObject
from dbus.mainloop.glib import DBusGMainLoop


from gi.repository import GObject, GLib

## "Lazy imports"
uuid = None
Gio = None
Gdk = None
Gtk = None
Vte = None
Pango = None

debug = True

def lazy_import(name, fullname=None):
    if globals()[name] is None:
        globals()[name] = importlib.import_module(fullname or name)

def plainlog(*args):
    for arg in args:
        sys.stderr.write(str(arg))
        sys.stderr.write(" ")
    sys.stderr.write("\n")

def debug_log(*args):
    if debug:
        sys.stderr.write("%s: " % __name__)
        sys.stderr.write(str(time.time()) + " ")
        plainlog(*args)

def log(*args):
    sys.stderr.write("%s: " % __name__)
    sys.stderr.write(str(time.time()) + " ")
    plainlog(*args)

def error(*args):
    sys.stderr.write("Error: ")
    plainlog(*args)

def _(x):
    return x

# }}}
# Default configuration {{{
DEFAULT_NOTE_NAME ="Empty Note"
NEW_NOTE_TEMPLATE="Note %s"
MAXTITLELEN=50
WINDOW_SIZE_MAIN = (300, 400)
NOTE_ICON = "gtk-file"
N_RECENT_MENU = 15

DATA_ATTIC="attic"
CACHE_SWP="cache"
CACHE_NOTETITLES="notetitles"
CONFIG_RCTEXT=r"""
" NOTE: This file is overwritten regularly.
so ./notemode.vim
"""
CONFIG_USERRC="user.vim"
CONFIG_VIMRC="%s.vim" % APPNAME
CONFIG_FILENAME="config.json"
VIM_EXTRA_FLAGS=[]

DATA_WELCOME_NOTE="""\
Welcome to kzrnote
..................

As of this writing, no special syntax file
exists for kzrnote, so you're free to use any
mode you would like for each note.

Each note remembers its size and position.

Links are created to other notes if their
title is mentioned, and can be opened with
`gf`

→ Configuring kzrnote

kzrnote has a D-Bus API that allows application
integration as well as full-text search.

There are two commands available

 :Note        create a new note, or with an
              argument, open an existing note.
 :DeleteNote  delete the current note
"""

DATA_ABOUT_NOTE="""\
Configuring kzrnote
...................

You can edit terminal colors, font and vim executable
in ~/.config/kzrnote/config.json

Example::

    {
        "colors": {
            "foreground": "black",
            "background": "white"
        },
        "font": "DejaVu Sans Mono 10",
        "vim": "vim"
    }

You can set kzrnote-specific vim settings in the
file ~/.config/kzrnote/user.vim

You can set::

    let g:kzrnote_link_notes = 0

to disable linking.

The default configuration is set up to
vigorously autosave all open notes. Persistent
undo is also enabled.

Deleted notes are moved to
~/.local/share/kzrnote/attic

You can set::

    let g:kzrnote_autosave = 0

to disable autosaving

kzrnote works best with Vim 7.3. The minimal
configuration to make sure links are highlighted and
that the `:Note` command works is something like the
following::

    set nocompatible
    syntax on
"""

# }}}
# Note Access {{{
def ensurefile(filename, default_content=None):
    """
    ensure @filename exists:
    it is touched if it does not exist.
    directories in the path are NOT created.

    @default_content: bytestring, if not None, to
        write into the file by default.
    """
    if not os.path.exists(filename):
        touch_filename(filename, lcontent=default_content)
    return filename

def ensuredir(dirpath):
    """
    ensure @dirpath exists and return it again

    raises OSError on other error than EEXIST
    """
    try:
        os.makedirs(dirpath, 0o700)
    except FileExistsError:
        pass
    return dirpath

def get_xdg_dir(xdg_var, fallback):
    xdg_dir = os.getenv(xdg_var) or os.path.expanduser(fallback)
    return os.path.abspath(os.path.join(xdg_dir, APPNAME))

def get_notesdir():
    return get_xdg_dir("XDG_DATA_HOME", "~/.local/share")

def get_config_dir():
    return get_xdg_dir("XDG_CONFIG_HOME", "~/.config")

def get_cache_dir():
    return get_xdg_dir("XDG_CACHE_HOME", "~/.cache")

## make uris just  like gnote
## template  note://kzrnote/1823-aa8s9df-1231290

URL_SCHEME = "note"
URL_NETLOC = APPNAME
NOTE_SUFFIX = ".note"
## All uuids we use are this length (characters)
FILENAME_LEN = 36 + len(NOTE_SUFFIX)

### Should we use UTF-8 or locale encoding?
##NOTE_ENCODING="UTF-8"
## Right now we are using locale encoding

def tolocaleencoding(ustr, errors=True):
    enc = locale.getpreferredencoding(do_setlocale=False)
    if errors:
        return ustr.encode(enc)
    else:
        return ustr.encode(enc, 'replace')

def tofilename(ustr, errors=True):
    return ustr

def fromlocaleencoding(lstr, errors=True):
    """
    Return a unicode string from the locale-encoded @lstr
    """
    enc = locale.getpreferredencoding(do_setlocale=False)
    if errors:
        return lstr.decode(enc)
    else:
        return lstr.decode(enc, 'replace')

def tonoteencoding(ustr, errors=True):
    """
    Return a byte string in the note encoding from @ustr
    """
    return tolocaleencoding(ustr, errors)

def fromnoteencoding(lstr, errors=True):
    """
    Return a unicode string from the note-encoded @lstr
    """
    return fromlocaleencoding(lstr, errors)

def opennote(filename, mode, **kwargs):
    if 'errors' not in kwargs:
        kwargs['errors'] = "replace"
    return open(filename, mode, **kwargs)

def fromgtkstring(gtkstr):
    return gtkstr.decode("utf-8") if isinstance(gtkstr, str) else gtkstr

def toasciiuri(uuri):
    return uuri.encode("utf-8") if isinstance(uuri, str) else uuri

def note_uuid_from_filename(filename):
    """
    Raises ValueError for invalid filename
    """
    if filename.endswith(NOTE_SUFFIX):
        return os.path.basename(filename)[:-len(NOTE_SUFFIX)]
    raise ValueError

def get_note_uri(filepath):
    return "%s://%s/%s" % (URL_SCHEME, URL_NETLOC,
                           note_uuid_from_filename(filepath))

def get_filename_for_note_uri(uri):
    """
    Raises ValueError on invalid url

    does not check if it exists
    """
    parse = urllib.parse.urlparse(uri)
    if parse.scheme != URL_SCHEME or parse.netloc != URL_NETLOC:
        raise ValueError("Not a %s://%s/.. URI" % (URL_SCHEME, URL_NETLOC))
    if len(parse.path) < 2:
        raise ValueError("Invalid path in %s" % uri)
    return os.path.join(get_notesdir(), os.path.basename(parse.path)) + NOTE_SUFFIX

def get_filename_for_note_basename(notename):
    """
    Leniently accept uuids and file basenames and convert into notes.

    Raises ValueError if invalid name or does not exist.
    """
    if notename.endswith(NOTE_SUFFIX):
        end = -len(NOTE_SUFFIX)
    else:
        end = None
    filename = get_note(os.path.basename(notename)[:end])
    if is_note(filename):
        return filename
    raise ValueError("No note found")

def get_note_paths():
    D = get_notesdir()
    for x in os.listdir(D):
        path = os.path.join(D, x)
        if is_note(path):
            yield path

def get_note(note_uuid):
    return os.path.join(get_notesdir(), note_uuid + NOTE_SUFFIX)

def is_valid_note_filename(filename):
    return (filename.startswith(get_notesdir())  and
            len(os.path.basename(filename)) == FILENAME_LEN and
            filename.endswith(NOTE_SUFFIX))

def is_note(filename):
    return is_valid_note_filename(filename) and os.path.exists(filename)

def get_new_note_name():
    for retry in range(1000):
        name = str(uuid.uuid4())
        if not os.path.exists(get_note(name)):
            return get_note(name)
    raise RuntimeError

def touch_filename(filename, lcontent=None):
    """
    Touch non-existing @filename

    optionally write the bytestring @lcontent into it
    """
    fd = os.open(filename, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    if lcontent:
        written = 0
        while written < len(lcontent):
            written += os.write(fd, lcontent[written:])
    os.close(fd)

def overwrite_by_rename(filename, lcontent):
    """
    Overwrite @filename by writing to a temporary file,
    then renaming over the original file.

    Write the bytestring @lcontent into it
    """
    tmp_filename = "%s.tmp_%d" % (filename, os.getpid())
    touch_filename(tmp_filename, lcontent)
    os.rename(tmp_filename, filename)

def read_note_contents(filename):
    """
    Read @filename which must exist

    return a byte string
    """
    read = []
    with opennote(filename, "r") as fobj:
        while 1:
            r = fobj.read()
            if not r:
                break
            read.append(r)
    return "".join(read)

def try_register_pr_pdeathsig():
    """
    Register PR_SET_PDEATHSIG (linux-only) for the calling process
    which is a signal delivered when its parent dies.

    This should ensure child processes die with the parent.
    """
    PR_SET_PDEATHSIG=1
    SIGHUP=1
    if sys.platform != 'linux2':
        return
    try:
        import ctypes
    except ImportError:
        return
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(PR_SET_PDEATHSIG, SIGHUP)
    except (AttributeError, OSError):
        pass

# }}}
class NoteMetadataService (object):  # {{{
    def __init__(self):
        self.storagefile = os.path.join(get_cache_dir(), "metadata")
        self.geometries = {}

    def load(self):
        """
        Load configuration
        """
        try:
            with open(self.storagefile, 'r') as fobj:
                for line in fobj:
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    uri = parts[0]
                    try:
                        coords = [abs(int(x)) for x in parts[1:]]
                    except ValueError:
                        pass
                    else:
                        (a,b) = coords[:2]
                        (c,d) = coords[2:]
                        self.geometries[uri] = ((a,b), (c,d))
        except FileNotFoundError:
            pass

    def save(self):
        """
        Save configuration
        """
        with open(self.storagefile, 'w') as outfobj:
            for uri, geometry in self.geometries.items():
                outfobj.write("%s " % uri)
                ((a,b), (c,d)) = geometry
                outfobj.write("%d %d %d %d" % (a,b,c,d))
                outfobj.write("\n")

    def update_window_geometry(self, window, event, notefilename):
        note_uri = get_note_uri(notefilename)
        self.geometries[note_uri] = (window.get_size(), window.get_position())

    def get_geometry_for(self, notefilename):
        """
        Return a (size, position) tuple for @notefilename
        or None if nothing is recorded.
        """
        note_uri = get_note_uri(notefilename)
        return self.geometries.get(note_uri, None)

class Config:
    def __init__(self):
        CONFIG = ensuredir(get_config_dir())
        self.filename = os.path.join(CONFIG, CONFIG_FILENAME)
        self.config = {}

    def load(self):
        try:
            with open(self.filename) as f:
                self.config = json.load(f)
        except FileNotFoundError:
            return
        except OSError as exc:
            error("When reading config:", exc)
            return

    def get_vim(self):
        vim = self.config.get("vim")
        if isinstance(vim, str) and vim:
            return vim
        else:
            return VIM_DEFAULT

    def get_color(self, name):
        fg = self.config.get("colors", {}).get(name)
        if fg is None:
            return None
        c = Gdk.RGBA()
        if isinstance(fg, str) and c.parse(fg):
            return c
        else:
            error("Could not parse color: %r" % (fg, ))
            return None

    def get_font(self):
        font_desc = self.config.get("font")
        if not font_desc or not isinstance(font_desc, str):
            return None
        fd = Pango.FontDescription.from_string(font_desc)
        if not fd.get_size():
            fd.set_size(10)
        return fd

def guess_default_window_size(cols=80, rows=60):
    """
    Return size tuple width, height (in pixels)
    """
    textview = Gtk.TextView.new()
    textview.set_property("monospace", True)
    # Find the size of one (monospace) letter
    playout = textview.create_pango_layout("X")
    ink_r, logical_r = playout.get_pixel_extents()

    return (
        ink_r.width * cols,
        ink_r.height * rows,
    )

# }}}
# MainInstance {{{
server_name = "io.github.kupferlauncher.%s" % APPNAME
interface_name = "io.github.kupferlauncher.%s" % APPNAME
object_name = "/io/github/kupferlauncher/%s" % APPNAME

class MainInstance (ExportedGObject):
    __gsignals__ = {
        "note-created": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_STRING, )),
        ## signature: filepath, bool:user_action
        "note-deleted": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_STRING, GObject.TYPE_BOOLEAN)),
        "title-updated": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_STRING, GObject.TYPE_STRING )),
        "note-contents-changed": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_STRING, )),
        "note-opened": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE,
            (GObject.TYPE_STRING, GObject.TYPE_PYOBJECT)),
        ## signature: filename, GtkWindow
    }
    def __init__(self):
        """Create a new service on the Session Bus

        Raises RuntimeError on no dbus-connection
        Raises NameError if the service already exists
        """
        try:
            session_bus = dbus.Bus()
        except dbus.DBusException:
            raise RuntimeError("No D-Bus connection")
        if session_bus.name_has_owner(server_name):
            raise NameError

        bus_name = dbus.service.BusName(server_name, bus=session_bus)
        super(MainInstance, self).__init__(conn=session_bus,
                                           object_path=object_name,
                                           bus_name=bus_name)
        #gobject.GObject.__init__(self)

        self.open_files = {}
        self.file_names = {}
        self.preload_ids = {}
        self.window = None
        self.status_icon = None
        self.connect("note-deleted", self.on_note_deleted)
        self.connect("title-updated", self.on_note_title_updated)
        self.connect("note-opened", self.on_note_opened)
        self.metadata_service = NoteMetadataService()
        self.config = Config()
        self.ready_to_display_notes = False

    def unregister(self):
        dbus.Bus().release_name(server_name)

    def wait_for_display_notes(self):
        debug_log("Wait for display_notes, setup done: %s" % self.ready_to_display_notes)
        while Gtk.events_pending() and not self.ready_to_display_notes:
            Gtk.main_iteration()

    # }}}
    # D-Bus Interface {{{
    @dbus.service.method(interface_name, in_signature="", out_signature="s")
    def CreateNote(self):
        new_note = get_new_note_name()
        touch_filename(new_note)
        return get_note_uri(new_note)

    @dbus.service.method(interface_name, in_signature="s", out_signature="s")
    def CreateNamedNote(self, title):
        new_note = get_new_note_name()
        touch_filename(new_note, tonoteencoding(title))
        return get_note_uri(new_note)

    @dbus.service.method(interface_name, in_signature="s", out_signature="b")
    def DeleteNote(self, uri):
        """
        Raises ValueError on invalid @uri
        """
        filename = get_filename_for_note_uri(uri)
        if is_note(filename):
            self.delete_note(filename)
            return True
        else:
            error("Is not a note", uri)
            return False

    @dbus.service.method(interface_name, in_signature="s", out_signature="b")
    def DisplayNote(self, uri):
        """
        Raises ValueError on invalid @uri
        """
        filename = get_filename_for_note_uri(uri)
        if is_note(filename):
            self.wait_for_display_notes()
            self.display_note_by_file(filename)
            return True
        else:
            error("Is not a note", uri)
            return False

    @dbus.service.method(interface_name)
    def DisplaySearch(self):
        return self.KzrnoteCommandline([], '', '')

    @dbus.service.method(interface_name, in_signature="s", out_signature="s")
    def FindNote(self, linked_title):
        """
        Returns "" for not found
        """
        filename = self.has_note_by_title(linked_title)
        if filename and is_note(filename):
            return get_note_uri(filename)
        return ""

    @dbus.service.method(interface_name, in_signature="s", out_signature="b")
    def NoteExists(self, uri):
        """
        Raises ValueError on invalid @uri
        """
        filename = get_filename_for_note_uri(uri)
        return is_note(filename)

    @dbus.service.method(interface_name, in_signature="", out_signature="as")
    def ListAllNotes(self):
        all_notes = []
        for note in self.get_note_filenames(True):
            all_notes.append(get_note_uri(note))
        return all_notes

    @dbus.service.method(interface_name, in_signature="s", out_signature="s")
    def GetNoteTitle(self, uri):
        """
        Raises ValueError on invalid @uri
        """
        filename = get_filename_for_note_uri(uri)
        if is_note(filename):
            return self.ensure_note_title(filename)
        return ""

    @dbus.service.method(interface_name, in_signature="s", out_signature="u")
    def GetNoteChangeDate(self, uri):
        """
        Raises ValueError on invalid @uri
        Raises OSError for internal filesystem error
        """
        filename = get_filename_for_note_uri(uri)
        return self.get_note_change_date(filename)

    @dbus.service.method(interface_name, in_signature="s", out_signature="s")
    def GetNoteContents(self, uri):
        """
        Raises ValueError on invalid @uri
        Raises UnicodeDecodeError on coding error
        """
        filename = get_filename_for_note_uri(uri)
        if is_note(filename):
            return read_note_contents(filename)
        else:
            return ""

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def SetNoteContents(self, uri, contents):
        """
        Raises ValueError on invalid @uri
        Raises UnicodeEncodeError on coding error
        """
        filename = get_filename_for_note_uri(uri)
        if is_note(filename):
            lcontents = tonoteencoding(contents)
            overwrite_by_rename(filename, lcontents)
            self.emit("note-contents-changed", filename)
            return True
        else:
            return False

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def SetNoteContentsXml(self, uri, contents):
        # Easy choice: SetNoteContentsXml broken on Gnote. We can support
        # SetNoteCompleteXml
        raise NotImplementedError

    @dbus.service.method(interface_name, in_signature="sb", out_signature="as")
    def SearchNotes(self, query, case_sensistive):
        ## NOTE: For "compatibility", we are always case sensistive
        results = []
        grep_cmd = ['/bin/grep', '-l', '-i']
        grep_cmd.extend(['-e', query])
        grep_cmd.extend(['-r', get_notesdir()])
        grep_cmd.append('--include=*%s' % NOTE_SUFFIX)
        grep_cmd.extend(['--exclude-dir=%s' % CACHE_SWP,
                         '--exclude-dir=%s' % DATA_ATTIC])
        debug_log(grep_cmd)
        p = subprocess.Popen(grep_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             close_fds=True)
        cin, cout = (p.stdin, p.stdout)
        cin.close()
        try:
            for line in cout:
                line = fromlocaleencoding(line)
                debug_log(line)
                line = line.strip()
                if is_note(line):
                    results.append(get_note_uri(line))
        finally:
            cout.close()
        return results


    @dbus.service.method(interface_name, in_signature="s", out_signature="as")
    def GetTagsForNote(self, tagname):
        ## FIXME
        return []

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def AddTagToNote(self, uri, tagname):
        ## FIXME
        raise NotImplementedError

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def RemoveTagFromNote(self, uri, tagname):
        ## FIXME
        raise NotImplementedError

    @dbus.service.method(interface_name, in_signature="s", out_signature="as")
    def GetAllNotesWithTag(self, tagname):
        ## FIXME
        return []

    @dbus.service.method(interface_name, out_signature="s")
    def Version(self):
        return "%s %s" % (APPNAME, VERSION)

    ## Kzrnote-specific D-Bus methods
    @dbus.service.method(interface_name, in_signature="asss", out_signature="s")
    def KzrnoteCommandline(self, uargv, display, desktop_startup_id):
        return self.handle_commandline(uargv, display, desktop_startup_id)

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def KzrnoteNew(self, argument, sfilename):
        debug_log("KzrnoteNew: %s, %s" % (argument, sfilename))
        self.create_open_note(None)
        return True

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def KzrnoteDelete(self, argument, sfilename):
        debug_log("KzrnoteDelete: %s, %s" % (argument, sfilename))
        lfilename = tofilename(sfilename, False)
        if not is_note(lfilename):
            raise ValueError("Cannot delete %r" % lfilename)
        self.delete_note(lfilename)
        return True

    @dbus.service.method(interface_name, in_signature="ss", out_signature="b")
    def KzrnoteOpen(self, argument, sfilename):
        debug_log("KzrnoteOpen: %s, %s" % (argument, sfilename))
        ## Open note either by note uuid or by title
        try:
            ## make sure the filename is a byte string
            largument = tofilename(argument, False)
            filename = get_filename_for_note_basename(largument)
        except ValueError:
            filename = self.has_note_by_title(argument, False)
        if filename and is_note(filename):
            debug_log("Open:", filename)
            self.display_note_by_file(filename)
            return True
        error("Can not open:", largument)
        return False


    @dbus.service.method(interface_name)
    def Quit(self):
        Gtk.main_quit()

    # }}}
    # Note Model {{{
    def reload_filemodel(self, model):
        model.clear()
        for filename in self.get_note_filenames(True):
            display_name = self.ensure_note_title(filename)
            model.append((filename, display_name))

    def model_reassess_file(self, model, filename, addrm=False, change=False):
        """
        Examine changed @filename and decide
        whether to insert, delete, update it

        @addrm: if created/deleted
        @change: if changed
        """
        if not is_valid_note_filename(filename):
            return False
        ## linear search. Will also hit the most recently
        ## changed files fast anyway
        row_filename, row_title = (None, None)
        existed_before = True
        rowidx = None
        for idx, row in enumerate(model):
            row_filename, row_title = row
            if row_filename == filename:
                rowidx = idx
                break
        else:
            existed_before = False
        exists_now = is_note(filename)
        if not existed_before and exists_now:
            new_title = self.ensure_note_title(filename)
            model.insert(0, (filename, new_title))
            self.emit("note-created", filename)
        elif existed_before and exists_now:
            self.reload_file_note_title(filename)
            new_title = self.file_names[filename]
            ## write in new title
            model[rowidx] = (filename, new_title)
            ## Move it to the top
            rowpath = (rowidx, )
            rowiter = model.get_iter(rowpath)
            topiter = model.get_iter((0, ))
            model.move_before(rowiter, topiter)
            self.emit("note-contents-changed", filename)
        elif existed_before and not exists_now:
            del model[rowidx]
            self.emit("note-deleted", filename, False)
        else:
            error("File modifed does not exist: %r" % filename)


    def get_note_change_date(self, filename):
        """
        Get the change date for @filename (as an number)

        raises OSError on error when reading @filename
        """
        stat_res = os.stat(filename)
        return stat_res.st_mtime

    def get_note_filenames(self, date_sort=False):
        """
        Return a sequence of file paths for all notes

        @date_sort: if True, sort by most recent first
        """
        filenames = get_note_paths()
        if date_sort:
            return sorted(filenames,
                          key=self.get_note_change_date,
                          reverse=True)
        else:
            return filenames

    def has_note_by_title(self, utitle, case_sensitive=True):
        """
        Return (the first) filename if exists, None otherwise

        Titles longer than the max length are truncated(!)
        """
        utitle = utitle[:MAXTITLELEN]
        for filename, note_title in self.file_names.items():
            if case_sensitive and note_title == utitle:
                return filename
            elif not case_sensitive and note_title.lower() == utitle.lower():
                return filename
        return None

    def ensure_note_title(self, filename):
        """make sure we have a title for @filename, and return it for convenience"""
        if not filename in self.file_names:
            self.reload_file_note_title(filename)
        return self.file_names[filename]

    def reload_file_note_title(self, filename):
        self.file_names[filename] = self.extract_note_title(filename)
        self.emit("title-updated", filename, self.file_names[filename])

    def extract_note_title(self, filepath):
        try:
            with opennote(filepath, "r") as f:
                for firstline in f:
                    ufirstline = firstline.strip()
                    if ufirstline:
                        return ufirstline[:MAXTITLELEN]
                    break
        except EnvironmentError:
            pass
        return DEFAULT_NOTE_NAME
    # }}}
    # GUI {{{
    def setup_basic(self):
        """
        Setup basic data needed for displaying notes
        """
        self.metadata_service.load()
        self.config.load()
        self.ready_to_display_notes = True

    def setup_gui(self):
        # notification icon
        status_icon = Gtk.StatusIcon.new_from_icon_name(ICONNAME)
        status_icon.set_tooltip_text(APPNAME)
        status_icon.set_visible(True)
        self.status_icon = status_icon

        # main window with its toolbar and note list
        Gtk.Window.set_default_icon_name(ICONNAME)
        self.window = Gtk.Window.new(Gtk.WindowType.TOPLEVEL)
        self.window.set_default_size(*WINDOW_SIZE_MAIN)
        self.list_view = Gtk.TreeView.new()
        self.list_store = Gtk.ListStore(GObject.TYPE_STRING,
                                        GObject.TYPE_STRING)
        self.list_view.set_model(self.list_store)
        cell = Gtk.CellRendererText()
        filename_col = Gtk.TreeViewColumn("Note", cell, text=1)
        self.list_view.append_column(filename_col)
        self.reload_filemodel(self.list_store)
        self.list_view.set_rules_hint(True)
        self.list_view.set_search_column(1)
        self.list_view.show()
        self.list_view.connect("row-activated", self.on_list_view_row_activate)

        ## setup the list view to match searches by any substring
        ## (the default only matches prefixes)
        def search_cmp(model, column, key, miter):
            ## NOTE: Return *False* for matches
            return key not in model.get_value(miter, column).lower()
        self.list_view.set_search_equal_func(search_cmp)
        toolbar = Gtk.Toolbar()
        new = Gtk.ToolButton(Gtk.STOCK_NEW)
        new.set_label(_("Create _New Note"))
        new.set_use_underline(True)
        new.set_is_important(True)
        new.connect("clicked", self.create_open_note)
        delete = Gtk.ToolButton(Gtk.STOCK_DELETE)
        delete.connect("clicked", self.on_delete_row_cliecked, self.list_view)
        delete.set_is_important(True)
        quit = Gtk.ToolButton(Gtk.STOCK_QUIT)
        quit.set_is_important(True)
        quit.connect("clicked", Gtk.main_quit)
        def toolbar_append(item):
            toolbar.insert(item, toolbar.get_n_items())
        toolbar_append(new)
        toolbar_append(delete)
        toolbar_append(quit)
        toolbar.show_all()
        scrollwin = Gtk.ScrolledWindow()
        scrollwin.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrollwin.add(self.list_view)
        scrollwin.show()
        vbox = Gtk.VBox()
        vbox.pack_start(toolbar, False, True, 0)
        vbox.pack_start(scrollwin, True, True, 0)
        vbox.show()
        self.window.add(vbox)
        # focus the list so that the user can search immediately
        self.list_view.grab_focus()
        self.window.connect("delete-event", lambda *args: self.window.hide() or True)
        status_icon.connect("activate", self.on_status_icon_clicked)
        status_icon.connect("popup-menu", self.on_status_icon_menu)

        gfile = Gio.File.new_for_path(get_notesdir())
        self.monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        if self.monitor:
            self.monitor.connect("changed",
                                 self.on_notes_monitor_changed,
                                 self.list_store)
        self.do_first_run()

    def do_first_run(self):
        """
        If there are no notes, create them
        and display the welcome note
        """
        if next(iter(get_note_paths()), None) is not None:
            return
        welcome_file = get_new_note_name()
        about_file = get_new_note_name()
        touch_filename(welcome_file, tonoteencoding(DATA_WELCOME_NOTE, False))
        touch_filename(about_file, tonoteencoding(DATA_ABOUT_NOTE, False))
        self.display_note_by_file(welcome_file)

    def on_list_view_row_activate(self, treeview, path, view_column):
        store = treeview.get_model()
        titer = store.get_iter(path)
        (filepath, ) = store.get(titer, 0)
        self.display_note_by_file(filepath)

    def on_status_icon_clicked(self, widget):
        ## on activate, emit a signal to open the menu
        widget.emit("popup-menu", 1, Gtk.get_current_event_time())

    def on_status_icon_menu(self, widget, button, activate_time):
        def present_window(sender):
            self.window.present()

        def display_note(sender, filename):
            self.display_note_by_file(filename)

        ## make and show a popup menu
        ## None marks the separators and the recent notes
        actions = [
            (Gtk.STOCK_NEW, _("Create _New Note"), self.create_open_note),
            (Gtk.STOCK_FIND, _("_Show All Notes"), present_window),
            None,
            (Gtk.STOCK_QUIT, None, Gtk.main_quit),
        ]

        menu = Gtk.Menu()

        for action in actions:
            if action is not None:
                icon, title, target = action
                mitem = Gtk.ImageMenuItem.new_from_stock(icon)
                if title:
                    mitem.set_label(title)
                mitem.connect("activate", target)
                menu.append(mitem)
            else:
                ## insert the recent notes
                menu.append(Gtk.SeparatorMenuItem())
                notes_sorted = list(self.get_note_filenames(True))
                for filename in notes_sorted[:N_RECENT_MENU]:
                    display_name = self.ensure_note_title(filename)
                    mitem = Gtk.ImageMenuItem.new()
                    #mitem.set(NOTE_ICON)
                    mitem.set_label(display_name)
                    mitem.set_use_underline(False)
                    mitem.set_always_show_image(True)
                    mitem.connect("activate", display_note, filename)
                    menu.append(mitem)
                menu.append(Gtk.SeparatorMenuItem())
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu,
                   widget, button, activate_time)

    def on_delete_row_cliecked(self, toolitem, treeview):
        path, column = treeview.get_cursor()
        if path is None:
            return
        store = treeview.get_model()
        titer = store.get_iter(path)
        (filepath, ) = store.get(titer, 0)
        self.delete_note(filepath)
    # }}}
    # Embedding VIM {{{
    def display_note_by_file(self, filename):
        if filename in self.open_files:
            self.open_files[filename].present()
        else:
            self.open_note_on_screen(filename)

    def delete_note(self, filepath):
        debug_log("Moving ", filepath)
        notes_dir = get_notesdir()
        attic_dir = os.path.join(notes_dir, DATA_ATTIC)
        try:
            os.makedirs(attic_dir)
        except OSError:
            pass
        os.rename(filepath, os.path.join(attic_dir, os.path.basename(filepath)))
        self.emit("note-deleted", filepath, True)

    def close_all(self):
        """
        Close all open windows and hidden windows
        """
        self.metadata_service.save()
        self.window.hide()
        for filepath in list(self.open_files):
            debug_log("closing", filepath)
            self.open_files.pop(filepath).destroy()
        for preload_id in list(self.preload_ids):
            debug_log("closing", preload_id)
            self.preload_ids.pop(preload_id).destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.5)

    def on_note_deleted(self, sender, filepath, user_action):
        ## only close its window if the user deleted it
        if filepath in self.open_files and user_action:
            self.open_files.pop(filepath).destroy()

    def on_note_title_updated(self, sender, filepath, new_title):
        if filepath in self.open_files:
            title = self.get_window_title_for_note_title(new_title)
            self.open_files[filepath].set_title(title)
        ## write out all titles to a cache file
        cache = ensuredir(get_cache_dir())
        with opennote(os.path.join(cache, CACHE_NOTETITLES), "w") as fobj:
            for filepath in self.get_note_filenames(False):
                title = self.ensure_note_title(filepath)
                fobj.write("%s\n" % (title, ))

    def on_notes_monitor_changed(self, monitor, gfile1, gfile2, event, model):
        if event in (Gio.FileMonitorEvent.CREATED,
                     Gio.FileMonitorEvent.DELETED):
            self.model_reassess_file(model, gfile1.get_path(), addrm=True)
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, ):
            self.model_reassess_file(model, gfile1.get_path(), change=True)

    def on_note_opened(self, sender, filepath, window):
        window.connect("configure-event",
                       self.metadata_service.update_window_geometry,
                       filepath)
        # TODO: Support notes changing font size (and thus size)?

    def position_window(self, window, filepath):
        """
        Modify @window and move to the correct spot for @filepath
        """
        geometry = self.metadata_service.get_geometry_for(filepath)
        if geometry is not None:
            size, position = geometry
            window.resize(*size)
            window.move(*position)

    def get_window_title_for_note_title(self, note_title):
        progname = GLib.get_application_name()
        title = "%s: %s" % (progname, note_title)
        return title

    def open_note_on_screen(self, filepath, title=None, screen=None,
                            timestamp=None):
        """
        Open @filepath that does not have a window open
        since before
        """
        display_name_long = self.ensure_note_title(filepath)
        self.file_names[filepath] = display_name_long
        title = self.get_window_title_for_note_title(display_name_long)
        self.new_vimdow(title, filepath)

    def create_open_note(self, sender):
        note_name = get_new_note_name()
        time_ustr = time.strftime("%c")
        lcontent = tonoteencoding(NEW_NOTE_TEMPLATE % time_ustr, errors=False)
        touch_filename(note_name, lcontent)
        return self.open_note_on_screen(note_name)

    # }}}
    def handle_commandline(self, arguments, display, desktop_startup_id): #{{{
        """
        When handling commandline:

        Open The Note URIS on the commandline,
        if nothing else is there, present the main window.

        @arguments: A unicode sequence of arguments
        @display: the name of the X screen (not implemented)
        @desktop_startup_id: $DESKTOP_STARTUP_ID from invocation

        returns: Error output (unicode) (Argument parsing messages)
        """
        debug_log("handle commandline", arguments, display, desktop_startup_id)

        ## parse out timestamp from startup id
        timestamp = 0
        if '_TIME' in desktop_startup_id:
            try:
                timestamp = abs(int(desktop_startup_id.split('_TIME')[1]))
            except ValueError:
                pass
        if not arguments:
            if timestamp:
                debug_log(timestamp)
                self.window.set_startup_id(desktop_startup_id)
                self.window.present_with_time(timestamp)
            else:
                self.window.present()
        try:
            for arg in arguments:
                if arg == "--no-show":
                    continue
                elif arg.startswith("--"):
                    error("Unknown argument", arg)
                self.DisplayNote(arg)
        except ValueError as exc:
            return "Argument %s: %s" % (arg, exc)
        return ""

    def handle_commandline_main(self, arguments, display, desktop_startup_id):
        """handling commandline as main instance, will output errors"""
        errmsg = self.handle_commandline(arguments, display, desktop_startup_id)
        if errmsg:
            error(errmsg)
        # stop the GLib idle_add invocation
        return False

    # }}}
    # Embedding VIM {{{

    def start_vim_hidden(self, extra_args=[], is_preload=False):
        """
        Open a new hidden Vim window

        Return (window, preload_id)
        """
        if is_preload:
            return (None, None)

        window = Gtk.Window()
        window.set_default_size(*guess_default_window_size())

        argv = [self.config.get_vim()]
        argv.extend(VIM_EXTRA_FLAGS)
        argv.extend(['-S', self.write_vimrc_file()])
        argv.extend(extra_args)


        debug_log("Spawning", argv)
        fd = self.config.get_font()
        terminal = Vte.Terminal(scrollback_lines=0, font_desc=fd)
        for name, f in [
                ("background", terminal.set_color_background),
                ("foreground", terminal.set_color_foreground),
            ]:
            color = self.config.get_color(name)
            if color:
                f(color)
        success, pid = terminal.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            None,
            argv,
            None,
            GLib.SpawnFlags.SEARCH_PATH,
            None,
            None,
            None
        )
        if not success:
            return None
        terminal.connect("child-exited", self.on_vim_exit, pid, window)

        has_killed = False
        def window_close(window, event):
            nonlocal has_killed
            if has_killed:
                debug_log("Destroy window")
                self.on_vim_exit(terminal, 1, pid, window)
            else:
                debug_log("Send kill -15", pid)
                has_killed = True
                os.kill(pid, signal.SIGTERM)
                return True
        window.connect("delete-event", window_close)
        terminal.connect("key-press-event", self.on_terminal_key_press_event)

        window.add(terminal)
        window.show_all()
        return window

    def on_spawn_child_setup(self):
        try_register_pr_pdeathsig()

    def on_terminal_key_press_event(self, terminal, event):
        # Intercept Ctrl + Shift + C/V for copy paste
        keymap = Gdk.Keymap.get_default()
        _was_bound, keyv, _egroup, level, consumed = keymap.translate_keyboard_state(
                    event.hardware_keycode, event.get_state(), event.group)
        all_modifiers = Gtk.accelerator_get_default_mod_mask()
        ctrl_shift = ((event.get_state() & all_modifiers)
                      == (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK))

        copy_key = Gdk.keyval_from_name("C")
        paste_key = Gdk.keyval_from_name("V")
        if ctrl_shift and keyv == paste_key:
            debug_log("paste")
            terminal.paste_clipboard()
            return True
        elif ctrl_shift and keyv == copy_key:
            debug_log("copy")
            terminal.copy_clipboard()
            return True
        return False

    def write_vimrc_file(self):
        ## make sure the swp/backup dir exists at this point
        ensuredir(os.path.join(get_cache_dir(), CACHE_SWP))
        CONFIG = ensuredir(get_config_dir())
        ## touch the user config file
        ensurefile(os.path.join(CONFIG, CONFIG_USERRC))
        ## write the kzrnote .vim file
        rpath = os.path.join(CONFIG, CONFIG_VIMRC)
        with open(rpath, "w") as runtimefobj:
            runtimefobj.write(CONFIG_RCTEXT)
        return rpath

    def on_vim_remote_exit(self, pid, condition, preload_argv):
        exit_status = os.WEXITSTATUS(condition)
        debug_log(" vim --remote exited with status", exit_status)
        if exit_status != 0:
            error(" vim --remote exited with status", exit_status)
            #GLib.timeout_add(800, self._respawn_again, preload_argv)

    def new_vimdow(self, name, filepath):
        window = self.start_vim_hidden(['-c', 'e %s' % filepath])
        self.open_files[filepath] = window
        window.set_title(name)
        self.position_window(window, filepath)
        window.present()
        self.emit("note-opened", filepath, window)

    def on_vim_exit(self, terminal, condition, pid, window):
        debug_log( "Vim Pid: %d  exited  (%x)" % (pid, condition))
        for k,v in list(self.open_files.items()):
            if v == window:
                del self.open_files[k]
                break
        else:
            error("Window closed but already unregistered: %d %d" % (pid, condition))
        window.destroy()

# }}}
# main {{{
def service_send_commandline(uargv, display, desktop_startup_id):
    "return an exit code (0 for success)"
    bus = dbus.Bus()
    proxy_obj = bus.get_object(server_name, object_name)
    iface = dbus.Interface(proxy_obj, interface_name)
    errmsg = iface.KzrnoteCommandline(uargv, display, desktop_startup_id)
    if errmsg:
        error(errmsg)
        return 1
    return 0

def setup_locale():
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

def main(argv):
    setup_locale()
    DBusGMainLoop(set_as_default=True)
    GLib.set_application_name(APPNAME)
    GLib.set_prgname(APPNAME)
    uargv = argv[1:]
    if uargv and uargv[0] == '--debug':
        uargv.pop(0)
        global debug
        debug = True
    else:
        debug = False
    desktop_startup_id = os.getenv("DESKTOP_STARTUP_ID", "")
    try:
        m = MainInstance()
    except RuntimeError as exc:
        error(exc)
        return 1
    except NameError as exc:
        debug_log(exc)
        log("An instance already running, passing on commandline...")
        return service_send_commandline(uargv, "", desktop_startup_id)
    lazy_import("uuid")
    for gi_mod in "Gtk Gdk Gio Vte Pango".split():
        lazy_import(gi_mod, "gi.repository." + gi_mod)
    GLib.idle_add(m.setup_basic)
    GLib.idle_add(m.setup_gui)
    GLib.idle_add(m.handle_commandline_main, uargv, "", desktop_startup_id)
    ensuredir(get_notesdir())
    try:
        Gtk.main()
    finally:
        m.unregister()
        m.close_all()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

# }}}
