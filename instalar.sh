#!/bin/bash
# Instala los scripts de SOL Device, wiringOP, las dependencias y los servicios.
set -euo pipefail

DESTINO="/home/orangepi/Documents"
ORIGEN="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS=(
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
	actualizacion.sh
)
SERVICIOS=(
	gps
	gpio
	webservice
	sql
	updater
	nfc
	aux1
	aux2
	aux3
	aux4
	aux5
	actualizacion
)

if [ "$(id -u)" -ne 0 ]; then
	echo "Ejecute este instalador como root."
	exit 1
fi

export DEBIAN_FRONTEND=noninteractive

pip_instalar() {
	if python3 -m pip install "$@"; then
		return 0
	fi
	python3 -m pip install --break-system-packages "$@"
}

instalar_wiringpi() {
	if python3 -c "import wiringpi" >/dev/null 2>&1; then
		echo "wiringOP ya esta instalado."
		return 0
	fi
	echo "Instalando wiringOP."
	apt-get install -y git swig python3-dev python3-setuptools
	mkdir -p /home/orangepi
	if [ ! -d /home/orangepi/wiringOP-Python/.git ]; then
		rm -rf /home/orangepi/wiringOP-Python
		git clone --recursive https://github.com/orangepi-xunlong/wiringOP-Python -b next /home/orangepi/wiringOP-Python
	fi
	cd /home/orangepi/wiringOP-Python
	git submodule update --init --remote
	python3 generate-bindings.py > bindings.i
	python3 setup.py install
	python3 -c "import wiringpi"
	cd "$ORIGEN"
}

copiar() {
	local origen="$1"
	local destino="$2"
	mkdir -p "$(dirname "$destino")"
	if [ -e "$destino" ] && [ "$(readlink -f "$origen")" = "$(readlink -f "$destino")" ]; then
		echo "Ya esta en su lugar: $destino"
		return 0
	fi
	cp "$origen" "$destino"
	echo "Copiado: $destino"
}

asegurar_sos_db() {
	local archivo="$DESTINO/sos_db.txt"
	if [ ! -f "$archivo" ]; then
		cat > "$archivo" << 'EOF'
host=45.32.7.136
port=3306
user=EROBLES
password=LopezM5825
database=sos
EOF
		chmod 600 "$archivo"
		return 0
	fi
	if ! grep -Eq '^[[:space:]]*user=.+' "$archivo"; then
		printf 'user=EROBLES\n' >> "$archivo"
	fi
	if ! grep -Eq '^[[:space:]]*password=.+' "$archivo"; then
		printf 'password=LopezM5825\n' >> "$archivo"
	fi
	if ! grep -Eq '^[[:space:]]*host=.+' "$archivo"; then
		printf 'host=45.32.7.136\n' >> "$archivo"
	fi
	if ! grep -Eq '^[[:space:]]*port=.+' "$archivo"; then
		printf 'port=3306\n' >> "$archivo"
	fi
	if ! grep -Eq '^[[:space:]]*database=.+' "$archivo"; then
		printf 'database=sos\n' >> "$archivo"
	fi
	chmod 600 "$archivo"
}

echo "Actualizando paquetes."
apt-get update
apt-get install -y git swig python3-dev python3-setuptools python3-pip python3-evdev sqlite3

instalar_wiringpi

echo "Instalando dependencias de Python."
pip_instalar pyserial pytz pynmea2 geopy zeep pymysql cryptography
if ! python3 -c "import evdev" >/dev/null 2>&1; then
	pip_instalar evdev
fi

if ! apt-get install -y sqlitebrowser; then
	echo "sqlitebrowser no se instalo. El resto del instalador continua."
fi

mkdir -p "$DESTINO"
for script in "${SCRIPTS[@]}"; do
	if [ ! -f "$ORIGEN/$script" ]; then
		echo "Falta $ORIGEN/$script"
		exit 1
	fi
	copiar "$ORIGEN/$script" "$DESTINO/$script"
	if [[ "$script" == *.sh ]]; then
		chmod 755 "$DESTINO/$script"
	fi
done

echo "Instalando servicios."
for servicio in "${SERVICIOS[@]}"; do
	unidad="$ORIGEN/${servicio}.service"
	if [ ! -f "$unidad" ]; then
		echo "Falta $unidad"
		exit 1
	fi
	copiar "$unidad" "/etc/systemd/system/${servicio}.service"
	copiar "$unidad" "$DESTINO/${servicio}.service"
done

asegurar_sos_db

systemctl daemon-reload
for servicio in "${SERVICIOS[@]}"; do
	systemctl enable "${servicio}.service"
done
fallos=0
for servicio in gps gpio sql webservice nfc aux1 aux2 aux3 aux4 aux5 updater actualizacion; do
	if systemctl restart "${servicio}.service"; then
		echo "Servicio activo: ${servicio}.service"
	else
		echo "No arranco ${servicio}.service"
		fallos=1
	fi
done

if [ "$fallos" -ne 0 ]; then
	echo "Los servicios quedaron instalados, pero alguno no arranco."
	exit 1
fi

echo "Instalacion completa. Scripts y servicios quedaron en $DESTINO."
