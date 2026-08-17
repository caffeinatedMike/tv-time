import string
import sys
import time
from collections.abc import Callable

import broadlink
from broadlink import Device
from pynput import keyboard
from roku import Roku, RokuException
from wakepy import keep

TV_POWER_BTN = "260050000001229115101411143514111410151015101510153415341411143514341534153415341510151015101534141114111410151016331534153415101534143514351434150005140001284714000d050000000000000000"
TV_MUTE_BTN = "260050000001229115101510153415101510141114111410153415341510153415341534143514351434151015101534151015101510151014111434153415101534153415341534150005140001274715000d050000000000000000"
TV_VOLUME_DOWN_BTN = "260058000001279212131213123811131213121312131213123712381213123812371238123812371238123811131213121312131213121312131113123812381237123812381237120005210001274a12000c5c0001274912000d05"
TV_VOLUME_UP_BTN = "260050000001239511131213113811141114111314111114113811391113113911381138113911381114113811141114101411141114111311391113113911381138123811381139110005260001254b12000d05"


class TVRemote:
    """
    Previously-learned codes saved to Broadlink app were retrieved from:
        /storage/emulated/0/Android/data/cn.com.broadlink.econtrol.international/cache/let/ircode

    Local configuration returned via discover:

    .. code-block:: python

        broadlink.remote.rm4mini(
            ('192.168.0.36', 80),
            mac=b'\xa0C\xb0]\x88\x90',
            devtype=25741,
            timeout=10,
            name='智能遥控',
            model='RM4 mini',
            manufacturer='Broadlink',
            # if True, must go into Broadlink app and unselect "Lock" for other on WLAN
            is_locked=False
        )
    """

    def __init__(self):
        self._device: Device | None = None

    @property
    def key_map(self) -> dict[keyboard.Key | keyboard.KeyCode, Callable[[], None]]:
        return {
            # tv keys
            #   mute keys
            keyboard.Key.media_volume_mute: self.toggle_mute_unmute,
            keyboard.Key.f10: self.toggle_mute_unmute,
            #   volume down keys
            keyboard.Key.media_volume_down: self.volume_down,
            keyboard.Key.f11: self.volume_down,
            keyboard.KeyCode.from_char("-"): self.volume_down,
            #   volume up keys
            keyboard.Key.media_volume_up: self.volume_up,
            keyboard.Key.f12: self.volume_up,
            keyboard.KeyCode.from_char("+"): self.volume_up,
        }

    def dispatch_key(self, key: keyboard.Key | keyboard.KeyCode):
        if mapped_key := self.key_map.get(key):
            mapped_key()

    def connect(self):
        print("Attempting to connect to tv remote.")
        try:
            self._device = next(broadlink.xdiscover())
        except StopIteration:
            raise RuntimeError(
                "Could not locate device. Make sure you're on the same local network and the device is powered on."
            )

        print("Located tv remote.")
        if self._device.is_locked:
            raise RuntimeError(
                "Device is blocking operation over WLAN. Turn off the 'Locked' setting in the devices preferences using the Broadlink app."
            )

        print("Attempting to authenticate with tv remote.")
        self._authenticate()

        print("Successfully connected to tv remote!")

    def toggle_on_off(self):
        self._send(TV_POWER_BTN)

    def _repeat(self, code: str, count: int = 1):
        for x in range(1, count + 1):
            if x > 1:
                time.sleep(0.2)
            self._send(code)

    def volume_up(self, count: int = 1):
        self._repeat(TV_VOLUME_UP_BTN, count)

    def volume_down(self, count: int = 1):
        self._repeat(TV_VOLUME_DOWN_BTN, count)

    def toggle_mute_unmute(self):
        self._send(TV_MUTE_BTN)

    def _authenticate(self):
        if self._device and not self._device.auth():
            raise RuntimeError("Failed to authenticate with the device.")

    def _send(self, code: str):
        if not self._device:
            raise RuntimeError("Must call connect() before sending any commands.")

        try:
            try:
                self._device.send_data(bytes.fromhex(code))  # type: ignore[reportAttributeAccessIssue]
            except broadlink.e.AuthorizationError:
                # unencountered, but a safety precaution in case .auth() expires
                # if this doesn't work, next course of action is replacing self._device instance
                # and re-calling self.connect()
                print("Re-authenticating with the tv remote.")
                self._authenticate()
                self._device.send_data(bytes.fromhex(code))  # type: ignore[reportAttributeAccessIssue]
        except broadlink.e.BroadlinkException as e:
            print(f"Encountered unexpected error: {e!s}")
            raise


class RokuStick:
    """
    Open Roku Mobile App on phone
    connect to stick
    immediately navigate to
      Settings >
      System >
      Advanced system settings >
      Control by mobile apps >
      Enabled

    # uv run roku discover --timeout 10 --retries 3
    # 192.168.0.17:8060
    """

    def __init__(self):
        self._device: Roku | None = None

    @property
    def key_map(self) -> dict[keyboard.Key | keyboard.KeyCode, Callable[[], None]]:
        return {
            # rogu keys
            keyboard.Key.up: self.up,
            keyboard.Key.down: self.down,
            keyboard.Key.left: self.left,
            keyboard.Key.right: self.right,
            keyboard.Key.enter: self.ok,
            keyboard.Key.space: self.ok,
            keyboard.Key.home: self.home,
            # home is fn+7 on keypad, so added simple 7 for shortcut
            keyboard.KeyCode.from_char("7"): self.home,
            keyboard.Key.media_previous: self.rewind,
            keyboard.Key.media_play_pause: self.toggle_play_pause,
            keyboard.Key.media_next: self.fast_forward,
            keyboard.Key.backspace: self.back,
            # left is fn+4 on keypad, so use simple 4 for replay leaving left reserved for movement
            keyboard.KeyCode.from_char("4"): self.replay,
            # info opens system's side menu to toggle captions
            keyboard.KeyCode.from_char("*"): self.info,
            # * is shift+overhead 8, so added simple 8 for shortcut
            keyboard.KeyCode.from_char("8"): self.info,
            # RokuStick._device.literal(full_text_input)
        }

    def dispatch_key(self, key: keyboard.Key | keyboard.KeyCode):
        if mapped_key := self.key_map.get(key):
            mapped_key()

    def connect(self):
        print("Attempting to locate Roku stick. This can take up to 30 seconds.")
        rokus: list[Roku] = Roku.discover(timeout=10, retries=3)

        if not rokus:
            raise RuntimeError(
                "Could not locate device. Make sure the device is plugged in and you're on the same local network."
            )

        self._device = rokus[0]
        print(f"Discovered device at {self._device.host}")
        print("Device info:", self._device.device_info)
        print(f"Device is currently {self._device.power_state}")
        if self._device.power_state == "Off":
            print("Attempting to power on device.")
            self._device.poweron()

    def up(self):
        self._send("up")

    def down(self):
        self._send("down")

    def left(self):
        self._send("left")

    def right(self):
        self._send("right")

    def ok(self):
        self._send("select")

    def home(self):
        self._send("home")

    def rewind(self):
        self._send("reverse")

    def toggle_play_pause(self):
        self._send("play")

    def fast_forward(self):
        self._send("forward")

    def back(self):
        self._send("back")

    def replay(self):
        self._send("replay")

    def info(self):
        self._send("info")

    def enter_text(self, term: str):
        if term:  # avoid sending an empty string
            self._send("literal", term)

    def _send(self, command: str, value: str | None = None, retry: bool = True):
        if not self._device:
            raise RuntimeError("Must call connect() before sending any commands.")

        if not (known_command := getattr(self._device, command, None)):
            print(f"Unknown Roku command: {command}")
            return

        try:
            if value:
                known_command(value)
            else:
                known_command()
        except RokuException:
            if not retry or self._device.power_state == "On":
                raise

            print("Encountered error while device was off: {e!r}")
            print("Powering on and retrying.")
            self._device.poweron()
            time.sleep(5)

            self._send(command, value, retry=False)


class MediaMonitor:
    def __init__(self):
        self._tv: TVRemote | None = None
        self._rogu: RokuStick | None = None
        self._started: bool = False
        self._typing_enabled: bool = False
        self._input_buffer: list[str] = []

    def start(self):
        print("Starting media monitor.")

        print("Establishing local connections.")
        self._tv = TVRemote()
        self._tv.connect()

        self._rogu = RokuStick()
        self._rogu.connect()
        self._started = True

        print("Setting up keyboard listener.")
        self._listener = keyboard.Listener(on_press=self._on_press, suppress=True)
        self._listener.start()
        print("Keyboard listener started.")
        print("Note: All keyboard input will be suppressed while program is running.")
        print("Use the 'esc' or 'end' key to exit the program.")
        print("Use the 'tab' or 'ctrl' key to enter text mode.")
        print("Ready to receive input...")
        try:
            with keep.presenting():
                self._listener.join()
        except Exception as e:  # noqa: BLE001
            print(f"Encountered exception: {e}")
            input("Press any key to exit...")

        if self._listener.is_alive():
            print("Keyboard listener is still running.")
            self._listener.stop()

        print("Keyboard listener stopped.")

    def _on_press(
        self,
        key: keyboard.Key | keyboard.KeyCode | None,
        _: bool | None,
    ) -> bool | None:
        if not self._started or not key:
            return

        if key in (keyboard.Key.esc, keyboard.Key.end):
            print(f"Exit key received: {key!r}")
            return False

        if self._typing_enabled:
            if key == keyboard.Key.backspace:
                if self._input_buffer:
                    self._input_buffer.pop()
                    # visually erase character from stdout
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif hasattr(key, "char") and key.char and key.char in string.printable:  # type: ignore[reportAttributeAccessIssue]
                self._input_buffer.append(key.char)  # type: ignore[reportAttributeAccessIssue]
                sys.stdout.write(key.char)  # type: ignore[reportAttributeAccessIssue]
                sys.stdout.flush()
            elif key == keyboard.Key.enter:
                self._rogu.enter_text("".join(self._input_buffer))  # type: ignore[reportAttributeAccessIssue]
                self._typing_enabled = False
                self._input_buffer.clear()
                sys.stdout.write("\n")
                sys.stdout.flush()
                print("Exiting text mode.")
                print("Ready to receive input...")
            return

        if key in (keyboard.Key.tab, keyboard.Key.ctrl):
            print("Entering text mode.")
            print("Type your search term below, then hit 'enter'.")
            self._typing_enabled = True
            sys.stdout.write("\n> ")
            sys.stdout.flush()
            return

        if key in self._tv.key_map:  # type: ignore[reportAttributeAccessIssue]
            self._tv.dispatch_key(key)  # type: ignore[reportAttributeAccessIssue]
        elif key in self._rogu.key_map:  # type: ignore[reportAttributeAccessIssue]
            self._rogu.dispatch_key(key)  # type: ignore[reportAttributeAccessIssue]
        else:
            # unmapped keypress, do nothing
            pass


def print_event_keys():
    print("Use Ctrl+C to raise a KeyboardInterrupt and exit.")
    print("Press any key or key combination...")
    with keyboard.Events() as events:
        for event in events:
            print(event)


if __name__ == "__main__":
    # print_event_keys()
    mm = MediaMonitor()
    mm.start()
