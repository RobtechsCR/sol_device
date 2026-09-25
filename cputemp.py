import os
import threading

print("Auxiliar 5 prueba")
def muestraMensaje():
	try :
		with open("/sys/class/thermal//thermal_zone0/temp","r") as f:
			temp_raw = f.read()
			temp_c=float(temp_raw) / 1000.0
			print (temp_c)
		
		
		threading.Timer(5.0,muestraMensaje).start()
	except Exception as e:
		print(e)
		threading.Timer(300.0,muestraMensaje).start()
print("Auxiliar 5 en linea")
threading.Timer(5,muestraMensaje).start()
