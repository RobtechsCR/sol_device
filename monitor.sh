#!/bin/bash
# Muestra el estado, la temperatura y los ultimos mensajes de cada servicio.
# Redibuja la pantalla cada 5 segundos. Ctrl+C para salir.
#
# Uso:
#   sudo bash monitor.sh
#   sudo bash monitor.sh 5

INTERVALO="${1:-5}"
LINEAS=3
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

if ! [[ "$INTERVALO" =~ ^[0-9]+$ ]] || [ "$INTERVALO" -lt 1 ]; then
	echo "El intervalo debe ser un numero de segundos."
	exit 1
fi

salir() {
	printf '\nMonitoreo cerrado.\n'
	exit 0
}
trap salir INT TERM

acortar() {
	local ancho="${COLUMNS:-100}"
	if [ "$ancho" -gt 4 ]; then
		ancho=$((ancho - 2))
	fi
	cut -c1-"$ancho"
}

mostrar_temperaturas() {
	local resumen
	echo "Temperaturas"
	if ! command -v sensors >/dev/null 2>&1; then
		echo "  sensors no esta instalado"
		return
	fi
	resumen="$(sensors 2>/dev/null | awk '
		$1 ~ /^temp[0-9]+:/ && nombre != "" {
			printf "%s %s  ", nombre, $2
			next
		}
		/^[^ \t]/ && $0 !~ /^Adapter:/ {
			nombre = $1
			sub(/:$/, "", nombre)
			sub(/_thermal.*/, "", nombre)
			sub(/-virtual.*/, "", nombre)
		}
	')"
	if [ -z "$resumen" ]; then
		echo "  sin lecturas"
	else
		printf '  %s\n' "$resumen"
	fi
}

mostrar_estado() {
	local servicio estado linea=""
	for servicio in "${SERVICIOS[@]}"; do
		estado="$(systemctl is-active "${servicio}.service" 2>/dev/null || true)"
		if [ -z "$estado" ]; then
			estado="desconocido"
		fi
		linea="${linea}  ${servicio}:${estado}"
	done
	printf 'Estado%s\n' "$linea"
}

mostrar_servicio() {
	local servicio="$1"
	local texto
	echo "[${servicio}]"
	texto="$(journalctl -u "${servicio}.service" -n 80 -o cat --no-pager 2>/dev/null || true)"
	if [ "$servicio" = "gps" ]; then
		texto="$(printf '%s\n' "$texto" | grep -vE '^\$[A-Z]{4,},' || true)"
	fi
	texto="$(printf '%s\n' "$texto" | sed '/^[[:space:]]*$/d' | tail -n "$LINEAS")"
	if [ -z "$texto" ]; then
		echo "  sin mensajes"
		return
	fi
	printf '%s\n' "$texto" | sed 's/^/  /' | acortar
}

pintar() {
	printf '\033[H\033[2J'
	echo "==== $(date '+%Y-%m-%d %H:%M:%S') ====  cada ${INTERVALO}s  Ctrl+C para salir"
	mostrar_estado
	mostrar_temperaturas
	echo
	for servicio in "${SERVICIOS[@]}"; do
		mostrar_servicio "$servicio"
	done
}

while true; do
	pintar
	sleep "$INTERVALO"
done
