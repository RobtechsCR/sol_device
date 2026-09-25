import time, serial
import pynmea2
import threading
import serial.tools.list_ports 
import math
import os
from serial.serialutil import SerialException
from geopy.distance import geodesic
from time import sleep

calidadgps=0
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
def calcular_distancia(lat1, lon1, lat2, lon2):
	punto1 = (float(lat1), float(lon1))
	punto2 = (float(lat2), float(lon2))

	# Calcular distancia en metros
	distancia = geodesic(punto1, punto2).meters
	print ("Calcular Dist: ",distancia)
	return distancia
	"""if (lat1 == 0 or lat2 == 0 or lon1 == 0 or lon2 == 0 ):
		distancia = 0
		return distancia
		
	R = 6371  # Earth radius in km
	dlat = math.radians(lat2 - lat1)
	dlon = math.radians(lon2 - lon1)
	a = (math.sin(dlat / 2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon / 2)**2)
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	distancia = round(R * c, 2)
	return distancia
"""

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
def get_latitud():
	if os.path.isfile("/home/orangepi/Documents/gps.txt"):
		with open("/home/orangepi/Documents/gps.txt",'r') as file:
			filedata=file.read()
			file.close()
		if ("Latitud" in filedata): 	
			latitud=(filedata[filedata.index("Latitud:")+8:filedata.index(",",filedata.index("Latitud:"))])
			return latitud
		return 0
def get_km():
	if os.path.isfile("/home/orangepi/Documents/km.txt"):
		with open("/home/orangepi/Documents/km.txt",'r') as file:
			filedata=file.read()
			file.close()
		km=filedata
		print ("KMP", km)
		return km
	file = open("/home/orangepi/Documents/km.txt","w")
	file.write("0")	
	file.close
def get_longitud():
	if os.path.isfile("/home/orangepi/Documents/gps.txt"):
		with open("/home/orangepi/Documents/gps.txt",'r') as file:
			filedata=file.read()
			file.close()
		if ("Latitud" in filedata): 
			longitud=(filedata[filedata.index("Longitud: ")+10:filedata.index(",",filedata.index("Longitud: "))])
			return longitud
		return 0		
def get_gps():	
	global datagps
	global calidadgps	
	if (gps.isOpen()==False):
		print("Puerto cerrado reintentando dentro de 5 segundos")
		open_gps()
		
		return
	line = "Datos gps"
	while True:
		try:
			
			line = gps.readline().decode("ascii", errors = 'replace').strip()
			print(line)
			if ("GGA" in line):
				msg=pynmea2.parse(line)
				hdop=msg.horizontal_dil
				calidad=msg.gps_qual
				print("Calidad gps ",hdop, calidad)
				if (float(calidad)>0 and float(hdop)<2):
					calidadgps = float(hdop)
				else:
					calidadgps = 1000
				print ("Exactitud gps: ",calidadgps)
			if (calidadgps>2):
				print("GPS Poco Preciso")
			if (line.startswith('$GPRMC') and calidadgps<=2):
				print("Getting coordinates")
				print(line)
				resp = pynmea2.parse(line)
				latitud_decimal = resp.latitude
				longitud_decimal = resp.longitude
				velocidad_n=resp.spd_over_grnd
				velocidad = float(velocidad_n) * 1.852 if velocidad_n else 0.0
				latitud_previa=get_latitud()
				print(latitud_previa)
				longitud_previa=get_longitud()
				print(longitud_previa)
				km_previo=get_km()
				print(km_previo)
				km_recorrido=calcular_distancia(latitud_decimal,longitud_decimal,float(latitud_previa),float(longitud_previa))
				print(km_recorrido)
				if (km_recorrido>=5 and km_recorrido<70 and velocidad>2):
					km_acumulado = float(km_previo) + float(km_recorrido)
					
				else:
					km_acumulado = float(km_previo)
				print(km_acumulado)
				print(str(latitud_decimal) + ", "+str(longitud_decimal))
				print(velocidad)
				with open("/home/orangepi/Documents/gps.txt","w") as file :	
					file.write("Latitud:"+str(latitud_decimal)+",Longitud: "+str(longitud_decimal)+",Velocidad: "+str(velocidad))	
				if (float(km_acumulado)>0):
					with open("/home/orangepi/Documents/km.txt","w") as file :
						print("Escribe en archivo ",str(km_acumulado))
						file.write(str(km_acumulado))
				
			if (line.startswith('$GNGLL') and calidadgps<=2):
				while ("$GNVTG" not in line):
					sleep(0.05)	
					myData=gps.readline()
					line = line + gps.readline().decode("ascii", errors = 'replace').strip()
									
				print("Getting coordinates")
				print(line)
				index1=line.index("$GNGLL")+7
				index2=line.index(",",index1)
				index3=line.index(",",index2+1)
				index4=line.index(",",index3+1)
				index5=line.index(",",index4+1)
				latitud=line[index1:index2]
				latitud_t=line[index2+1:index3]
				longitud=line[index3+1:index4]
				longitud_t=line[index4+1:index5]
				latitud_dms=get_coordenadas_dms(latitud + latitud_t, 1)
				longitud_dms=get_coordenadas_dms(longitud + longitud_t, 2)
				if not latitud_dms:	
					print("Datos latitud gps invalidos")
					threading.Timer(2.0,get_gps).start()
					return
				else:
					latitud_decimal=dms_a_decimal(latitud_dms[0],latitud_dms[1],latitud_dms[2], latitud_dms[3])
					print(latitud_decimal)
				if not longitud_dms:
					print("Datos longitud gps invalidos")
					threading.Timer(2.0,get_gps).start()
					return
				else:
					longitud_decimal=dms_a_decimal(longitud_dms[0],longitud_dms[1],longitud_dms[2], longitud_dms[3])
					print(longitud_decimal)
				index2=line.index("$GNVTG")
				index3=line.index("N",index2+6)
				index4=line.index(",",index3+2)	
				velocidad=line[index3+2:index4]
				

				latitud_previa=get_latitud()
				print("Latitud previa: " ,latitud_previa)
				
				longitud_previa=get_longitud()
				print("Longitud previa ",longitud_previa)
				km_previo=get_km()
				print("KM PRevio ",km_previo)
				km_recorrido=calcular_distancia(latitud_decimal,longitud_decimal,float(latitud_previa),float(longitud_previa))
				print("KMRecorrido",km_recorrido)
				if (km_recorrido>=5 and km_recorrido<70 and float(velocidad)>2):
					km_acumulado = float(km_previo) + float(km_recorrido)
					
				else:
					km_acumulado = float(km_previo)
				print(km_acumulado)
				print("KM ACUMU", km_acumulado)

				print(line[index3+2:index4])
				with open("/home/orangepi/Documents/gps.txt","w") as file :	
					file.write("Latitud:"+str(latitud_decimal)+",Longitud: "+str(longitud_decimal)+",Velocidad: "+velocidad)	
				
				if (float(km_acumulado)>4):
					with open("/home/orangepi/Documents/km.txt","w") as file :
						print("Escribe en archivo ",str(km_acumulado))
						file.write(str(km_acumulado))	
					
				
		except pynmea2.ParseError:
			print("Pynmea2 error")
			continue
		except ValueError as e:
			print(f"Caught an error: {e}")
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

