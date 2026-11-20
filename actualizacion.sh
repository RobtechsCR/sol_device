#!/bin/bash
# Descarga los scripts y los servicios desde el repositorio y reinicia los que cambiaron.
# No toca gps.txt, los contadores, sos_db.txt ni las demas bases de datos.
#
# Uso:
#   sudo bash actualizacion.sh
#
# La primera ejecucion deja actualizacion.service activo. Despues revisa el
# repositorio cada 5 minutos y aplica los cambios sola.

set -u

REPO="https://github.com/RobtechsCR/sol_device/raw/main"
DESTINO="/home/orangepi/Documents"
ARCHIVOS=(
	gps.py
	gpio.py
	sql.py
	webservice.py
	updater.py
	nfc.py
	data_device.py
	aux1.py
	aux2.py
	aux3.py
	aux4.py
	aux5.py
	gps.service
	gpio.service
	sql.service
	webservice.service
	updater.service
	nfc.service
	aux1.service
	aux2.service
	aux3.service
	aux4.service
	aux5.service
	actualizacion.sh
	actualizacion.service
	check.sh
	install.sh
	services.sh
	monitor.sh
)
SERVICIOS=(
	gps
	gpio
	sql
	webservice
	nfc
	aux1
	aux2
	aux3
	aux4
	aux5
	updater
)

if [ "$(id -u)" -ne 0 ]; then
	echo "Ejecute este actualizador como root."
	exit 1
fi

mkdir -p "$DESTINO"
fallos=0
cambiados=()

descargar() {
	local url="$1"
	local destino="$2"
	local intento
	for intento in 1 2 3; do
		if curl -fsSL --connect-timeout 20 --max-time 90 -o "$destino" "$url"; then
			return 0
		fi
		if curl -4 --noproxy '*' -fsSL --connect-timeout 20 --max-time 90 -o "$destino" "$url"; then
			return 0
		fi
		sleep 2
	done
	return 1
}

for archivo in "${ARCHIVOS[@]}"; do
	temporal="$(mktemp)"
	if ! descargar "$REPO/$archivo" "$temporal"; then
		echo "No se pudo descargar $archivo"
		rm -f "$temporal"
		fallos=1
		continue
	fi
	if [ ! -s "$temporal" ]; then
		echo "La descarga de $archivo llego vacia"
		rm -f "$temporal"
		fallos=1
		continue
	fi
	destino="$DESTINO/$archivo"
	if [ -f "$destino" ] && cmp -s "$temporal" "$destino"; then
		rm -f "$temporal"
		continue
	fi
	mv "$temporal" "$destino"
	if [[ "$archivo" == *.sh ]]; then
		chmod 755 "$destino"
	fi
	echo "Actualizado: $archivo"
	cambiados+=("$archivo")
done

for servicio in gps gpio sql webservice updater nfc aux1 aux2 aux3 aux4 aux5 actualizacion; do
	unidad="$DESTINO/${servicio}.service"
	if [ -f "$unidad" ]; then
		cp "$unidad" "/etc/systemd/system/${servicio}.service"
	fi
done
systemctl daemon-reload
if ! systemctl enable actualizacion.service; then
	echo "No se pudo habilitar actualizacion.service"
	fallos=1
fi

for servicio in "${SERVICIOS[@]}"; do
	if [ "$servicio" = "updater" ]; then
		continue
	fi
	cambio_py=0
	cambio_unidad=0
	for archivo in "${cambiados[@]}"; do
		if [ "$archivo" = "${servicio}.py" ]; then
			cambio_py=1
		fi
		if [ "$archivo" = "${servicio}.service" ]; then
			cambio_unidad=1
		fi
	done
	if [ "$cambio_py" -eq 0 ] && [ "$cambio_unidad" -eq 0 ]; then
		continue
	fi
	if systemctl restart "${servicio}.service"; then
		echo "Servicio reiniciado: ${servicio}.service"
	else
		echo "No arranco ${servicio}.service"
		fallos=1
	fi
done
if [ "${#cambiados[@]}" -gt 0 ]; then
	for archivo in "${cambiados[@]}"; do
		if [ "$archivo" = "updater.py" ]; then
			echo "updater.py quedo actualizado y no se reinicio, para que no reemplace los scripts desde el servidor SOAP."
		fi
	done
fi

unidad_cambio=0
if [ "${#cambiados[@]}" -gt 0 ]; then
	for archivo in "${cambiados[@]}"; do
		if [ "$archivo" = "actualizacion.service" ]; then
			unidad_cambio=1
		fi
	done
fi
if systemctl is-active --quiet actualizacion.service; then
	if [ "$unidad_cambio" -eq 1 ]; then
		echo "Reiniciando actualizacion.service"
		systemctl restart actualizacion.service
	fi
else
	if systemctl start actualizacion.service; then
		echo "actualizacion.service quedo activo y revisa el repositorio cada 5 minutos."
	else
		echo "No arranco actualizacion.service"
		fallos=1
	fi
fi

if [ "$fallos" -ne 0 ]; then
	echo "La actualizacion termino con errores."
	exit 1
fi

if [ "${#cambiados[@]}" -eq 0 ]; then
	echo "Sin actualizaciones."
else
	echo "Actualizacion completa."
fi
