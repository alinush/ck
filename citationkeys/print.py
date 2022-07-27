import click


def style_ck(ck):
    return click.style(ck, fg="blue")


def style_error(msg):
    return click.style(msg, fg="red")


def print_error(msg):
    click.secho("ERROR: " + msg, fg="red", err=True)


def style_warning(msg):
    return click.style(msg, fg="yellow")


def print_warning(msg):
    click.secho("WARNING: " + msg, fg="yellow")


def print_warning_no_nl(msg):
    click.secho("WARNING: " + msg, nl=False, fg="yellow")


def print_success(msg):
    click.secho(msg, fg="green")
