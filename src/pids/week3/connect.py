import time
from robomaster import conn
from MyQR import myqr
from PIL import Image

QRCODE_NAME = "qrcode.png"
WIFI_SSID = "<wifi-ssid>"
WIFI_PASSWD = "<wifi-passwd>"
SERIAL_NUMBER = "<robot-serial-number>"

if __name__ == '__main__':

    # Manually indicate the IP of your computer if it is not found automatically
    # robomaster.config.LOCAL_IP_STR = "XXX.XXX.XXX.XXX"
    
    # Write serial number to txt
    with open('serial_number.txt', 'w') as f:
        f.write(SERIAL_NUMBER)

    # Create QR to connect the robot to your Wi-Fi
    helper = conn.ConnectionHelper()
    info = helper.build_qrcode_string(ssid=WIFI_SSID, password=WIFI_PASSWD)
    myqr.run(words=info)

    # Show the QR
    img = Image.open(QRCODE_NAME)
    img.show()

    # Wait for connection (scan the qr with the robot)
    print("Waiting for connections...")
    time.sleep(5)
    if helper.wait_for_connection():
        print("Connected!")
    else:
        print("Connect failed!")
