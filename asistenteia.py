import os
import ctypes
import json
import sqlite3
import csv
import googlemaps
import math
import re
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
IA_LIBS_DIR = "/home/orangepi/Documents/ia_libs"
MODEL_PATH = "/home/orangepi/Documents/models/qwen3-vl-2b-instruct_w8a8_rk3588.rkllm"
PATH_GPS, PATH_SENTIDO = "/home/orangepi/Documents/gps.txt", "/home/orangepi/Documents/sentido.txt"
PATH_RUTA_OFICIAL = "/home/orangepi/Documents/ruta_actual.json"
DB_PATH = "/home/orangepi/Documents/memoria_bus.db"
API_KEY_GOOGLE = "AIzaSyCMHt7vdg3aqqoy2D3P6mSbO2obQsng2AA"

gmaps = googlemaps.Client(key=API_KEY_GOOGLE)

# ==========================================
# 2. MOTOR NPU (ESTRUCTURAS SEGURAS C++)
# ==========================================
try:
    ctypes.CDLL(os.path.join(IA_LIBS_DIR, "librknnrt.so"), mode=ctypes.RTLD_GLOBAL)
    rkllm_lib = ctypes.CDLL(os.path.join(IA_LIBS_DIR, "librkllmrt.so"))
except Exception as e:
    print(f"❌ Error NPU: {e}"); exit(1)

class RKLLMParam(ctypes.Structure):
    _fields_ = [("model_path", ctypes.c_char_p), ("max_context_len", ctypes.c_int32), ("max_new_tokens", ctypes.c_int32), ("top_k", ctypes.c_int32), ("top_p", ctypes.c_float), ("temperature", ctypes.c_float), ("repeat_penalty", ctypes.c_float), ("frequency_penalty", ctypes.c_float), ("presence_penalty", ctypes.c_float), ("mirostat", ctypes.c_int32), ("mirostat_tau", ctypes.c_float), ("mirostat_eta", ctypes.c_float), ("logprobs", ctypes.c_bool), ("top_logprobs", ctypes.c_int32), ("use_mmap", ctypes.c_bool), ("use_gpu", ctypes.c_bool), ("is_async", ctypes.c_bool), ("img_start", ctypes.c_char_p), ("img_end", ctypes.c_char_p), ("img_content", ctypes.c_char_p), ("reserved", ctypes.c_uint8 * 128)]

class RKLLMInput(ctypes.Structure):
    class Union(ctypes.Union): _fields_ = [("prompt", ctypes.c_char_p), ("padding", ctypes.c_uint8 * 256)]
    _fields_ = [("role", ctypes.c_char_p), ("enable_thinking", ctypes.c_bool), ("input_type", ctypes.c_int32), ("inputs", Union)]

class RKLLMResult(ctypes.Structure): _fields_ = [("text", ctypes.c_char_p)]

respuesta_tokens = []
@ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
def llm_cb(res_ptr, usr, state):
    if res_ptr:
        t = ctypes.cast(res_ptr, ctypes.POINTER(RKLLMResult)).contents.text
        if t: 
            txt = t.decode('utf-8', errors='ignore')
            print(txt, end='', flush=True); respuesta_tokens.append(txt)
    return 0

class AssistantNPU:
    def __init__(self):
        rkllm_lib.rkllm_createDefaultParam.restype = RKLLMParam
        p = rkllm_lib.rkllm_createDefaultParam()
        p.model_path = MODEL_PATH.encode('utf-8')
        p.max_context_len, p.max_new_tokens, p.temperature, p.top_k = 1024, 300, 0.1, 10
        self.h = ctypes.c_void_p()
        rkllm_lib.rkllm_init(ctypes.byref(self.h), ctypes.byref(p), ctypes.cast(llm_cb, ctypes.c_void_p))

    def hablar(self, ctx, pregunta):
        global respuesta_tokens
        respuesta_tokens = []
        prompt = f"<|im_start|>system\nEres el asistente a bordo de Ruta 09. Usa la INFORMACIÓN DEL SISTEMA para responder. Si el sistema sugiere alternativas porque el lugar principal no está en ruta, recomiéndalas de forma amable indicando paradas y distancias.<|im_end|>\n<|im_start|>user\nINFORMACIÓN DEL SISTEMA: {ctx}. PREGUNTA DEL PASAJERO: {pregunta}<|im_end|>\n<|im_start|>assistant\n"
        prompt_bytes = prompt.encode('utf-8')
        inp = RKLLMInput(); inp.input_type = 0; inp.inputs.prompt = prompt_bytes
        print("\nIA: ", end='', flush=True)
        class InferDummy(ctypes.Structure): _fields_ = [("mode", ctypes.c_int32), ("p1", ctypes.c_void_p), ("p2", ctypes.c_void_p)]
        rkllm_lib.rkllm_run(self.h, ctypes.byref(inp), ctypes.byref(InferDummy(0, None, None)), None)
        print("\n")

# ==========================================
# 3. MOTOR LOGÍSTICO Y CONCIERGE
# ==========================================
def calcular_distancia(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def buscar_alternativas(lat_bus, lon_bus, tipo_negocio, waypoints_futuros, idx_bus_actual, waypoints_completos):
    """Busca negocios similares en la ruta futura si el principal falló."""
    if not tipo_negocio or tipo_negocio in ["point_of_interest", "establishment"]: 
        return "" # Ignora tipos muy genéricos
    
    # Adaptar el tipo de Google a una búsqueda amigable
    tipo_query = tipo_negocio.replace("_", " ") 
    res_alt = gmaps.places_nearby(location=(lat_bus, lon_bus), keyword=tipo_query, rank_by="distance")
    
    alternativas = []
    if res_alt.get('results'):
        for alt in res_alt['results']:
            t_lat, t_lon = alt['geometry']['location']['lat'], alt['geometry']['location']['lng']
            # Verificamos si esta alternativa sí está en nuestra ruta futura
            dist_futuras = [calcular_distancia(p['lat'], p['lon'], t_lat, t_lon) for p in waypoints_futuros]
            if not dist_futuras: break
            min_d = min(dist_futuras)
            
            if min_d <= 800: # Tolerancia de caminata: 800 metros
                idx_wp_global = idx_bus_actual + dist_futuras.index(min_d)
                parada = waypoints_completos[idx_wp_global]['nombre']
                alternativas.append(f"'{alt['name']}' (a {int(min_d)}m de parada {parada})")
                if len(alternativas) == 3: break # Máximo 3 recomendaciones
                
    if alternativas:
        return f" Negocios similares en nuestra ruta futura: {', '.join(alternativas)}."
    return " No encontré otros negocios similares más adelante en la ruta."

def motor_vial(pregunta, lat_bus, lon_bus, sentido):
    p_low = pregunta.lower()
    
    # 1. Limpieza universal (sin if's restrictivos)
    lugar = re.sub(r'(hola|puedes|decirme|donde|hay|algun|alguna|un|una|ir a|llegar a|cuanto tardo|cuanto falta|bus pasa por|quisiera saber|a que hora|recomendar|recomiendame|sabes si)', '', p_low).strip()
    lugar = lugar.replace("estaré llegando a", "").replace("por favor", "").split("?")[0].split(",")[0].strip()

    if len(lugar) < 2: return "Por favor, indique un destino o lugar a buscar."

    try:
        with open(PATH_RUTA_OFICIAL, 'r') as f: waypoints = json.load(f).get(sentido, [])
        
        # Estado actual del bus
        dist_bus = [((p['lat']-lat_bus)**2 + (p['lon']-lon_bus)**2) for p in waypoints]
        idx_bus = dist_bus.index(min(dist_bus))
        waypoints_futuros = waypoints[idx_bus:]

        # ==========================================
        # PASO A: Buscar en Waypoints Oficiales
        # ==========================================
        for i, p in enumerate(waypoints):
            if lugar in p['nombre'].lower():
                if i >= idx_bus:
                    dirs = gmaps.directions((lat_bus, lon_bus), (p['lat'], p['lon']), mode="driving")
                    t_google = dirs[0]['legs'][0]['duration']['value'] // 60 if dirs else 0
                    t_total = t_google + ((i - idx_bus) * 0.5)
                    return f"El destino coincide con la parada '{p['nombre']}'. Llegaremos en aprox {int(t_google)}-{int(t_total)} minutos."
                else:
                    return f"Esa parada ('{p['nombre']}') ya quedó atrás en el recorrido."

        # ==========================================
        # PASO B: Búsqueda Universal en Google Places
        # ==========================================
        # Hacemos una búsqueda abierta en un radio amplio desde el bus
        res_geo = gmaps.places(query=f"{lugar}, Costa Rica", location=(lat_bus, lon_bus), radius=10000)
        
        if not res_geo.get('results'):
            return f"No logré ubicar '{lugar}' en el mapa."

        # Ordenamos los resultados de Google por su distancia real (Haversine) al BUS
        resultados = res_geo['results']
        for r in resultados:
            print(r)
            r['dist_bus'] = calcular_distancia(lat_bus, lon_bus, r['geometry']['location']['lat'], r['geometry']['location']['lng'])
        resultados.sort(key=lambda x: x['dist_bus'])
    
        # Evaluamos el lugar más cercano al bus para ver si es viable
        mejor_lugar = resultados[0]
        t_lat, t_lon = mejor_lugar['geometry']['location']['lat'], mejor_lugar['geometry']['location']['lng']
        tipo_principal = mejor_lugar.get('types', [None])[0]

        # Comparamos contra la ruta FUTURA
        distancias_futuras = [calcular_distancia(p['lat'], p['lon'], t_lat, t_lon) for p in waypoints_futuros]
        if distancias_futuras:
            min_dist_futura = min(distancias_futuras)
            idx_parada_futura = idx_bus + distancias_futuras.index(min_dist_futura)
        else:
            min_dist_futura = float('inf')

        # Comparamos contra TODA la ruta (para saber si ya pasamos)
        distancias_total = [calcular_distancia(p['lat'], p['lon'], t_lat, t_lon) for p in waypoints]
        min_dist_total = min(distancias_total)
        idx_parada_absoluta = distancias_total.index(min_dist_total)

        # ==========================================
        # PASO C: Toma de Decisiones y Alternativas
        # ==========================================
        info = f"Destino: {mejor_lugar['name']}. "

        if min_dist_futura <= 1000: # 1. ¡Éxito! Está en el futuro y a menos de 1km
            parada = waypoints[idx_parada_futura]
            walk = gmaps.distance_matrix((parada['lat'], parada['lon']), (t_lat, t_lon), mode="walking")
            dist_pie = walk['rows'][0]['elements'][0]['distance']['value']
            
            dirs = gmaps.directions((lat_bus, lon_bus), (parada['lat'], parada['lon']), mode="driving")
            t_google = dirs[0]['legs'][0]['duration']['value'] // 60 if dirs else 0
            t_total = t_google + ((idx_parada_futura - idx_bus) * 0.5)
            hora = (datetime.now() + timedelta(minutes=t_total)).strftime("%I:%M %p")
            
            info += f"Bájate en la parada '{parada['nombre']}'. Caminata desde ahí: {dist_pie}m. Llegada al destino: {int(t_google)}-{int(t_total)} min (aprox {hora})."

        elif min_dist_total <= 1000 and idx_parada_absoluta < idx_bus: # 2. Ya pasamos
            info += f"Ya pasamos por ese lugar. La parada era '{waypoints[idx_parada_absoluta]['nombre']}' a {int(min_dist_total)}m."
            info += buscar_alternativas(lat_bus, lon_bus, tipo_principal, waypoints_futuros, idx_bus, waypoints)

        else: # 3. No pasa ni pasará cerca
            parada = waypoints[idx_parada_absoluta]
            info += f"Nuestra ruta no pasa cerca. La parada menos lejana es '{parada['nombre']}' pero queda a {int(min_dist_total)} metros (demasiado lejos)."
            info += buscar_alternativas(lat_bus, lon_bus, tipo_principal, waypoints_futuros, idx_bus, waypoints)

        return info

    except Exception as e: return f"Error del sistema vial: {e}"

# ==========================================
# 4. BUCLE
# ==========================================
if __name__ == "__main__":
    ia = AssistantNPU()
    print("\n🚌 RUTA 09: CONCIERGE LOGÍSTICO V17.0 (SOPORTE DE ALTERNATIVAS) ACTIVO.\n")

    while True:
        try:
            with open(PATH_GPS, 'r') as f:
                d = f.read().strip().split(','); lt, ln = float(d[0].split(':')[1]), float(d[1].split(':')[1])
            with open(PATH_SENTIDO, 'r') as f: st = f.read().strip()
        except: lt, ln, st = 9.93, -84.08, "2"

        p_u = input("Pasajero: ")
        if p_u.lower() in ["salir", "exit"]: break

        ctx = motor_vial(p_u, lt, ln, st)
        ia.hablar(ctx, p_u)
