import uuid

def get_device_id():
	id=str(uuid.uuid4())	
	return id[-8:]
	
print(get_device_id())
