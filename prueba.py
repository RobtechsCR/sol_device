import googlemaps
from datetime import datetime

# Tu API Key
API_KEY = "AIzaSyCMHt7vdg3aqqoy2D3P6mSbO2obQsng2AA"
gmaps = googlemaps.Client(key=API_KEY)

try:
    print("--- Iniciando prueba de Directions API ---")
    res = gmaps.directions(
        origin="9.9333,-84.0833", 
        destination="9.9350,-84.0900", 
        mode="driving",
        departure_time="now"
    )

    if not res:
        print("❌ No se encontraron rutas. Esto suele pasar si la API Key no tiene permisos o las coordenadas están mal.")
    else:
        print("✅ Conexión con Google: EXITOSA")
        
        # Analizamos la primera ruta y el primer tramo (leg)
        ruta = res[0]
        tramo = ruta['legs'][0]
        
        print(f"📍 Origen: {tramo['start_address']}")
        print(f"📍 Destino: {tramo['end_address']}")
        print(f"⏱️ Duración Estándar: {tramo['duration']['text']}")

        # La prueba de fuego para el tráfico:
        if 'duration_in_traffic' in tramo:
            print(f"🚦 ¡TRÁFICO DETECTADO!: {tramo['duration_in_traffic']['text']}")
            print("Tu cuenta está configurada correctamente para datos Advanced.")
        else:
            print("⚠️ Google NO envió datos de tráfico ('duration_in_traffic').")
            print("\nPOSIBLES CAUSAS:")
            print("1. La 'Directions API' no está habilitada en tu consola de Google Cloud.")
            print("2. Tu cuenta de facturación no tiene el 'Upgrade' hecho (aunque tengas los $200 gratis).")
            print("3. La API Key tiene restricciones de IP o Referrer que bloquean datos avanzados.")

except Exception as e:
    print(f"❌ Error durante la ejecución: {e}")