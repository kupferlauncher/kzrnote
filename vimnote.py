
APPNAME = "vimnote"
VIM = 'vim'
ICONNAME = 'vim'

import locale
import os
import sys
import uuid

import gtk
import gio
import gobject
import glib

NEW_NOTE_NAME = "New Note"
MAXTITLELEN=50
ATTICDIR="attic"

def get_notesdir():
	notesdir = os.path.join(glib.get_user_data_dir(), APPNAME)
	try:
		os.makedirs(notesdir)
	except OSError:
		pass
	return notesdir

def get_notes():
	D = get_notesdir()
	for x in os.listdir(D):
		path = os.path.join(D, x)
		if os.path.isfile(path):
			yield path

def get_note(notename):
	return os.path.join(get_notesdir(), notename)

def get_new_note_name():
	for retry in xrange(1000):
		name = str(uuid.uuid4())
		if not os.path.exists(get_note(name)):
			return get_note(name)
	raise RuntimeError

def fromlocale_flatten(lstr):
	"""
	Get unicode from locale bytestring @lstr,
	flatten if needed
	"""
	enc = locale.getpreferredencoding(do_setlocale=False)
	return lstr.decode(enc, 'replace')

def get_relative_name(path, relativeto):
	display_name_long = glib.filename_display_name(path)
	rel_display = glib.filename_display_name(relativeto)
	homedir = glib.filename_display_name(os.path.expanduser("~"))
	if display_name_long.startswith(rel_display):
		return display_name_long.replace(rel_display, '', 1).lstrip("/")
	elif display_name_long.startswith(homedir):
		return display_name_long.replace(homedir, "~", 1)
	return display_name_long

class MainInstance (gobject.GObject):
	__gsignals__ = {
		"note-deleted": (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
			(gobject.TYPE_STRING, )),
	}
	def __init__(self):
		gobject.GObject.__init__(self)
		self.open_files = {}
		self.file_names = {}
		self.connect("note-deleted", self.on_note_deleted)

	def reload_filemodel(self, model):
		notes_dir = get_notesdir()
		model.clear()
		for filename in get_notes():
			if not filename in self.file_names:
				self.reload_file_note_title(filename)
			display_name = self.file_names[filename]
			model.append((filename, display_name))

	def reload_file_note_title(self, filename):
		self.file_names[filename] = self.extract_note_title(filename)

	def extract_note_title(self, filepath):
		try:
			with open(filepath, "r") as f:
				for firstline in f:
					ufirstline = fromlocale_flatten(firstline).strip()
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
		status_icon.connect("activate", gtk.main_quit)
		status_icon.set_visible(True)
		self.status_icon = status_icon

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
		vbox = gtk.VBox()
		vbox.pack_start(toolbar, False, True, 0)
		vbox.pack_start(self.list_view, True, True, 0)
		vbox.show()
		self.window.add(vbox)
		self.window.present()

		gfile = gio.File(path=get_notesdir())
		self.monitor = gfile.monitor_directory()
		if self.monitor:
			self.monitor.connect("changed", self.on_notes_monitor_changed, self.list_store)

	def on_list_view_row_activate(self, treeview, path, view_column):
		store = treeview.get_model()
		titer = store.get_iter(path)
		(filepath, ) = store.get(titer, 0)
		if filepath in self.open_files:
			self.open_files[filepath].present()
		else:
			self.new_note_on_screen(filepath)

	def on_delete_row_cliecked(self, toolitem, treeview):
		path, column = treeview.get_cursor()
		if path is None:
			return
		store = treeview.get_model()
		titer = store.get_iter(path)
		(filepath, ) = store.get(titer, 0)
		print "Moving ", filepath
		notes_dir = get_notesdir()
		attic_dir = os.path.join(notes_dir, ATTICDIR)
		try:
			os.makedirs(attic_dir)
		except OSError:
			pass
		os.rename(filepath, os.path.join(attic_dir, os.path.basename(filepath)))
		self.emit("note-deleted", filepath)

	def on_note_deleted(self, sender, filepath):
		if filepath in self.open_files:
			self.open_files[filepath].destroy()

	def on_notes_monitor_changed(self, monitor, gfile1, gfile2, event, model):
		if event in (gio.FILE_MONITOR_EVENT_CREATED, gio.FILE_MONITOR_EVENT_DELETED):
			self.reload_filemodel(model)
		if event in (gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT, ):
			self.file_names.pop(gfile1.get_path(), None)
			self.reload_filemodel(model)

	def new_note_on_screen(self, filepath, title=None, screen=None, timestamp=None):
		progname = glib.get_application_name()
		display_name_long = self.extract_note_title(filepath)
		self.file_names[filepath] = display_name_long
		title = u"%s: %s" % (progname, display_name_long)
		self.new_vimdow(title, filepath)

	def new_note(self, sender):
		return self.new_note_on_screen(get_new_note_name())

	def handle_commandline(self, progname, arguments):
		for filename in arguments:
			gfile = gio.File(filename)
			display_name_long = glib.filename_display_name(gfile.get_path())
			homedir = glib.filename_display_name(os.path.expanduser("~"))
			if display_name_long.startswith(homedir):
				display_name_long = display_name_long.replace(homedir, "~", 1)
			self.new_vimdow(u"%s: %s" % (progname, display_name_long), gfile.get_path())

	def new_vimdow(self, name, filepath):
		window = gtk.Window()
		window.set_title(name)
		window.set_default_size(400, 400)

		socket = gtk.Socket()
		window.realize()
		window.add(socket)
		socket.show()
		window.show()
		socket.grab_focus()
		print socket, socket.get_id()

		self.open_files[filepath] = window

		pid, sin, sout, serr = \
				glib.spawn_async([VIM, '-g', '-f', '--socketid', '%s' % socket.get_id(), filepath],
						 flags=glib.SPAWN_SEARCH_PATH|glib.SPAWN_DO_NOT_REAP_CHILD)
		glib.child_watch_add(pid, self.on_vim_exit, window)

	def on_vim_exit(self, pid, condition, window):
		print "Vim Pid: %d  exited  (%x)" % (pid, condition)
		for k,v in self.open_files.items():
			if v == window:
				del self.open_files[k]
				break
		else:
			raise RuntimeError("Unknown window closed %d %d" % (pid, condition))
		window.destroy()
		print gtk.window_list_toplevels()
		if not gtk.window_list_toplevels():
			print "No windows left, exiting.."
			gtk.main_quit()


def setup_locale():
	try:
		locale.setlocale(locale.LC_ALL, "")
	except locale.Error:
		pass

def main(argv):
	setup_locale()
	glib.set_application_name(APPNAME)
	glib.set_prgname(APPNAME)
	m = MainInstance()
	glib.idle_add(m.setup_gui)
	glib.idle_add(m.handle_commandline, argv[0], argv[1:])
	return gtk.main()


if __name__ == '__main__':
	sys.exit(main(sys.argv))

