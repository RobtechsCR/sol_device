import os
import threading
print("Auxiliar 3 prueba")
def muestraMensaje():
	try :
		print("Auxiliar 3 en linea")
		threading.Timer(300.0,muestraMensaje).start()
	except Exception as e:
		print(e)
		threading.Timer(300.0,muestraMensaje).start()
print("Auxiliar 3 en linea")
threading.Timer(300.0,muestraMensaje).start()
