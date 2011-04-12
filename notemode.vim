" Vim auto-load script
"  Was taken out from Peter's vim-notes
" Author: Peter Odding <peter@peterodding.com>
" Last Change: January 7, 2011
" URL: http://peterodding.com/code/vim/notes/
" Changed-by: Ulrik Sverdrup <ulrik.sverdrup@gmail.com>
" Last Change: Tuesday, 12 April 2011

" Highlighting note titles

if !exists('s:cache_mtime')
  let s:have_cached_names = 0
  let s:have_cached_titles = 0
  let s:cached_fnames = []
  let s:cached_titles = []
  let s:cache_mtime = 0
endif

function! KaizerNotesGetFnames() " {{{3
  " Get list with filenames of all existing notes.
  " from the vimnote cache file
  if !s:have_cached_names
    let listing = readfile($HOME . "/.cache/vimnote/filenames")
    for line in listing
      " split each line by literal '.note '
      let linesp = split(line, '\.note\ \zs')
      " strip last space
      call add(s:cached_fnames, strpart(linesp[0], 0, strlen(linesp[0])-1))
    endfor
    let s:have_cached_names = 1
  endif
  return copy(s:cached_fnames)
endfunction

function! KaizerNotesGetTitles() " {{{3
  " Get list with titles of all existing notes.
  " from the vimnote cache file
  if !s:have_cached_titles
    let listing = readfile($HOME . "/.cache/vimnote/filenames")
    for line in listing
      " split each line by literal '.note '
      let linesp = split(line, '\.note\ \zs')
      call add(s:cached_titles, linesp[1])
    endfor
    let s:have_cached_titles = 1
  endif
  return copy(s:cached_titles)
endfunction
      



function! KaizerNotesHighlightTitles(force) " {{{3
  " Highlight the names of all notes as "kaizerNoteTitle" (linked to "Underlined").
  highlight def link kaizerNoteTitle Underlined
  if a:force || !(exists('b:notes_names_last_highlighted') && b:notes_names_last_highlighted > s:cache_mtime)
    let titles = filter(KaizerNotesGetTitles(), '!empty(v:val)')
    call map(titles, 's:words_to_pattern(v:val)')
    call sort(titles, 's:sort_longest_to_shortest')
    syntax clear kaizerNoteTitle
    execute 'syntax match kaizerNoteTitle /\c\%>2l\%(' . escape(join(titles, '\|'), '/') . '\)/'
    let b:notes_names_last_highlighted = localtime()
  endif
endfunction

function! s:escape_pattern(string)
  if type(a:string) == type('')
    let string = escape(a:string, '^$.*\~[]')
    return substitute(string, '\n', '\\n', 'g')
  endif
  return ''
endfunction

function! s:words_to_pattern(words)
  " Quote regex meta characters, enable matching of hard wrapped words.
  return substitute(s:escape_pattern(a:words), '\s\+', '\\_s\\+', 'g')
endfunction

function! s:sort_longest_to_shortest(a, b)
  " Sort note titles by length, starting with the shortest.
  return len(a:a) < len(a:b) ? 1 : -1
endfunction




" vim: ts=2 sw=2 et



