sudo apt install -y mosquitto
sudo cp  rfid.conf /etc/mosquitto/conf.d/
sudo cp aclfile /etc/mosquitto
sudo touch  /etc/mosquitto/passwd
sudo chown mosquitto /etc/mosquitto/passwd
sudo chown mosquitto /etc/mosquitto/aclfile
sudo mosquitto_passwd /etc/mosquitto/aclfile rfid
sudo systemctl restart mosquitto

