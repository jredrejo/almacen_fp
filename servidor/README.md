apt install -yf uwsgi-plugin-python3 uwsgi redis-server nginx-full

En producción: python manage.py collectstatic

sockets en /tmp/almacen.sock

/etc/nginx/sites-available/almacen.conf



sudo systemctl disable uwsgi

cp  servidor/almacen-uwsgi.service   /etc/systemd/system/almacen-uwsgi.service
sudo systemctl daemon-reload
sudo systemctl enable almacen-uwsgi
sudo systemctl start almacen-uwsgi



sudo mv servidor/almacen.conf /etc/nginx/sites-available/almacen_fp
sudo ln -sf /etc/nginx/sites-available/almacen_fp /etc/nginx/sites-enabled/

certbot certonly --manual --preferred-challenges=dns -d fp.santiagoapostol.net

