# checkfiles.py detect and fix tabs and(or trailing whitespace in commits
#
# Copyright: Marcus Lindblom 2010
# License: GPLv2+

'''detects (and optionally fixes) tabs and trailing whitespace in committed files

== The hooks ==

check_hook: prevents commits containing tabs or trailing whitespace, without actually touching
            any files. Use as pretxncommit locally or pretxnchangegroup on a central repo.

fixup_hook: automatically fixes any problematic files before commit. Useful in pre-commit.
             (As this hook may changes files on disc, you will need to recompile your
             project after committing if any files needed fixing)

             If you're not comfortable with this kind of magic, use the check_hook and
             manually run the command with the --fixup option.

== The commands ==

hg checkfiles [options]

checks changed files in the working directory for tabs or trailing whitespace

    - --verbose shows the location of offending characters in each line
    - --quiet hides filenames and only reports summary information
    - --debug shows settings and details about each file considered for checking

    If problems are found, the command returns 1, otherwise 0.

hg fixwhitespace [options]

Replaces tabs -> spaces and removes trailing whitespace

    If --fixup is given, the return value is always 0 (unless an error occurs).

options:

 -t --tabsize VALUE  set the tab length (default: 4)
    --all            fix all files in working directory, not just the changes ones

== Example usage ==

[extensions]
checkfiles = /path/to/checkfiles.py enable command

[hooks]
pretxnchangegroup.checkfiles = python:/path/to/checkfiles.py:check_hook
pretxncommit.checkfiles = python:/path/to/checkfiles.py:check_hook
precommit.checkfiles = python:/path/to/checkfiles.py:fixup_hook

[checkfiles]
# default is all text files
checked_exts = .c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl
# default is .sln .suo .vcproj .csproj .ui
ignored_exts = .xslt
ignored_files = foo/contains_tabs.txt bar/contains_trailing_ws.txt
tab_size = 4
# to examine only modified lines from check_hook (no effect on fixup_hook or command), use:
# check_diffs = True
'''

from mercurial.i18n import _
from mercurial import cmdutil, patch
import re

class CheckFiles(object):
    def __init__(self, ui, repo, ctx, opts = {}):
        self.ctx = ctx
        self.ui = ui
        self.repo = repo

        if opts['all']:
            modified, added, removed, deleted, unknown, ignored, clean = repo.status(clean=True)
            self.files = modified + added + clean # we can't get filecontext for unknown files
        else:
            self.files = ctx.files()

        self.checked_exts = ui.configlist('checkfiles', 'checked_exts',
            default='""')
        self.ignored_exts = ui.configlist('checkfiles', 'ignored_exts',
            default='.sln .suo .vcproj .csproj .ui') # some common autogenerated filetypes
        self.ignored_files = ui.configlist('checkfiles', 'ignored_files')
        self.check_diffs = ui.configbool('checkfiles', 'check_diffs')
        self.tab_size = int(ui.config('checkfiles', 'tab_size', default='4'))
        self.use_spaces = ui.configbool('checkfiles', 'use_spaces', True)

        if 'tabsize' in opts:
            self.tab_size = int(opts['tabsize'])

        if self.checked_exts == '""':
            self.ui.debug('checkfiles: checked extensions: (all text files)\n')
        else:
            self.ui.debug('checkfiles: checked extensions: %s\n' % ' '.join(self.checked_exts))

        self.ui.debug('checkfiles: ignored extensions: %s\n' % ' '.join(self.ignored_exts))
        self.ui.debug('checkfiles: ignored files: %s\n' % ' '.join(self.ignored_files))
        self.ui.debug('checkfiles: check diffs only: %r\n' % self.check_diffs)
        self.ui.debug('checkfiles: use spaces: %r\n' % self.use_spaces)

        self.ui.debug('checkfiles: considering files:\n  %s\n' % '\n  '.join(self.files))

    def is_relevant(self, file):
        if file in self.ignored_files:
            self.ui.debug('checkfiles: ignoring %s (explicit ignore)\n' % file)
            return False

        if any(map(lambda e:file.endswith(e), self.ignored_exts)):
            self.ui.debug('checkfiles: ignoring %s (ignored extension)\n' % file)
            return False

        if not any(map(lambda e:file.endswith(e), self.checked_exts)):
            self.ui.debug('checkfiles: ignoring %s (non-checked extension)\n' % file)
            return False

        try:
            fctx = self.ctx[file]
        except LookupError:
            self.ui.debug('checkfiles: skipping %s (deleted)\n' % file)
            return False
            
        if fctx == None:
            self.ui.debug('checkfiles: skipping %s (deleted)\n' % file)
            return False

        try:
            data = fctx.data()
        except:
            self.ui.debug('checkfiles: skipping %s (deleted)\n' % file)
            return False
            
        if '\0' in fctx.data():
            self.ui.debug('checkfiles: skipping %s (binary)\n' % file)
            return False

        return True

    def check(self):
        if self.use_spaces:
            indicator = '^' * self.tab_size
        else:
            indicator = '^'

        class State:
            def __init__(self, ui):
                self.ui = ui
                self.ws_begin = False
                self.ws_end = False
                self.all_ws = False
                self.filecount = 0
                self.probcount = 0
            def endfile(self, file):
                if file is None:
                    return
                if self.ws_begin or self.ws_end or self.all_ws:
                    self.filecount += 1
                    self.ui.status('checkfiles: %s:%s%s%s\n' %
                        (file, ' whitespace_begin' if self.ws_begin else '', ' whitespace_end' if self.ws_end else '', ' all_whitespace' if self.all_ws else ''))
                    self.ws_begin = False
                    self.ws_end = False
                    self.all_ws = False
                else:
                    self.ui.note('checkfiles: %s: ok\n' % file)
            def found_all_ws(self):
                self.all_ws = True
                self.probcount += 1
            def found_ws_end(self):
                self.ws_end = True
                self.probcount += 1
            def found_ws_begin(self):
                self.ws_begin = True
                self.probcount += 1
        state = State(self.ui)

        if self.check_diffs:
            if len(self.ctx.parents()) == 1:
                # XXX would be nicer if checked_exts were a proper pattern;
                # then cmdutil.match would work naturally with it
                file = None
                hunk = None
                lastlabel = None
                for chunk, label in patch.diffui(self.repo,
                                                 self.ctx.p1().node(),
                                                 self.ctx.node(),
                                                 cmdutil.match(self.repo)):
                    if len(label) > 0 or chunk != '\n':
                        self.ui.debug('checkfiles: %s="%s"\n' % (label, chunk))
                    if label == 'diff.file_b':
                        state.endfile(file)
                        file = re.sub(r'^[+][+][+] b/(.+)\t.+$', r'\1', chunk)
                        if self.is_relevant(file):
                            self.ui.debug('checkfiles: checking %s ...\n' % file)
                        else:
                            file = None
                    elif label == 'diff.hunk':
                        hunk = chunk
                    elif file and label == 'diff.trailingwhitespace' and lastlabel == 'diff.inserted' and chunk != '\r':
                        state.found_ws_end()
                        self.ui.note('%s: trailing whitespace in %s\n' % (file, hunk))
                    elif file and label == 'diff.inserted' and self.is_ws_before_text(chunk[1:]):
                        state.found_ws_begin()
                        if self.use_spaces:
                            self.ui.note('%s: tab character(s) in %s\n' % (file, hunk))
                        else:
                            self.ui.note('%s: space(s) before text in %s\n' % (file, hunk))

                    lastlabel = label
                state.endfile(file)
            else:
                self.ui.note('checkfiles: skipping merge changeset\n')
        else:
            for file in filter(self.is_relevant, self.files):
                self.ui.debug('checkfiles: checking %s ...\n' % file)
                fctx = self.ctx[file]

                for num, line in enumerate(fctx.data().splitlines(), 1):
                    if line.isspace():
                        state.found_all_ws()
                        self.ui.note('%s (%i): all whitespace\n' % (file, num))

                    elif line.endswith((' ', '\t')):
                        state.found_ws_end()
                        self.ui.note('%s (%i): trailing whitespace\n' % (file, num))

                        line = line.expandtabs(self.tab_size)
                        non_ws_len = len(line.rstrip())
                        line_show = ' ' * non_ws_len + '^' * (len(line) - non_ws_len)
                        self.ui.note('  %s\n  %s\n' % (line, line_show))

                    self.detect_ws_before_text(file, num, line, indicator, state)

                state.endfile(file)

        if state.filecount > 0:
            from mercurial.node import short
            self.ui.warn('checkfiles: %i issues(s) found in %i file(s) in %s\n' %
                (state.probcount, state.filecount,
                short(self.ctx.node()) if self.ctx.node() else 'working directory'))

        return state.filecount > 0

    def fixup(self):
        import os.path

        for file in filter(self.is_relevant, self.files):
            data = self.ctx[file].data()
            lines = data.splitlines()
            nl_at_eof = data.endswith('\n')

            if not any(line.isspace() or self.is_ws_before_text(line) or line.endswith((' ', '\t')) for line in lines):
                self.ui.note('checkfiles: %s ok\n' % file)
                continue

            self.ui.status('checkfiles: fixing %s\n' % file)

            with open(os.path.join(self.repo.root, file), 'w') as fileobj:
                def fixline():
                    if self.use_spaces:
                        for line in lines:
                            yield line.rstrip().expandtabs(self.tab_size)
                    else:
                        for line in lines:
                            match = re.match(r'^(\t*( \t*)+)[^ \t]', line)
                            if match:
                                ws = match.group(1)
                                text = line[len(ws):]

                                yield ws.expandtabs(self.tab_size).replace(' ' * self.tab_size, '\t') + text.rstrip()
                            else:
                                yield line.rstrip()

                fileobj.writelines('\n'.join(fixline()))
                if nl_at_eof:
                    fileobj.write('\n')

    def match_spaces_before_text(self, line):
        return re.match(r'^\t*( \t*)+[^ \t]', line)

    def is_ws_before_text(self, line):
        if self.use_spaces:
            return '\t' in line
        else:
            return self.match_spaces_before_text(line)

    def detect_ws_before_text(self, file, num, line, indicator, state):
        if self.use_spaces:
            if self.is_ws_before_text(line):
                state.found_ws_begin()
                self.ui.note('%s (%i): tab character(s)\n' % (file, num))

                line_show = ''.join(indicator if c == '\t' else ' ' for c in line)
                line = line.expandtabs(self.tab_size)
                self.ui.note('  %s\n  %s\n' % (line, line_show))
        else:
            match = self.match_spaces_before_text(line)
            if match:
                state.found_ws_begin()
                self.ui.note('%s (%i): space(s) before text\n' % (file, num))

                line = line.expandtabs(self.tab_size)
                line_show = match.group()[0:-1].replace(' ', indicator).expandtabs(self.tab_size)
                self.ui.note('  %s\n  %s\n' % (line, line_show))

################################################################################################

def check_hook(ui, repo, hooktype, node, **kwargs):
    '''blocks commits/changesets containing tabs or trailing whitespace'''

    if hooktype == 'pretxncommit':
        ui.note('checkfiles: checking commit for tabs or trailing whitespace...\n')
        cf = CheckFiles(ui, repo, repo.changectx(node))
        return cf.check()

    elif hooktype == 'pretxnchangegroup':
        from mercurial import cmdutil

        ui.note('checkfiles: checking incoming changes for tabs or trailing whitespace...\n')
        cf = CheckFiles(ui, repo, None)
        fail = False

        for rev in cmdutil.revrange(repo, ['%s::' % node]):
            cf.ctx = repo.changectx(rev)
            fail = cf.check() or fail

        return fail
    else:
        from mercurial import util
        raise util.Abort(_('checkfiles: check_hook installed as unsupported hooktype: %s') %
                           hooktype)

def fixup_hook(ui, repo, hooktype, **kwargs):
    '''Removes tabs and/or trailing whitespace from modified files in the working directory'''

    ui.note('checkfiles: removing tabs and/or trailing whitespace in changed files...\n')

    cf = CheckFiles(ui, repo, repo[None])
    cf.fixup()
    return False

def check_cmd(ui, repo, **opts):
    '''checks changed files in the working directory for tabs or trailing whitespace

    - --verbose shows the location of offending characters in each line
    - --quiet hides filenames and only reports summary information
    - --debug shows settings and details about each file considered for checking

    If problems are found, the command returns 1, otherwise 0.
    '''

    ui.note('checkfiles: checking %s files for tabs or trailing whitespace...\n'
             % ('all' if opts['all'] else 'modified'))

    cf = CheckFiles(ui, repo, repo[None], opts)
    return cf.check()

def fixup_cmd(ui, repo, **opts):
    '''Replaces tabs with spaces and removes trailing whitespace from changed files
    '''

    ui.note('checkfiles: removing tabs and/or trailing whitespace in %s files...\n'
             % ('all' if opts['all'] else 'modified'))

    cf = CheckFiles(ui, repo, repo[None], opts)
    cf.fixup()
    return 0

################################################################################################

cmdtable = {
    'checkfiles': (check_cmd,
                   [('t', 'tabsize', 4, 'set the tab length'),
                     ('', 'all', None, 'fix all tracked files (not just changed)')],
                   'hg checkfiles [options]'),

    'fixwhitespace': (fixup_cmd,
                     [('t', 'tabsize', 4, 'set the tab length'),
                      ('', 'all', None, 'fix all tracked files (not just changed)')],
                      'hg fixwhitespace [options]')
}
