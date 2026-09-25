import datetime
import os
import tempfile
import time

BASE_DIR = "/home/orangepi/Documents"
DEVICE_FILE = os.path.join(BASE_DIR, "nfc_device.txt")
LAST_FILE = os.path.join(BASE_DIR, "nfc.txt")
LOG_FILE = os.path.join(BASE_DIR, "nfc_lecturas.txt")
BURST_SECONDS = 1.0
DUPLICATE_SECONDS = 2.0
SPECIFIC_HINTS = ("rfid", "nfc", "mifare", "barcode", "reader", "card", "sycreader", "proximity")
GENERIC_HINTS = ("hid",)


def accept_code(text, elapsed, ended_with_enter, gap_exceeded=False):
	if not ended_with_enter or gap_exceeded:
		return None
	try:
		elapsed = float(elapsed)
	except (TypeError, ValueError):
		return None
	if elapsed >= BURST_SECONDS:
		return None
	if text is None:
		return None
	code = str(text).strip()
	if len(code) <= 5 or not code.isalnum():
		return None
	return code


def is_recent_duplicate(code, previous_code, previous_ts, now, window=DUPLICATE_SECONDS):
	if not previous_code or previous_ts is None:
		return False
	return code == previous_code and (now - previous_ts) < window


def begin_or_append(buffer, first_ts, last_ts, char, now):
	if first_ts is None or last_ts is None or (now - last_ts) >= BURST_SECONDS or len(buffer) > 64:
		return [char], now, now
	return buffer + [char], first_ts, now


def finish_burst(buffer, first_ts, last_ts, now):
	if not buffer or first_ts is None:
		return None
	gap = last_ts is not None and (now - last_ts) >= BURST_SECONDS
	return accept_code("".join(buffer), now - first_ts, True, gap)


def atomic_write(path, data):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
	try:
		with os.fdopen(fd, "w") as handle:
			handle.write(data)
			handle.flush()
			os.fsync(handle.fileno())
		os.replace(tmp, path)
	except Exception:
		try:
			os.unlink(tmp)
		except OSError:
			pass
		raise


def timestamp():
	try:
		import pytz
		zone = pytz.timezone("America/Costa_Rica")
		return datetime.datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_read(code):
	stamp = timestamp()
	atomic_write(LAST_FILE, "Tarjeta:" + code + ",Fecha: " + stamp + "\n")
	with open(LOG_FILE, "a") as handle:
		handle.write(stamp + " " + code + "\n")
		handle.flush()
	print("Tarjeta leida " + code)


def configured_device():
	try:
		with open(DEVICE_FILE, "r") as handle:
			hint = handle.read().strip()
	except OSError:
		return None
	return hint or None


def usb_keyboard_paths():
	base = "/dev/input/by-id"
	found = []
	if not os.path.isdir(base):
		return found
	for name in os.listdir(base):
		lower = name.lower()
		if "usb" in lower and ("kbd" in lower or "keyboard" in lower):
			found.append(os.path.realpath(os.path.join(base, name)))
	return found


def is_keyboard(device, ecodes):
	keys = device.capabilities().get(ecodes.EV_KEY, [])
	has_enter = ecodes.KEY_ENTER in keys or ecodes.KEY_KPENTER in keys
	has_chars = ecodes.KEY_A in keys or ecodes.KEY_1 in keys
	return has_enter and has_chars


def match_hint(hint, devices, evdev_module):
	path = hint
	if hint.startswith("event"):
		path = os.path.join("/dev/input", hint)
	if path.startswith("/dev/") and os.path.exists(path):
		for device in devices:
			if device.path == path:
				return device
		return evdev_module.InputDevice(path)
	lowered = hint.lower()
	for device in devices:
		name = (device.name or "").lower()
		if lowered == name or lowered in name or lowered in device.path.lower():
			return device
	return None


def match_reader(devices, ecodes):
	keyboards = [device for device in devices if is_keyboard(device, ecodes)]
	specific = []
	generic = []
	for device in keyboards:
		name = (device.name or "").lower()
		if any(hint in name for hint in SPECIFIC_HINTS):
			specific.append(device)
		elif any(hint in name for hint in GENERIC_HINTS):
			generic.append(device)
	if specific:
		if len(specific) > 1:
			print("Varios lectores, se usa " + specific[0].path + " " + specific[0].name)
		return specific[0]
	if len(generic) == 1:
		return generic[0]
	usb_paths = set(usb_keyboard_paths())
	usb = [device for device in keyboards if os.path.realpath(device.path) in usb_paths]
	if len(usb) == 1:
		return usb[0]
	return None


def close_unused(devices, selected):
	selected_path = None if selected is None else selected.path
	for device in devices:
		if device.path == selected_path:
			continue
		try:
			device.close()
		except Exception:
			pass


def find_device(evdev_module):
	devices = []
	for path in evdev_module.list_devices():
		try:
			devices.append(evdev_module.InputDevice(path))
		except (OSError, PermissionError) as error:
			print(error)
	selected = None
	try:
		hint = configured_device()
		if hint:
			try:
				selected = match_hint(hint, devices, evdev_module)
			except (OSError, PermissionError) as error:
				print(error)
		if selected is None:
			selected = match_reader(devices, evdev_module.ecodes)
		return selected
	except Exception:
		if selected is not None:
			try:
				selected.close()
			except Exception:
				pass
		raise
	finally:
		close_unused(devices, None if selected is None else selected)


def keymap(ecodes):
	keys = {}
	digits = (
		(ecodes.KEY_1, "1"),
		(ecodes.KEY_2, "2"),
		(ecodes.KEY_3, "3"),
		(ecodes.KEY_4, "4"),
		(ecodes.KEY_5, "5"),
		(ecodes.KEY_6, "6"),
		(ecodes.KEY_7, "7"),
		(ecodes.KEY_8, "8"),
		(ecodes.KEY_9, "9"),
		(ecodes.KEY_0, "0"),
	)
	letters = "abcdefghijklmnopqrstuvwxyz"
	letter_codes = (
		ecodes.KEY_A, ecodes.KEY_B, ecodes.KEY_C, ecodes.KEY_D, ecodes.KEY_E,
		ecodes.KEY_F, ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_I, ecodes.KEY_J,
		ecodes.KEY_K, ecodes.KEY_L, ecodes.KEY_M, ecodes.KEY_N, ecodes.KEY_O,
		ecodes.KEY_P, ecodes.KEY_Q, ecodes.KEY_R, ecodes.KEY_S, ecodes.KEY_T,
		ecodes.KEY_U, ecodes.KEY_V, ecodes.KEY_W, ecodes.KEY_X, ecodes.KEY_Y,
		ecodes.KEY_Z,
	)
	keypad = (
		(ecodes.KEY_KP0, "0"),
		(ecodes.KEY_KP1, "1"),
		(ecodes.KEY_KP2, "2"),
		(ecodes.KEY_KP3, "3"),
		(ecodes.KEY_KP4, "4"),
		(ecodes.KEY_KP5, "5"),
		(ecodes.KEY_KP6, "6"),
		(ecodes.KEY_KP7, "7"),
		(ecodes.KEY_KP8, "8"),
		(ecodes.KEY_KP9, "9"),
	)
	for code, char in digits:
		keys[code] = char
	for code, char in zip(letter_codes, letters):
		keys[code] = char
	for code, char in keypad:
		keys[code] = char
	return keys


def read_loop(device, evdev_module):
	ecodes = evdev_module.ecodes
	keys = keymap(ecodes)
	buffer = []
	first_ts = None
	last_ts = None
	shifted = False
	previous_code = None
	previous_ts = None
	shift_codes = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
	enter_codes = {ecodes.KEY_ENTER, ecodes.KEY_KPENTER}
	for event in device.read_loop():
		if event.type != ecodes.EV_KEY:
			continue
		now = time.monotonic()
		if event.code in shift_codes:
			shifted = event.value != 0
			continue
		if event.value != 1:
			continue
		if event.code in enter_codes:
			code = finish_burst(buffer, first_ts, last_ts, now)
			buffer = []
			first_ts = None
			last_ts = None
			if code and not is_recent_duplicate(code, previous_code, previous_ts, now):
				try:
					save_read(code)
					previous_code = code
					previous_ts = now
				except OSError as error:
					print(error)
			continue
		char = keys.get(event.code)
		if char is None:
			continue
		if shifted and char.isalpha():
			char = char.upper()
		buffer, first_ts, last_ts = begin_or_append(buffer, first_ts, last_ts, char, now)


def main():
	while True:
		device = None
		try:
			import evdev
		except ImportError:
			print("Falta el modulo evdev")
			time.sleep(10)
			continue
		try:
			device = find_device(evdev)
			if device is None:
				print("Lector NFC no encontrado")
				time.sleep(2)
				continue
			print("Lector NFC " + device.path + " " + device.name)
			read_loop(device, evdev)
		except Exception as error:
			print("Error NFC", error)
			time.sleep(2)
		finally:
			if device is not None:
				try:
					device.close()
				except Exception:
					pass


if __name__ == "__main__":
	main()
