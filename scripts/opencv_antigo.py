from ultralytics import YOLO
import cv2
from pyfirmata2 import Arduino # type: ignore
import time
import threading
import subprocess
import re

def obter_ip_telefone():
    print("🔍 Procurando o IP do celular na rede USB...")
    try:
        # 1. FIX WSL: Adicionado '.exe' para chamar o comando de rede do Windows por dentro do Linux
        output = subprocess.check_output("ipconfig.exe", shell=True, encoding="cp850")
        
        adaptadores = output.split("Adaptador")
        
        for adaptador in adaptadores:
            match = re.search(r"Gateway Padrão.*?: ([\d\.]+)", adaptador)
            
            if match:
                ip_gateway = match.group(1)
                
                if ip_gateway.startswith("25.") or ip_gateway.startswith("26.") or ip_gateway == "0.0.0.0":
                    continue
                
                if ip_gateway.startswith("192.168.") or ip_gateway.startswith("172.") or ip_gateway.startswith("10."):
                    return ip_gateway
                    
    except Exception as e:
        print(f"⚠️ Erro ao buscar IP: {e}")
        
    return "172.31.184.205"

IP_TELEFONE = obter_ip_telefone()
print(f"📱 IP do telefone detectado: {IP_TELEFONE}")

url = f"http://{IP_TELEFONE}:8080/video"

# ==========================================
# ESCOLHA SUA CÂMERA AQUI:
# Para usar o celular: CAMERA_SOURCE = url
# Para usar a webcam nativa no WSL: CAMERA_SOURCE = 0 (ou "/dev/video0")
# ==========================================
CAMERA_SOURCE = url

class CameraStream:
    def __init__(self, src):
        is_url = isinstance(src, str) and ("http" in src or "rtsp" in src)
        
        if is_url:
            print("🌐 Iniciando câmera via REDE (Celular)...")
            self.cap = cv2.VideoCapture(src)
            # FIX: Limita o buffer para 1 frame na rede para acabar com o delay/atraso
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            print("💻 Iniciando câmera via USB (Webcam/WSL)...")
            self.cap = cv2.VideoCapture(src)
            # FIX: Configuração anti-Segmentation Fault para o WSL
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        if not self.cap.isOpened():
            print(f"❌ Erro: Não foi possível abrir a câmera '{src}'.")
            
        self.ret = False
        self.frame = None
        self.stopped = False
        
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
            threading.Thread(target=self.update, daemon=True).start()

    def update(self):
        while not self.stopped:
            if self.cap.isOpened():
                # FIX: Removido o time.sleep() para ler o vídeo na velocidade máxima sem acumular quadros antigos
                self.ret, self.frame = self.cap.read()

    def read(self):
        return self.ret, self.frame

    def release(self):
        self.stopped = True
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

# ==========================================
# --- 1. SETUP DO HARDWARE ---
# ==========================================
print("🔌 Iniciando conexão com o Arduino...")
try:
    # 2. FIX WSL: Proteção extra no caso do USB não ter sido anexado
    board = Arduino(Arduino.AUTODETECT) 
    print("✅ Hardware conectado!")
except Exception as e:
    print(f"❌ Erro de Hardware: {e}")
    print("⚠️ DICA WSL: Você esqueceu de rodar 'usbipd attach --wsl --busid <ID>' no PowerShell do Windows?")
    print("Testando apenas a câmera (Hardware ignorado para simulação da esteira)...")
    board = None

if board:
    servo_plastico = board.get_pin('d:10:s')    
    servo_metal = board.get_pin('d:9:s')
    servo_papel = board.get_pin('d:8:s')

    servo_plastico.write(0)
    servo_metal.write(0)
    servo_papel.write(0)

estado_plastico = False
estado_metal = False
estado_papel = False

ultimo_visto_plastico = 0.0
ultimo_visto_metal = 0.0
ultimo_visto_papel = 0.0

TIMEOUT_PERDA_SINAL = 1.0 

# ==========================================
# --- 3. SETUP DA VISÃO ---
# ==========================================
model = YOLO("models/best.pt")

print(f"📡 Conectando à fonte de vídeo: {CAMERA_SOURCE}...")
cap = CameraStream(CAMERA_SOURCE)
time.sleep(2)

print("🚀 Sistema de Monitoramento de Estado Iniciado.")
print("💡 DICA: Pressione 'q' na janela do vídeo ou Ctrl+C no terminal para sair.")

# Janela criada preventivamente para evitar o erro (-27:Null pointer)
NOME_JANELA = "Monitoramento de Estado Continuo"
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

        results = model.predict(frame, conf=0.25, verbose=False)
        result = results[0] 

        classes_na_tela = result.boxes.cls.cpu().numpy()
        tempo_atual = time.time()
        classes_vistas_agora = set()
        
        for cls_index in classes_na_tela:
            index = int(cls_index)
            nome_classe = model.names[index].lower() 
            
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
                if board: servo_plastico.write(45)
                estado_plastico = True
        else:
            if estado_plastico: 
                print("🔴 Plástico saiu da tela -> FECHANDO Servo 10")
                if board: servo_plastico.write(0)
                estado_plastico = False

        if (tempo_atual - ultimo_visto_metal) < TIMEOUT_PERDA_SINAL:
            if not estado_metal:
                print("🟢 METAL na tela -> ABRINDO Servo 9")
                if board: servo_metal.write(45)
                estado_metal = True
        else:
            if estado_metal:
                print("🔴 Metal saiu da tela -> FECHANDO Servo 9")
                if board: servo_metal.write(0)
                estado_metal = False

        if (tempo_atual - ultimo_visto_papel) < TIMEOUT_PERDA_SINAL:
            if not estado_papel:
                print("🟢 PAPEL na tela -> ABRINDO Servo 8")
                if board: servo_papel.write(45)
                estado_papel = True
        else:
            if estado_papel:
                print("🔴 Papel saiu da tela -> FECHANDO Servo 8")
                if board: servo_papel.write(0)
                estado_papel = False

        annotated_frame = result.plot()
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
            servo_plastico.write(0)
            servo_metal.write(0)
            servo_papel.write(0)
            time.sleep(0.5) 
            board.exit()
        except:
            pass
    print("✅ Sistema fechado com sucesso.")
