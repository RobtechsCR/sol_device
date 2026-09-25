import os
import threading
print("Auxiliar 1 prueba")
def muestraMensaje():
	try :
		print("Auxiliar 1 en linea")
		threading.Timer(300.0,muestraMensaje).start()
	except Exception as e:
		print(e)
		threading.Timer(300.0,muestraMensaje).start()
print("Auxiliar 1 en linea")
threading.Timer(300.0,muestraMensaje).start()