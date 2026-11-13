import ac
import traceback


def console(*args, join_char=' '):
    """Log a message to the AC console, prefixed with the app name."""
    ac.console('[TelemetryInput]: ' + join_char.join([str(a) for a in args]))


def console_exception(exception, description='Caught exception', log=False):
    """Log an exception with full traceback to the AC console."""
    console(description + ':', exception)
    for line in traceback.format_exc().splitlines():
        ac.console(line)
    if log:
        ac.log('[TelemetryInput] ' + description + ': ' + str(exception))
        ac.log(traceback.format_exc())
