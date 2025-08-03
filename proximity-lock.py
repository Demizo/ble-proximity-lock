import asyncio
import subprocess
import logging
import sys
import time
import argparse

from dbus_next.aio import MessageBus
from dbus_next import BusType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

CONNECTED = False
LAST_GOOD_SIGNAL = 0
DEVICE_PATH = None
PHONE_MAC = None

# Default settings (can be overridden by args)
RSSI_THRESHOLD = -3
GRACE_PERIOD = 10
POLL_INTERVAL = 5


def lock_screen():
    logger.info("Locking screen...")
    subprocess.run(["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "Lock"])


def is_screen_locked():
    """Return True if the screen is currently locked."""
    try:
        # Get the current session ID
        session_id = subprocess.check_output(
            ["loginctl", "show-user", str(subprocess.check_output(['id', '-u']).decode().strip()), "--property=Sessions"]
        ).decode().strip().split('=')[-1].split()[0]

        # Check the LockedHint property
        locked = subprocess.check_output(
            ["loginctl", "show-session", session_id, "--property=LockedHint"]
        ).decode().strip()
        return locked.endswith("yes")
    except Exception as e:
        logger.warning(f"Unable to determine screen lock state: {e}")
        return False


def unlock_screen():
    logger.info("Unlocking screen...")
    subprocess.run(["loginctl", "unlock-session"])


def get_paired_devices():
    """Return a list of paired device MAC addresses and names using bluetoothctl."""
    output = subprocess.check_output(["bluetoothctl", "devices", "Bonded"]).decode().strip()
    devices = []
    for line in output.splitlines():
        # Format: Device XX:XX:XX:XX:XX:XX Name
        parts = line.split(" ", 2)
        if len(parts) >= 3:
            devices.append((parts[1], parts[2]))
    return devices


def get_rssi():
    """Poll RSSI for the given PHONE_MAC."""
    try:
        output = subprocess.check_output(["hcitool", "rssi", PHONE_MAC]).decode()
        return int(output.split(":")[-1].strip())
    except Exception as e:
        logger.warning(f"Failed to read RSSI: {e}")
        return None


async def poll_rssi():
    global LAST_GOOD_SIGNAL
    while True:
        if CONNECTED:
            rssi = get_rssi()
            if rssi is not None:
                logger.info(f"RSSI: {rssi}")
                if rssi >= RSSI_THRESHOLD:
                    LAST_GOOD_SIGNAL = time.time()
                    if is_screen_locked():
                        unlock_screen()
                elif time.time() - LAST_GOOD_SIGNAL > GRACE_PERIOD:
                    if not is_screen_locked():
                        lock_screen()
        await asyncio.sleep(POLL_INTERVAL)


async def main():
    global CONNECTED, DEVICE_PATH

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    # Introspect and get the Properties interface for our device
    introspection = await bus.introspect("org.bluez", DEVICE_PATH)
    device_obj = bus.get_proxy_object("org.bluez", DEVICE_PATH, introspection)
    props_iface = device_obj.get_interface("org.freedesktop.DBus.Properties")

    # Sync connected state at startup
    CONNECTED = (await props_iface.call_get("org.bluez.Device1", "Connected")).value
    logger.info(f"Initial connected state: {CONNECTED}")

    def properties_changed(iface_name, changed, invalidated):
        global CONNECTED
        if iface_name != "org.bluez.Device1":
            return

        if "Connected" in changed:
            CONNECTED = changed["Connected"].value
            logger.info(f"Connected: {CONNECTED}")
            if not CONNECTED:
                lock_screen()

    props_iface.on_properties_changed(properties_changed)
    logger.info(f"Monitoring {PHONE_MAC}...")
    await poll_rssi()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BLE proximity lock")
    parser.add_argument("device", nargs="?", help="BLE device address (optional)")
    parser.add_argument("--rssi-threshold", type=int, default=RSSI_THRESHOLD,
                        help=f"RSSI threshold below which the screen unlocks (default: {RSSI_THRESHOLD}, highest strength: 0)")
    parser.add_argument("--grace-period", type=int, default=GRACE_PERIOD,
                        help=f"Grace period in seconds before locking after signal loss (default: {GRACE_PERIOD})")
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL,
                        help=f"Interval in seconds for RSSI polling (default: {POLL_INTERVAL})")
    args = parser.parse_args()

    # Apply args to globals
    RSSI_THRESHOLD = args.rssi_threshold
    GRACE_PERIOD = args.grace_period
    POLL_INTERVAL = args.poll_interval
    if args.device:
        PHONE_MAC = args.device.upper()
    else:
        devices = get_paired_devices()
        if not devices:
            logger.error("No paired devices found.")
            sys.exit(1)

        print("Select a paired device:")
        for i, (mac, name) in enumerate(devices, start=1):
            print(f"{i}. {name} ({mac})")

        choice = input("Enter the number of the device: ")
        try:
            PHONE_MAC = devices[int(choice) - 1][0]
        except (IndexError, ValueError):
            logger.error("Invalid choice.")
            sys.exit(1)

    DEVICE_PATH = f"/org/bluez/hci0/dev_{PHONE_MAC.replace(':', '_')}"

    asyncio.run(main())

