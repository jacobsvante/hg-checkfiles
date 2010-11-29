# Copyright: Marcus Lindblom 2010
# License: GPLv2+
#
# This extension provides two hooks and a command for avoiding commits with 
# tabs or trailing whitespace in specific files.
#
#
# == The hooks ==
#
# There is a pretxncommit hook for checking for tabs/whitespace, which is useful on a central 
# repository.

# The second hook runs in pre-commit and automatically fixes any problematic files before commit.
# (As this actually changes files on disc, you will need to recompile your project after your commit,
#  but naturally only if there were changes.)
#
# If you're not confortable with this kind of magic, use the pretxncommit hook and the command with
# the --fixup option.
#
#
# == The command == 
#
# hg checkfiles [options]
# 
# checks changed files in the working directory for tabs or trailing whitespace
# 
#     - --verbose shows the location of offending characters in each line
#     - --quiet hides filenames and only reports summary information
#     - --debug shows settings and details about each file considered for checking
# 
#     If problems are found, the command returns 1, otherwise 0.
#     If --fixup is given, the return value is always 0 (unless an error occurs).
#
# options:
# 
#  -f --fixup          fix files by replacing tabs and removing trailing whitespace
#  -t --tabsize VALUE  set the tab length (default: 8 or checkfiles.tab_size) (default: 4) 
#
#
# == Example usage ==
#
# [extensions]
# checkfiles = /path/to/checkfiles.py
#
# [checkfiles]
# checked_exts = .c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl
# ignored_files = foo/contains_tabs.txt bar/contains_trailing_ws.txt
# tab_size = 4
# commitcheck = True
# autofixup = True


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
            fail = False

            for num, line in enumerate(fctx.data().splitlines(), 1):
                if line.isspace():
                    fail = True
                    probcount += 1
                    self.ui.status('%s (%i): all whitespace\n' % (file, num))

                elif line.endswith((' ', '\t')):
                    fail = True
                    probcount += 1
                    self.ui.status('%s (%i): trailing whitespace\n' % (file, num))

                    line = line.expandtabs(self.tab_size)
                    non_ws_len = len(line.rstrip())
                    line_show = ' ' * non_ws_len + '^' * (len(line) - non_ws_len)
                    self.ui.note('  %s\n  %s\n' % (line, line_show))

                elif '\t' in line:
                    fail = True
                    probcount += 1
                    self.ui.status('%s (%i): tab character(s)\n' % (file, num))

                    line_show = ''.join(tab_indicator if c == '\t' else ' ' for c in line)
                    line = line.expandtabs(self.tab_size)
                    self.ui.note('  %s\n  %s\n' % (line, line_show))

            if fail:
                filecount += 1
            else:
                self.ui.note("%s: ok\n" % file)

        if filecount > 0:
            self.ui.warn('checkfiles: %i problem(s) found in %i file(s)\n' % (probcount, filecount))

        return filecount > 0

    def fixup(self):
        import os.path

        for file in filter(self.is_relevant, self.ctx.files()):
            lines = self.ctx[file].data().splitlines()
            if not any(line.isspace() or '\t' in line or line.endswith(' ') for line in lines):
                continue

            self.ui.status('checkfiles: fixing %s\n' % file)

            with open(os.path.join(self.repo.root, file), 'w') as fileobj:
                def fixline():
                    for line in lines:
                        yield line.rstrip().expandtabs(self.tab_size)
                        yield '\n'

                fileobj.writelines(fixline())


#######################################################################

def checkfiles_hook(ui, repo, node, **kwargs):
    ui.status('checkfiles: checking commit for tabs or trailing whitespace...\n')

    cf = CheckFiles(ui, repo, repo.changectx(node))
    return cf.check()

def fixup_hook(ui, repo, **kwargs):
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

    ui.note('checkfiles: checking modified files in working directory for tabs or trailing whitespace...\n')
    cf = CheckFiles(ui, repo, repo[None])
    cf.tab_size = int(opts['tabsize'])

    if cf.check():
        if opts['fixup']:
            cf.fixup()
        else:
            return 1

    return 0

#######################################################################

def uisetup(ui):
    if ui.configbool('checkfiles', 'autofixup', False):
        ui.setconfig('hooks', 'pre-commit.checkfiles', fixup_hook)

def reposetup(ui, repo):
    if ui.configbool('checkfiles', 'commitcheck', False):
        ui.setconfig('hooks', 'pretxncommit.checkfiles', checkfiles_hook)

cmdtable = {
    # 'command-name': (function-call, options-list, help-string)
    'checkfiles': (checkfiles_cmd,
                     [('f', 'fixup', None, 'fix files by replacing tabs and removing trailing whitespace'),
                      ('t', 'tabsize', 4, 'set the tab length')],
                     'hg checkfiles [options]')
}