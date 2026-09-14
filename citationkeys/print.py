import click


def style_ck(ck):
    return click.style(ck, fg="blue")


def style_error(msg):
    return click.style(msg, fg="red")


def print_error(msg):
    click.secho("ERROR: " + msg, fg="red", err=True)


# Prints a download failure the way a user wants to read it, rather than as a traceback. If the site
# threw one of the codes that usually means "you are asking too often", we say so, since by the time
# we get here citationkeys.urlhandlers has already retried and given up.
def print_http_error(err):
    # NOTE: .filename (not .url), since HTTPError only gets a .url when it is built with a response body
    print_error("Could not download " + str(err.filename) + ": HTTP " + str(err.code) + " " + str(err.msg))

    if err.code in (403, 406, 429):
        print_warning("The site is likely rate-limiting us. Please wait a bit and try again.")


def style_warning(msg):
    return click.style(msg, fg="yellow")


def print_warning(msg):
    click.secho("WARNING: " + msg, fg="yellow")


def print_warning_no_nl(msg):
    click.secho("WARNING: " + msg, nl=False, fg="yellow")


def print_success(msg):
    click.secho(msg, fg="green")
