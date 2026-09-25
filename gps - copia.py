import time, serial
import pynmea2
import threading
import serial.tools.list_ports 
from serial.serialutil import SerialException
from time import sleep

def get_coordenadas_dms(coordenada, tipo):
	try:	
		print(coordenada,tipo)
		if (tipo==int(1)):
			grados=coordenada[0:2]	
			minutos=coordenada[2:4]
			segundos=coordenada[5:len(coordenada)-1]
		if (tipo==int(2)):
			grados=coordenada[0:3]	
			minutos=coordenada[3:5]
			segundos=coordenada[6:len(coordenada)-1]
		
		segundos="0."+str(segundos)
		sec=float(segundos)
		sec=sec*60
		direccion=coordenada[len(coordenada)-1:]
		datosdms=[grados,minutos,str(sec)+"",direccion]
		return datosdms
	except:
		print("Datos gps invalidos")
		datosdms=[]
		return datosdms

def dms_a_decimal (grados, minutos, segundos, direccion):
	try:
		dd=float(grados) + float(minutos)/60 + float(segundos)/(60*60)
		if ( direccion == 'E' or direccion == 'S' or direccion == 'W'):
			dd *=-1
		return dd
	except:
		return 0.0

def open_gps():
	global gps
	try:
		print("Open serial port gps")
		gps = serial.Serial("/dev/ttyACM0", baudrate=19200, timeout=30)
		print("Serial Port ttyACM0 opened")
		threading.Timer(5.0,get_gps).start()
	except:
		
		print("Sin conexion con gps")
		file = open("/home/orangepi/Documents/gps.txt","w")
		file.write("Sin conexion con gps")	
		file.close
		threading.Timer(2.0,open_gps).start()
		return
def close_gps():
	if (gps.isOpen()):
		gps.close()
		
def get_gps():	
	global datagps	
	if (gps.isOpen()==False):
		print("Puerto cerrado reintentando dentro de 5 segundos")
		open_gps()
		
		return
	line = "Datos gps"
	while True:
		try:
			
			line = gps.readline().decode("ascii", errors = 'replace').strip()
			if (line.startswith('$GPRMC')):
				print("Getting coordinates")
				print(line)
				resp = pynmea2.parse(line)
				latitud_decimal = resp.latitude
				longitud_decimal = resp.longitude
				velocidad_n=resp.spd_over_grnd
				velocidad = float(velocidad_n) * 1.852 if velocidad_n else 0.0
				print(str(latitud_decimal) + ", "+str(longitud_decimal))
				print(velocidad)
				file = open("/home/orangepi/Documents/gps.txt","w")
				file.write("Latitud:"+str(latitud_decimal)+",Longitud: "+str(longitud_decimal)+",Velocidad: "+str(velocidad))	
				file.close
			
		except pynmea2.ParseError:
			print("Pynmea2 error")
			continue
		except ValueError:
			print("Value error")
			continue
		except SerialException:
			print("Conexion Serial con error, puerto cerrado o sin comunicacion con dispositivo")
			close_gps()
			open_gps()
			break
		
			
	
	
	return
	#except:
	#	print("Sin datos gps validos")
	#	file = open("/home/orangepi/Documents/gps.txt","w")
	#	file.write("Sin conexion con gps")	
	#	file.close
	#	threading.Timer(2.0,get_gps).start()
	#	return	
open_gps()

