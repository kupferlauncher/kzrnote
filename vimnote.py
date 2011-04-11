# encoding: utf-8

APPNAME = "vimnote"
VIM = 'vim'
ICONNAME = 'vimnote'

import errno
import locale
import os
import sys
import time
import urlparse

import dbus
from dbus.gobject_service import ExportedGObject
from dbus.mainloop.glib import DBusGMainLoop
import gobject
import glib

## "Lazy imports"
uuid = None
gtk = None
gio = None

def lazy_import(name):
	if globals()[name] is None:
		globals()[name] = __import__(name)


def plainlog(*args):
	for arg in args:
		sys.stderr.write(unicode(arg).encode("ascii", "replace"))
		sys.stderr.write(" ")
	sys.stderr.write("\n")

def log(*args):
	sys.stderr.write("%s: " % __name__)
	sys.stderr.write(str(time.time()) + " ")
	plainlog(*args)

def error(*args):
	sys.stderr.write("Error in %s: " % __name__)
	plainlog(*args)


NEW_NOTE_NAME = "New Note"
MAXTITLELEN=50
DEFAULT_WIN_SIZE = (450, 450)

ATTICDIR="attic"
SWPDIR="cache"
## set wm=2  wrapmargin för automatisk wrapping till fönsterstorlek
## CACHE, CONFIG etc is replaced by the user directories
VIMNOTERC="""
" NOTE: This file is overwritten regularly.
"
" It loads CONFIG/user.vim which
" should be used for user customization.

" hide menubar and toolbar
set guioptions-=m guioptions-=T
set shortmess+=a

" autosave quickly
augroup vimnote
au InsertLeave,CursorHold,CursorHoldI *.note silent! update
au BufRead *.note setlocal autoread

au BufReadPre *.note set noshowcmd
au BufWinEnter *.note set showcmd
augroup END

set updatetime=200

" enable persistent undo by default
set undofile
set undodir=CACHE/cache

set directory=CACHE/cache
set backupdir=CACHE/cache

" set text editing options
" use wrapmargin to adjust to window size
set wm=1
set linebreak

" other options you maybe want to use
" set guifont=Monospace\ 8
" set softtabstop=2 sw=2 et

" read the user's config file
silent! so CONFIG/user.vim
"""
VIMNOTERC_FILE="%s.vim" % APPNAME
VIM_EXTRA_FLAGS=[]


#:set guioptions=-T
#:set shortmess+=T
def ensure_notesdir():
	try:
		os.makedirs(get_notesdir())
	except OSError as exc:
		if not exc.errno == errno.EEXIST:
			raise

def get_notesdir():
	return os.path.join(glib.get_user_data_dir(), APPNAME)

def get_config_dir():
	configdir = os.path.join(glib.get_user_config_dir(), APPNAME)
	try:
		os.makedirs(configdir)
	except OSError:
		pass
	return configdir

def get_cache_dir():
	cachedir = os.path.join(glib.get_user_cache_dir(), APPNAME)
	try:
		os.makedirs(cachedir)
	except OSError:
		pass
	return cachedir

## make uris just  like gnote
## template  note://vimnote/1823-aa8s9df-1231290

URL_SCHEME = "note"
URL_NETLOC = "vimnote"
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

def toasciiuri(uuri):
	return uuri.encode("utf-8") if isinstance(uuri, unicode) else uuri

def note_uuid_from_filename(filename):
	"""
	Raises ValueError for invalid filename
	"""
	if filename.endswith(NOTE_SUFFIX):
		return os.path.basename(filename)[:-len(NOTE_SUFFIX)]
	raise ValueError

def get_note_uri(filepath):
	return "%s://%s/%s" % (URL_SCHEME, URL_NETLOC, note_uuid_from_filename(filepath))

def get_filename_for_note_uri(uri):
	"""
	Raises ValueError on invalid url

	does not check if it exists
	"""
	parse = urlparse.urlparse(toasciiuri(uri))
	if parse.scheme != URL_SCHEME or parse.netloc != URL_NETLOC:
		raise ValueError("Not a %s://%s/.. URI" % (URL_SCHEME, URL_NETLOC))
	if len(parse.path) < 2:
		raise ValueError("Invalid path in %s" % uri)
	return os.path.join(get_notesdir(), os.path.basename(parse.path)) + NOTE_SUFFIX

def get_note_paths():
	D = get_notesdir()
	for x in os.listdir(D):
		path = os.path.join(D, x)
		if is_note(path):
			yield path

def get_note(note_uuid):
	return os.path.join(get_notesdir(), note_uuid + NOTE_SUFFIX)

def is_note(filename):
	return (filename.startswith(get_notesdir()) and os.path.exists(filename) and
	        len(os.path.basename(filename)) == FILENAME_LEN and
	        filename.endswith(NOTE_SUFFIX))

def get_new_note_name():
	for retry in xrange(1000):
		name = str(uuid.uuid4())
		if not os.path.exists(get_note(name)):
			return get_note(name)
	raise RuntimeError

def touch_filename(filename, lcontent=None):
	"""
	Touch non-existing @filename

	optionally write the bytestring @lcontent into it
	"""
	fd = os.open(filename, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0666)
	if lcontent:
		written = 0
		while written < len(lcontent):
			written += os.write(fd, lcontent[written:])
	os.close(fd)

def overwrite_filename(filename, lcontent):
	"""
	Overwrite @filename

	write the bytestring @lcontent into it
	"""
	fd = os.open(filename, os.O_CREAT| os.O_TRUNC | os.O_WRONLY, 0666)
	written = 0
	while written < len(lcontent):
		written += os.write(fd, lcontent[written:])
	os.close(fd)

def read_filename(filename):
	"""
	Read @filename which must exists

	return a byte string
	"""
	read = []
	with open(filename, "rb") as fobj:
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
	try:
		import ctypes
	except ImportError:
		return
	try:
		libc = ctypes.CDLL("libc.so.6")
		libc.prctl(PR_SET_PDEATHSIG, SIGHUP)
	except (AttributeError, OSError):
		pass

def get_relative_name(path, relativeto):
	display_name_long = glib.filename_display_name(path)
	rel_display = glib.filename_display_name(relativeto)
	homedir = glib.filename_display_name(os.path.expanduser("~"))
	if display_name_long.startswith(rel_display):
		return display_name_long.replace(rel_display, '', 1).lstrip("/")
	elif display_name_long.startswith(homedir):
		return display_name_long.replace(homedir, "~", 1)
	return display_name_long

server_name = "se.kaizer.%s" % APPNAME
interface_name = "se.kaizer.%s" % APPNAME
object_name = "/se/kaizer/%s" % APPNAME

class NoteMetadataService (object):
	def __init__(self):
		self.storagefile = os.path.join(get_cache_dir(), "metadata")
		self.geometries = {}

	def load(self):
		"""
		Load configuration
		"""
		try:
			with open(self.storagefile, 'rb') as fobj:
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
		except EnvironmentError as exc:
			if exc.errno != errno.ENOENT:
				raise

	def save(self):
		"""
		Save configuration
		"""
		with open(self.storagefile, 'wb') as outfobj:
			for uri, geometry in self.geometries.iteritems():
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

class MainInstance (ExportedGObject):
	__gsignals__ = {
		"note-deleted": (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING, )),
		"title-updated": (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING, gobject.TYPE_STRING )),
		"note-contents-changed": (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING, )),
		"note-opened": (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)),
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

	def unregister(self):
		dbus.Bus().release_name(server_name)

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
			return False

	@dbus.service.method(interface_name, in_signature="s", out_signature="b")
	def DisplayNote(self, uri):
		"""
		Raises ValueError on invalid @uri
		"""
		filename = get_filename_for_note_uri(uri)
		if is_note(filename):
			self.display_note_by_file(filename)
			return True
		else:
			return False

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
		"""
		filename = get_filename_for_note_uri(uri)
		if is_note(filename):
			try:
				return fromnoteencoding(read_filename(filename))
			except UnicodeDecodeError:
				return ""
		else:
			return ""

	@dbus.service.method(interface_name, in_signature="ss", out_signature="b")
	def SetNoteContents(self, uri, contents):
		"""
		Raises ValueError on invalid @uri
		"""
		filename = get_filename_for_note_uri(uri)
		if is_note(filename):
			try:
				lcontents = tonoteencoding(contents)
			except UnicodeEncodeError:
				return False
			overwrite_filename(filename, lcontents)
			self.emit("note-contents-changed", filename)
			return True
		else:
			return False

	@dbus.service.method(interface_name, in_signature="ss", out_signature="b")
	def SetNoteContentsXml(self, uri, contents):
		## Easy choice: SetNoteContentsXml broken on Gnote. We can support SetNoteCompleteXml
		raise NotImplementedError

	@dbus.service.method(interface_name, in_signature="sb", out_signature="as")
	def SearchNotes(self, query, case_sensistive):
		## NOTE: For "compatibility", we are always case sensistive
		results = []
		grep_cmd = ['/bin/grep', '-l', '-i']
		grep_cmd.extend(['-e', tolocaleencoding(query, errors=False)])
		grep_cmd.extend(['-r', get_notesdir()])
		grep_cmd.append('--include=*%s' % NOTE_SUFFIX)
		grep_cmd.extend(['--exclude-dir=%s' % SWPDIR, '--exclude-dir=%s' % ATTICDIR])
		log(grep_cmd)
		cin, cout = os.popen2(grep_cmd)
		cin.close()
		try:
			for line in cout:
				log(line)
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

	## Vimnote-specific D-Bus methods
	@dbus.service.method(interface_name, in_signature="asss", out_signature="s")
	def VimnoteCommandline(self, uargv, display, desktop_startup_id):
		return self.handle_commandline(uargv, display, desktop_startup_id)

	def reload_filemodel(self, model):
		notes_dir = get_notesdir()
		model.clear()
		for filename in self.get_note_filenames(True):
			display_name = self.ensure_note_title(filename)
			model.append((filename, display_name))

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

	def has_note_by_title(self, utitle):
		"""
		Return (the first) filename if exists, None otherwise

		Titles longer than the max length are truncated(!)
		"""
		utitle = utitle[:MAXTITLELEN]
		for filename, note_title in self.file_names.iteritems():
			if note_title == utitle:
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
			with open(filepath, "r") as f:
				for firstline in f:
					ufirstline = fromnoteencoding(firstline, errors=False).strip()
					if ufirstline:
						return ufirstline[:MAXTITLELEN]
					break
		except EnvironmentError:
			pass
		return NEW_NOTE_NAME


	def setup_gui(self):
		status_icon = gtk.StatusIcon()
		status_icon.set_from_icon_name(ICONNAME)
		status_icon.set_tooltip_text(APPNAME)
		status_icon.set_visible(True)
		self.status_icon = status_icon

		gtk.window_set_default_icon_name(ICONNAME)
		self.window = gtk.Window()
		self.window.set_default_size(300, 400)
		self.list_view = gtk.TreeView()
		self.list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
		self.list_view.set_model(self.list_store)
		cell = gtk.CellRendererText()
		filename_col = gtk.TreeViewColumn("Note", cell, text=1)
		self.list_view.append_column(filename_col)
		self.reload_filemodel(self.list_store)
		self.list_view.show()
		self.list_view.connect("row-activated", self.on_list_view_row_activate)
		toolbar = gtk.Toolbar()
		new = gtk.ToolButton(gtk.STOCK_NEW)
		new.connect("clicked", self.new_note)
		delete = gtk.ToolButton(gtk.STOCK_DELETE)
		delete.connect("clicked", self.on_delete_row_cliecked, self.list_view)
		quit = gtk.ToolButton(gtk.STOCK_QUIT)
		quit.connect("clicked", gtk.main_quit)
		delete.show()
		new.show()
		quit.show()
		toolbar.insert(new, 0)
		toolbar.insert(delete, 1)
		toolbar.insert(quit, 2)
		toolbar.show()
		scrollwin = gtk.ScrolledWindow()
		scrollwin.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		scrollwin.add(self.list_view)
		scrollwin.show()
		vbox = gtk.VBox()
		vbox.pack_start(toolbar, False, True, 0)
		vbox.pack_start(scrollwin, True, True, 0)
		vbox.show()
		self.window.add(vbox)
		self.window.present()
		self.window.connect("delete-event", self.window.hide_on_delete)
		status_icon.connect("activate", lambda x: self.window.present())

		gfile = gio.File(path=get_notesdir())
		self.monitor = gfile.monitor_directory()
		if self.monitor:
			self.monitor.connect("changed", self.on_notes_monitor_changed, self.list_store)
		self.metadata_service.load()
		self.preload()

	def on_list_view_row_activate(self, treeview, path, view_column):
		store = treeview.get_model()
		titer = store.get_iter(path)
		(filepath, ) = store.get(titer, 0)
		self.display_note_by_file(filepath)

	def display_note_by_file(self, filename):
		if filename in self.open_files:
			self.open_files[filename].present()
		else:
			self.new_note_on_screen(filename)

	def on_delete_row_cliecked(self, toolitem, treeview):
		path, column = treeview.get_cursor()
		if path is None:
			return
		store = treeview.get_model()
		titer = store.get_iter(path)
		(filepath, ) = store.get(titer, 0)
		self.delete_note(filepath)

	def delete_note(self, filepath):
		log("Moving ", filepath)
		notes_dir = get_notesdir()
		attic_dir = os.path.join(notes_dir, ATTICDIR)
		try:
			os.makedirs(attic_dir)
		except OSError:
			pass
		os.rename(filepath, os.path.join(attic_dir, os.path.basename(filepath)))
		self.emit("note-deleted", filepath)

	def close_all(self):
		"""
		Close all open windows and hidden windows
		"""
		self.metadata_service.save()
		self.window.hide()
		for filepath in list(self.open_files):
			log("closing", filepath)
			self.open_files.pop(filepath).destroy()
		for preload_id in list(self.preload_ids):
			log("closing", preload_id)
			self.preload_ids.pop(preload_id).destroy()
		while gtk.events_pending():
			gtk.main_iteration()
		time.sleep(0.5)

	def on_note_deleted(self, sender, filepath):
		if filepath in self.open_files:
			self.open_files.pop(filepath).destroy()

	def on_note_title_updated(self, sender, filepath, new_title):
		if filepath in self.open_files:
			title = self.get_window_title_for_note_title(new_title)
			self.open_files[filepath].set_title(title)

	def on_notes_monitor_changed(self, monitor, gfile1, gfile2, event, model):
		if event in (gio.FILE_MONITOR_EVENT_CREATED, gio.FILE_MONITOR_EVENT_DELETED):
			self.reload_filemodel(model)
		if event in (gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT, ):
			self.file_names.pop(gfile1.get_path(), None)
			self.reload_filemodel(model)

	def on_note_opened(self, sender, filepath, window):
		window.connect("configure-event",
		               self.metadata_service.update_window_geometry,
		               filepath)
		glib.timeout_add_seconds(1, self.nudge_window, window)

	def nudge_window(self, window):
		## disabled for now
		return
		## Nudge window so that the child's size is reallocated
		sz = tuple(window.get_size())
		log("nudge", window.get_title(), sz)
		bw = window.get_border_width()
		window.set_border_width(bw+1)
		glib.timeout_add(100,window.set_border_width, bw)

	def get_window_title_for_note_title(self, note_title):
		progname = glib.get_application_name()
		title = u"%s: %s" % (progname, note_title)
		return title

	def position_window(self, window, filepath):
		"""
		Modify @window and move to the correct spot for @filepath
		"""
		geometry = self.metadata_service.get_geometry_for(filepath)
		if geometry is not None:
			size, position = geometry
			window.resize(*size)
			window.move(*position)

	def new_note_on_screen(self, filepath, title=None, screen=None, timestamp=None):
		display_name_long = self.ensure_note_title(filepath)
		self.file_names[filepath] = display_name_long
		title = self.get_window_title_for_note_title(display_name_long)
		self.new_vimdow(title, filepath)

	def new_note(self, sender):
		return self.new_note_on_screen(get_new_note_name())

	def handle_commandline(self, arguments, display, desktop_startup_id):
		"""
		When handling commandline:

		Open The Note URIS on the commandline,
		if nothing else is there, present the main window.

		@arguments: A unicode sequence of arguments
		@display: the name of the X screen (not implemented)
		@desktop_startup_id: $DESKTOP_STARTUP_ID from invocation

		returns: String output (Usage help if applicable)
		"""
		log("handle commandline", arguments, display, desktop_startup_id)

		## parse out timestamp from startup id
		timestamp = 0
		if '_TIME' in desktop_startup_id:
			try:
				timestamp = abs(int(desktop_startup_id.split('_TIME')[1]))
			except ValueError:
				pass
		if not arguments:
			if timestamp:
				log(timestamp)
				self.window.set_startup_id(desktop_startup_id)
				self.window.present_with_time(timestamp)
			else:
				self.window.present()
		for noteuri in arguments:
			self.DisplayNote(noteuri)
		return ""

	@classmethod
	def generate_preload_id(cls):
		return "__%s_%s_" % (APPNAME, time.time())

	def preload(self):
		"""
		Open a new hidden Vim window
		"""
		preload_id = self.generate_preload_id()
		extra_args = ['--servername', preload_id]
		## Update self.preload_ids in on_socket_plug_added when we
		## know that the preloaded window has "contact" with our proxy vim
		self.start_vim_hidden(extra_args, preload_id)

	def start_vim_hidden(self, extra_args=[], preload_id=None):
		"""
		Open a new hidden Vim window

		Return (window, preload_id)
		"""
		window = gtk.Window()
		window.set_default_size(*DEFAULT_WIN_SIZE)

		socket = gtk.Socket()
		window.realize()
		window.add(socket)
		socket.show()
		socket.connect("plug-added", self.on_socket_plug_added,
		               preload_id, window)

		argv = [VIM, '-g', '-f', '--socketid', '%s' % socket.get_id()]
		argv.extend(VIM_EXTRA_FLAGS)
		argv.extend(['-c', 'so %s' % self.write_vimrc_file()])
		argv.extend(extra_args)

		log("Spawning", argv)
		pid, sin, sout, serr = \
				glib.spawn_async(argv, child_setup=self.on_spawn_child_setup,
						 flags=glib.SPAWN_SEARCH_PATH|glib.SPAWN_DO_NOT_REAP_CHILD)
		glib.child_watch_add(pid, self.on_vim_exit, window)
		return window

	def on_spawn_child_setup(self):
		try_register_pr_pdeathsig()

	def on_socket_plug_added(self, socket, preload_id, window):
		log("Plug connected to Socket")
		if preload_id is not None:
			## delay registration just a bit longer
			glib.timeout_add(100, self.after_socket_plug_added, preload_id, window)

	def after_socket_plug_added(self, preload_id, window):
		log("Registering %r as ready" % preload_id)
		## put the returned window in the preload table
		self.preload_ids[preload_id] = window
		return False

	def write_vimrc_file(self):
		CONFIG = get_config_dir()
		CACHE = get_cache_dir()
		vimswpdir = os.path.join(CACHE, SWPDIR)
		try:
			os.makedirs(vimswpdir, 0o700)
		except EnvironmentError:
			pass
		rpath = os.path.join(CONFIG, VIMNOTERC_FILE)
		with open(rpath, "wb") as runtimefobj:
			## Write in the directories in VIMNOTERC
			runtimefobj.write(
				VIMNOTERC.replace('CONFIG', CONFIG).replace('CACHE', CACHE))
		return rpath

	def new_vimdow_preloaded(self, name, filepath):
		if not self.preload_ids:
			raise RuntimeError("No Preloaded instances found!")
		preload_id, window = self.preload_ids.popitem()
		window.set_title(name)
		self.open_files[filepath] = window

		## Note: Filename requires escaping (but our defaults are safe ones)
		preload_argv = [VIM, '-g', '-f', '--servername', preload_id,
		                '--remote-send', '<ESC>:e %s<CR>' % filepath]

		log("Using preloaded", preload_argv)
		## watch this process
		pid, sin, sout, serr = \
				glib.spawn_async(preload_argv,
				                 flags=glib.SPAWN_SEARCH_PATH|glib.SPAWN_DO_NOT_REAP_CHILD)
		glib.child_watch_add(pid, self.on_vim_remote_exit, preload_argv)
		self.position_window(window, filepath)
		window.present()
		self.emit("note-opened", filepath, window)

	def on_vim_remote_exit(self, pid, condition, preload_argv):
		exit_status = os.WEXITSTATUS(condition)
		log(" vim --remote exited with status", exit_status)
		if exit_status != 0:
			pass
			#glib.timeout_add(800, self._respawn_again, preload_argv)
	
	def new_vimdow(self, name, filepath):
		if self.preload_ids:
			self.new_vimdow_preloaded(name, filepath)
			glib.timeout_add_seconds(1, self.preload)
			return
		window = self.start_vim_hidden([filepath])
		self.open_files[filepath] = window
		window.set_title(name)
		self.position_window(window, filepath)
		window.present()
		self.emit("note-opened", filepath, window)

	def on_vim_exit(self, pid, condition, window):
		log( "Vim Pid: %d  exited  (%x)" % (pid, condition))
		for k,v in self.open_files.items():
			if v == window:
				del self.open_files[k]
				break
		else:
			raise RuntimeError("Unknown window closed %d %d" % (pid, condition))
		window.destroy()

def service_send_commandline(uargv, display, desktop_startup_id):
	bus = dbus.Bus()
	proxy_obj = bus.get_object(server_name, object_name)
	iface = dbus.Interface(proxy_obj, interface_name)
	try:
		iface.VimnoteCommandline(uargv, display, desktop_startup_id)
	except dbus.DBusException as exc:
		error(exc)
	#iface.VimnoteCommandline(uargv,"", "", error_handler=_dummy, reply_handler=_dummy)

def setup_locale():
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error:
		pass

def main(argv):
	setup_locale()
	DBusGMainLoop(set_as_default=True)
	glib.set_application_name(APPNAME)
	glib.set_prgname(APPNAME)
	uargv = [fromlocaleencoding(arg, errors=False) for arg in argv[1:]]
	desktop_startup_id = os.getenv("DESKTOP_STARTUP_ID", "")
	try:
		m = MainInstance()
	except RuntimeError as exc:
		log(exc)
		return 1
	except NameError as exc:
		log(exc)
		log("An instance already running, passing on commandline...")
		service_send_commandline(uargv, "", desktop_startup_id)
		return 0
	lazy_import("uuid")
	lazy_import("gtk")
	lazy_import("gio")
	glib.idle_add(m.setup_gui)
	glib.idle_add(m.handle_commandline, uargv, "", desktop_startup_id)
	ensure_notesdir()
	try:
		gtk.main()
	finally:
		m.unregister()
		m.close_all()



if __name__ == '__main__':
	sys.exit(main(sys.argv))

