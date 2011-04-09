
VIM = ['vim', '-g']


import os
import sys

import gtk
import gio
import glib

def vim_exited(pid, condition, window):
	window.destroy()
	print gtk.window_list_toplevels()
	if not gtk.window_list_toplevels():
		print "No windows left, exiting.."
		gtk.main_quit()

def open_vimdow(name, filepath):
	window = gtk.Window()
	window.set_title(name)
	window.set_default_size(400, 400)

	socket = gtk.Socket()
	window.realize()
	window.add(socket)
	socket.show()
	window.show()
	print socket, socket.get_id()

	pid, sin, sout, serr = \
			glib.spawn_async(['vim', '-g', '-f', '--socketid', '%s' % socket.get_id(), filepath],
					 flags=glib.SPAWN_SEARCH_PATH|glib.SPAWN_DO_NOT_REAP_CHILD)

	glib.child_watch_add(pid, vim_exited, window)

def handle_commandline(progname, arguments):
	for filename in arguments:
		gfile = gio.File(filename)
		display_name_long = glib.filename_display_name(gfile.get_path())
		homedir = glib.filename_display_name(os.path.expanduser("~"))
		if display_name_long.startswith(homedir):
			display_name_long = display_name_long.replace(homedir, "~", 1)
		open_vimdow(u"%s: %s" % (progname, display_name_long), gfile.get_path())

def main(argv):
	glib.idle_add(handle_commandline, argv[0], argv[1:])
	return gtk.main()


if __name__ == '__main__':
	sys.exit(main(sys.argv))
