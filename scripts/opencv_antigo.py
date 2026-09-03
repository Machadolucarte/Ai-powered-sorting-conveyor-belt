from ultralytics import YOLO
import cv2 # type: ignore
import numpy as np
from pyfirmata2 import Arduino # type: ignore
import time
import threading
import subprocess
import re

def obter_ip_telefone() -> str:
    print("🔍 Procurando o IP do celular na rede USB...")
    try:
        # WSL: Adicionado '.exe' para chamar o comando de rede do Windows por dentro do Linux
        output: str = subprocess.check_output("ipconfig.exe", shell=True, encoding="cp850")
        
        # Agora usando 'list' minúsculo (Padrão Python 3.9+)
        adaptadores: list[str] = output.split("Adaptador")
        
        for adaptador in adaptadores:
            # Usando '| None' no lugar de Optional (Padrão Python 3.10+)
            match: re.Match[str] | None = re.search(r"Gateway Padrão.*?: ([\d\.]+)", adaptador)
            
            if match:
                ip_gateway: str = match.group(1)
                
                if ip_gateway.startswith("25.") or ip_gateway.startswith("26.") or ip_gateway == "0.0.0.0":
                    continue
                
                if ip_gateway.startswith("192.168.") or ip_gateway.startswith("172.") or ip_gateway.startswith("10."):
                    return ip_gateway
                    
    except Exception as e:
        print(f"⚠️ Erro ao buscar IP: {e}")
        
    return "172.31.184.205"

IP_TELEFONE: str = obter_ip_telefone()
print(f"📱 IP do telefone detectado: {IP_TELEFONE}")

url: str = f"http://{IP_TELEFONE}:8080/video"

# ==========================================
# ESCOLHA SUA CÂMERA AQUI:
# Para usar o celular: CAMERA_SOURCE = url
# Para usar a webcam nativa no WSL: CAMERA_SOURCE = 0 (ou "/dev/video0")
# ==========================================
# Usando '|' no lugar de Union (Padrão Python 3.10+)
CAMERA_SOURCE: str | int = "/dev/video0"

class CameraStream:
    def __init__(self, src: str | int) -> None:
        # Tipagem explícita dos atributos da classe com as bibliotecas reais
        self.cap: cv2.VideoCapture
        self.ret: bool
        self.frame: np.ndarray | None
        self.stopped: bool

        is_url: bool = isinstance(src, str) and ("http" in str(src) or "rtsp" in str(src))
        
        if is_url:
            print("🌐 Iniciando câmera via REDE (Celular)...")
            self.cap = cv2.VideoCapture(src)
            _: bool = self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            print("💻 Iniciando câmera via USB (Webcam/WSL)...")
            self.cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
            _: bool = self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')) # type: ignore
            _: bool = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            _: bool = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            _: bool = self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        if not self.cap.isOpened():
            print(f"❌ Erro: Não foi possível abrir a câmera '{src}'.")
            
        self.ret = False
        self.frame = None
        self.stopped = False
        
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
            threading.Thread(target=self.update, daemon=True).start()

    def update(self) -> None:
        while not self.stopped:
            if self.cap.isOpened():
                self.ret, self.frame = self.cap.read()

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self.ret, self.frame

    def release(self) -> None:
        self.stopped = True
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

# ==========================================
# --- 1. SETUP DO HARDWARE ---
# ==========================================
print("🔌 Iniciando conexão com o Arduino...")
# Em modo estrito, quando não há tipagem, usamos 'object'
board: object | None = None

try:
    board = Arduino(Arduino.AUTODETECT) # type: ignore
    print("✅ Hardware conectado!")
except Exception as e:
    print(f"❌ Erro de Hardware: {e}")
    print("⚠️ DICA WSL: Você esqueceu de rodar 'usbipd attach --wsl --busid <ID>' no PowerShell do Windows?")
    print("Testando apenas a câmera (Hardware ignorado para simulação da esteira)...")

servo_plastico: object | None = None
servo_metal: object | None = None
servo_papel: object | None = None

if board:
    servo_plastico = board.get_pin('d:10:s') # type: ignore
    servo_metal = board.get_pin('d:9:s') # type: ignore
    servo_papel = board.get_pin('d:8:s') # type: ignore

    servo_plastico.write(0) # type: ignore
    servo_metal.write(0) # type: ignore
    servo_papel.write(0) # type: ignore

estado_plastico: bool = False
estado_metal: bool = False
estado_papel: bool = False

ultimo_visto_plastico: float = 0.0
ultimo_visto_metal: float = 0.0
ultimo_visto_papel: float = 0.0

TIMEOUT_PERDA_SINAL: float = 1.0 

# ==========================================
# --- 3. SETUP DA VISÃO ---
# ==========================================
model: YOLO = YOLO("models/best.pt")

print(f"📡 Conectando à fonte de vídeo: {CAMERA_SOURCE}...")
cap: CameraStream = CameraStream(CAMERA_SOURCE)
time.sleep(2)

print("🚀 Sistema de Monitoramento de Estado Iniciado.")
print("💡 DICA: Pressione 'q' na janela do vídeo ou Ctrl+C no terminal para sair.")

NOME_JANELA: str = "Monitoramento de Estado Continuo"
cv2.namedWindow(NOME_JANELA)

try:
    while True:
        ret, frame = cap.read()
        
        if not ret or frame is None:
            print("Aguardando sinal da câmera...")
            if cv2.waitKey(500) & 0xFF == ord("q"):
                break
            if cv2.getWindowProperty(NOME_JANELA, cv2.WND_PROP_VISIBLE) < 1:
                break
            continue

        # A YOLO agora cuida dos próprios tipos nativamente
        results = model.predict(frame, conf=0.25, verbose=False)
        result = results[0] 

        # A matriz de classificação convertida do PyTorch para Numpy
        classes_na_tela: np.ndarray = result.boxes.cls.cpu().numpy()
        tempo_atual: float = time.time()
        
        # Usando 'set' minúsculo (Padrão Python 3.9+)
        classes_vistas_agora: set[str] = set()
        
        for cls_index in classes_na_tela:
            index: int = int(cls_index)
            nome_classe: str = str(model.names[index]).lower() 
            
            classes_vistas_agora.add(f"{nome_classe} (ID: {index})")
            
            if index == 3 or nome_classe in ['paper', 'cardboard', 'papel', 'papelao']:
                ultimo_visto_papel = tempo_atual
            elif nome_classe in ['plastic', 'plastic bag', 'plastic bottle', 'plastico']:
                ultimo_visto_plastico = tempo_atual
            elif nome_classe in ['can', 'metal', 'lata']:
                ultimo_visto_metal = tempo_atual

        if classes_vistas_agora:
            print(f"👀 IA está vendo: {', '.join(classes_vistas_agora)}")

        # --- 4. LÓGICA DE CONTROLE DE ESTADO ---
        if (tempo_atual - ultimo_visto_plastico) < TIMEOUT_PERDA_SINAL:
            if not estado_plastico: 
                print("🟢 PLÁSTICO na tela -> ABRINDO Servo 10")
                if board and servo_plastico: servo_plastico.write(45) # type: ignore
                estado_plastico = True
        else:
            if estado_plastico: 
                print("🔴 Plástico saiu da tela -> FECHANDO Servo 10")
                if board and servo_plastico: servo_plastico.write(0) # type: ignore
                estado_plastico = False

        if (tempo_atual - ultimo_visto_metal) < TIMEOUT_PERDA_SINAL:
            if not estado_metal:
                print("🟢 METAL na tela -> ABRINDO Servo 9")
                if board and servo_metal: servo_metal.write(45) # type: ignore
                estado_metal = True
        else:
            if estado_metal:
                print("🔴 Metal saiu da tela -> FECHANDO Servo 9")
                if board and servo_metal: servo_metal.write(0) # type: ignore
                estado_metal = False

        if (tempo_atual - ultimo_visto_papel) < TIMEOUT_PERDA_SINAL:
            if not estado_papel:
                print("🟢 PAPEL na tela -> ABRINDO Servo 8")
                if board and servo_papel: servo_papel.write(45) # type: ignore
                estado_papel = True
        else:
            if estado_papel:
                print("🔴 Papel saiu da tela -> FECHANDO Servo 8")
                if board and servo_papel: servo_papel.write(0) # type: ignore
                estado_papel = False

        # O resultado do desenho é um novo frame (matriz Numpy)
        annotated_frame: np.ndarray = result.plot()
        cv2.imshow(NOME_JANELA, annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        if cv2.getWindowProperty(NOME_JANELA, cv2.WND_PROP_VISIBLE) < 1:
            break

except KeyboardInterrupt:
    print("\n🛑 Interrompido pelo usuário (Ctrl+C).")

finally:
    print("🛑 Encerrando sistema e limpando memória...")
    cap.release()
    cv2.destroyAllWindows()

    if board:
        try:
            if servo_plastico: servo_plastico.write(0) # type: ignore
            if servo_metal: servo_metal.write(0) # type: ignore
            if servo_papel: servo_papel.write(0) # type: ignore
            time.sleep(0.5) 
            board.exit() # type: ignore
        except:
            pass
    print("✅ Sistema fechado com sucesso.")
