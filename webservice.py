import zeep
import pytz
import datetime
import threading
from time import sleep
import uuid
import os
import subprocess

wsdl = 'http://45.32.7.136:8080/WebServiceSOLV3-3/SolSrv?wsdl'
transport = zeep.Transport(timeout=5, operation_timeout=3)
client = zeep.Client(wsdl=wsdl, transport=transport)
timezone=pytz.timezone("America/Costa_Rica")
def getFecha():
		result=client.service.getFechaSrv()
		file = open("/home/orangepi/Documents/fecha_srv.txt","w")
		file.write(str(result))
		file.close
		command2="sudo timedatectl set-timezone America/Costa_Rica"	
		command = f"sudo date -s \"{result}\""
		try:
			subprocess.run(command2, shell=True, check=True)
			subprocess.run(command, shell=True, check=True)
			print("Fecha Actualizada Exitosamente")
			print(command)
			return str(result)
		except subprocess.CalledProcessError as e:
			print(e)

def server_alive():
	try:
		
		now=datetime.datetime.now(timezone)
		result=client.service.checkConnection()
		print(result)
		file = open("/home/orangepi/Documents/serverstatus.txt","w")
		file.write(str(now) + " estado "+str(result)+"\n")
		file.close
		threading.Timer(10.0,server_alive).start()
	except:
		try:
			if (now == None):
				now=datetime.datetime.now()
			file.write(str(now) + " estado SIN CONEXION")
			file.close()
			threading.Timer(10.0,server_alive).start()
		except:
			now=datetime.datetime.now()
		file = open("/home/orangepi/Documents/serverstatus.txt","w")
		print("SIN CONEXION")
		file.write(str(now) + " estado SIN CONEXION")
		file.close
		threading.Timer(10.0,server_alive).start()
def device_id():
	if os.path.isfile("/home/orangepi/Documents/device_id.txt"):
		with open("/home/orangepi/Documents/device_id.txt",'r') as file:
			filedata=file.read()
		file.close()	
		return str(filedata)
	else:
		id=str(uuid.uuid4())	
		filedata = id[-8:]
		with open("/home/orangepi/Documents/device_id.txt",'w') as file:
			file.write(filedata)
		file.close()
		return str(filedata)
def getKM():
	if os.path.isfile("/home/orangepi/Documents/km.txt"):
		with open("/home/orangepi/Documents/km.txt",'r') as file:
			filedata=file.read()
		file.close()	
		return str(filedata)
	
def getUnidad():
	if os.path.isfile("/home/orangepi/Documents/device_id.txt"):
		with open("/home/orangepi/Documents/device_id.txt",'r') as file:
			filedata=file.read()
		file.close()
		result=client.service.getUnidad(str(filedata))
		
		file = open("/home/orangepi/Documents/unidad_srv.txt","w")
		file.write(str(result))
		file.close	
		return str(result)
	else:
		device_id()
		getUnidad()
def send_data_srv():
	try:
		getUnidad()
		deviceid=device_id()
		entradas=get_entradas_pe()
		salidas=get_salidas_pe()
		entradas_ps=get_entradas_ps()
		salidas_ps=get_salidas_ps()
		latitud=get_latitud()
		longitud=get_longitud()
		velocidad=get_velocidad()
		km=getKM()
		now=datetime.datetime.now(timezone)
		result=client.service.insertarTransmisionConKM(now,deviceid,latitud,longitud,velocidad,entradas,salidas,entradas_ps,salidas_ps,km)
		#result=client.service.insertarTransmision('asdasd','adasd','adasd','adasd','adasd','adasd','adasd')
		print(result)
		threading.Timer(15.0,send_data_srv).start()
	except Exception as e:
		threading.Timer(15.0,send_data_srv).start()
		print(e)
	
def get_salidas_pe():
	if os.path.isfile("/home/orangepi/Documents/data_barras_entradas_pe.txt"):
		with open("/home/orangepi/Documents/data_barras_entradas_pe.txt",'r') as file:
			filedata=file.read()
		total_marcas_sal=int(filedata[filedata.index("GeneralSalidasPe: ")+18:filedata.index("$$",filedata.index("GeneralSalidasPe: "))])
		return total_marcas_sal
def get_salidas_ps():
	if os.path.isfile("/home/orangepi/Documents/data_barras_entradas_ps.txt"):
		with open("/home/orangepi/Documents/data_barras_entradas_ps.txt",'r') as file:
			filedata=file.read()
		total_marcas_sal_ps=int(filedata[filedata.index("GeneralSalidasPs: ")+18:filedata.index("$$",filedata.index("GeneralSalidasPs: "))])
		return total_marcas_sal_ps
def get_entradas_pe():
	if os.path.isfile("/home/orangepi/Documents/data_barras_entradas_pe.txt"):
		with open("/home/orangepi/Documents/data_barras_entradas_pe.txt",'r') as file:
			filedata=file.read()
		total_marcas_ent=int(filedata[filedata.index("GeneralEntradasPe: ")+19:filedata.index("$$",filedata.index("GeneralEntradasPe: "))])
		return total_marcas_ent
def get_entradas_ps():
	if os.path.isfile("/home/orangepi/Documents/data_barras_entradas_ps.txt"):
		with open("/home/orangepi/Documents/data_barras_entradas_ps.txt",'r') as file:
			filedata=file.read()
		total_marcas_ent_ps=int(filedata[filedata.index("GeneralEntradasPs: ")+19:filedata.index("$$",filedata.index("GeneralEntradasPs: "))])
		return total_marcas_ent_ps
def get_latitud():
	if os.path.isfile("/home/orangepi/Documents/gps.txt"):
		with open("/home/orangepi/Documents/gps.txt",'r') as file:
			filedata=file.read()
		latitud=(filedata[filedata.index("Latitud:")+8:filedata.index(",",filedata.index("Latitud:"))])
		return latitud
def get_longitud():
	if os.path.isfile("/home/orangepi/Documents/gps.txt"):
		with open("/home/orangepi/Documents/gps.txt",'r') as file:
			filedata=file.read()
		longitud=(filedata[filedata.index("Longitud: ")+10:filedata.index(",",filedata.index("Longitud: "))])
		return longitud

def get_velocidad():
	if os.path.isfile("/home/orangepi/Documents/gps.txt"):
		with open("/home/orangepi/Documents/gps.txt",'r') as file:
			filedata=file.read()
		velocidad=float(filedata[filedata.index("Velocidad: ")+11:])
		print(velocidad)
		return velocidad


print("Device Id:" + device_id())
print("Unidad Sol:" + getUnidad())
print("Unidad Sol:" + getFecha())
threading.Timer(5.0,server_alive).start()
threading.Timer(2.0,send_data_srv).start()
