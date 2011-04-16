" Changed-by: kaizer <post@kaizer.se>
" Last Change: Tuesday, 12 April 2011
"
" Was taken out from Peter's vim-notes, his version header
" Author: Peter Odding <peter@peterodding.com>
" Last Change: January 7, 2011
" URL: http://peterodding.com/code/vim/notes/
"
" Peter's vim/notes is licenced under a MIT license
" and so are my additions as well -- kaizer, Tuesday, 12 April 2011

" The extracted parts only concern highlighting note titles with
" syntax colors
"
"
" This file loads ~/.config/kzrnote/user.vim which
" should be used for user customization.


" Don't source this when its already been loaded or &compatible is set.
if &cp || exists('g:loaded_kzrnote')
    finish
endif

if !exists('g:kzrnote_link_notes')
    let g:kzrnote_link_notes = 1
endif

if !exists('g:kzrnote_autosave')
    let g:kzrnote_autosave = 1
endif

if $XDG_CACHE_HOME == ''
    let $XDG_CACHE_HOME = expand("~/.cache")
endif
if $XDG_CONFIG_HOME == ''
    let $XDG_CONFIG_HOME = expand("~/.config")
endif

if !exists('s:cache_mtime')
    let s:have_cached_names = 0
    let s:have_cached_titles = 0
    let s:cached_fnames = []
    let s:cached_titles = []
    let s:cache_mtime = 0
endif

function! KaizerNotesGetTitles()
    " Get list with titles of all existing notes.
    " from the kzrnote cache file
    if !s:have_cached_titles
        "" each line of notetitles is a title
        let listing = readfile($XDG_CACHE_HOME . "/kzrnote/notetitles")
        for line in listing
            call add(s:cached_titles, line)
        endfor
        let s:have_cached_titles = 1
    endif
    return copy(s:cached_titles)
endfunction


function! KaizerNotesHighlightTitles(force)
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

function! CurSyntaxText(synname)
    "" returns (on the current line)
    "" the text of the syntax item @synname or ''
    let curlinen = line(".")
    let curcoln = col(".")
    if a:synname != synIDattr(synID(curlinen, curcoln, 1), "name")
        return ''
    endif
    let synid = synID(curlinen, curcoln, 1)

    "" find beginning
    let coln = curcoln
    while coln > 0 && synID(curlinen, coln-1, 1) == synid
        let coln = coln - 1
    endwhile
    "" find end
    let endcoln = curcoln
    while endcoln < col("$") && synID(curlinen, endcoln+1, 1) == synid
        let endcoln = endcoln + 1
    endwhile
    " strpart (str, start, len)
    return strpart(getline("."), coln-1, endcoln-coln + 1)
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

function! s:CompleteNote(arglead, cmdline, cursorpos) 
    " a:arglead is the current word and
    " a:cmdline is the whole thing starting with Note
    " we complete on the whole thing
    " and then we must return matches without the first words,
    " since vim believes it is inserting the next word, after the whitespace
    let allargs = substitute(a:cmdline, "Note \s*", "", "")
    let firstparts = strpart(allargs, 0, strlen(allargs) - strlen(a:arglead))
    let matchtitles = filter(KaizerNotesGetTitles(), 'v:val =~? allargs')
    return map(matchtitles, 'substitute(v:val, firstparts, "", "i")')
endfunction


" settings that we need inside kzrnote

" hide menubar and toolbar
set guioptions-=m guioptions-=T
set shortmess=atTIOsWA

" autosave vigorously
set updatetime=200

augroup kzrnote
au!
au BufRead *.note setlocal autoread
au InsertLeave,CursorHold,CursorHoldI *.note
    \ if g:kzrnote_autosave == 1 | silent! update | endif
augroup END

" enable persistent undo by default
set undofile
set undodir=$XDG_CACHE_HOME/kzrnote/cache

set directory=$XDG_CACHE_HOME/kzrnote/cache
set backupdir=$XDG_CACHE_HOME/kzrnote/cache

" set text editing options
" use wrapmargin to adjust to window size
set wm=1
set linebreak


let s:kzrnote_service = 'se.kaizer.kzrnote'
let s:kzrnote_object = '/se/kaizer/kzrnote'
let s:kzrnote_interface = 'se.kaizer.kzrnote'

function! KzrnoteMethod (method, arg, sender)
    silent exe '!dbus-send' '--type=method_call' '--print-reply'
     \ '--dest=' . s:kzrnote_service s:kzrnote_object
     \ s:kzrnote_interface . '.' . a:method
     \ 'string:' . a:arg 'string:' . a:sender
endfunction

function! s:DeleteNote()
    call KzrnoteMethod('KzrnoteDelete', '', expand("%:p"))
endfunction

function! s:NewNote(notename)
    " empty shellescaped string
    if a:notename != "''"
        call KzrnoteMethod('KzrnoteOpen', a:notename, expand("%:p"))
    else
        call KzrnoteMethod('KzrnoteNew', '', expand("%:p"))
    endif
endfunction

" hijack gf to open other notes
function! KzrnoteOpenLink(nname)
    if a:nname != ''
        let escname = escape(a:nname, '!')
        let name = shellescape(escname)
        call s:NewNote(name)
    else
        normal! gf <cfile>
    endif
endfunction

noremap gf :call KzrnoteOpenLink(CurSyntaxText("kaizerNoteTitle"))<CR><CR>

augroup kzrnote
au BufWinEnter *.note
    \ if g:kzrnote_link_notes == 1 | call KaizerNotesHighlightTitles(0) | endif
au Syntax *
    \ if g:kzrnote_link_notes == 1 | call KaizerNotesHighlightTitles(1) | endif
augroup END

command! -bar -nargs=* -complete=customlist,s:CompleteNote
                 \ Note call s:NewNote(shellescape(<q-args>))
command! -bar DeleteNote call s:DeleteNote()

let g:loaded_kzrnote = 1


" read the user's config file
silent! so $XDG_CONFIG_HOME/kzrnote/user.vim

" vim: sts=4 sw=4 et

