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

# PARA ACTUALIZAR GPS
def getVersionGPS():
	try :
		result=client.service.getGpsV()
		checkVersionGPS(float(result))
		sleep(10)
		getVersionGPIO()
		sleep(10)
		getVersionWb()
		sleep(10)
		getVersionSQL()
		sleep(10)
		getVersionAux1()
		sleep(10)
		getVersionAux2()
		sleep(10)
		getVersionAux3()
		sleep(10)
		getVersionAux4()
		sleep(10)
		getVersionAux5()
		threading.Timer(180.0,getVersionGPS).start()
	except Exception as e:
		getVersionGPIO()
		getVersionWb()
		getVersionSQL()
		getVersionAux1()
		getVersionAux2()
		getVersionAux3()
		getVersionAux4()
		getVersionAux5()
		threading.Timer(180.0,getVersionGPS).start()
		print(e)


def checkVersionGPS(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/version_gps.txt"):
			with open("/home/orangepi/Documents/version_gps.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de gps encontrada")
					getScriptGPS(version_srv)
					with open("/home/orangepi/Documents/version_gps.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart gps.service')
						

				else:
					print ("GPS actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_gps.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptGPS(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/gps.py"):
			result=client.service.getGpsScript()
			with open("/home/orangepi/Documents/gps.py",'r') as file:
				print ("Aplicando actualizacion GPS")
				with open("/home/orangepi/Documents/gps.py",'w') as file:
					filedata=file.write(result)
					
				
			
		else:
			result=client.service.getGpsScript()
			with open("/home/orangepi/Documents/gps.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)


# PARA ACTUALIZAR GPIO
def getVersionGPIO():
	try:
		result=client.service.getGpioV()
		checkVersionGPIO(float(result))
	except Exception as e:
		print(e)

def checkVersionGPIO(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/version_gpio.txt"):
			with open("/home/orangepi/Documents/version_gpio.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de gpio encontrada")
					getScriptGPIO(version_srv)
					with open("/home/orangepi/Documents/version_gpio.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart gpio.service')
						

				else:
					print ("GPIO actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_gpio.txt",'w') as file:
				filedata=file.write(filedata)
				threading.Timer(60.0,getVersionGPIO).start()
	except Exception as e:
		print(e)

def getScriptGPIO(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/gpio.py"):
			result=client.service.getGpioScript()
			with open("/home/orangepi/Documents/gpio.py",'r') as file:
				print ("Aplicando actualizacion GPIO")
				with open("/home/orangepi/Documents/gpio.py",'w') as file:
					filedata=file.write(result)
					
				
			
		else:
			result=client.service.getGpioScript()
			with open("/home/orangepi/Documents/gpio.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)
# para webservice
def getVersionWb():
	try:
		result=client.service.getWbV()
		checkVersionWb(float(result))
	except Exception as e:
		print(e)

def checkVersionWb(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_wb.txt"):
			with open("/home/orangepi/Documents/version_wb.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de webservice encontrada")
					getScriptWb(version_srv)
					with open("/home/orangepi/Documents/version_wb.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart webservice.service')
						

				else:
					print ("Webservice actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_wb.txt",'w') as file:
				filedata=file.write(filedata)
				threading.Timer(60.0,getVersionWb).start()
	except Exception as e:
		print(e)

def getScriptWb(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/webservice.py"):
			result=client.service.getWbScript()
			with open("/home/orangepi/Documents/webservice.py",'r') as file:
				print ("Aplicando actualizacion WebService")
				with open("/home/orangepi/Documents/webservice.py",'w') as file:
					filedata=file.write(result)
					
				
			
		else:
			result=client.service.getWbScript()
			with open("/home/orangepi/Documents/webservice.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)


# PARA ACTUALIZAR SQL
def getVersionSQL():
	try:
		result=client.service.getSqlV()
		checkVersionSQL(float(result))
	except Exception as e:
		print(e)	

def checkVersionSQL(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_sql.txt"):
			with open("/home/orangepi/Documents/version_sql.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de sql encontrada")
					getScriptSQL(version_srv)
					with open("/home/orangepi/Documents/version_sql.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart sql.service')
						

				else:
					print ("SQL actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_sql.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptSQL(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/sql.py"):
			result=client.service.getSqlScript()
			with open("/home/orangepi/Documents/sql.py",'r') as file:
				print ("Aplicando actualizacion SQL")
				with open("/home/orangepi/Documents/sql.py",'w') as file:
					filedata=file.write(result)
					
				
			
		else:
			result=client.service.getSqlScript()
			with open("/home/orangepi/Documents/sql.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)

# PARA ACTUALIZAR AUX1
def getVersionAux1():
	try:
		result=client.service.getAux1V()
		checkVersionAux1(float(result))
	except Exception as e:
		print(e)	

def checkVersionAux1(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_aux1.txt"):
			with open("/home/orangepi/Documents/version_aux1.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de Auxiliar 1 encontrada")
					getScriptAux1(version_srv)
					with open("/home/orangepi/Documents/version_aux1.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart aux1.service')
						

				else:
					print ("Auxiliar 1 actualizado")

			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_aux1.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptAux1(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/aux1.py"):
			result=client.service.getAux1Script()
			with open("/home/orangepi/Documents/aux1.py",'r') as file:
				print ("Aplicando actualizacion Auxiliar 1")
				with open("/home/orangepi/Documents/aux1.py",'w') as file:
					filedata=file.write(result)
		else:
			result=client.service.getAux1Script()
			with open("/home/orangepi/Documents/aux1.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)

# PARA ACTUALIZAR AUX2
def getVersionAux2():
	try:
		result=client.service.getAux2V()
		checkVersionAux2(float(result))
	except Exception as e:
		print(e)	

def checkVersionAux2(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_aux2.txt"):
			with open("/home/orangepi/Documents/version_aux2.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de Auxiliar 2 encontrada")
					getScriptAux2(version_srv)
					with open("/home/orangepi/Documents/version_aux2.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart aux2.service')
						

				else:
					print ("Auxiliar 2 actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_aux2.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptAux2(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/aux2.py"):
			result=client.service.getAux2Script()
			with open("/home/orangepi/Documents/aux2.py",'r') as file:
				print ("Aplicando actualizacion Auxiliar 2")
				with open("/home/orangepi/Documents/aux2.py",'w') as file:
					filedata=file.write(result)
		else:
			result=client.service.getAux2Script()
			with open("/home/orangepi/Documents/aux2.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)


# PARA ACTUALIZAR AUX3
def getVersionAux3():
	try:
		result=client.service.getAux3V()
		checkVersionAux3(float(result))
	except Exception as e:
		print(e)	

def checkVersionAux3(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_aux3.txt"):
			with open("/home/orangepi/Documents/version_aux3.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de Auxiliar 3 encontrada")
					getScriptAux2(version_srv)
					with open("/home/orangepi/Documents/version_aux3.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart aux3.service')
						

				else:
					print ("Auxiliar 3 actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_aux3.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptAux3(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/aux3.py"):
			result=client.service.getAux3Script()
			with open("/home/orangepi/Documents/aux3.py",'r') as file:
				print ("Aplicando actualizacion Auxiliar 3")
				with open("/home/orangepi/Documents/aux3.py",'w') as file:
					filedata=file.write(result)
		else:
			result=client.service.getAux3Script()
			with open("/home/orangepi/Documents/aux3.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)


# PARA ACTUALIZAR AUX4
def getVersionAux4():
	try:
		result=client.service.getAux4V()
		checkVersionAux4(float(result))
	except Exception as e:
		print(e)	

def checkVersionAux4(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_aux4.txt"):
			with open("/home/orangepi/Documents/version_aux4.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de Auxiliar 4 encontrada")
					getScriptAux2(version_srv)
					with open("/home/orangepi/Documents/version_aux4.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart aux4.service')
						

				else:
					print ("Auxiliar 4 actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_aux4.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptAux4(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/aux4.py"):
			result=client.service.getAux4Script()
			with open("/home/orangepi/Documents/aux4.py",'r') as file:
				print ("Aplicando actualizacion Auxiliar 4")
				with open("/home/orangepi/Documents/aux4.py",'w') as file:
					filedata=file.write(result)
		else:
			result=client.service.getAux4Script()
			with open("/home/orangepi/Documents/aux4.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)


# PARA ACTUALIZAR AUX5
def getVersionAux5():
	try:
		result=client.service.getAux5V()
		checkVersionAux5(float(result))
	except Exception as e:
		print(e)	

def checkVersionAux5(version_srv):
	try: 
		if os.path.isfile("/home/orangepi/Documents/version_aux5.txt"):
			with open("/home/orangepi/Documents/version_aux5.txt",'r') as file:
				filedata=file.read()
				version_device=float(filedata)
				if (version_srv>version_device):
					print ("Nueva version de Auxiliar 5 encontrada")
					getScriptAux5(version_srv)
					with open("/home/orangepi/Documents/version_aux5.txt",'w') as file:
						filedata=file.write(str(version_srv))
						os.system('sudo systemctl restart aux5.service')
						

				else:
					print ("Auxiliar 5 actualizado")
					
			
		else:
			filedata = str(version_srv)
			with open("/home/orangepi/Documents/version_aux5.txt",'w') as file:
				filedata=file.write(filedata)
				
	except Exception as e:
		print(e)
def getScriptAux5(version_srv):
	try:
		if os.path.isfile("/home/orangepi/Documents/aux5.py"):
			result=client.service.getAux5Script()
			with open("/home/orangepi/Documents/aux5.py",'r') as file:
				print ("Aplicando actualizacion Auxiliar 5")
				with open("/home/orangepi/Documents/aux5.py",'w') as file:
					filedata=file.write(result)
		else:
			result=client.service.getAux5Script()
			with open("/home/orangepi/Documents/aux5.py",'w') as file:
				filedata=file.write(result)
	except Exception as e:
		print(e)

print("Updater online:")

threading.Timer(10.0,getVersionGPS).start()
