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

import mercurial.commands


def rebaseif(ui, repo, **opts):
    '''rebases if no conflicts and merges otherwise

    '''

    import hgext.rebase

    origmerge = ui.config('ui', 'merge')
    try:
        ui.setconfig('ui', 'merge', 'internal:merge')
        if hgext.rebase.rebase(ui, repo) == 0:
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

cmdtable = {
    # 'command-name': (function-call, options-list, help-string)
    'rebaseif': (rebaseif, [], 'hg rebaseif')
}
