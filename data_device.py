import os
import time
import uuid

BASE_DIR = "/home/orangepi/Documents"
DEVICE_ID_PATH = os.path.join(BASE_DIR, "device_id.txt")


def get_device_id():
	if os.path.isfile(DEVICE_ID_PATH):
		with open(DEVICE_ID_PATH, "r") as handle:
			existing = handle.read().strip()
		if existing:
			return existing
	os.makedirs(BASE_DIR, exist_ok=True)
	new_id = str(uuid.uuid4())[-8:]
	try:
		fd = os.open(DEVICE_ID_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
	except FileExistsError:
		with open(DEVICE_ID_PATH, "r") as handle:
			existing = handle.read().strip()
		if existing:
			return existing
		raise
	with os.fdopen(fd, "w") as handle:
		handle.write(new_id)
	return new_id


def main():
	while True:
		try:
			print(get_device_id())
			return
		except Exception as error:
			print(error)
			time.sleep(2)


if __name__ == "__main__":
	main()
