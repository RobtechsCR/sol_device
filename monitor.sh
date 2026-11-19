#!/bin/bash
# Muestra el estado y los mensajes nuevos de todos los servicios.
# Se actualiza cada 5 segundos hasta que se cierre con Ctrl+C.
#
# Uso:
#   sudo bash monitor.sh
#   sudo bash monitor.sh 5

INTERVALO="${1:-5}"
SERVICIOS=(
	gps
	gpio
	sql
	webservice
	updater
	nfc
	aux1
	aux2
	aux3
	aux4
	aux5
)
UNIDADES=()
for servicio in "${SERVICIOS[@]}"; do
	UNIDADES+=(-u "${servicio}.service")
done

if ! [[ "$INTERVALO" =~ ^[0-9]+$ ]] || [ "$INTERVALO" -lt 1 ]; then
	echo "El intervalo debe ser un numero de segundos."
	exit 1
fi

cursor=""

mostrar_estado() {
	echo "==== $(date '+%Y-%m-%d %H:%M:%S') ===="
	for servicio in "${SERVICIOS[@]}"; do
		estado="$(systemctl is-active "${servicio}.service" 2>/dev/null || true)"
		if [ -z "$estado" ]; then
			estado="desconocido"
		fi
		printf '  %-18s %s\n' "${servicio}.service" "$estado"
	done
}

leer_journal() {
	local salida nueva
	if [ -n "$cursor" ]; then
		salida="$(journalctl --after-cursor="$cursor" "${UNIDADES[@]}" -o short-iso --no-pager --show-cursor 2>&1 || true)"
	else
		salida="$(journalctl "${UNIDADES[@]}" -n 40 -o short-iso --no-pager --show-cursor 2>&1 || true)"
	fi
	nueva="$(printf '%s\n' "$salida" | sed -n 's/^-- cursor: //p' | tail -n 1)"
	if [ -n "$nueva" ]; then
		cursor="$nueva"
	fi
	printf '%s\n' "$salida" | sed '/^-- cursor: /d'
}

salir() {
	echo
	echo "Monitoreo cerrado."
	exit 0
}
trap salir INT TERM

echo "Monitoreando todos los servicios cada ${INTERVALO} segundos. Ctrl+C para salir."
mostrar_estado
echo "---- ultimos mensajes ----"
leer_journal

while true; do
	sleep "$INTERVALO"
	echo
	mostrar_estado
	mensajes="$(leer_journal)"
	if [ -n "$(printf '%s' "$mensajes" | tr -d '[:space:]')" ]; then
		echo "---- mensajes nuevos ----"
		printf '%s\n' "$mensajes"
	else
		echo "---- sin mensajes nuevos ----"
	fi
done
