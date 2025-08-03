# BLE Proximity Lock Script

This Python script locks or unlocks your screen based on the proximity of a paired Bluetooth device (e.g. your phone). When your device is connected and within range, the screen can be unlocked; if it disconnects or is too far away, the screen will lock.

## Requirements

- Linux system with BlueZ. Tested on KDE Plasma
- bluetoothctl (for paired device discovery)
- hcitool (for RSSI polling)
- qdbus and loginctl (for lock/unlock)

## Usage

```
python proximity-lock.py [BLE_DEVICE_MAC]
```

If you provide a BLE device MAC:

```
python proximity-lock.py XX:XX:XX:XX:XX:XX
```

If you don't specify a device, the script will list paired devices and prompt you to choose:

```
1. My Phone (XX:XX:XX:XX:XX:XX)
2. My Tablet (XX:XX:XX:XX:XX:XX)
Enter the number of the device:
```

For more options:

```
python proximity-lock.py --help
```
