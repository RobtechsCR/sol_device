import os
import threading
print("Auxiliar 5 prueba")
def muestraMensaje():
	try :
		print("Auxiliar 5 en linea")
		threading.Timer(300.0,muestraMensaje).start()
	except Exception as e:
		print(e)
		threading.Timer(300.0,muestraMensaje).start()
print("Auxiliar 5 en linea")
threading.Timer(300.0,muestraMensaje).start()