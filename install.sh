cd /
sudo apt update
sudo apt install -y git swig python3-dev python3-setuptools
cd /home/orangepi
git clone --recursive https://github.com/orangepi-xunlong/wiringOP-Python -b next
cd wiringOP-Python
git submodule update --init --remote
python3 generate-bindings.py > bindings.i
sudo python3 setup.py install
sudo apt install python3-pip
sudo pip3 install pyserial
sudo pip3 install pytz
sudo pip3 install pynmea2
sudo pip3 install geopy
sudo python3 -m pip install zeep
sudo apt install -y python3-evdev
sudo pip3 install evdev
sudo pip3 install pymysql cryptography
if [ ! -f /home/orangepi/Documents/sos_db.txt ]; then
sudo mkdir -p /home/orangepi/Documents
sudo tee /home/orangepi/Documents/sos_db.txt > /dev/null << 'EOF'
host=45.32.7.136
port=3306
user=
password=
database=sos
EOF
fi
sudo apt install sqlite3
sudo apt-get install sqlitebrowser
