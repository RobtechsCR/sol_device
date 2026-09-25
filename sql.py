import pytz
import datetime
import threading
from time import sleep
import uuid
import os
import sqlite3

con = sqlite3.connect("/home/orangepi/Documents/backup.db")
cur = con.cursor()
cur.execute("CREATE TABLE if not exists monitoreo(Fecha DATETIME not null,DeviceId VARCHAR(50) not null, latitud FLOAT not null, longitud FLOAT not null, Velocidad FLOAT not null, GeneralEntradasPe INTEGER not null, GeneralSalidasPe INTEGER not null, GeneralEntradasPs INTEGER not null, GeneralSalidasPs INTEGER not null, SrvOnline VARCHAR(50) not null)")
timezone=pytz.timezone("America/Costa_Rica")

def server_alive():
	try:
		if os.path.isfile("/home/orangepi/Documents/serverstatus.txt"):
			with open("/home/orangepi/Documents/serverstatus.txt",'r') as file:
				filedata=file.read()
			file.close()	
			return str(filedata)
			threading.Timer(10.0,server_alive).start()
	except:
		
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
def save_data_sql():
	try:
		deviceid=device_id()
		entradas=get_entradas_pe()
		salidas=get_salidas_pe()
		entradas_ps=get_entradas_ps()
		salidas_ps=get_salidas_ps()
		#latitud=get_latitud()
		#longitud=get_longitud()
		#velocidad=get_velocidad()
		latitud='0'
		longitud='0'
		velocidad='0'
		isOnline=server_alive()
		if(len(isOnline) and isOnline.find("True")>0):
			isOnline="True"
		else:
			isOnline="False"
		now=datetime.datetime.now(timezone)
		fecha=now.strftime("%Y-%m-%d %H:%M:%S")
		con = sqlite3.connect("/home/orangepi/Documents/backup.db")
		cur = con.cursor()
		sentencia ="insert into monitoreo (Fecha, DeviceId, latitud, longitud, velocidad, GeneralEntradasPe, GeneralSalidasPe, GeneralEntradasPs, GeneralSalidasPs, SrvOnline) values ('"+fecha+"','"+str(deviceid)+"','"+str(latitud)+"','"+str(longitud)+"','"+str(velocidad)+"','"+str(entradas)+"','"+str(salidas)+"','"+str(entradas_ps)+"','"+str(salidas_ps)+"','"+str(isOnline)+"')"
		print(sentencia)
		cur.execute(sentencia)
		con.commit()
		
		threading.Timer(30.0,save_data_sql).start()
	except Exception as e:
		threading.Timer(30.0,save_data_sql).start()
		print("Error al insertar dato ")
		print(e)
def delete_data_sql():
	try:
		con = sqlite3.connect("/home/orangepi/Documents/backup.db")
		cur = con.cursor()
		sentencia ="delete from monitoreo where Fecha < DATETIME('now','-180 day')"
		print(sentencia)
		cur.execute(sentencia)
		con.commit()
		
	except Exception as e:
		
		print("Error al borrar dato ")
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
delete_data_sql()
threading.Timer(5.0,server_alive).start()
threading.Timer(2.0,save_data_sql).start()
