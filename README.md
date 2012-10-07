# checkfiles

hg checkfiles [options]

checks changed files in the working directory for tabs or trailing whitespace

    --verbose shows the location of offending characters in each line
    --quiet hides filenames and only reports summary information
    --debug shows settings and details about each file considered for checking

    If problems are found, the command returns 1, otherwise 0.

options:

    -f --fixup    fix files by replacing tabs and removing trailing whitespace
    -t --tabsize  set the tab length (default: 8 or checkfiles.tab_size)

use "hg -v help checkfiles" to show global options
