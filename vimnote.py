
APPNAME = "vimnote"
VIM = 'vim'
ICONNAME = 'vim'

import os
import sys

import gtk
import gio
import gobject
import glib

NEW_NOTE_NAME = "New Note"

def get_notesdir():
	notesdir = os.path.join(glib.get_user_data_dir(), APPNAME)
	try:
		os.makedirs(notesdir)
	except OSError:
		pass
	return notesdir

def get_notes():
	D = get_notesdir()
	return [os.path.join(D, x) for x in os.listdir(D)]

def get_note(notename):
	return os.path.join(get_notesdir(), notename)

def get_new_note_name(base):
	for retry in xrange(1000):
		name = base if not retry else "%s %d" % (base, retry)
		if not os.path.exists(get_note(name)):
			return get_note(name)
	raise RuntimeError


def get_relative_name(path, relativeto):
	display_name_long = glib.filename_display_name(path)
	rel_display = glib.filename_display_name(relativeto)
	homedir = glib.filename_display_name(os.path.expanduser("~"))
	if display_name_long.startswith(rel_display):
		return display_name_long.replace(rel_display, '', 1).lstrip("/")
	elif display_name_long.startswith(homedir):
		return display_name_long.replace(homedir, "~", 1)
	return display_name_long

class MainInstance (object):
	def __init__(self):
		self.open_files = {}

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
		notes_dir = get_notesdir()
		filename_col = gtk.TreeViewColumn("Note", cell, text=1)
		self.list_view.append_column(filename_col)
		for filename in get_notes():
			print filename
			self.list_store.append((filename, get_relative_name(filename, notes_dir)))
		self.list_view.show()
		self.list_view.connect("row-activated", self.on_list_view_row_activate)
		toolbar = gtk.Toolbar()
		new = gtk.ToolButton("gtk-new")
		new.connect("clicked", self.new_note)
		quit = gtk.ToolButton("gtk-quit")
		quit.connect("clicked", gtk.main_quit)
		new.show()
		quit.show()
		toolbar.insert(new, 0)
		toolbar.insert(quit, 1)
		toolbar.show()
		vbox = gtk.VBox()
		vbox.pack_start(toolbar, False, True, 0)
		vbox.pack_start(self.list_view, True, True, 0)
		vbox.show()
		self.window.add(vbox)
		self.window.present()

	def on_list_view_row_activate(self, treeview, path, view_column):
		store = treeview.get_model()
		titer = store.get_iter(path)
		(filepath, ) = store.get(titer, 0)
		print filepath
		if filepath in self.open_files:
			self.open_files[filepath].present()
		else:
			self.new_note_on_screen(filepath)


	def new_note_on_screen(self, filepath, title=None, screen=None, timestamp=None):
		progname = glib.get_application_name()
		display_name_long = get_relative_name(filepath, get_notesdir())
		self.new_vimdow(u"%s: %s" % (progname, display_name_long), filepath)

	def new_note(self, sender):
		return self.new_note_on_screen(get_new_note_name(NEW_NOTE_NAME))

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



def main(argv):
	glib.set_application_name(APPNAME)
	glib.set_prgname(APPNAME)
	m = MainInstance()
	glib.idle_add(m.setup_gui)
	glib.idle_add(m.handle_commandline, argv[0], argv[1:])
	return gtk.main()


if __name__ == '__main__':
	sys.exit(main(sys.argv))

