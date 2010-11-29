# checkfiles.py detect and fix tabs and(or trailing whitespace in commits
#
# Copyright: Marcus Lindblom 2010
# License: GPLv2+

'''detects (and optionally fixes) tabs and trailing whitespace in commited files

== The hooks ==

check_hook: prevents commits containing tabs or trailing whitespace, without actually touching
            any files. Use as pretxncommit locally or pretxnchangegroup on a central repo.

fixup_hook: automatically fixes any problematic files before commit. Useful in pre-commit.
             (As this hook may changes files on disc, you will need to recompile your
             project after commiting if any files needed fixing)

             If you're not confortable with this kind of magic, use the check_hook and
             manually run the command with the --fixup option.

== The command ==

hg checkfiles [options]

checks changed files in the working directory for tabs or trailing whitespace

    - --verbose shows the location of offending characters in each line
    - --quiet hides filenames and only reports summary information
    - --debug shows settings and details about each file considered for checking

    If problems are found, the command returns 1, otherwise 0.
    If --fixup is given, the return value is always 0 (unless an error occurs).

options:

 -f --fixup          fix files by replacing tabs and removing trailing whitespace
 -t --tabsize VALUE  set the tab length (default: 4)


== Example usage ==

[extensions]
checkfiles = /path/to/checkfiles.py enable command

[hooks]
pretxnchangegroup.checkfiles = python:/path/to/checkfiles.py:check_hook
pretxncommit.checkfiles = python:/path/to/checkfiles.py:check_hook
pre-commit.checkfiles = python:/path/to/checkfiles.py:fixup_hook

[checkfiles]
checked_exts = .c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl
ignored_files = foo/contains_tabs.txt bar/contains_trailing_ws.txt
tab_size = 4
'''

from mercurial.i18n import _

class CheckFiles(object):
    def __init__(self, ui, repo, ctx):
        self.ctx = ctx
        self.ui = ui
        self.repo = repo

        self.checked_exts = ui.configlist('checkfiles', 'checked_exts',
            default='.c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl')
        self.ignored_files = ui.configlist('checkfiles', 'ignored_files')
        self.tab_size = int(ui.config('checkfiles', 'tab_size', default='4'))

        self.ui.debug('checkfiles: checked extensions: %s\n' % ' '.join(self.checked_exts))
        self.ui.debug('checkfiles: ignored files: %s\n' % ' '.join(self.ignored_files))

    def is_relevant(self, file):
        if file in self.ignored_files:
            self.ui.debug('checkfiles: ignoring %s (explicit ignore)\n' % file)
            return False

        if not any(map(lambda e:file.endswith(e), self.checked_exts)):
            self.ui.debug('checkfiles: ignoring %s (non-checked extension)\n' % file)
            return False

        try:
            fctx = self.ctx[file]
        except LookupError:
            self.ui.debug('checkfiles: skipping %s (deleted)\n' % file)
            return False

        if '\0' in fctx.data():
            self.ui.debug('checkfiles: skipping %s (binary)\n' % file)
            return False

        return True

    def check(self):
        filecount = 0
        probcount = 0
        tab_indicator = '^' * self.tab_size

        for file in filter(self.is_relevant, self.ctx.files()):
            self.ui.debug('checkfiles: checking %s ...\n' % file)
            fctx = self.ctx[file]
            tab = False
            ws = False

            for num, line in enumerate(fctx.data().splitlines(), 1):
                if line.isspace():
                    ws = True
                    probcount += 1
                    self.ui.note('%s (%i): all whitespace\n' % (file, num))

                elif line.endswith((' ', '\t')):
                    ws = True
                    probcount += 1
                    self.ui.note('%s (%i): trailing whitespace\n' % (file, num))

                    line = line.expandtabs(self.tab_size)
                    non_ws_len = len(line.rstrip())
                    line_show = ' ' * non_ws_len + '^' * (len(line) - non_ws_len)
                    self.ui.note('  %s\n  %s\n' % (line, line_show))

                elif '\t' in line:
                    tab = True
                    probcount += 1
                    self.ui.note('%s (%i): tab character(s)\n' % (file, num))

                    line_show = ''.join(tab_indicator if c == '\t' else ' ' for c in line)
                    line = line.expandtabs(self.tab_size)
                    self.ui.note('  %s\n  %s\n' % (line, line_show))

            if tab or ws:
                filecount += 1
                self.ui.status('checkfiles: %s: %s%s\n' %
                    (file, 'tabs ' if tab else '', 'whitespace' if ws else ''))
            else:
                self.ui.note('checkfiles: %s: ok\n' % file)

        if filecount > 0:
            from mercurial.node import short
            self.ui.warn('checkfiles: %i issues(s) found in %i file(s) in %s\n' %
                (probcount, filecount,
                short(self.ctx.node()) if self.ctx.node() else 'working directory'))

        return filecount > 0

    def fixup(self):
        import os.path

        for file in filter(self.is_relevant, self.ctx.files()):
            lines = self.ctx[file].data().splitlines()
            if not any(line.isspace() or '\t' in line or line.endswith(' ') for line in lines):
                self.ui.note('checkfiles: %s ok\n' % file)
                continue

            self.ui.status('checkfiles: fixing %s\n' % file)

            with open(os.path.join(self.repo.root, file), 'w') as fileobj:
                def fixline():
                    for line in lines:
                        yield line.rstrip().expandtabs(self.tab_size)
                        yield '\n'

                fileobj.writelines(fixline())

################################################################################################

def check_hook(ui, repo, hooktype, node, **kwargs):
    '''blocks commits/changesets containing tabs or trailing whitespace'''

    if hooktype == 'pretxncommit':
        ui.status('checkfiles: checking commit for tabs or trailing whitespace...\n')
        cf = CheckFiles(ui, repo, repo.changectx(node))
        return cf.check()

    elif hooktype == 'pretxnchangegroup':
        from mercurial import cmdutil

        ui.status('checkfiles: checking incoming changes for tabs or trailing whitespace...\n')
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

def checkfiles_cmd(ui, repo, **opts):
    '''checks changed files in the working directory for tabs or trailing whitespace

    - --verbose shows the location of offending characters in each line
    - --quiet hides filenames and only reports summary information
    - --debug shows settings and details about each file considered for checking

    If problems are found, the command returns 1, otherwise 0.
    If --fixup is given, the return value is always 0 (unless an error occurs).
    '''

    cf = CheckFiles(ui, repo, repo[None])
    cf.tab_size = int(opts['tabsize'])

    if opts['fixup']:
        ui.note('checkfiles: removing tabs and/or trailing whitespace in changed files...\n')
        cf.fixup()
        return 0
    else:
        ui.note('checkfiles: checking modified files for tabs or trailing whitespace...\n')
        return cf.check()

################################################################################################

cmdtable = {
    'checkfiles': (checkfiles_cmd,
                     [('f', 'fixup', None, 'fix files by replacing tabs and removing trailing whitespace'),
                      ('t', 'tabsize', 4, 'set the tab length')],
                     'hg checkfiles [options]')
}