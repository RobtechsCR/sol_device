from rknn.api import RKNN

# 1. Instanciar la herramienta
rknn = RKNN(verbose=True)

# 2. Configuración vital: Le decimos que es para tu placa exacta
print('--> Configurando para RK3588...')
rknn.config(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]], target_platform='rk3588')

# 3. Cargar el modelo ONNX original
print('--> Cargando modelo ONNX...')
ret = rknn.load_onnx(model='yolov8n.onnx')
if ret != 0:
    print('Error al cargar el archivo .onnx')
    exit(ret)

# 4. Construir la red neuronal (Usamos FP16)
# do_quantization=False evita tener que pasarle un set de imágenes de calibración por ahora
print('--> Construyendo la red neuronal para NPU...')
ret = rknn.build(do_quantization=False)
if ret != 0:
    print('Error en la compilación del modelo.')
    exit(ret)

# 5. Exportar el archivo final
print('--> Exportando el binario .rknn...')
ret = rknn.export_rknn('yolov8n_rk3588.rknn')
if ret != 0:
    print('Error al exportar.')
    exit(ret)

print('✅ ¡ÉXITO! Tu archivo yolov8n_rk3588.rknn está listo.')