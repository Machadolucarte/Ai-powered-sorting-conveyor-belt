import serial
import time

ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
time.sleep(2)
ser.write(b"S180\n")
print("Comando enviado")
