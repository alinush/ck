import readline


def readline_enable_tab_autocompletion():
    if readline.__doc__ and 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind -e")
        readline.parse_and_bind("bind '\t' rl_complete")
    else:
        readline.parse_and_bind('tab: complete')
