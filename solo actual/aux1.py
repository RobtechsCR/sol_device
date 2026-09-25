import subprocess
import os
import sys

def es_root():
    """Verifica si el script se está ejecutando como root (sudo)."""
    return os.geteuid() == 0

def ejecutar_comando(comando, shell=False):
    """Ejecuta un comando de sistema y maneja errores básicos."""
    try:
        # DEBIAN_FRONTEND=noninteractive evita que apt haga preguntas de configuración visuales
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        
        resultado = subprocess.run(
            comando, 
            shell=shell, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        return True, resultado.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def instalar_anydesk_ubuntu():
    print("--- Iniciando instalación desatendida de AnyDesk en Ubuntu ---")

    # 1. Agregar la llave GPG de AnyDesk
    print("[1/5] Agregando claves de seguridad GPG...")
    # Descargamos la llave y la guardamos en el keyring de confianza
    cmd_key = "wget -qO - https://keys.anydesk.com/repos/DEB-GPG-KEY | gpg --dearmor | tee /etc/apt/trusted.gpg.d/anydesk.gpg > /dev/null"
    exito, output = ejecutar_comando(cmd_key, shell=True)
    if not exito:
        print(f"Error agregando GPG Key: {output}")
        return

    # 2. Agregar el repositorio a sources.list
    print("[2/5] Agregando repositorio oficial...")
    contenido_repo = "deb http://deb.anydesk.com/ all main"
    archivo_repo = "/etc/apt/sources.list.d/anydesk.list"
    
    try:
        with open(archivo_repo, "w") as f:
            f.write(contenido_repo)
    except Exception as e:
        print(f"Error escribiendo archivo de repositorio: {e}")
        return

    # 3. Actualizar la lista de paquetes
    print("[3/5] Actualizando repositorios (apt update)...")
    exito, output = ejecutar_comando(["apt-get", "update"])
    if not exito:
        print(f"Error en update: {output}")
        # No retornamos aquí porque a veces el update falla en otros repos pero anydesk podría estar bien

    # 4. Instalar AnyDesk
    print("[4/5] Instalando paquete AnyDesk...")
    # -y: Responde sí a todo
    cmd_install = ["apt-get", "install", "-y", "anydesk"]
    exito, output = ejecutar_comando(cmd_install)
    
    if exito:
        print("Instalación de paquete exitosa.")
    else:
        print(f"Error instalando AnyDesk: {output}")
        return

    # 5. Configurar contraseña para acceso desatendido (Opcional)
    # Esto permite conectarse a la máquina sin que un humano acepte la conexión.
    configurar_password = True # Cambiar a False si no se desea
    password_acceso = "TuContraseñaSegura123" 

    if configurar_password:
        print("[5/5] Configurando contraseña de acceso desatendido...")
        # AnyDesk en Linux usa el comando: echo password | anydesk --set-password
        cmd_pwd = f"echo '{password_acceso}' | anydesk --set-password"
        exito, output = ejecutar_comando(cmd_pwd, shell=True)
        
        if exito:
            print("Contraseña configurada correctamente.")
            # Obtener el ID de AnyDesk para mostrarlo
            _, anydesk_id = ejecutar_comando("anydesk --get-id", shell=True)
            print(f"\n>>> Instalación completada. Tu ID de AnyDesk es: {anydesk_id.strip()}")
        else:
            print(f"Advertencia: No se pudo establecer la contraseña. Error: {output}")
            print("Es posible que AnyDesk no esté corriendo todavía. Intenta reiniciar el servicio.")

if __name__ == "__main__":
    if es_root():
        instalar_anydesk_ubuntu()
    else:
        print("Error: Debes ejecutar este script con sudo.")
        print("Ejemplo: sudo python3 script_anydesk.py")