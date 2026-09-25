import os
import threading
print("Auxiliar 2 prueba")
def muestraMensaje():
	try :
		print("Auxiliar 2 en linea")
		threading.Timer(300.0,muestraMensaje).start()
	except Exception as e:
		print(e)
		threading.Timer(300.0,muestraMensaje).start()
print("Auxiliar 2 en linea")
threading.Timer(300.0,muestraMensaje).start()