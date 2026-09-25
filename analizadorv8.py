import cv2
import numpy as np
import threading
import time
import queue
import json
import os
import logging
from datetime import datetime
from rknnlite.api import RKNNLite
from flask import Flask, Response

# --- CONFIGURACIÓN DE LOGS ---
LOG_FILE = "/home/orangepi/Documents/ruta09_eventos.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# --- REVISA ESTE NOMBRE: Debe coincidir exactamente con tu archivo .rknn ---
MODELO_RKNN = "/home/orangepi/Documents/yolov8s_rk3588.rknn" 
RTSP_URL = "rtsp://admin:Tapa.Cilt1907*@192.168.1.64:554/Streaming/Channels/102"
ARCHIVO_DATOS = "/home/orangepi/Documents/contadores_ruta09.json"
CARPETA_CALIB = "/home/orangepi/Documents/dataset_calib"
ARCHIVO_DATASET = "/home/orangepi/Documents/dataset.txt"

# --- RENDIMIENTO ---
NUM_WORKERS = 3
FPS_OBJETIVO_GLOBAL = 15 
TIEMPO_POR_FRAME = NUM_WORKERS / FPS_OBJETIVO_GLOBAL 

# --- GEOMETRÍA ---
LINEA_SUP, LINEA_INF = 100, 430
BARRA_VERDE_X1, BARRA_VERDE_X2 = 355, 395
MIN_H_PX = 70
MAX_LOST = 30

# --- ESTADOS ---
entradas, salidas = 0, 0
seguimiento = {}
proximo_id = 0
ultima_captura_time = 0
fotos_esta_hora = 0
ultima_hora = -1
ultimo_conteo_real = 0
conteo_estable = 0

app = Flask(__name__)
output_frame = None
lock = threading.Lock()
cola_captura = queue.Queue(maxsize=3)
cola_resultados = queue.Queue(maxsize=6)

if not os.path.exists(CARPETA_CALIB): os.makedirs(CARPETA_CALIB)

def cargar_datos():
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, 'r') as f:
                d = json.load(f); return d['entradas'], d['salidas']
        except: return 0, 0
    return 0, 0

def guardar_datos(e, s):
    try:
        with open(ARCHIVO_DATOS, 'w') as f:
            json.dump({'entradas': e, 'salidas': s, 't': str(datetime.now())}, f)
        logging.info(f"📊 CONTEO: E:{e} S:{s}")
    except: pass

def recolector_inteligente(frame, personas_activas, hora_h):
    global ultima_captura_time, ultimo_conteo_guardado, fotos_esta_hora, ultima_hora
    ahora = time.time()
    num = len(personas_activas)
    if hora_h != ultima_hora:
        ultima_hora = hora_h; fotos_esta_hora = 0
    if ahora - ultima_captura_time < 15: return
    
    # Disparar si hay gente o por tiempo
    if (num > 0 or ahora - ultima_captura_time > 600) and fotos_esta_hora < 40:
        nombre = f"calib_H{hora_h}_P{num}_{int(ahora)}.jpg"
        path = os.path.join(CARPETA_CALIB, nombre)
        if cv2.imwrite(path, frame):
            with open(ARCHIVO_DATASET, 'a') as f: f.write(f"{path}\n")
            ultima_captura_time = ahora
            fotos_esta_hora += 1
            logging.info(f"📸 Foto guardada: {nombre}")

class NPUWorker(threading.Thread):
    def __init__(self, core_id):
        super().__init__()
        self.core_id = core_id
        self.rknn = RKNNLite()
        try:
            ret = self.rknn.load_rknn(MODELO_RKNN)
            if ret != 0: logging.error(f"❌ Error al cargar modelo en Core {core_id}")
            self.rknn.init_runtime(core_mask=(1 << core_id))
            logging.info(f"✅ NPU Core {core_id} listo.")
        except Exception as e:
            logging.error(f"❌ Crash en NPU Core {core_id}: {e}")
        self.daemon = True

    def run(self):
        while True:
            try:
                frame = cola_captura.get(timeout=2)
                img = cv2.resize(frame, (640, 640))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                outputs = self.rknn.inference(inputs=[np.expand_dims(img, 0)])
                if not cola_resultados.full():
                    cola_resultados.put((frame, outputs))
            except queue.Empty: continue
            except Exception as e:
                logging.error(f"⚠️ Error en inferencia Core {self.core_id}: {e}")
                time.sleep(1)

def post_process(outputs):
    if not outputs: return []
    data = np.squeeze(outputs[0])
    # UMBRAL BAJADO A 0.35 PARA INT8
    mask = data[4, :] > 0.35 
    valid = data[:, mask]
    return [[int(x-w/2), int(y-h/2), int(w), int(h)] for x,y,w,h in valid[0:4, :].T]

def procesador_central():
    global entradas, salidas, seguimiento, proximo_id, output_frame, lock
    global conteo_estable, ultimo_conteo_real
    
    entradas, salidas = cargar_datos()

    while True:
        cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            logging.error("No se pudo conectar a la cámara. Reintento en 10s.")
            time.sleep(10); continue

        logging.info("📡 Cámara conectada. Procesando frames...")

        while True:
            ret, frame_cap = cap.read()
            if not ret: break

            if not cola_captura.full():
                cola_captura.put(frame_cap)

            # --- CAMBIO CLAVE: Actualizar la web aunque la NPU no haya respondido aún ---
            frame_visual = cv2.resize(frame_cap, (640, 480))
            
            if not cola_resultados.empty():
                frame_raw, outputs = cola_resultados.get()
                detecciones = post_process(outputs)
                
                centros_actuales = []
                for x, y, w, h in detecciones:
                    cx, cy = x + w//2, int((y + h//2) * (480/640))
                    if LINEA_SUP < cy < LINEA_INF:
                        centros_actuales.append({'c': (cx, cy), 'h': int(h * (480/640))})

                for pid in seguimiento: seguimiento[pid]['lost'] += 1
                for det in centros_actuales:
                    cx, cy = det['c']
                    mid, mdist = None, 100
                    for pid, d in seguimiento.items():
                        dist = np.hypot(cx - d['c'][0], cy - d['c'][1])
                        if dist < mdist: mdist, mid = dist, pid
                    
                    if mid is not None:
                        hist = seguimiento[mid].get('historia', [])
                        hist.append((cx, cy)); hist = hist[-5:]
                        nx, ny = int(np.mean([p[0] for p in hist])), int(np.mean([p[1] for p in hist]))
                        seguimiento[mid].update({'c': (nx, ny), 'historia': hist, 'lost': 0, 'h': det['h']})
                    else:
                        lado = 'puerta' if cx < BARRA_VERDE_X1 else 'interior'
                        seguimiento[proximo_id] = {'c': (cx, cy), 'historia': [(cx, cy)], 'lado_origen': lado, 'contado': False, 'lost': 0, 'h': det['h']}
                        proximo_id += 1

                cambio_c = False
                for pid, d in seguimiento.items():
                    if d['contado'] or d['lost'] > 0: continue
                    if d['lado_origen'] == 'puerta' and d['c'][0] > BARRA_VERDE_X2:
                        entradas += 1; d['contado'] = True; cambio_c = True
                    elif d['lado_origen'] == 'interior' and d['c'][0] < BARRA_VERDE_X1:
                        salidas += 1; d['contado'] = True; cambio_c = True
                
                if cambio_c: guardar_datos(entradas, salidas)

                activos = [d for d in seguimiento.values() if d['lost'] == 0]
                recolector_inteligente(frame_raw, activos, datetime.now().hour)
                
                # Dibujar sobre el frame visual
                for pid, d in seguimiento.items():
                    if d['lost'] == 0:
                        color = (0, 255, 0) if d['contado'] else (255, 255, 0)
                        cv2.circle(frame_visual, d['c'], 7, color, -1)

            # UI constante
            cv2.rectangle(frame_visual, (BARRA_VERDE_X1, LINEA_SUP), (BARRA_VERDE_X2, LINEA_INF), (0,255,0), 2)
            cv2.putText(frame_visual, f"E: {entradas} | S: {salidas}", (20, 40), 2, 0.8, (255,255,255), 2)
            
            with lock:
                output_frame = frame_visual.copy()
                
            seguimiento = {p: d for p, d in seguimiento.items() if d['lost'] < MAX_LOST}

        cap.release()
        time.sleep(5)

@app.route("/")
def video_feed():
    def generate():
        while True:
            with lock:
                if output_frame is None: continue
                (_, enc) = cv2.imencode(".jpg", output_frame)
            yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(enc) + b'\r\n')
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == '__main__':
    logging.info("=== INICIANDO SISTEMA V36 DIAGNOSTICO ===")
    for i in range(NUM_WORKERS): NPUWorker(i).start()
    threading.Thread(target=procesador_central, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
