# display_sleep.py - a basic blanking screensaver.
#
# Example Configuration:
#
#     [display_sleep]
#     sleep_timeout: 300
#     sleep_while_printing: False
#
# Source: https://github.com/MapleLeafMakers/KlipperMacros/klippy/extras/display_sleep.py


class DisplaySleep:

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.sleep_timeout = config.getint('sleep_timeout', -1)
        self.sleep_while_printing = config.getboolean('sleep_while_printing', False)
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.printer.register_event_handler("idle_timeout:printing", self.handle_printing)
        self.sleep_timer = self.reactor.register_timer(self.sleep)
        self.is_sleeping = False
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command("DISPLAY_SLEEP",
                                    self.cmd_DISPLAY_SLEEP,
                                    desc=self.cmd_DISPLAY_SLEEP_help)
        self.gcode.register_command("DISPLAY_WAKE",
                                    self.cmd_DISPLAY_WAKE,
                                    desc=self.cmd_DISPLAY_WAKE_help)

    def iter_displays(self):
        for _, display in self.printer.lookup_objects('display'):
            yield display

    def patch_display(self):
        from .display.display import PrinterLCD, REDRAW_TIME, REDRAW_MIN_TIME

        def screen_update_event(self_, eventtime):
            if self_.redraw_request_pending:
                self_.redraw_request_pending = False
                self_.redraw_time = eventtime + REDRAW_MIN_TIME
            self_.lcd_chip.clear()
            if self.is_sleeping:
                self_.lcd_chip.flush()
                return eventtime + REDRAW_TIME
            # update menu component
            if self_.menu is not None:
                ret = self_.menu.screen_update_event(eventtime)
                if ret:
                    self_.lcd_chip.flush()
                    return eventtime + REDRAW_TIME
            # Update normal display
            try:
                self_.show_data_group.show(self_, self_.display_templates, eventtime)
            except:
                logging.exception("Error during display screen update")
            self_.lcd_chip.flush()
            return eventtime + REDRAW_TIME

        for d in self.iter_displays():
            if d.screen_update_timer:
                self.reactor.unregister_timer(d.screen_update_timer)

        if hasattr(PrinterLCD, 'base_screen_update_event'):
            # Unpatch
            PrinterLCD.screen_update_event = PrinterLCD.base_screen_update_event

        PrinterLCD.base_screen_update_event = PrinterLCD.screen_update_event
        PrinterLCD.screen_update_event = screen_update_event

        for d in self.iter_displays():
            if d.screen_update_timer:
                d.screen_update_timer = self.reactor.register_timer(d.screen_update_event)

    def update_timer(self):
        if self.sleep_timeout > 0:
            self.reactor.update_timer(
                self.sleep_timer,
                self.reactor.monotonic() + self.sleep_timeout)

    def patch_menu(self):
        # We can't cleanly replace the key_event handler because it's already set up, so we replace
        # the individual button handlers instead.
        def _click_callback(self_, eventtime, key):
            self.update_timer()
            if self.is_sleeping:
                self.wake()
                return
            self_.base_click_callback(eventtime, key)
        def up(self_, fast):
            self.update_timer()
            if self.is_sleeping:
                self.wake()
                return
            self_.base_up(fast)
        def down(self_, fast):
            self.update_timer()
            if self.is_sleeping:
                self.wake()
                return
            self_.base_down(fast)
        def back(self_):
            self.update_timer()
            if self.is_sleeping:
                self.wake()
                return
            self_.base_back()

        from .display.menu import MenuManager
        if hasattr(MenuManager, 'base_click_callback'):
            # Unpatch
            MenuManager._click_callback = MenuManager.base_click_callback
            MenuManager.up = MenuManager.base_up
            MenuManager.down = MenuManager.base_down 
            MenuManager.back = MenuManager.base_back 

        MenuManager.base_click_callback = MenuManager._click_callback
        MenuManager._click_callback = _click_callback
        MenuManager.base_up = MenuManager.up
        MenuManager.up = up
        MenuManager.base_down = MenuManager.down
        MenuManager.down = down
        MenuManager.base_back = MenuManager.back
        MenuManager.back = back

    def handle_ready(self):
        self.patch_menu()
        self.patch_display()
        self.update_timer()

    def handle_printing(self, eventtime):
        if not self.sleep_while_printing:
            self.wake()

    def wake(self):
        self.is_sleeping = False
        for display in self.iter_displays():
            display.request_redraw()

    def sleep(self, eventtime, force=False):
        idle_timeout = self.printer.lookup_object("idle_timeout")
        state = idle_timeout.get_status(eventtime)["state"]
        if state == "Printing" and not force and not self.sleep_while_printing:
            return eventtime + self.sleep_timeout
        self.is_sleeping = True
        for display in self.iter_displays():
            display.request_redraw()
        return self.reactor.NEVER

    cmd_DISPLAY_SLEEP_help = "Blanks the display until a key is pressed, or DISPLAY_WAKE is called."
    def cmd_DISPLAY_SLEEP(self, gcmd):
        self.sleep(self.reactor.monotonic(), force=True)

    cmd_DISPLAY_WAKE_help = "Wakes the display."
    def cmd_DISPLAY_WAKE(self, gcmd):
        self.update_timer()
        self.wake()

def load_config(config):
    return DisplaySleep(config)
