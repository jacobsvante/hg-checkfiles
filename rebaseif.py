# Copyright Marcus Lindblom 2010
# License: GPL 2.0+
#
# This extension adds a command 'rebaseif' that rebases if there are no conflicts and merges otherwise.
# The reason for doing so is that a badly resolved conflict is easier to detect and fix afterwards
# if it was merges, since the conflict resolution is explicit in a separate commit, rather than mashed
# up with others as in the rebase case
#
# See http://stackoverflow.com/questions/4086724/how-do-i-check-for-potential-merge-rebase-conflicts-in-mercurial
# for some discussion on the matter

from mercurial import hg, commands, extensions, cmdutil
from mercurial.i18n import _

def rebaseif(ui, repo, **opts):
    '''rebases if there are no file conflicts and merges otherwise.

    See each command's documentation for details.
    '''

    # temporarly replace merge tool to try automatic rebase
    origmerge = ui.config('ui', 'merge')
    ui.setconfig('ui', 'merge', 'internal:merge')

    import hgext.rebase

    try:
        hgext.rebase.rebase(ui, repo)
        ui.status("rebaseif: successful rebase")
        return 0
    except:
        hgext.rebase.rebase(ui, repo, abort=True)
    finally:
        ui.setconfig('ui', 'merge', origmerge)

    ui.status("rebaseif: failed to rebase, attempting merge")

    import mercurial.commands
    mercurial.commands.merge(ui, repo)

    return 0

# taken almost in verbatim from rebase extension

def pullrebaseif(orig, ui, repo, *args, **opts):
    'Call rebaseif after pull if the latter has been invoked with --rebaseif'

    if opts.get('rebaseif'):
        if opts.get('update'):
            del opts['update']
            ui.debug('--update and --rebase are not compatible, ignoring '
                     'the update flag\n')

        cmdutil.bail_if_changed(repo)
        revsprepull = len(repo)
        origpostincoming = commands.postincoming
        def _dummy(*args, **kwargs):
            pass
        commands.postincoming = _dummy
        try:
            orig(ui, repo, *args, **opts)
        finally:
            commands.postincoming = origpostincoming
        revspostpull = len(repo)
        if revspostpull > revsprepull:
            rebaseif(ui, repo, **opts)
            branch = repo[None].branch()
            dest = repo[branch].rev()
            if dest != repo['.'].rev():
                # there was nothing to rebase we force an update
                hg.update(repo, dest)
    else:
        orig(ui, repo, *args, **opts)

def uisetup(ui):
    'Replace pull with a decorator to provide --rebaseif option'
    entry = extensions.wrapcommand(commands.table, 'pull', pullrebaseif)
    entry[1].append(('', 'rebaseif', None,
                     _("rebase or merge working directory to branch head"))
)

cmdtable = {
    # 'command-name': (function-call, options-list, help-string)
    'rebaseif': (rebaseif, [], 'hg rebaseif')
}
