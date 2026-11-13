import ac

from _TelemetryInput.app import App
from _TelemetryInput.utils import console_exception

app_state = None


def acMain(ac_version):
    global app_state

    try:
        app_state = App()
        app_state.load_main()
        ac.addRenderCallback(app_state.graph_window, on_graph_render)
        ac.addRenderCallback(app_state.bars_window, on_bars_render)
    except Exception as e:
        console_exception(e, 'acMain() failed', log=True)

    return "TelemetryInput"


def acUpdate(dt):
    global app_state

    if not app_state:
        return

    try:
        app_state.on_update(dt)
    except Exception as e:
        console_exception(e, 'acUpdate() failed')


def on_graph_render(dt):
    global app_state

    if not app_state:
        return

    try:
        app_state.on_render(dt)
    except Exception as e:
        console_exception(e, 'on_graph_render() failed')


def on_bars_render(dt):
    global app_state

    if not app_state:
        return

    try:
        app_state.on_render_bars(dt)
    except Exception as e:
        console_exception(e, 'on_bars_render() failed')


def acShutDown():
    global app_state

    if not app_state:
        return

    # Always save config on exit
    if app_state.config and app_state.config.update_cfg:
        app_state.config.save()
