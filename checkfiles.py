# Copyright Marcus Lindblom 2010
# License: GPL 2.0+
#
# This extension adds a pretxncommit hook that checks files for tabs or trailing whitespace and fails if so
#
# Example usage:
#
# [extensions]
# pretxncommit = <path>/checkfiles.py
#
# [checkfiles]
# checked_exts = .c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl
# ignored_files = foo/contains_tabs.txt bar/contains_trailing_ws.txt
# tab_size = 4

def checkfiles(ui, repo, node, **kwargs):
    ui.note("checkfiles: checking commit for tabs or trailing whitespace...\n")

    checked_exts = ui.configlist('checkfiles', 'checked_exts', default='.c .h .cpp .xml .cs .html .js .css .txt .py .nsi .java .aspx .asp .bat .cmd .glsl')
    ignored_files = ui.configlist('checkfiles', 'ignored_files')
    tab_size = int(ui.config('checkfiles', 'tab_size', default='8'))

    ui.debug("checkfiles: checked extensions: %s\n" % ' '.join(checked_exts))
    ui.debug("checkfiles: ignored files: %s\n" % ' '.join(ignored_files))

    ctx = repo.changectx(node)
    fail = False
    tab_indicator = '^' * tab_size

    for file in ctx.files():
        if file in ignored_files:
            ui.debug("checkfiles: ignoring %s (explicit ignore)\n" % file)
            continue

        if not any(map(lambda e:file.endswith(e), checked_exts)):
            ui.debug("checkfiles: ignoring %s (non-checked extension)\n" % file)
            continue

        try:
            fctx = ctx[file]
        except LookupError:
            ui.debug("checkfiles: skipping %s (deleted)\n" % file)
            continue # file/path was deleted in commit, so ignore it

        if '\0' in fctx.data():
            ui.debug("checkfiles: skipping %s (binary)\n" % file)
            continue

        ui.debug("checkfiles: checking %s ...\n" % file)

        for num, line in enumerate(fctx.data().splitlines(), 1):
            if line.isspace():
                fail = True
                ui.warn("%s (%i): all whitespace\n" % (file, num))

            elif line.endswith((' ', '\t')):
                fail = True
                ui.warn("%s (%i): trailing whitespace\n" % (file, num))

                line = line.expandtabs(tab_size)
                non_ws_len = len(line.rstrip())
                line_show = ' ' * non_ws_len + '^' * (len(line) - non_ws_len)
                ui.note("  %s\n  %s\n" % (line, line_show))

            elif '\t' in line:
                fail = True
                ui.warn("%s (%i): tab character(s)\n" % (file, num))

                line_show = ''.join([tab_indicator if c == '\t' else ' ' for c in line])
                line = line.expandtabs(tab_size)
                ui.note("  %s\n  %s\n" % (line, line_show))

    if fail:
        ui.warn("checkfiles: aborting commit due to tabs and/or trailing whitespace\n")
    else:
        ui.note("checkfiles: tab check ok...\n")

    return fail


def reposetup(ui, repo):
    ui.setconfig("hooks", "pretxncommit", checkfiles)

