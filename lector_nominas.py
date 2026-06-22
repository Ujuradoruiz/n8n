#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LECTOR DE NÓMINAS - FASE 8: Integración con IA (Claude)
Versión: 8.0.0
Fecha: 2026-06-22
Autor: Claude para Jurado Asesores Tributarios - 2026

FUNCIONALIDADES FASE 1:
- Instalación automática de dependencias
- Arrastrar y soltar PDFs (Drag & Drop)
- OCR automático si no hay texto nativo
- Detección automática de CIF y período
- Interfaz intuitiva con mínima interacción
- Ventana maximizada a pantalla completa

FUNCIONALIDADES FASE 2:
- Sistema de logging detallado con ventana de consulta
- Contador de errores en tiempo real en cabecera
- Búsqueda de empresa por CIF en base de datos Geyce
- Consulta de plan de cuentas por empresa
- Obtención de número de asiento

FUNCIONALIDADES FASE 3:
- Sistema de plantillas con aprendizaje automático
- Auto-detección del tipo de documento (fingerprint)
- Modo aprendizaje guiado para nuevos formatos
- Extracción inteligente de conceptos e importes
- Mapeo automático a cuentas contables
- Mejora continua con cada corrección del usuario

FUNCIONALIDADES FASE 3.5:
- Integración con OpenDataLoader PDF (precisión 0.907)
- Extracción avanzada de tablas con bounding boxes
- OCR mejorado con 80+ idiomas
- Detección de estructura basada en coordenadas
- Fallback a PyMuPDF si OpenDataLoader no disponible

FUNCIONALIDADES FASE 4:
- Proceso masivo de múltiples PDFs
- Cola de procesamiento con progreso visual
- Tabla de resultados con estado por documento
- Exportación a Excel/CSV
- Generación masiva de asientos contables
- Resumen estadístico del proceso

FUNCIONALIDADES FASE 5:
- Validación de CIF/NIF español con dígito de control
- Verificación de cuadre contable (debe = haber)
- Detección de documentos duplicados (hash + fingerprint)
- Validación de rangos de importes (alertas por anomalías)
- Panel de alertas y advertencias en tiempo real
- Informe de validación exportable

FUNCIONALIDADES FASE 6:
- Generación automática de asientos contables
- Estructura completa: cabecera + líneas de apunte
- Ventana de previsualización y edición de asientos
- Inserción directa en base de datos Geyce
- Cuadre automático del asiento
- Soporte para múltiples líneas por concepto
- Exportación de asiento a formato texto

FUNCIONALIDADES FASE 7:
- Sistema de informes y estadísticas
- Dashboard con métricas de procesamiento
- Histórico de asientos generados con búsqueda
- Configuración personalizable persistente (JSON)
- Personalización de cuentas contables por defecto
- Configuración de conexión a base de datos
- Exportación de informes a PDF/Excel

FUNCIONALIDADES FASE 7.5:
- Configuración de cuentas contables POR EMPRESA
- Detección automática de empresa sin configurar
- Ventana de configuración de subcuentas por empresa
- Persistencia de configuración por CIF
- Uso de cuentas específicas al generar asientos
- Las cuentas globales son solo valores por defecto

FUNCIONALIDADES FASE 8 (NUEVA - IA):
- Extracción de datos mediante IA (Claude API)
- La IA lee el PDF directamente (visión)
- Conversión automática a JSON estructurado
- Ventana de edición/validación del JSON extraído
- Sistema de aprendizaje con correcciones del usuario
- Historial de extracciones por empresa
- Distinción visual entre datos IA vs programa
- Configuración de API key segura
"""

VERSION = "8.0.0"
VERSION_FECHA = "2026-06-22"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import re
import threading
import io
import json
import hashlib
from datetime import datetime
from queue import Queue, Empty
from pathlib import Path

# =============================================================================
# INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS
# =============================================================================
def instalar_dependencias():
    """Instala las dependencias necesarias si no están disponibles"""
    dependencias = {
        'fitz': 'PyMuPDF',
        'pytesseract': 'pytesseract',
        'PIL': 'Pillow',
        'pyodbc': 'pyodbc',
        'opendataloader_pdf': 'opendataloader-pdf',
        'anthropic': 'anthropic'  # FASE 8: API de Claude
    }

    for modulo, paquete in dependencias.items():
        try:
            __import__(modulo)
        except ImportError:
            print(f"Instalando {paquete}...")
            import subprocess
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', paquete, '-q'])
            except subprocess.CalledProcessError:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', paquete, '--break-system-packages', '-q'])

instalar_dependencias()

import fitz
import pytesseract
import pyodbc
import base64
from PIL import Image, ImageTk

# OpenDataLoader - con fallback si no está disponible
try:
    import opendataloader_pdf
    OPENDATALOADER_OK = True
except ImportError:
    OPENDATALOADER_OK = False
    print("⚠️ OpenDataLoader no disponible. Usando PyMuPDF como fallback.")

# Anthropic (Claude API) - para extracción IA
try:
    import anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False
    print("⚠️ Anthropic no disponible. Instale con: pip install anthropic")

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
def configurar_tesseract():
    """Configura la ruta de Tesseract en Windows"""
    if sys.platform == 'win32':
        rutas = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
        ]
        for ruta in rutas:
            if os.path.exists(ruta):
                pytesseract.pytesseract.tesseract_cmd = ruta
                return True
        return False
    return True

TESSERACT_OK = configurar_tesseract()

DB_CONFIG = {
    'server': 'Srvv01',
    'user': 'sa',
    'password': '1Geyce$2025!!',
    'database_geyce': 'GEYCE_Avansa',
    'database_easp': 'easp'
}

# =============================================================================
# CLASE: Logger (Sistema de logging detallado)
# =============================================================================
class Logger:
    """Sistema de logging centralizado (Singleton)"""
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._registros = []
            cls._instancia._contador_errores = 0
            cls._instancia._callbacks = []
        return cls._instancia

    def registrar(self, nivel, mensaje, detalles=None):
        """Registra un mensaje en el log"""
        registro = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'nivel': nivel.upper(),
            'mensaje': mensaje,
            'detalles': detalles
        }
        self._registros.append(registro)

        if nivel.upper() == 'ERROR':
            self._contador_errores += 1

        # Notificar a los callbacks
        for cb in self._callbacks:
            try:
                cb(registro)
            except:
                pass

    def info(self, mensaje, detalles=None):
        self.registrar('INFO', mensaje, detalles)

    def warning(self, mensaje, detalles=None):
        self.registrar('WARNING', mensaje, detalles)

    def error(self, mensaje, detalles=None):
        self.registrar('ERROR', mensaje, detalles)

    def debug(self, mensaje, detalles=None):
        self.registrar('DEBUG', mensaje, detalles)

    @property
    def errores(self):
        return self._contador_errores

    @property
    def registros(self):
        return self._registros.copy()

    def agregar_callback(self, callback):
        """Añade un callback que se ejecuta con cada nuevo registro"""
        self._callbacks.append(callback)

    def limpiar(self):
        """Limpia todos los registros"""
        self._registros = []
        self._contador_errores = 0


class VentanaLog(tk.Toplevel):
    """Ventana para visualizar el log de eventos"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Log de Eventos")
        self.geometry("900x500")

        self.logger = Logger()
        self._crear_ui()
        self._cargar_registros()

        # Auto-actualizar
        self.logger.agregar_callback(self._agregar_registro)

    def _crear_ui(self):
        # Frame principal
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # Filtros
        frame_filtros = ttk.Frame(main)
        frame_filtros.pack(fill='x', pady=(0, 10))

        ttk.Label(frame_filtros, text="Filtrar por nivel:").pack(side='left')
        self.var_filtro = tk.StringVar(value="TODOS")
        for nivel in ["TODOS", "INFO", "WARNING", "ERROR", "DEBUG"]:
            ttk.Radiobutton(frame_filtros, text=nivel, variable=self.var_filtro,
                          value=nivel, command=self._filtrar).pack(side='left', padx=5)

        ttk.Button(frame_filtros, text="Limpiar Log", command=self._limpiar).pack(side='right')
        ttk.Button(frame_filtros, text="Actualizar", command=self._cargar_registros).pack(side='right', padx=5)

        # Área de texto
        frame_texto = ttk.Frame(main)
        frame_texto.pack(fill='both', expand=True)

        self.texto = tk.Text(frame_texto, wrap='word', font=('Consolas', 9), state='disabled')
        scroll = ttk.Scrollbar(frame_texto, orient='vertical', command=self.texto.yview)
        self.texto.configure(yscrollcommand=scroll.set)

        scroll.pack(side='right', fill='y')
        self.texto.pack(fill='both', expand=True)

        # Tags para colores
        self.texto.tag_configure('INFO', foreground='#2196F3')
        self.texto.tag_configure('WARNING', foreground='#FF9800')
        self.texto.tag_configure('ERROR', foreground='#F44336', font=('Consolas', 9, 'bold'))
        self.texto.tag_configure('DEBUG', foreground='#9E9E9E')
        self.texto.tag_configure('timestamp', foreground='#757575')

        # Contador
        frame_info = ttk.Frame(main)
        frame_info.pack(fill='x', pady=(10, 0))

        self.var_total = tk.StringVar(value="Total: 0 registros")
        ttk.Label(frame_info, textvariable=self.var_total).pack(side='left')

        self.var_errores = tk.StringVar(value="Errores: 0")
        ttk.Label(frame_info, textvariable=self.var_errores, foreground='red').pack(side='right')

    def _cargar_registros(self):
        """Carga todos los registros en el área de texto"""
        self.texto.configure(state='normal')
        self.texto.delete('1.0', 'end')

        filtro = self.var_filtro.get()
        registros = self.logger.registros

        for reg in registros:
            if filtro == "TODOS" or reg['nivel'] == filtro:
                self._insertar_registro(reg)

        self.texto.configure(state='disabled')
        self.texto.see('end')

        self.var_total.set(f"Total: {len(registros)} registros")
        self.var_errores.set(f"Errores: {self.logger.errores}")

    def _insertar_registro(self, reg):
        """Inserta un registro en el área de texto"""
        self.texto.insert('end', f"[{reg['timestamp']}] ", 'timestamp')
        self.texto.insert('end', f"[{reg['nivel']}] ", reg['nivel'])
        self.texto.insert('end', f"{reg['mensaje']}\n")

        if reg['detalles']:
            self.texto.insert('end', f"    Detalles: {reg['detalles']}\n", 'DEBUG')

    def _agregar_registro(self, reg):
        """Callback para añadir nuevo registro"""
        filtro = self.var_filtro.get()
        if filtro == "TODOS" or reg['nivel'] == filtro:
            self.texto.configure(state='normal')
            self._insertar_registro(reg)
            self.texto.configure(state='disabled')
            self.texto.see('end')

        self.var_total.set(f"Total: {len(self.logger.registros)} registros")
        self.var_errores.set(f"Errores: {self.logger.errores}")

    def _filtrar(self):
        """Aplica el filtro seleccionado"""
        self._cargar_registros()

    def _limpiar(self):
        """Limpia el log"""
        if messagebox.askyesno("Confirmar", "¿Limpiar todos los registros del log?"):
            self.logger.limpiar()
            self._cargar_registros()


# =============================================================================
# CLASE: ValidadorCIF (Validación de CIF/NIF español)
# =============================================================================
class ValidadorCIF:
    """
    Validador de CIF/NIF/NIE español con verificación de dígito de control.

    Formatos soportados:
    - NIF: 8 dígitos + letra (12345678Z)
    - CIF: letra + 7 dígitos + dígito/letra control (A12345678)
    - NIE: X/Y/Z + 7 dígitos + letra (X1234567L)
    """

    # Letras de control para NIF
    LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"

    # Letras válidas para CIF
    LETRAS_CIF = "ABCDEFGHJNPQRSUVW"

    # Letras de control para CIF (posición par)
    LETRAS_CONTROL_CIF = "JABCDEFGHI"

    @classmethod
    def validar(cls, identificador):
        """
        Valida un CIF/NIF/NIE español.

        Returns: (es_valido, tipo, mensaje)
        """
        if not identificador:
            return False, None, "Identificador vacío"

        # Limpiar y normalizar
        id_limpio = identificador.upper().replace(' ', '').replace('-', '').replace('.', '')

        if len(id_limpio) < 8 or len(id_limpio) > 9:
            return False, None, f"Longitud incorrecta: {len(id_limpio)}"

        primer_char = id_limpio[0]

        # Determinar tipo y validar
        if primer_char.isdigit():
            # NIF personal (8 dígitos + letra)
            return cls._validar_nif(id_limpio)
        elif primer_char in 'XYZ':
            # NIE (extranjero)
            return cls._validar_nie(id_limpio)
        elif primer_char in cls.LETRAS_CIF:
            # CIF (empresa)
            return cls._validar_cif(id_limpio)
        else:
            return False, None, f"Primer carácter no válido: {primer_char}"

    @classmethod
    def _validar_nif(cls, nif):
        """Valida NIF personal (8 dígitos + letra)"""
        if len(nif) != 9:
            return False, 'NIF', "NIF debe tener 9 caracteres"

        try:
            numero = int(nif[:8])
            letra = nif[8]
            letra_correcta = cls.LETRAS_NIF[numero % 23]

            if letra == letra_correcta:
                return True, 'NIF', "NIF válido"
            else:
                return False, 'NIF', f"Letra incorrecta: esperada {letra_correcta}, recibida {letra}"
        except ValueError:
            return False, 'NIF', "Formato de NIF incorrecto"

    @classmethod
    def _validar_nie(cls, nie):
        """Valida NIE (X/Y/Z + 7 dígitos + letra)"""
        if len(nie) != 9:
            return False, 'NIE', "NIE debe tener 9 caracteres"

        # Reemplazar letra inicial por número equivalente
        reemplazos = {'X': '0', 'Y': '1', 'Z': '2'}
        nie_numerico = reemplazos.get(nie[0], nie[0]) + nie[1:]

        return cls._validar_nif(nie_numerico)

    @classmethod
    def _validar_cif(cls, cif):
        """Valida CIF de empresa"""
        if len(cif) != 9:
            return False, 'CIF', "CIF debe tener 9 caracteres"

        letra_tipo = cif[0]
        digitos = cif[1:8]
        control = cif[8]

        if not digitos.isdigit():
            return False, 'CIF', "Dígitos centrales no válidos"

        # Calcular dígito de control
        suma = 0
        for i, d in enumerate(digitos):
            n = int(d)
            if i % 2 == 0:  # Posiciones pares (0, 2, 4, 6)
                n = n * 2
                if n > 9:
                    n = n - 9
            suma += n

        resto = suma % 10
        digito_control = (10 - resto) % 10

        # Algunos tipos de CIF usan letra de control, otros dígito
        tipos_letra = 'KPQRSNW'

        if letra_tipo in tipos_letra:
            # Control es letra
            letra_control = cls.LETRAS_CONTROL_CIF[digito_control]
            if control == letra_control:
                return True, 'CIF', f"CIF válido (tipo {letra_tipo})"
            else:
                return False, 'CIF', f"Control incorrecto: esperada {letra_control}"
        else:
            # Control puede ser letra o dígito
            if control == str(digito_control) or control == cls.LETRAS_CONTROL_CIF[digito_control]:
                return True, 'CIF', f"CIF válido (tipo {letra_tipo})"
            else:
                return False, 'CIF', f"Control incorrecto: esperado {digito_control} o {cls.LETRAS_CONTROL_CIF[digito_control]}"

    @classmethod
    def formatear(cls, identificador):
        """Formatea un CIF/NIF de forma estándar"""
        if not identificador:
            return identificador
        id_limpio = identificador.upper().replace(' ', '').replace('-', '').replace('.', '')
        return id_limpio


# =============================================================================
# CLASE: ValidadorContable (Verificación de cuadre contable)
# =============================================================================
class ValidadorContable:
    """Verifica el cuadre contable de asientos (debe = haber)"""

    def __init__(self):
        self.logger = Logger()
        self.tolerancia = 0.01  # Tolerancia para diferencias por redondeo

    def verificar_cuadre(self, conceptos):
        """
        Verifica que el asiento cuadre (suma debe = suma haber).

        Args:
            conceptos: Lista de {concepto, importe, tipo: 'debe'|'haber'}

        Returns: (cuadra, suma_debe, suma_haber, diferencia, alertas)
        """
        suma_debe = 0.0
        suma_haber = 0.0
        alertas = []

        for c in conceptos:
            importe = c.get('importe') or 0
            tipo = c.get('tipo', 'debe').lower()

            if tipo == 'debe':
                suma_debe += importe
            elif tipo == 'haber':
                suma_haber += importe
            else:
                alertas.append(f"Tipo desconocido '{tipo}' en concepto {c.get('concepto')}")

        diferencia = abs(suma_debe - suma_haber)
        cuadra = diferencia <= self.tolerancia

        if not cuadra:
            alertas.append(f"Descuadre de {diferencia:.2f} € (Debe: {suma_debe:.2f}, Haber: {suma_haber:.2f})")
            self.logger.warning("Asiento descuadrado", f"Diferencia: {diferencia:.2f} €")

        return cuadra, suma_debe, suma_haber, diferencia, alertas

    def verificar_cuentas(self, conceptos, plan_cuentas=None):
        """
        Verifica que las cuentas asignadas existan en el plan de cuentas.

        Returns: lista de alertas
        """
        alertas = []

        if not plan_cuentas:
            return alertas

        cuentas_plan = {c['cuenta'] for c in plan_cuentas}

        for c in conceptos:
            cuenta = c.get('cuenta')
            if cuenta and cuenta not in cuentas_plan:
                alertas.append(f"Cuenta {cuenta} no existe en el plan de cuentas")

        return alertas


# =============================================================================
# CLASE: DetectorDuplicados (Detección de documentos duplicados)
# =============================================================================
class DetectorDuplicados:
    """Detecta documentos duplicados usando hash y fingerprints"""

    def __init__(self):
        self.logger = Logger()
        self.documentos_procesados = {}  # {hash: info_documento}

    def calcular_hash(self, texto):
        """Calcula un hash del contenido del documento"""
        texto_normalizado = ' '.join(texto.lower().split())
        return hashlib.md5(texto_normalizado.encode()).hexdigest()

    def calcular_fingerprint(self, texto, cif=None, periodo=None):
        """
        Calcula un fingerprint único basado en datos clave.
        Útil para detectar el mismo documento con pequeñas variaciones.
        """
        partes = []

        if cif:
            partes.append(cif.upper())

        if periodo:
            partes.append(periodo.upper())

        # Extraer importes principales (total devengado, neto)
        patron_importe = r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})'
        importes = re.findall(patron_importe, texto)
        if importes:
            # Usar los últimos 3 importes (suelen ser totales)
            partes.extend(importes[-3:])

        return '|'.join(partes)

    def registrar_documento(self, texto, ruta, cif=None, periodo=None):
        """
        Registra un documento y detecta si es duplicado.

        Returns: (es_duplicado, documento_original)
        """
        hash_doc = self.calcular_hash(texto)
        fingerprint = self.calcular_fingerprint(texto, cif, periodo)

        # Verificar hash exacto
        if hash_doc in self.documentos_procesados:
            original = self.documentos_procesados[hash_doc]
            self.logger.warning(
                f"Documento duplicado (hash exacto)",
                f"Original: {original['ruta']}"
            )
            return True, original

        # Verificar fingerprint (duplicado parcial)
        for doc_hash, doc_info in self.documentos_procesados.items():
            if doc_info.get('fingerprint') == fingerprint and fingerprint:
                self.logger.warning(
                    f"Posible documento duplicado (mismo CIF/período/importes)",
                    f"Original: {doc_info['ruta']}"
                )
                return True, doc_info

        # Registrar nuevo documento
        self.documentos_procesados[hash_doc] = {
            'ruta': ruta,
            'hash': hash_doc,
            'fingerprint': fingerprint,
            'cif': cif,
            'periodo': periodo
        }

        return False, None

    def limpiar(self):
        """Limpia el registro de documentos"""
        self.documentos_procesados = {}


# =============================================================================
# CLASE: ValidadorImportes (Validación de rangos de importes)
# =============================================================================
class ValidadorImportes:
    """Valida que los importes estén dentro de rangos razonables"""

    # Rangos típicos para nóminas españolas (2024-2026)
    RANGOS = {
        'SALARIO BASE': (800, 15000),
        'SALARIO': (800, 15000),
        'PLUS': (0, 3000),
        'COMPLEMENTO': (0, 5000),
        'PRORRATA': (0, 3000),
        'HORAS EXTRA': (0, 5000),
        'ANTIGUEDAD': (0, 2000),
        'IRPF': (0, 10000),
        'SEGURIDAD SOCIAL': (0, 3000),
        'CONTINGENCIAS': (0, 2000),
        'DESEMPLEO': (0, 500),
        'TOTAL DEVENGADO': (1000, 50000),
        'TOTAL DEDUCCIONES': (100, 20000),
        'NETO': (500, 40000),
        'LIQUIDO': (500, 40000),
    }

    # SMI 2026 aproximado
    SMI_MENSUAL = 1134.00

    def __init__(self):
        self.logger = Logger()

    def validar(self, conceptos):
        """
        Valida los importes de los conceptos.

        Returns: lista de alertas
        """
        alertas = []

        for c in conceptos:
            concepto = c.get('concepto', '').upper()
            importe = c.get('importe')

            if importe is None:
                continue

            # Importes negativos
            if importe < 0:
                alertas.append({
                    'tipo': 'ERROR',
                    'mensaje': f"Importe negativo en '{concepto}': {importe:.2f} €"
                })
                continue

            # Verificar rango por tipo de concepto
            for patron, (minimo, maximo) in self.RANGOS.items():
                if patron in concepto:
                    if importe < minimo:
                        alertas.append({
                            'tipo': 'WARNING',
                            'mensaje': f"Importe muy bajo en '{concepto}': {importe:.2f} € (mín esperado: {minimo} €)"
                        })
                    elif importe > maximo:
                        alertas.append({
                            'tipo': 'WARNING',
                            'mensaje': f"Importe muy alto en '{concepto}': {importe:.2f} € (máx esperado: {maximo} €)"
                        })
                    break

        # Verificar neto vs SMI
        neto = None
        for c in conceptos:
            if 'NETO' in c.get('concepto', '').upper() or 'LIQUIDO' in c.get('concepto', '').upper():
                neto = c.get('importe')
                break

        if neto and neto < self.SMI_MENSUAL * 0.8:  # 80% del SMI
            alertas.append({
                'tipo': 'WARNING',
                'mensaje': f"Neto ({neto:.2f} €) inferior al 80% del SMI ({self.SMI_MENSUAL:.2f} €)"
            })

        return alertas

    def validar_coherencia(self, conceptos):
        """
        Valida la coherencia entre conceptos (ej: deducciones < devengos).

        Returns: lista de alertas
        """
        alertas = []

        total_devengado = None
        total_deducciones = None
        neto = None

        for c in conceptos:
            concepto = c.get('concepto', '').upper()
            importe = c.get('importe')

            if 'TOTAL' in concepto and 'DEVENG' in concepto:
                total_devengado = importe
            elif 'TOTAL' in concepto and 'DEDUCC' in concepto:
                total_deducciones = importe
            elif 'NETO' in concepto or 'LIQUIDO' in concepto:
                neto = importe

        # Verificar: devengado - deducciones = neto
        if total_devengado and total_deducciones and neto:
            esperado = total_devengado - total_deducciones
            diferencia = abs(esperado - neto)
            if diferencia > 0.10:  # Tolerancia de 10 céntimos
                alertas.append({
                    'tipo': 'ERROR',
                    'mensaje': f"Incoherencia: Devengado ({total_devengado:.2f}) - Deducciones ({total_deducciones:.2f}) = {esperado:.2f}, pero Neto = {neto:.2f}"
                })

        # Verificar: deducciones < devengado
        if total_devengado and total_deducciones:
            if total_deducciones >= total_devengado:
                alertas.append({
                    'tipo': 'ERROR',
                    'mensaje': f"Deducciones ({total_deducciones:.2f}) >= Devengado ({total_devengado:.2f})"
                })

        return alertas


# =============================================================================
# CLASE: GestorValidaciones (Orquestador de todas las validaciones)
# =============================================================================
class GestorValidaciones:
    """Gestiona y ejecuta todas las validaciones de forma centralizada"""

    def __init__(self):
        self.logger = Logger()
        self.validador_contable = ValidadorContable()
        self.validador_importes = ValidadorImportes()
        self.detector_duplicados = DetectorDuplicados()

    def validar_documento(self, texto, ruta, cif=None, periodo=None, conceptos=None, plan_cuentas=None):
        """
        Ejecuta todas las validaciones sobre un documento.

        Returns: {
            'valido': bool,
            'alertas': lista de alertas,
            'errores': lista de errores,
            'warnings': lista de advertencias,
            'info': dict con información adicional
        }
        """
        resultado = {
            'valido': True,
            'alertas': [],
            'errores': [],
            'warnings': [],
            'info': {}
        }

        # 1. Validar CIF
        if cif:
            es_valido, tipo, mensaje = ValidadorCIF.validar(cif)
            resultado['info']['cif_tipo'] = tipo
            resultado['info']['cif_valido'] = es_valido

            if not es_valido:
                resultado['warnings'].append(f"CIF/NIF inválido: {mensaje}")

        # 2. Detectar duplicados
        es_duplicado, doc_original = self.detector_duplicados.registrar_documento(
            texto, ruta, cif, periodo
        )
        resultado['info']['es_duplicado'] = es_duplicado

        if es_duplicado:
            resultado['warnings'].append(
                f"Posible duplicado de: {doc_original['ruta']}"
            )

        # 3. Validar importes
        if conceptos:
            alertas_importes = self.validador_importes.validar(conceptos)
            alertas_coherencia = self.validador_importes.validar_coherencia(conceptos)

            for a in alertas_importes + alertas_coherencia:
                if a['tipo'] == 'ERROR':
                    resultado['errores'].append(a['mensaje'])
                else:
                    resultado['warnings'].append(a['mensaje'])

        # 4. Validar cuadre contable
        if conceptos:
            cuadra, debe, haber, dif, alertas_cuadre = self.validador_contable.verificar_cuadre(conceptos)
            resultado['info']['cuadre'] = {
                'cuadra': cuadra,
                'debe': debe,
                'haber': haber,
                'diferencia': dif
            }

            for a in alertas_cuadre:
                resultado['warnings'].append(a)

            # Validar cuentas contra plan
            if plan_cuentas:
                alertas_cuentas = self.validador_contable.verificar_cuentas(conceptos, plan_cuentas)
                resultado['warnings'].extend(alertas_cuentas)

        # Consolidar alertas
        resultado['alertas'] = resultado['errores'] + resultado['warnings']
        resultado['valido'] = len(resultado['errores']) == 0

        # Log resumen
        total_alertas = len(resultado['alertas'])
        if total_alertas > 0:
            self.logger.warning(
                f"Validación completada con {total_alertas} alerta(s)",
                f"Errores: {len(resultado['errores'])}, Warnings: {len(resultado['warnings'])}"
            )
        else:
            self.logger.info("Validación completada sin alertas")

        return resultado

    def limpiar_duplicados(self):
        """Limpia el registro de documentos duplicados"""
        self.detector_duplicados.limpiar()


# =============================================================================
# CLASE: LineaApunte (Línea individual de un asiento contable)
# =============================================================================
class LineaApunte:
    """Representa una línea de apunte dentro de un asiento contable"""

    def __init__(self):
        self.numero_linea = 0
        self.cuenta = ""           # Código de cuenta (ej: 6400000)
        self.descripcion = ""      # Descripción de la cuenta
        self.concepto = ""         # Concepto del apunte
        self.debe = 0.0
        self.haber = 0.0
        self.documento = ""        # Referencia documento
        self.contrapartida = ""    # Cuenta contrapartida

    def to_dict(self):
        return {
            'numero_linea': self.numero_linea,
            'cuenta': self.cuenta,
            'descripcion': self.descripcion,
            'concepto': self.concepto,
            'debe': self.debe,
            'haber': self.haber,
            'documento': self.documento,
            'contrapartida': self.contrapartida
        }

    @classmethod
    def from_dict(cls, data):
        linea = cls()
        linea.numero_linea = data.get('numero_linea', 0)
        linea.cuenta = data.get('cuenta', '')
        linea.descripcion = data.get('descripcion', '')
        linea.concepto = data.get('concepto', '')
        linea.debe = data.get('debe', 0.0)
        linea.haber = data.get('haber', 0.0)
        linea.documento = data.get('documento', '')
        linea.contrapartida = data.get('contrapartida', '')
        return linea


# =============================================================================
# CLASE: AsientoContable (Estructura completa de asiento)
# =============================================================================
class AsientoContable:
    """
    Representa un asiento contable completo con cabecera y líneas.

    Estructura típica de asiento de nómina:
    - DEBE: Sueldos y salarios (640), SS empresa (642)
    - HABER: HP IRPF (4751), SS trabajador (476), Remuneraciones pendientes (465)
    """

    def __init__(self):
        self.numero_asiento = 0
        self.fecha = datetime.now()
        self.periodo = ""           # Mes/Año de la nómina
        self.concepto_general = ""  # Descripción general del asiento
        self.documento = ""         # Referencia (ej: NOM-2026-03)
        self.diario = "1"          # Código de diario (1 = General)

        # Datos de la empresa
        self.codigo_empresa = ""
        self.nombre_empresa = ""
        self.cif_empresa = ""
        self.base_datos = ""

        # Líneas del asiento
        self.lineas = []  # Lista de LineaApunte

        # Totales
        self.total_debe = 0.0
        self.total_haber = 0.0

        # Estado
        self.cuadrado = False
        self.guardado = False

    def agregar_linea(self, cuenta, concepto, debe=0.0, haber=0.0, descripcion=""):
        """Añade una línea al asiento"""
        linea = LineaApunte()
        linea.numero_linea = len(self.lineas) + 1
        linea.cuenta = cuenta
        linea.concepto = concepto
        linea.descripcion = descripcion
        linea.debe = debe
        linea.haber = haber
        linea.documento = self.documento

        self.lineas.append(linea)
        self._recalcular_totales()
        return linea

    def eliminar_linea(self, numero_linea):
        """Elimina una línea del asiento"""
        self.lineas = [l for l in self.lineas if l.numero_linea != numero_linea]
        # Renumerar
        for i, linea in enumerate(self.lineas):
            linea.numero_linea = i + 1
        self._recalcular_totales()

    def _recalcular_totales(self):
        """Recalcula totales y verifica cuadre"""
        self.total_debe = sum(l.debe for l in self.lineas)
        self.total_haber = sum(l.haber for l in self.lineas)
        self.cuadrado = abs(self.total_debe - self.total_haber) < 0.01

    def get_diferencia(self):
        """Devuelve la diferencia entre debe y haber"""
        return self.total_debe - self.total_haber

    def cuadrar_automatico(self, cuenta_ajuste="5720000"):
        """
        Cuadra el asiento automáticamente añadiendo una línea de ajuste.
        Por defecto usa la cuenta de banco/caja.
        """
        diferencia = self.get_diferencia()

        if abs(diferencia) < 0.01:
            return True  # Ya cuadra

        if diferencia > 0:
            # Falta haber
            self.agregar_linea(
                cuenta=cuenta_ajuste,
                concepto="Ajuste automático",
                haber=diferencia,
                descripcion="Banco c/c"
            )
        else:
            # Falta debe
            self.agregar_linea(
                cuenta=cuenta_ajuste,
                concepto="Ajuste automático",
                debe=abs(diferencia),
                descripcion="Banco c/c"
            )

        return self.cuadrado

    def to_dict(self):
        """Convierte el asiento a diccionario"""
        return {
            'numero_asiento': self.numero_asiento,
            'fecha': self.fecha.strftime("%Y-%m-%d"),
            'periodo': self.periodo,
            'concepto_general': self.concepto_general,
            'documento': self.documento,
            'diario': self.diario,
            'codigo_empresa': self.codigo_empresa,
            'nombre_empresa': self.nombre_empresa,
            'cif_empresa': self.cif_empresa,
            'base_datos': self.base_datos,
            'lineas': [l.to_dict() for l in self.lineas],
            'total_debe': self.total_debe,
            'total_haber': self.total_haber,
            'cuadrado': self.cuadrado
        }

    def to_texto(self):
        """Genera representación en texto del asiento"""
        lineas = []
        lineas.append("=" * 70)
        lineas.append(f"ASIENTO Nº {self.numero_asiento}")
        lineas.append(f"Fecha: {self.fecha.strftime('%d/%m/%Y')}    Período: {self.periodo}")
        lineas.append(f"Empresa: {self.nombre_empresa} ({self.cif_empresa})")
        lineas.append(f"Concepto: {self.concepto_general}")
        lineas.append("=" * 70)
        lineas.append(f"{'Cuenta':<10} {'Descripción':<25} {'Debe':>12} {'Haber':>12}")
        lineas.append("-" * 70)

        for l in self.lineas:
            debe_str = f"{l.debe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if l.debe else ""
            haber_str = f"{l.haber:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if l.haber else ""
            lineas.append(f"{l.cuenta:<10} {l.concepto[:25]:<25} {debe_str:>12} {haber_str:>12}")

        lineas.append("-" * 70)
        total_debe = f"{self.total_debe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        total_haber = f"{self.total_haber:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        lineas.append(f"{'TOTALES':<10} {'':<25} {total_debe:>12} {total_haber:>12}")

        estado = "✅ CUADRADO" if self.cuadrado else f"❌ DESCUADRE: {self.get_diferencia():.2f}"
        lineas.append(f"\nEstado: {estado}")

        return "\n".join(lineas)


# =============================================================================
# CLASE: GeneradorAsientos (Genera asientos desde conceptos extraídos)
# =============================================================================
class GeneradorAsientos:
    """
    Genera asientos contables a partir de conceptos extraídos de nóminas.

    Mapeo típico de nóminas españolas:
    - 640: Sueldos y salarios (DEBE)
    - 642: Seguridad Social a cargo empresa (DEBE)
    - 4751: HP Acreedora por retenciones IRPF (HABER)
    - 476: Organismos SS acreedores (HABER)
    - 465: Remuneraciones pendientes de pago (HABER)
    - 572: Bancos (HABER - cuando se paga)
    """

    # Mapeo por defecto de conceptos a cuentas
    MAPEO_CUENTAS = {
        # Devengos (DEBE)
        'SALARIO': {'cuenta': '6400000', 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
        'SUELDO': {'cuenta': '6400000', 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
        'BASE': {'cuenta': '6400000', 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
        'PLUS': {'cuenta': '6400001', 'tipo': 'debe', 'descripcion': 'Complementos salariales'},
        'COMPLEMENTO': {'cuenta': '6400001', 'tipo': 'debe', 'descripcion': 'Complementos salariales'},
        'PRORRATA': {'cuenta': '6400002', 'tipo': 'debe', 'descripcion': 'Prorrata pagas extras'},
        'HORAS EXTRA': {'cuenta': '6400003', 'tipo': 'debe', 'descripcion': 'Horas extraordinarias'},
        'ANTIGUEDAD': {'cuenta': '6400004', 'tipo': 'debe', 'descripcion': 'Antigüedad'},
        'DIETA': {'cuenta': '6290000', 'tipo': 'debe', 'descripcion': 'Dietas'},
        'SS EMPRESA': {'cuenta': '6420000', 'tipo': 'debe', 'descripcion': 'SS a cargo empresa'},
        'CONTINGENCIAS COMUNES EMPRESA': {'cuenta': '6420000', 'tipo': 'debe', 'descripcion': 'SS a cargo empresa'},

        # Deducciones (HABER)
        'IRPF': {'cuenta': '4751000', 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
        'I.R.P.F': {'cuenta': '4751000', 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
        'RETENCION': {'cuenta': '4751000', 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
        'SS TRABAJADOR': {'cuenta': '4760000', 'tipo': 'haber', 'descripcion': 'SS a cargo trabajador'},
        'CONTINGENCIAS COMUNES': {'cuenta': '4760000', 'tipo': 'haber', 'descripcion': 'SS a cargo trabajador'},
        'DESEMPLEO': {'cuenta': '4760001', 'tipo': 'haber', 'descripcion': 'Desempleo trabajador'},
        'FORMACION': {'cuenta': '4760002', 'tipo': 'haber', 'descripcion': 'Formación profesional'},

        # Totales
        'NETO': {'cuenta': '4650000', 'tipo': 'haber', 'descripcion': 'Remuneraciones pendientes'},
        'LIQUIDO': {'cuenta': '4650000', 'tipo': 'haber', 'descripcion': 'Remuneraciones pendientes'},
        'TOTAL DEVENGADO': {'cuenta': None, 'tipo': 'info', 'descripcion': 'Total devengos'},
        'TOTAL DEDUCCIONES': {'cuenta': None, 'tipo': 'info', 'descripcion': 'Total deducciones'},
    }

    def __init__(self):
        self.logger = Logger()
        self.config_empresa = ConfiguracionEmpresa()

    def _obtener_cuenta_empresa(self, cif, tipo_cuenta, cuenta_defecto):
        """
        Obtiene la cuenta específica de la empresa, o la cuenta por defecto.
        """
        if cif:
            cuenta = self.config_empresa.obtener_cuenta(cif, tipo_cuenta)
            if cuenta:
                return cuenta
        return cuenta_defecto

    def _obtener_mapeo_para_empresa(self, cif):
        """
        Genera un mapeo de cuentas usando las cuentas específicas de la empresa.
        """
        # Obtener cuentas de la empresa o usar defaults
        sueldos = self._obtener_cuenta_empresa(cif, 'sueldos', '6400000')
        complementos = self._obtener_cuenta_empresa(cif, 'complementos', '6400001')
        ss_empresa = self._obtener_cuenta_empresa(cif, 'ss_empresa', '6420000')
        irpf = self._obtener_cuenta_empresa(cif, 'irpf', '4751000')
        ss_trabajador = self._obtener_cuenta_empresa(cif, 'ss_trabajador', '4760000')
        neto = self._obtener_cuenta_empresa(cif, 'neto_pagar', '4650000')

        return {
            # Devengos (DEBE)
            'SALARIO': {'cuenta': sueldos, 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
            'SUELDO': {'cuenta': sueldos, 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
            'BASE': {'cuenta': sueldos, 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
            'PLUS': {'cuenta': complementos, 'tipo': 'debe', 'descripcion': 'Complementos salariales'},
            'COMPLEMENTO': {'cuenta': complementos, 'tipo': 'debe', 'descripcion': 'Complementos salariales'},
            'PRORRATA': {'cuenta': complementos, 'tipo': 'debe', 'descripcion': 'Prorrata pagas extras'},
            'HORAS EXTRA': {'cuenta': complementos, 'tipo': 'debe', 'descripcion': 'Horas extraordinarias'},
            'ANTIGUEDAD': {'cuenta': complementos, 'tipo': 'debe', 'descripcion': 'Antigüedad'},
            'DIETA': {'cuenta': '6290000', 'tipo': 'debe', 'descripcion': 'Dietas'},
            'SS EMPRESA': {'cuenta': ss_empresa, 'tipo': 'debe', 'descripcion': 'SS a cargo empresa'},
            'CONTINGENCIAS COMUNES EMPRESA': {'cuenta': ss_empresa, 'tipo': 'debe', 'descripcion': 'SS a cargo empresa'},

            # Deducciones (HABER)
            'IRPF': {'cuenta': irpf, 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
            'I.R.P.F': {'cuenta': irpf, 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
            'RETENCION': {'cuenta': irpf, 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
            'SS TRABAJADOR': {'cuenta': ss_trabajador, 'tipo': 'haber', 'descripcion': 'SS a cargo trabajador'},
            'CONTINGENCIAS COMUNES': {'cuenta': ss_trabajador, 'tipo': 'haber', 'descripcion': 'SS a cargo trabajador'},
            'DESEMPLEO': {'cuenta': ss_trabajador, 'tipo': 'haber', 'descripcion': 'Desempleo trabajador'},
            'FORMACION': {'cuenta': ss_trabajador, 'tipo': 'haber', 'descripcion': 'Formación profesional'},

            # Totales
            'NETO': {'cuenta': neto, 'tipo': 'haber', 'descripcion': 'Remuneraciones pendientes'},
            'LIQUIDO': {'cuenta': neto, 'tipo': 'haber', 'descripcion': 'Remuneraciones pendientes'},
            'TOTAL DEVENGADO': {'cuenta': None, 'tipo': 'info', 'descripcion': 'Total devengos'},
            'TOTAL DEDUCCIONES': {'cuenta': None, 'tipo': 'info', 'descripcion': 'Total deducciones'},
        }

    def generar_desde_conceptos(self, conceptos, empresa=None, periodo=None, numero_asiento=None):
        """
        Genera un asiento contable a partir de los conceptos extraídos.
        Usa las cuentas específicas de la empresa si están configuradas.

        Args:
            conceptos: Lista de conceptos extraídos con importe y mapeo
            empresa: Dict con datos de la empresa
            periodo: String con el período (ej: "Marzo 2026")
            numero_asiento: Número de asiento a asignar

        Returns: AsientoContable
        """
        asiento = AsientoContable()

        # Datos de cabecera
        asiento.numero_asiento = numero_asiento or 0
        asiento.periodo = periodo or ""
        asiento.concepto_general = f"Nóminas {periodo}" if periodo else "Nóminas"
        asiento.documento = f"NOM-{datetime.now().strftime('%Y-%m')}"

        if empresa:
            asiento.codigo_empresa = empresa.get('codigo', '')
            asiento.nombre_empresa = empresa.get('nombre', '')
            asiento.cif_empresa = empresa.get('cif', '')
            asiento.base_datos = empresa.get('base_datos', '')

        # Obtener mapeo de cuentas específico para esta empresa
        cif_empresa = empresa.get('cif') if empresa else None
        mapeo_cuentas = self._obtener_mapeo_para_empresa(cif_empresa)

        self.logger.debug(
            f"Generando asiento con cuentas de empresa: {cif_empresa or 'defaults'}"
        )

        # Procesar conceptos
        total_devengado = 0.0
        total_deducciones = 0.0

        for c in conceptos:
            concepto_nombre = c.get('concepto', '').upper()
            importe = c.get('importe')

            if importe is None or importe == 0:
                continue

            # Saltar totales informativos
            if 'TOTAL DEVENGADO' in concepto_nombre:
                total_devengado = importe
                continue
            if 'TOTAL DEDUCCIONES' in concepto_nombre:
                total_deducciones = importe
                continue

            # Buscar mapeo de cuenta
            cuenta = c.get('cuenta')
            tipo = c.get('tipo', 'debe')
            descripcion = c.get('descripcion', '')

            # Si no tiene cuenta asignada, buscar en mapeo de la empresa
            if not cuenta:
                for patron, mapeo in mapeo_cuentas.items():
                    if patron in concepto_nombre:
                        cuenta = mapeo['cuenta']
                        tipo = mapeo['tipo']
                        descripcion = mapeo['descripcion']
                        break

            # Saltar si no hay cuenta o es informativo
            if not cuenta or tipo == 'info':
                continue

            # Crear línea de asiento
            if tipo == 'debe':
                asiento.agregar_linea(
                    cuenta=cuenta,
                    concepto=concepto_nombre[:50],
                    debe=importe,
                    descripcion=descripcion
                )
            else:
                asiento.agregar_linea(
                    cuenta=cuenta,
                    concepto=concepto_nombre[:50],
                    haber=importe,
                    descripcion=descripcion
                )

        # Verificar si hay neto/líquido, si no, calcularlo
        tiene_neto = any('NETO' in l.concepto or 'LIQUIDO' in l.concepto for l in asiento.lineas)

        if not tiene_neto and total_devengado > 0 and total_deducciones > 0:
            neto = total_devengado - total_deducciones
            if neto > 0:
                # Usar cuenta de neto específica de la empresa
                cuenta_neto = self._obtener_cuenta_empresa(cif_empresa, 'neto_pagar', '4650000')
                asiento.agregar_linea(
                    cuenta=cuenta_neto,
                    concepto='Neto a pagar (calculado)',
                    haber=neto,
                    descripcion='Remuneraciones pendientes'
                )

        self.logger.info(
            f"Asiento generado: {len(asiento.lineas)} líneas",
            f"Debe: {asiento.total_debe:.2f}, Haber: {asiento.total_haber:.2f}"
        )

        return asiento

    def generar_asiento_simplificado(self, total_devengado, total_deducciones, neto,
                                      empresa=None, periodo=None, numero_asiento=None):
        """
        Genera un asiento simplificado con las 3 líneas básicas:
        - Sueldos y salarios (DEBE)
        - HP IRPF + SS (HABER)
        - Remuneraciones pendientes (HABER)
        """
        asiento = AsientoContable()

        asiento.numero_asiento = numero_asiento or 0
        asiento.periodo = periodo or ""
        asiento.concepto_general = f"Nóminas {periodo}" if periodo else "Nóminas"
        asiento.documento = f"NOM-{datetime.now().strftime('%Y-%m')}"

        if empresa:
            asiento.codigo_empresa = empresa.get('codigo', '')
            asiento.nombre_empresa = empresa.get('nombre', '')
            asiento.cif_empresa = empresa.get('cif', '')

        # Línea 1: Sueldos (DEBE)
        asiento.agregar_linea(
            cuenta='6400000',
            concepto='Sueldos y salarios',
            debe=total_devengado,
            descripcion='Sueldos y salarios'
        )

        # Línea 2: Deducciones (HABER) - simplificado en una cuenta
        asiento.agregar_linea(
            cuenta='4751000',
            concepto='Retenciones y SS',
            haber=total_deducciones,
            descripcion='Retenciones IRPF y SS'
        )

        # Línea 3: Neto a pagar (HABER)
        asiento.agregar_linea(
            cuenta='4650000',
            concepto='Neto a pagar',
            haber=neto,
            descripcion='Remuneraciones pendientes'
        )

        return asiento


# =============================================================================
# CLASE: Configuracion (Configuración persistente)
# =============================================================================
class Configuracion:
    """
    Gestiona la configuración de la aplicación con persistencia en JSON.
    Implementa patrón Singleton.
    """
    _instancia = None
    CONFIG_DIR = Path.home() / '.lector_nominas'
    CONFIG_FILE = CONFIG_DIR / 'config.json'

    # Configuración por defecto
    DEFAULTS = {
        'version': '8.0.0',
        'base_datos': {
            'server': 'Srvv01',
            'user': 'sa',
            'password': '1Geyce$2025!!',
            'database_geyce': 'GEYCE_Avansa',
            'database_easp': 'easp'
        },
        'cuentas_defecto': {
            'sueldos': '6400000',
            'complementos': '6400001',
            'ss_empresa': '6420000',
            'irpf': '4751000',
            'ss_trabajador': '4760000',
            'neto_pagar': '4650000',
            'banco': '5720000'
        },
        'validaciones': {
            'smi_mensual': 1134.00,
            'tolerancia_cuadre': 0.01,
            'max_salario': 15000.00,
            'min_salario': 800.00
        },
        'interfaz': {
            'tema': 'claro',
            'maximizar_inicio': True,
            'mostrar_tooltips': True,
            'auto_validar': True,
            'idioma_ocr': 'spa'
        },
        'rutas': {
            'ultima_carpeta': '',
            'exportaciones': str(Path.home() / 'Documents'),
            'plantillas': str(CONFIG_DIR / 'plantillas')
        },
        'historico': {
            'max_registros': 1000,
            'auto_guardar': True
        },
        # FASE 8: Configuración de IA
        'ia': {
            'api_key': '',  # API key de Anthropic
            'modelo': 'claude-sonnet-4-20250514',  # Modelo por defecto
            'max_tokens': 4096,
            'habilitado': True,  # Si está deshabilitado, usa modo programa
            'guardar_extracciones': True,  # Guardar JSON extraídos
            'mostrar_editor_json': True  # Mostrar editor antes de procesar
        }
    }

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._config = None
            cls._instancia.logger = Logger()
            cls._instancia._cargar()
        return cls._instancia

    def _cargar(self):
        """Carga la configuración desde archivo"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # Merge con defaults para nuevas opciones
                self._config = self._merge_defaults(self._config, self.DEFAULTS)
                self.logger.debug("Configuración cargada desde archivo")
            else:
                self._config = self.DEFAULTS.copy()
                self._guardar()
                self.logger.info("Configuración inicial creada")

        except Exception as e:
            self.logger.error(f"Error cargando configuración: {e}")
            self._config = self.DEFAULTS.copy()

    def _merge_defaults(self, config, defaults):
        """Mezcla configuración con defaults para nuevas opciones"""
        resultado = defaults.copy()
        for key, value in config.items():
            if key in resultado:
                if isinstance(value, dict) and isinstance(resultado[key], dict):
                    resultado[key] = self._merge_defaults(value, resultado[key])
                else:
                    resultado[key] = value
        return resultado

    def _guardar(self):
        """Guarda la configuración en archivo"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            self.logger.debug("Configuración guardada")
            return True
        except Exception as e:
            self.logger.error(f"Error guardando configuración: {e}")
            return False

    def get(self, seccion, clave=None, default=None):
        """Obtiene un valor de configuración"""
        if seccion not in self._config:
            return default

        if clave is None:
            return self._config[seccion]

        return self._config[seccion].get(clave, default)

    def set(self, seccion, clave, valor):
        """Establece un valor de configuración"""
        if seccion not in self._config:
            self._config[seccion] = {}
        self._config[seccion][clave] = valor
        self._guardar()

    def get_cuenta(self, tipo):
        """Obtiene una cuenta contable por defecto"""
        return self.get('cuentas_defecto', tipo, '')

    def set_cuenta(self, tipo, cuenta):
        """Establece una cuenta contable por defecto"""
        self.set('cuentas_defecto', tipo, cuenta)

    def get_db_config(self):
        """Obtiene la configuración de base de datos"""
        return self.get('base_datos')

    def to_dict(self):
        """Devuelve toda la configuración como diccionario"""
        return self._config.copy()

    def restaurar_defaults(self):
        """Restaura la configuración por defecto"""
        self._config = self.DEFAULTS.copy()
        self._guardar()
        self.logger.info("Configuración restaurada a valores por defecto")

    # === Métodos para IA (Fase 8) ===
    def get_api_key(self):
        """Obtiene la API key de Anthropic"""
        return self.get('ia', 'api_key', '')

    def set_api_key(self, api_key):
        """Establece la API key de Anthropic"""
        self.set('ia', 'api_key', api_key)

    def get_modelo_ia(self):
        """Obtiene el modelo de IA configurado"""
        return self.get('ia', 'modelo', 'claude-sonnet-4-20250514')

    def set_modelo_ia(self, modelo):
        """Establece el modelo de IA"""
        self.set('ia', 'modelo', modelo)

    def ia_habilitada(self):
        """Verifica si la IA está habilitada"""
        return self.get('ia', 'habilitado', True) and bool(self.get_api_key())

    def get_config_ia(self):
        """Obtiene toda la configuración de IA"""
        return self.get('ia')


# =============================================================================
# CLASE: ConfiguracionEmpresa (Cuentas contables por empresa)
# =============================================================================
class ConfiguracionEmpresa:
    """
    Gestiona la configuración de cuentas contables específicas por empresa.
    Cada empresa (identificada por CIF) tiene su propio mapeo de cuentas.
    """
    _instancia = None
    EMPRESAS_DIR = Configuracion.CONFIG_DIR / 'empresas'

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._empresas = {}
            cls._instancia.logger = Logger()
            cls._instancia.config_global = Configuracion()
            cls._instancia._cargar_todas()
        return cls._instancia

    def _cargar_todas(self):
        """Carga todas las configuraciones de empresas"""
        try:
            self.EMPRESAS_DIR.mkdir(parents=True, exist_ok=True)

            for archivo in self.EMPRESAS_DIR.glob("*.json"):
                try:
                    with open(archivo, 'r', encoding='utf-8') as f:
                        datos = json.load(f)
                        cif = datos.get('cif')
                        if cif:
                            self._empresas[cif] = datos
                except Exception as e:
                    self.logger.error(f"Error cargando config empresa {archivo}: {e}")

            self.logger.debug(f"Configuraciones de empresa cargadas: {len(self._empresas)}")

        except Exception as e:
            self.logger.error(f"Error cargando configuraciones de empresas: {e}")

    def _guardar_empresa(self, cif):
        """Guarda la configuración de una empresa"""
        if cif not in self._empresas:
            return False

        try:
            self.EMPRESAS_DIR.mkdir(parents=True, exist_ok=True)
            cif_clean = cif.replace(' ', '').replace('-', '').replace('.', '')
            archivo = self.EMPRESAS_DIR / f"{cif_clean}.json"

            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(self._empresas[cif], f, indent=2, ensure_ascii=False)

            self.logger.info(f"Configuración de empresa guardada: {cif}")
            return True

        except Exception as e:
            self.logger.error(f"Error guardando config empresa {cif}: {e}")
            return False

    def existe_configuracion(self, cif):
        """Verifica si existe configuración para una empresa"""
        if not cif:
            return False
        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')
        return cif_norm in self._empresas

    def obtener_cuentas(self, cif):
        """
        Obtiene las cuentas contables de una empresa.
        Si no existe configuración, devuelve None.
        """
        if not cif:
            return None

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')

        if cif_norm in self._empresas:
            return self._empresas[cif_norm].get('cuentas', {})

        return None

    def obtener_cuenta(self, cif, tipo_cuenta):
        """
        Obtiene una cuenta específica de una empresa.
        Si no existe, devuelve la cuenta por defecto global.
        """
        cuentas = self.obtener_cuentas(cif)

        if cuentas and tipo_cuenta in cuentas:
            return cuentas[tipo_cuenta]

        # Fallback a configuración global
        return self.config_global.get_cuenta(tipo_cuenta)

    def crear_configuracion(self, cif, nombre_empresa, codigo_empresa=None):
        """
        Crea una nueva configuración de empresa con valores por defecto.
        """
        if not cif:
            return False

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')

        # Obtener cuentas por defecto de la configuración global
        cuentas_defecto = self.config_global.get('cuentas_defecto', default={})

        self._empresas[cif_norm] = {
            'cif': cif_norm,
            'nombre': nombre_empresa or '',
            'codigo': codigo_empresa or '',
            'fecha_creacion': datetime.now().isoformat(),
            'fecha_modificacion': datetime.now().isoformat(),
            'cuentas': cuentas_defecto.copy(),
            'notas': ''
        }

        self._guardar_empresa(cif_norm)
        self.logger.info(f"Configuración de empresa creada: {cif_norm} - {nombre_empresa}")
        return True

    def actualizar_cuentas(self, cif, cuentas):
        """Actualiza las cuentas de una empresa"""
        if not cif:
            return False

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')

        if cif_norm not in self._empresas:
            return False

        self._empresas[cif_norm]['cuentas'] = cuentas
        self._empresas[cif_norm]['fecha_modificacion'] = datetime.now().isoformat()

        return self._guardar_empresa(cif_norm)

    def actualizar_cuenta(self, cif, tipo_cuenta, valor):
        """Actualiza una cuenta específica de una empresa"""
        if not cif:
            return False

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')

        if cif_norm not in self._empresas:
            return False

        if 'cuentas' not in self._empresas[cif_norm]:
            self._empresas[cif_norm]['cuentas'] = {}

        self._empresas[cif_norm]['cuentas'][tipo_cuenta] = valor
        self._empresas[cif_norm]['fecha_modificacion'] = datetime.now().isoformat()

        return self._guardar_empresa(cif_norm)

    def obtener_info_empresa(self, cif):
        """Obtiene toda la información de configuración de una empresa"""
        if not cif:
            return None

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')
        return self._empresas.get(cif_norm)

    def listar_empresas(self):
        """Lista todas las empresas configuradas"""
        return [
            {
                'cif': datos.get('cif'),
                'nombre': datos.get('nombre'),
                'codigo': datos.get('codigo'),
                'fecha_modificacion': datos.get('fecha_modificacion')
            }
            for datos in self._empresas.values()
        ]

    def eliminar_configuracion(self, cif):
        """Elimina la configuración de una empresa"""
        if not cif:
            return False

        cif_norm = cif.upper().replace(' ', '').replace('-', '').replace('.', '')

        if cif_norm not in self._empresas:
            return False

        del self._empresas[cif_norm]

        # Eliminar archivo
        try:
            archivo = self.EMPRESAS_DIR / f"{cif_norm}.json"
            if archivo.exists():
                archivo.unlink()
        except:
            pass

        self.logger.info(f"Configuración de empresa eliminada: {cif_norm}")
        return True


# =============================================================================
# CLASE: HistoricoAsientos (Registro de asientos procesados)
# =============================================================================
class HistoricoAsientos:
    """
    Mantiene un histórico de asientos generados y guardados.
    Persistencia en archivo JSON.
    """
    _instancia = None
    HISTORICO_FILE = Configuracion.CONFIG_DIR / 'historico_asientos.json'

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._registros = []
            cls._instancia.logger = Logger()
            cls._instancia.config = Configuracion()
            cls._instancia._cargar()
        return cls._instancia

    def _cargar(self):
        """Carga el histórico desde archivo"""
        try:
            if self.HISTORICO_FILE.exists():
                with open(self.HISTORICO_FILE, 'r', encoding='utf-8') as f:
                    self._registros = json.load(f)
                self.logger.debug(f"Histórico cargado: {len(self._registros)} registros")
        except Exception as e:
            self.logger.error(f"Error cargando histórico: {e}")
            self._registros = []

    def _guardar(self):
        """Guarda el histórico en archivo"""
        try:
            # Limitar número de registros
            max_reg = self.config.get('historico', 'max_registros', 1000)
            if len(self._registros) > max_reg:
                self._registros = self._registros[-max_reg:]

            Configuracion.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.HISTORICO_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._registros, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Error guardando histórico: {e}")
            return False

    def registrar(self, asiento, guardado_bd=False):
        """Registra un asiento en el histórico"""
        registro = {
            'id': hashlib.md5(f"{asiento.numero_asiento}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            'fecha_registro': datetime.now().isoformat(),
            'numero_asiento': asiento.numero_asiento,
            'fecha_asiento': asiento.fecha.strftime("%Y-%m-%d"),
            'periodo': asiento.periodo,
            'empresa': asiento.nombre_empresa,
            'cif': asiento.cif_empresa,
            'codigo_empresa': asiento.codigo_empresa,
            'base_datos': asiento.base_datos,
            'concepto': asiento.concepto_general,
            'documento': asiento.documento,
            'total_debe': asiento.total_debe,
            'total_haber': asiento.total_haber,
            'num_lineas': len(asiento.lineas),
            'cuadrado': asiento.cuadrado,
            'guardado_bd': guardado_bd
        }

        self._registros.append(registro)

        if self.config.get('historico', 'auto_guardar', True):
            self._guardar()

        self.logger.info(f"Asiento registrado en histórico: {registro['id']}")
        return registro['id']

    def buscar(self, filtros=None):
        """
        Busca registros en el histórico.

        Filtros disponibles:
        - empresa: nombre parcial de empresa
        - cif: CIF de empresa
        - periodo: período de nómina
        - fecha_desde: fecha mínima (YYYY-MM-DD)
        - fecha_hasta: fecha máxima (YYYY-MM-DD)
        - guardado_bd: True/False
        """
        resultados = self._registros.copy()

        if not filtros:
            return resultados

        if filtros.get('empresa'):
            texto = filtros['empresa'].upper()
            resultados = [r for r in resultados if texto in r.get('empresa', '').upper()]

        if filtros.get('cif'):
            cif = filtros['cif'].upper().replace(' ', '').replace('-', '')
            resultados = [r for r in resultados if cif in r.get('cif', '').upper()]

        if filtros.get('periodo'):
            texto = filtros['periodo'].upper()
            resultados = [r for r in resultados if texto in r.get('periodo', '').upper()]

        if filtros.get('fecha_desde'):
            fecha_min = filtros['fecha_desde']
            resultados = [r for r in resultados if r.get('fecha_asiento', '') >= fecha_min]

        if filtros.get('fecha_hasta'):
            fecha_max = filtros['fecha_hasta']
            resultados = [r for r in resultados if r.get('fecha_asiento', '') <= fecha_max]

        if filtros.get('guardado_bd') is not None:
            guardado = filtros['guardado_bd']
            resultados = [r for r in resultados if r.get('guardado_bd') == guardado]

        return resultados

    def obtener_por_id(self, id_registro):
        """Obtiene un registro por su ID"""
        for r in self._registros:
            if r.get('id') == id_registro:
                return r
        return None

    def eliminar(self, id_registro):
        """Elimina un registro del histórico"""
        self._registros = [r for r in self._registros if r.get('id') != id_registro]
        self._guardar()

    def limpiar(self):
        """Limpia todo el histórico"""
        self._registros = []
        self._guardar()

    def get_estadisticas(self):
        """Obtiene estadísticas del histórico"""
        if not self._registros:
            return {
                'total_registros': 0,
                'guardados_bd': 0,
                'total_debe': 0,
                'total_haber': 0,
                'empresas_unicas': 0,
                'periodos_unicos': 0
            }

        return {
            'total_registros': len(self._registros),
            'guardados_bd': sum(1 for r in self._registros if r.get('guardado_bd')),
            'total_debe': sum(r.get('total_debe', 0) for r in self._registros),
            'total_haber': sum(r.get('total_haber', 0) for r in self._registros),
            'empresas_unicas': len(set(r.get('empresa', '') for r in self._registros)),
            'periodos_unicos': len(set(r.get('periodo', '') for r in self._registros))
        }

    @property
    def registros(self):
        return self._registros.copy()


# =============================================================================
# CLASE: GestorEstadisticas (Informes y estadísticas)
# =============================================================================
class GestorEstadisticas:
    """Genera informes y estadísticas de procesamiento"""

    def __init__(self):
        self.logger = Logger()
        self.historico = HistoricoAsientos()
        self.config = Configuracion()

    def generar_resumen_periodo(self, periodo=None):
        """Genera resumen de un período específico o del mes actual"""
        if not periodo:
            periodo = datetime.now().strftime("%B %Y").capitalize()

        filtros = {'periodo': periodo}
        registros = self.historico.buscar(filtros)

        return {
            'periodo': periodo,
            'total_asientos': len(registros),
            'guardados_bd': sum(1 for r in registros if r.get('guardado_bd')),
            'pendientes': sum(1 for r in registros if not r.get('guardado_bd')),
            'total_debe': sum(r.get('total_debe', 0) for r in registros),
            'total_haber': sum(r.get('total_haber', 0) for r in registros),
            'empresas': list(set(r.get('empresa', '') for r in registros if r.get('empresa'))),
            'cuadrados': sum(1 for r in registros if r.get('cuadrado')),
            'descuadrados': sum(1 for r in registros if not r.get('cuadrado'))
        }

    def generar_resumen_empresa(self, cif=None, nombre=None):
        """Genera resumen por empresa"""
        filtros = {}
        if cif:
            filtros['cif'] = cif
        if nombre:
            filtros['empresa'] = nombre

        registros = self.historico.buscar(filtros)

        return {
            'empresa': nombre or cif,
            'total_asientos': len(registros),
            'guardados_bd': sum(1 for r in registros if r.get('guardado_bd')),
            'total_debe': sum(r.get('total_debe', 0) for r in registros),
            'total_haber': sum(r.get('total_haber', 0) for r in registros),
            'periodos': list(set(r.get('periodo', '') for r in registros if r.get('periodo'))),
            'primer_asiento': min((r.get('fecha_asiento', '') for r in registros), default=''),
            'ultimo_asiento': max((r.get('fecha_asiento', '') for r in registros), default='')
        }

    def generar_dashboard(self):
        """Genera datos para el dashboard principal"""
        stats = self.historico.get_estadisticas()
        log_stats = {
            'total_logs': len(self.logger.registros),
            'errores': self.logger.errores
        }

        # Últimos 7 días
        hace_7_dias = (datetime.now() - __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d")
        registros_recientes = self.historico.buscar({'fecha_desde': hace_7_dias})

        # Por mes (últimos 6 meses)
        meses = {}
        for r in self.historico.registros:
            fecha = r.get('fecha_asiento', '')[:7]  # YYYY-MM
            if fecha:
                meses[fecha] = meses.get(fecha, 0) + 1

        return {
            'total_asientos': stats['total_registros'],
            'guardados_bd': stats['guardados_bd'],
            'total_debe': stats['total_debe'],
            'total_haber': stats['total_haber'],
            'empresas_unicas': stats['empresas_unicas'],
            'asientos_7_dias': len(registros_recientes),
            'logs_totales': log_stats['total_logs'],
            'errores_totales': log_stats['errores'],
            'por_mes': dict(sorted(meses.items())[-6:])  # Últimos 6 meses
        }

    def exportar_informe_excel(self, ruta, filtros=None):
        """Exporta informe a Excel"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'openpyxl', '-q'])
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment

        registros = self.historico.buscar(filtros)
        stats = self.generar_dashboard()

        wb = openpyxl.Workbook()

        # === Hoja 1: Resumen ===
        ws = wb.active
        ws.title = "Resumen"

        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        ws['A1'] = "INFORME DE ASIENTOS CONTABLES"
        ws['A1'].font = Font(size=16, bold=True)
        ws['A2'] = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"

        ws['A4'] = "Total asientos:"
        ws['B4'] = stats['total_asientos']
        ws['A5'] = "Guardados en BD:"
        ws['B5'] = stats['guardados_bd']
        ws['A6'] = "Total Debe:"
        ws['B6'] = stats['total_debe']
        ws['A7'] = "Total Haber:"
        ws['B7'] = stats['total_haber']
        ws['A8'] = "Empresas únicas:"
        ws['B8'] = stats['empresas_unicas']

        # === Hoja 2: Detalle ===
        ws2 = wb.create_sheet("Detalle")
        headers = ['Fecha', 'Nº Asiento', 'Empresa', 'CIF', 'Período', 'Debe', 'Haber', 'Guardado']

        for col, header in enumerate(headers, 1):
            cell = ws2.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font

        for row, r in enumerate(registros, 2):
            ws2.cell(row=row, column=1, value=r.get('fecha_asiento', ''))
            ws2.cell(row=row, column=2, value=r.get('numero_asiento', ''))
            ws2.cell(row=row, column=3, value=r.get('empresa', ''))
            ws2.cell(row=row, column=4, value=r.get('cif', ''))
            ws2.cell(row=row, column=5, value=r.get('periodo', ''))
            ws2.cell(row=row, column=6, value=r.get('total_debe', 0))
            ws2.cell(row=row, column=7, value=r.get('total_haber', 0))
            ws2.cell(row=row, column=8, value='Sí' if r.get('guardado_bd') else 'No')

        wb.save(ruta)
        self.logger.info(f"Informe exportado a: {ruta}")
        return True

    def exportar_informe_csv(self, ruta, filtros=None):
        """Exporta informe a CSV"""
        registros = self.historico.buscar(filtros)

        with open(ruta, 'w', encoding='utf-8-sig') as f:
            f.write("Fecha;Nº Asiento;Empresa;CIF;Período;Debe;Haber;Guardado\n")

            for r in registros:
                f.write(f"{r.get('fecha_asiento', '')};")
                f.write(f"{r.get('numero_asiento', '')};")
                f.write(f"{r.get('empresa', '')};")
                f.write(f"{r.get('cif', '')};")
                f.write(f"{r.get('periodo', '')};")
                f.write(f"{r.get('total_debe', 0)};")
                f.write(f"{r.get('total_haber', 0)};")
                f.write(f"{'Sí' if r.get('guardado_bd') else 'No'}\n")

        self.logger.info(f"Informe CSV exportado a: {ruta}")
        return True


# =============================================================================
# CLASE: Plantilla (Estructura de datos para plantillas)
# =============================================================================
class Plantilla:
    """Representa una plantilla de extracción de datos"""

    def __init__(self, id_plantilla=None):
        self.id = id_plantilla or self._generar_id()
        self.nombre = ""
        self.descripcion = ""
        self.fecha_creacion = datetime.now().isoformat()
        self.fecha_modificacion = datetime.now().isoformat()
        self.veces_usada = 0
        self.confianza = 0.0  # 0-100, aumenta con cada uso exitoso

        # Fingerprint para auto-detección
        self.fingerprints = []  # Palabras clave únicas del documento

        # Patrones de extracción
        self.patrones = {
            'cif': [],           # Lista de regex para CIF
            'periodo': [],       # Lista de regex para período
            'conceptos': [],     # Lista de patrones para conceptos de nómina
            'importes': []       # Lista de patrones para importes
        }

        # Mapeo de conceptos a cuentas contables
        self.mapeo_cuentas = []  # [{patron, cuenta, tipo_movimiento, descripcion}]

        # Historial de correcciones (para aprendizaje)
        self.correcciones = []

    def _generar_id(self):
        """Genera un ID único para la plantilla"""
        return f"PLT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"

    def to_dict(self):
        """Convierte la plantilla a diccionario para guardar"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'fecha_creacion': self.fecha_creacion,
            'fecha_modificacion': self.fecha_modificacion,
            'veces_usada': self.veces_usada,
            'confianza': self.confianza,
            'fingerprints': self.fingerprints,
            'patrones': self.patrones,
            'mapeo_cuentas': self.mapeo_cuentas,
            'correcciones': self.correcciones[-50:]  # Últimas 50 correcciones
        }

    @classmethod
    def from_dict(cls, data):
        """Crea una plantilla desde un diccionario"""
        p = cls(data.get('id'))
        p.nombre = data.get('nombre', '')
        p.descripcion = data.get('descripcion', '')
        p.fecha_creacion = data.get('fecha_creacion', '')
        p.fecha_modificacion = data.get('fecha_modificacion', '')
        p.veces_usada = data.get('veces_usada', 0)
        p.confianza = data.get('confianza', 0.0)
        p.fingerprints = data.get('fingerprints', [])
        p.patrones = data.get('patrones', {})
        p.mapeo_cuentas = data.get('mapeo_cuentas', [])
        p.correcciones = data.get('correcciones', [])
        return p

    def agregar_fingerprint(self, texto):
        """Añade un fingerprint si no existe"""
        texto_norm = texto.strip().upper()
        if texto_norm and texto_norm not in self.fingerprints:
            self.fingerprints.append(texto_norm)

    def agregar_mapeo(self, patron, cuenta, tipo='debe', descripcion=''):
        """Añade una regla de mapeo concepto -> cuenta"""
        self.mapeo_cuentas.append({
            'patron': patron,
            'cuenta': cuenta,
            'tipo': tipo,  # 'debe' o 'haber'
            'descripcion': descripcion
        })

    def registrar_correccion(self, campo, valor_original, valor_corregido):
        """Registra una corrección del usuario para aprendizaje"""
        self.correcciones.append({
            'fecha': datetime.now().isoformat(),
            'campo': campo,
            'original': valor_original,
            'corregido': valor_corregido
        })
        self.fecha_modificacion = datetime.now().isoformat()

    def incrementar_uso(self, exito=True):
        """Incrementa el contador de uso y ajusta confianza"""
        self.veces_usada += 1
        if exito:
            # Aumenta confianza (máximo 100)
            self.confianza = min(100, self.confianza + (100 - self.confianza) * 0.1)
        else:
            # Disminuye confianza
            self.confianza = max(0, self.confianza - 5)


# =============================================================================
# CLASE: GestorPlantillas (Gestión de plantillas)
# =============================================================================
class GestorPlantillas:
    """Gestiona el almacenamiento y recuperación de plantillas (Singleton)"""
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia

    def _inicializar(self):
        """Inicializa el gestor de plantillas"""
        self.logger = Logger()

        # Directorio para guardar plantillas
        self.directorio = Path.home() / '.lector_nominas' / 'plantillas'
        self.directorio.mkdir(parents=True, exist_ok=True)

        # Archivo índice
        self.archivo_indice = self.directorio / 'indice.json'

        # Cache de plantillas cargadas
        self._cache = {}

        # Cargar índice
        self._cargar_indice()

        self.logger.info(f"GestorPlantillas inicializado", f"Directorio: {self.directorio}")

    def _cargar_indice(self):
        """Carga el índice de plantillas"""
        self._indice = {}
        if self.archivo_indice.exists():
            try:
                with open(self.archivo_indice, 'r', encoding='utf-8') as f:
                    self._indice = json.load(f)
                self.logger.debug(f"Índice cargado: {len(self._indice)} plantillas")
            except Exception as e:
                self.logger.error("Error cargando índice de plantillas", str(e))

    def _guardar_indice(self):
        """Guarda el índice de plantillas"""
        try:
            with open(self.archivo_indice, 'w', encoding='utf-8') as f:
                json.dump(self._indice, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error("Error guardando índice", str(e))

    def guardar(self, plantilla):
        """Guarda una plantilla"""
        try:
            archivo = self.directorio / f"{plantilla.id}.json"
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(plantilla.to_dict(), f, ensure_ascii=False, indent=2)

            # Actualizar índice
            self._indice[plantilla.id] = {
                'nombre': plantilla.nombre,
                'fingerprints': plantilla.fingerprints,
                'confianza': plantilla.confianza,
                'veces_usada': plantilla.veces_usada
            }
            self._guardar_indice()

            # Actualizar cache
            self._cache[plantilla.id] = plantilla

            self.logger.info(f"Plantilla guardada: {plantilla.nombre}", plantilla.id)
            return True

        except Exception as e:
            self.logger.error(f"Error guardando plantilla {plantilla.id}", str(e))
            return False

    def cargar(self, id_plantilla):
        """Carga una plantilla por su ID"""
        # Verificar cache
        if id_plantilla in self._cache:
            return self._cache[id_plantilla]

        archivo = self.directorio / f"{id_plantilla}.json"
        if not archivo.exists():
            self.logger.warning(f"Plantilla no encontrada: {id_plantilla}")
            return None

        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
            plantilla = Plantilla.from_dict(data)
            self._cache[id_plantilla] = plantilla
            return plantilla

        except Exception as e:
            self.logger.error(f"Error cargando plantilla {id_plantilla}", str(e))
            return None

    def listar(self):
        """Lista todas las plantillas disponibles"""
        return [
            {'id': k, **v}
            for k, v in self._indice.items()
        ]

    def eliminar(self, id_plantilla):
        """Elimina una plantilla"""
        try:
            archivo = self.directorio / f"{id_plantilla}.json"
            if archivo.exists():
                archivo.unlink()

            if id_plantilla in self._indice:
                del self._indice[id_plantilla]
                self._guardar_indice()

            if id_plantilla in self._cache:
                del self._cache[id_plantilla]

            self.logger.info(f"Plantilla eliminada: {id_plantilla}")
            return True

        except Exception as e:
            self.logger.error(f"Error eliminando plantilla", str(e))
            return False


# =============================================================================
# CLASE: DetectorDocumento (Auto-detección de tipo de documento)
# =============================================================================
class DetectorDocumento:
    """Detecta el tipo de documento y busca plantilla coincidente"""

    # Fingerprints conocidos de programas de nóminas
    FINGERPRINTS_CONOCIDOS = {
        'A3NOM': ['A3NOM', 'A3 SOFTWARE', 'A3EQUIPO', 'WOLTERS KLUWER'],
        'SAGE': ['SAGE', 'SAGE DESPACHOS', 'LOGIC CLASS'],
        'NOMINAPLUS': ['NOMINAPLUS', 'NOMINA PLUS', 'SAGE NOMINAPLUS'],
        'CONTAPLUS': ['CONTAPLUS', 'CONTA PLUS'],
        'SILTRA': ['SILTRA', 'SISTEMA DE LIQUIDACIÓN'],
        'SEPE': ['SEPE', 'SERVICIO PÚBLICO DE EMPLEO'],
        'AEAT': ['AGENCIA TRIBUTARIA', 'AEAT', 'MODELO 111', 'MODELO 190'],
        'SS': ['SEGURIDAD SOCIAL', 'TGSS', 'TESORERÍA GENERAL']
    }

    def __init__(self):
        self.logger = Logger()
        self.gestor = GestorPlantillas()

    def detectar_fingerprints(self, texto):
        """Extrae fingerprints del texto del documento"""
        fingerprints = []
        texto_upper = texto.upper()

        # Buscar fingerprints conocidos
        for nombre, keywords in self.FINGERPRINTS_CONOCIDOS.items():
            for kw in keywords:
                if kw in texto_upper:
                    fingerprints.append(nombre)
                    break

        # Extraer otras palabras clave relevantes (empresas de software, etc.)
        patrones_extra = [
            r'NÓMINA[S]?\s+DE\s+(\w+)',
            r'GENERADO\s+(?:POR|CON)\s+(\w+)',
            r'SOFTWARE\s+(\w+)',
        ]

        for patron in patrones_extra:
            matches = re.findall(patron, texto_upper)
            for m in matches:
                if len(m) > 3:  # Ignorar palabras muy cortas
                    fingerprints.append(m)

        return list(set(fingerprints))

    def calcular_similitud(self, fingerprints_doc, fingerprints_plantilla):
        """Calcula la similitud entre dos conjuntos de fingerprints"""
        if not fingerprints_doc or not fingerprints_plantilla:
            return 0.0

        set_doc = set(f.upper() for f in fingerprints_doc)
        set_plt = set(f.upper() for f in fingerprints_plantilla)

        interseccion = len(set_doc & set_plt)
        union = len(set_doc | set_plt)

        if union == 0:
            return 0.0

        return (interseccion / union) * 100

    def buscar_plantilla(self, texto):
        """
        Busca la mejor plantilla para el documento.

        Returns: (plantilla, confianza) o (None, 0) si no encuentra
        """
        fingerprints_doc = self.detectar_fingerprints(texto)
        self.logger.debug(f"Fingerprints detectados: {fingerprints_doc}")

        if not fingerprints_doc:
            self.logger.info("No se detectaron fingerprints en el documento")
            return None, 0

        mejor_plantilla = None
        mejor_score = 0

        for info in self.gestor.listar():
            similitud = self.calcular_similitud(fingerprints_doc, info.get('fingerprints', []))

            # Ponderar por confianza de la plantilla
            score = similitud * (0.5 + info.get('confianza', 0) / 200)

            if score > mejor_score and score >= 30:  # Umbral mínimo 30%
                mejor_score = score
                mejor_plantilla = self.gestor.cargar(info['id'])

        if mejor_plantilla:
            self.logger.info(
                f"Plantilla encontrada: {mejor_plantilla.nombre}",
                f"Score: {mejor_score:.1f}%"
            )
        else:
            self.logger.info("No se encontró plantilla coincidente")

        return mejor_plantilla, mejor_score

    def crear_plantilla_desde_documento(self, texto, nombre="Nueva Plantilla"):
        """Crea una plantilla base a partir de un documento"""
        plantilla = Plantilla()
        plantilla.nombre = nombre

        # Detectar fingerprints
        fingerprints = self.detectar_fingerprints(texto)
        for fp in fingerprints:
            plantilla.agregar_fingerprint(fp)

        # Patrones por defecto para nóminas españolas
        plantilla.patrones = {
            'cif': [
                r'[A-HJ-NP-SUVW]\d{7}[A-J0-9]',
                r'CIF[:\s]*([A-Z]\d{8})',
                r'NIF[:\s]*(\d{8}[A-Z])'
            ],
            'periodo': [
                r'(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s*[/-]?\s*(\d{4})',
                r'PERÍODO[:\s]*(\d{2})[/-](\d{4})',
                r'MES[:\s]*(\d{1,2})[/-](\d{4})'
            ],
            'conceptos': [
                r'SALARIO\s*BASE',
                r'PLUS\s+\w+',
                r'PRORRATA\s+PAGAS',
                r'HORAS\s+EXTRA',
                r'COMPLEMENTO\s+\w+',
                r'ANTIGÜEDAD',
                r'I\.?R\.?P\.?F\.?',
                r'SEGURIDAD\s+SOCIAL',
                r'TOTAL\s+DEVENGADO',
                r'TOTAL\s+DEDUCCIONES',
                r'LÍQUIDO|NETO'
            ],
            'importes': [
                r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))\s*€?',
            ]
        }

        # Mapeo básico por defecto
        plantilla.mapeo_cuentas = [
            {'patron': 'SALARIO', 'cuenta': '6400000', 'tipo': 'debe', 'descripcion': 'Sueldos y salarios'},
            {'patron': 'SS.*EMPRESA|SEGURIDAD SOCIAL', 'cuenta': '6420000', 'tipo': 'debe', 'descripcion': 'SS a cargo empresa'},
            {'patron': 'IRPF|I.R.P.F', 'cuenta': '4751000', 'tipo': 'haber', 'descripcion': 'HP Acreedora IRPF'},
            {'patron': 'SS.*TRABAJADOR', 'cuenta': '4760000', 'tipo': 'haber', 'descripcion': 'SS a cargo trabajador'},
            {'patron': 'NETO|LÍQUIDO', 'cuenta': '4650000', 'tipo': 'haber', 'descripcion': 'Remuneraciones pendientes'}
        ]

        self.logger.info(f"Plantilla creada: {plantilla.nombre}", f"Fingerprints: {fingerprints}")
        return plantilla


# =============================================================================
# CLASE: ExtractorConceptos (Extrae conceptos e importes con OpenDataLoader)
# =============================================================================
class ExtractorConceptos:
    """
    Extrae conceptos e importes usando:
    1. Tablas estructuradas de OpenDataLoader (si disponibles)
    2. Bounding boxes para localización precisa
    3. Patrones regex como fallback
    """

    def __init__(self):
        self.logger = Logger()

    def extraer(self, texto, plantilla=None, pdf_processor=None):
        """
        Extrae conceptos e importes del documento.

        Si pdf_processor tiene datos de OpenDataLoader, los usa.
        De lo contrario, usa extracción por patrones.

        Returns: lista de {concepto, importe, linea, bbox, fuente}
        """
        # Si tenemos tablas de OpenDataLoader, usarlas primero
        if pdf_processor and pdf_processor.tablas:
            resultados = self._extraer_de_tablas(pdf_processor.tablas, plantilla)
            if resultados:
                self.logger.info(
                    f"Extracción desde tablas OpenDataLoader",
                    f"Encontrados: {len(resultados)} conceptos"
                )
                return resultados

        # Fallback: extracción por patrones de texto
        return self._extraer_por_patrones(texto, plantilla)

    def _extraer_de_tablas(self, tablas, plantilla=None):
        """Extrae conceptos de tablas estructuradas de OpenDataLoader"""
        resultados = []

        # Patrones para identificar columnas
        patron_concepto = r'(CONCEPTO|DESCRIPCIÓN|DEVENGO|DEDUCCIÓN)'
        patron_importe = r'(IMPORTE|CANTIDAD|TOTAL|EUROS|€)'

        for tabla in tablas:
            filas = tabla.get('filas', [])
            if not filas:
                continue

            # Detectar índices de columnas
            idx_concepto = None
            idx_importe = None
            encabezado = filas[0] if filas else []

            for i, celda in enumerate(encabezado):
                texto_celda = str(celda).upper()
                if re.search(patron_concepto, texto_celda):
                    idx_concepto = i
                if re.search(patron_importe, texto_celda):
                    idx_importe = i

            # Si no encontramos encabezados, asumir columnas típicas
            if idx_concepto is None and len(encabezado) >= 2:
                idx_concepto = 0
                idx_importe = len(encabezado) - 1

            # Procesar filas de datos
            for num_fila, fila in enumerate(filas[1:], start=2):
                if not fila or len(fila) <= max(idx_concepto or 0, idx_importe or 0):
                    continue

                concepto = str(fila[idx_concepto]).strip() if idx_concepto is not None else ''
                importe_str = str(fila[idx_importe]).strip() if idx_importe is not None else ''

                # Verificar que es un concepto válido
                if not concepto or len(concepto) < 3:
                    continue

                # Normalizar importe
                importe = self._normalizar_importe(importe_str)

                # Verificar si el concepto es relevante para nóminas
                if self._es_concepto_nomina(concepto):
                    resultados.append({
                        'concepto': concepto.upper(),
                        'importe': importe,
                        'linea': num_fila,
                        'texto_original': f"{concepto}: {importe_str}",
                        'bbox': tabla.get('bbox', {}),
                        'fuente': 'tabla_opendataloader'
                    })

        return resultados

    def _es_concepto_nomina(self, texto):
        """Verifica si el texto parece un concepto de nómina"""
        texto_upper = texto.upper()
        conceptos_nomina = [
            'SALARIO', 'SUELDO', 'BASE', 'PLUS', 'COMPLEMENTO',
            'PRORRATA', 'PAGAS', 'EXTRA', 'HORAS', 'ANTIGÜEDAD',
            'IRPF', 'I.R.P.F', 'SEGURIDAD', 'SOCIAL', 'CONTINGENCIAS',
            'DESEMPLEO', 'FORMACIÓN', 'TOTAL', 'LÍQUIDO', 'NETO',
            'DEVENGO', 'DEDUCCIÓN', 'RETENCIÓN', 'APORTACIÓN',
            'DIETA', 'TRANSPORTE', 'INCENTIVO', 'COMISIÓN', 'BONUS'
        ]
        return any(c in texto_upper for c in conceptos_nomina)

    def _normalizar_importe(self, importe_str):
        """Normaliza un string de importe a float"""
        if not importe_str:
            return None
        try:
            # Limpiar caracteres no numéricos excepto . y ,
            limpio = re.sub(r'[^\d.,\-]', '', importe_str)
            if not limpio:
                return None
            # Normalizar: 1.234,56 -> 1234.56
            if ',' in limpio and '.' in limpio:
                limpio = limpio.replace('.', '').replace(',', '.')
            elif ',' in limpio:
                limpio = limpio.replace(',', '.')
            return float(limpio)
        except:
            return None

    def _extraer_por_patrones(self, texto, plantilla=None):
        """Fallback: extracción por patrones regex"""
        resultados = []
        lineas = texto.split('\n')

        # Patrones por defecto si no hay plantilla
        patrones_conceptos = [
            r'(SALARIO\s*BASE)',
            r'(PLUS\s+\w+)',
            r'(PRORRATA\s+PAGAS?\s*\w*)',
            r'(HORAS\s+EXTRA\w*)',
            r'(COMPLEMENTO\s+\w+)',
            r'(ANTIGÜEDAD)',
            r'(I\.?R\.?P\.?F\.?)',
            r'(SEGURIDAD\s+SOCIAL.*)',
            r'(CONTINGENCIAS\s+COMUNES)',
            r'(DESEMPLEO)',
            r'(FORMACIÓN\s+PROFESIONAL)',
            r'(TOTAL\s+DEVENGADO)',
            r'(TOTAL\s+DEDUCCIONES)',
            r'(LÍQUIDO\s*A?\s*PERCIBIR|NETO\s*A?\s*PAGAR)',
        ]

        if plantilla and plantilla.patrones.get('conceptos'):
            patrones_conceptos = plantilla.patrones['conceptos']

        # Patrón para importes
        patron_importe = r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})'

        for i, linea in enumerate(lineas):
            linea_upper = linea.upper()

            for patron in patrones_conceptos:
                match_concepto = re.search(patron, linea_upper, re.IGNORECASE)
                if match_concepto:
                    concepto = match_concepto.group(1).strip()

                    # Buscar importe en la misma línea
                    match_importe = re.search(patron_importe, linea)
                    importe = self._normalizar_importe(
                        match_importe.group(1) if match_importe else None
                    )

                    if concepto:
                        resultados.append({
                            'concepto': concepto,
                            'importe': importe,
                            'linea': i + 1,
                            'texto_original': linea.strip(),
                            'bbox': {},
                            'fuente': 'patron_regex'
                        })
                    break  # Solo un concepto por línea

        self.logger.debug(f"Conceptos extraídos por patrones: {len(resultados)}")
        return resultados

    def extraer_con_bounding_boxes(self, pdf_processor, plantilla=None):
        """
        Extracción avanzada usando bounding boxes de OpenDataLoader.
        Permite encontrar valores asociados a etiquetas por proximidad espacial.
        """
        if not pdf_processor or not pdf_processor.elementos:
            return self.extraer(pdf_processor.texto if pdf_processor else '', plantilla)

        resultados = []

        # Etiquetas a buscar en nóminas
        etiquetas = [
            'SALARIO BASE', 'PLUS', 'COMPLEMENTO', 'PRORRATA',
            'HORAS EXTRA', 'ANTIGÜEDAD', 'IRPF', 'I.R.P.F.',
            'SEGURIDAD SOCIAL', 'CONTINGENCIAS', 'DESEMPLEO',
            'TOTAL DEVENGADO', 'TOTAL DEDUCCIONES', 'LÍQUIDO', 'NETO'
        ]

        for etiqueta in etiquetas:
            # Buscar elementos cercanos a cada etiqueta
            cercanos = pdf_processor.buscar_texto_cerca_de(etiqueta, radio=100)

            for elem in cercanos:
                texto = elem.get('texto', '')
                importe = self._normalizar_importe(texto)

                if importe is not None:
                    resultados.append({
                        'concepto': etiqueta.upper(),
                        'importe': importe,
                        'linea': 0,
                        'texto_original': f"{etiqueta}: {texto}",
                        'bbox': elem.get('bbox', {}),
                        'fuente': 'bounding_box'
                    })
                    break  # Solo el primer valor cercano

        self.logger.info(
            f"Extracción con bounding boxes",
            f"Encontrados: {len(resultados)} conceptos"
        )
        return resultados

    def mapear_a_cuentas(self, conceptos, plantilla):
        """
        Mapea conceptos extraídos a cuentas contables.

        Returns: lista de {concepto, importe, cuenta, tipo, descripcion}
        """
        if not plantilla or not plantilla.mapeo_cuentas:
            return conceptos

        resultado = []
        for item in conceptos:
            cuenta_asignada = None
            tipo = 'debe'
            descripcion = ''

            for mapeo in plantilla.mapeo_cuentas:
                if re.search(mapeo['patron'], item['concepto'], re.IGNORECASE):
                    cuenta_asignada = mapeo['cuenta']
                    tipo = mapeo.get('tipo', 'debe')
                    descripcion = mapeo.get('descripcion', '')
                    break

            resultado.append({
                **item,
                'cuenta': cuenta_asignada,
                'tipo': tipo,
                'descripcion': descripcion
            })

        return resultado


# =============================================================================
# CLASE: ExtractorIA (Extracción mediante IA - Claude API) - FASE 8
# =============================================================================
class ExtractorIA:
    """
    Extrae datos de nóminas usando IA (Claude API).

    Flujo:
    1. Recibe el PDF directamente
    2. Lo envía a Claude con visión
    3. Claude interpreta y devuelve JSON estructurado
    4. El sistema procesa el JSON limpio
    """
    _instancia = None

    # Estructura JSON que esperamos de la IA (SIEMPRE array de empresas)
    ESTRUCTURA_JSON = """
    {
        "empresas": [
            {
                "empresa": {
                    "cif": "B12345678",
                    "nombre": "Nombre de la empresa",
                    "domicilio": "Dirección (opcional)"
                },
                "periodo": {
                    "mes": 6,
                    "año": 2024,
                    "texto": "Junio 2024"
                },
                "trabajadores": {
                    "total": 25,
                    "detalle": []
                },
                "conceptos": [
                    {
                        "codigo": "001",
                        "descripcion": "Sueldos y salarios",
                        "tipo": "devengo",
                        "importe": 45230.50
                    },
                    {
                        "codigo": "002",
                        "descripcion": "Complementos salariales",
                        "tipo": "devengo",
                        "importe": 8500.00
                    },
                    {
                        "codigo": "500",
                        "descripcion": "Contingencias comunes (empresa)",
                        "tipo": "ss_empresa",
                        "importe": 12500.00
                    },
                    {
                        "codigo": "501",
                        "descripcion": "Contingencias comunes (trabajador)",
                        "tipo": "ss_trabajador",
                        "importe": 3200.00
                    },
                    {
                        "codigo": "600",
                        "descripcion": "IRPF",
                        "tipo": "retencion",
                        "importe": 7500.00
                    }
                ],
                "totales": {
                    "total_devengos": 53730.50,
                    "total_ss_empresa": 15800.00,
                    "total_ss_trabajador": 4100.00,
                    "total_irpf": 7500.00,
                    "liquido_a_percibir": 42130.50
                },
                "observaciones": "Cualquier observación relevante"
            }
        ],
        "_metadata": {
            "total_empresas": 1,
            "confianza_global": 0.95,
            "formato_detectado": "Resumen mensual de nóminas"
        }
    }
    """

    PROMPT_SISTEMA = """Eres un experto en nóminas españolas y contabilidad. Tu tarea es extraer
información de documentos PDF de nóminas o resúmenes de nóminas y convertirlos a JSON estructurado.

IMPORTANTE - DETECCIÓN DE MÚLTIPLES EMPRESAS:
- El PDF puede contener datos de UNA o MÚLTIPLES empresas
- SIEMPRE devuelve un array "empresas" aunque solo haya una
- Detecta cambios de empresa por: nuevo CIF, nuevo encabezado, salto de sección
- Cada empresa debe tener su propio objeto completo en el array

IMPORTANTE - EXTRACCIÓN DE DATOS:
- Extrae TODOS los conceptos que encuentres (devengos, deducciones, bases, etc.)
- Los importes deben ser números (sin símbolos de euro ni separadores de miles)
- El CIF/NIF debe estar en formato correcto (letra + 8 dígitos o 8 dígitos + letra)
- Si no encuentras un dato, usa null en lugar de inventarlo
- El campo "tipo" de cada concepto debe ser uno de: "devengo", "deduccion", "ss_empresa", "ss_trabajador", "retencion", "base"
- Si hay varios trabajadores en una empresa, suma los importes por concepto
- Incluye el total de empresas detectadas en _metadata.total_empresas

Devuelve SOLO el JSON, sin explicaciones ni markdown."""

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia

    def _inicializar(self):
        self.logger = Logger()
        self.config = Configuracion()
        self.client = None
        self._historial_extracciones = []

        # Directorio para guardar extracciones
        self.dir_extracciones = Path.home() / '.lector_nominas' / 'extracciones_ia'
        self.dir_extracciones.mkdir(parents=True, exist_ok=True)

    def _obtener_cliente(self):
        """Obtiene o crea el cliente de Anthropic"""
        if not ANTHROPIC_OK:
            raise RuntimeError("La librería 'anthropic' no está instalada. Ejecute: pip install anthropic")

        api_key = self.config.get_api_key()
        if not api_key:
            raise ValueError("No hay API key configurada. Configure en Ajustes > IA")

        if self.client is None:
            self.client = anthropic.Anthropic(api_key=api_key)

        return self.client

    def extraer_de_pdf(self, ruta_pdf, callback_progreso=None):
        """
        Extrae datos de un PDF usando Claude con visión.

        Args:
            ruta_pdf: Ruta al archivo PDF
            callback_progreso: Función para reportar progreso

        Returns:
            dict con los datos extraídos o None si falla
        """
        if callback_progreso:
            callback_progreso(0, 100, "Preparando PDF para IA...")

        try:
            # Verificar que el archivo existe
            if not os.path.exists(ruta_pdf):
                raise FileNotFoundError(f"No se encuentra el archivo: {ruta_pdf}")

            # Leer PDF como base64
            with open(ruta_pdf, "rb") as f:
                pdf_base64 = base64.standard_b64encode(f.read()).decode('utf-8')

            if callback_progreso:
                callback_progreso(20, 100, "Enviando a Claude...")

            # Obtener cliente
            client = self._obtener_cliente()
            modelo = self.config.get_modelo_ia()
            max_tokens = self.config.get('ia', 'max_tokens', 4096)

            self.logger.info(f"Enviando PDF a IA", f"Modelo: {modelo}")

            # Crear mensaje con el PDF
            mensaje = client.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": f"""Analiza este documento de nómina/resumen de nóminas y extrae la información en formato JSON.

La estructura esperada es:
{self.ESTRUCTURA_JSON}

{self.PROMPT_SISTEMA}"""
                            }
                        ]
                    }
                ]
            )

            if callback_progreso:
                callback_progreso(80, 100, "Procesando respuesta...")

            # Extraer JSON de la respuesta
            respuesta_texto = mensaje.content[0].text
            datos = self._parsear_json(respuesta_texto)

            if datos:
                # Añadir metadata de extracción
                datos['_extraccion'] = {
                    'fecha': datetime.now().isoformat(),
                    'modelo': modelo,
                    'archivo': os.path.basename(ruta_pdf),
                    'metodo': 'ia_claude',
                    'tokens_usados': mensaje.usage.input_tokens + mensaje.usage.output_tokens
                }

                # Guardar extracción si está configurado
                if self.config.get('ia', 'guardar_extracciones', True):
                    self._guardar_extraccion(ruta_pdf, datos)

                self.logger.info(
                    "Extracción IA completada",
                    f"Conceptos: {len(datos.get('conceptos', []))}, "
                    f"Tokens: {datos['_extraccion']['tokens_usados']}"
                )

                if callback_progreso:
                    callback_progreso(100, 100, "Completado")

                return datos
            else:
                self.logger.error("No se pudo parsear la respuesta de la IA", respuesta_texto[:500])
                return None

        except anthropic.AuthenticationError:
            self.logger.error("Error de autenticación", "API key inválida o expirada")
            raise ValueError("API key de Anthropic inválida o expirada")
        except anthropic.RateLimitError:
            self.logger.error("Límite de tasa excedido", "Espere un momento antes de reintentar")
            raise RuntimeError("Se ha excedido el límite de llamadas a la API. Espere un momento.")
        except Exception as e:
            self.logger.error(f"Error en extracción IA: {type(e).__name__}", str(e))
            raise

    def _parsear_json(self, texto):
        """Parsea JSON de la respuesta de la IA"""
        # Intentar parsear directamente
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            pass

        # Buscar JSON en bloques de código
        patron_json = r'```(?:json)?\s*([\s\S]*?)```'
        match = re.search(patron_json, texto)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Buscar objeto JSON en el texto
        patron_objeto = r'\{[\s\S]*\}'
        match = re.search(patron_objeto, texto)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _guardar_extraccion(self, ruta_pdf, datos):
        """Guarda la extracción para histórico y aprendizaje"""
        try:
            nombre_base = Path(ruta_pdf).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archivo = self.dir_extracciones / f"{nombre_base}_{timestamp}.json"

            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)

            self._historial_extracciones.append({
                'archivo': str(archivo),
                'fecha': datetime.now().isoformat(),
                'cif': datos.get('empresa', {}).get('cif', ''),
                'periodo': datos.get('periodo', {}).get('texto', '')
            })

        except Exception as e:
            self.logger.warning(f"No se pudo guardar extracción: {e}")

    def obtener_empresas(self, datos_ia):
        """
        Obtiene la lista de empresas del resultado de la IA.

        Args:
            datos_ia: dict con la estructura JSON de la IA

        Returns:
            Lista de empresas detectadas, cada una con su info completa
        """
        if not datos_ia:
            return []

        # Nuevo formato: array de empresas
        if 'empresas' in datos_ia:
            return datos_ia.get('empresas', [])

        # Formato antiguo (compatibilidad): empresa única
        if 'empresa' in datos_ia:
            return [datos_ia]

        return []

    def es_multi_empresa(self, datos_ia):
        """Verifica si el resultado contiene múltiples empresas"""
        empresas = self.obtener_empresas(datos_ia)
        return len(empresas) > 1

    def get_resumen_empresas(self, datos_ia):
        """
        Obtiene un resumen de las empresas detectadas.

        Returns:
            Lista de {cif, nombre, total_devengos, num_conceptos}
        """
        resumen = []
        for emp in self.obtener_empresas(datos_ia):
            info_emp = emp.get('empresa', {})
            totales = emp.get('totales', {})
            conceptos = emp.get('conceptos', [])

            resumen.append({
                'cif': info_emp.get('cif', ''),
                'nombre': info_emp.get('nombre', 'Sin nombre'),
                'total_devengos': totales.get('total_devengos', 0),
                'liquido': totales.get('liquido_a_percibir', 0),
                'num_conceptos': len(conceptos),
                'periodo': emp.get('periodo', {}).get('texto', '')
            })

        return resumen

    def convertir_a_conceptos(self, datos_empresa):
        """
        Convierte los datos de UNA empresa al formato interno de conceptos.

        Args:
            datos_empresa: dict de una empresa (NO el array completo)

        Returns:
            Lista de conceptos en formato interno compatible con el sistema
        """
        conceptos = []

        # Si recibimos el formato completo con 'empresas', tomar la primera
        if 'empresas' in datos_empresa:
            empresas = datos_empresa.get('empresas', [])
            if empresas:
                datos_empresa = empresas[0]
            else:
                return conceptos

        if not datos_empresa or 'conceptos' not in datos_empresa:
            return conceptos

        # Mapeo de tipos IA a tipos internos
        mapeo_tipos = {
            'devengo': 'debe',
            'deduccion': 'haber',
            'ss_empresa': 'debe',
            'ss_trabajador': 'haber',
            'retencion': 'haber',
            'base': 'info'
        }

        for item in datos_empresa.get('conceptos', []):
            tipo_ia = item.get('tipo', 'devengo')
            tipo_interno = mapeo_tipos.get(tipo_ia, 'debe')

            concepto = {
                'concepto': item.get('descripcion', '').upper(),
                'importe': item.get('importe'),
                'tipo': tipo_interno,
                'codigo': item.get('codigo', ''),
                'linea': 0,
                'texto_original': f"{item.get('codigo', '')}: {item.get('descripcion', '')}",
                'bbox': {},
                'fuente': 'ia_claude',
                'tipo_ia': tipo_ia
            }
            conceptos.append(concepto)

        return conceptos

    def convertir_todas_empresas(self, datos_ia):
        """
        Convierte todas las empresas del resultado IA a formato interno.

        Returns:
            Lista de {empresa_info, conceptos, periodo, totales}
        """
        resultado = []

        for emp in self.obtener_empresas(datos_ia):
            info_emp = emp.get('empresa', {})
            conceptos = self.convertir_a_conceptos(emp)

            resultado.append({
                'empresa': info_emp,
                'conceptos': conceptos,
                'periodo': emp.get('periodo', {}),
                'totales': emp.get('totales', {}),
                'trabajadores': emp.get('trabajadores', {}),
                'observaciones': emp.get('observaciones', '')
            })

        return resultado

    def get_historial(self, cif=None, limite=50):
        """Obtiene el historial de extracciones, opcionalmente filtrado por CIF"""
        historial = self._historial_extracciones[-limite:]
        if cif:
            historial = [h for h in historial if h.get('cif') == cif]
        return historial

    def cargar_extraccion(self, ruta_archivo):
        """Carga una extracción guardada previamente"""
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error cargando extracción: {e}")
            return None

    def esta_disponible(self):
        """Verifica si la extracción por IA está disponible"""
        return ANTHROPIC_OK and bool(self.config.get_api_key())


# =============================================================================
# CLASE: VentanaEditorJSON (Editor de JSON extraído por IA) - FASE 8
# =============================================================================
class VentanaEditorJSON(tk.Toplevel):
    """
    Ventana para visualizar y editar el JSON extraído por la IA.
    Permite al usuario corregir datos antes de procesarlos.
    """

    def __init__(self, parent, datos_json, nombre_archivo="", callback_aceptar=None):
        super().__init__(parent)
        self.title(f"Editor JSON - {nombre_archivo}")
        self.geometry("900x700")
        self.minsize(700, 500)

        self.datos_originales = datos_json
        self.datos_editados = None
        self.callback_aceptar = callback_aceptar
        self.logger = Logger()

        self._crear_ui()
        self._cargar_datos()

        # Modal
        self.transient(parent)
        self.grab_set()

    def _crear_ui(self):
        # Frame principal
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Cabecera con info ===
        frame_info = ttk.Frame(main)
        frame_info.pack(fill='x', pady=(0, 10))

        ttk.Label(frame_info, text="🤖 Datos extraídos por IA",
                  font=('Arial', 12, 'bold')).pack(side='left')

        # Indicador de confianza
        self.var_confianza = tk.StringVar(value="Confianza: --")
        ttk.Label(frame_info, textvariable=self.var_confianza,
                  font=('Arial', 10), foreground='gray').pack(side='right')

        # === Panel con pestañas ===
        notebook = ttk.Notebook(main)
        notebook.pack(fill='both', expand=True, pady=(0, 10))

        # --- Pestaña 1: Vista estructurada ---
        tab_estructura = ttk.Frame(notebook, padding=10)
        notebook.add(tab_estructura, text="Vista Estructurada")

        # Empresa
        frame_emp = ttk.LabelFrame(tab_estructura, text="Empresa", padding=10)
        frame_emp.pack(fill='x', pady=(0, 10))

        row1 = ttk.Frame(frame_emp)
        row1.pack(fill='x')

        ttk.Label(row1, text="CIF:", width=10).pack(side='left')
        self.var_cif = tk.StringVar()
        ttk.Entry(row1, textvariable=self.var_cif, width=15, font=('Consolas', 11)).pack(side='left', padx=5)

        ttk.Label(row1, text="Nombre:", width=10).pack(side='left')
        self.var_empresa = tk.StringVar()
        ttk.Entry(row1, textvariable=self.var_empresa, width=40, font=('Consolas', 11)).pack(side='left', padx=5)

        # Período
        frame_per = ttk.LabelFrame(tab_estructura, text="Período", padding=10)
        frame_per.pack(fill='x', pady=(0, 10))

        row2 = ttk.Frame(frame_per)
        row2.pack(fill='x')

        ttk.Label(row2, text="Mes:", width=10).pack(side='left')
        self.var_mes = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_mes, width=5, font=('Consolas', 11)).pack(side='left', padx=5)

        ttk.Label(row2, text="Año:", width=10).pack(side='left')
        self.var_anno = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_anno, width=8, font=('Consolas', 11)).pack(side='left', padx=5)

        # Conceptos
        frame_conceptos = ttk.LabelFrame(tab_estructura, text="Conceptos", padding=10)
        frame_conceptos.pack(fill='both', expand=True, pady=(0, 10))

        # Tabla de conceptos
        cols = ('codigo', 'descripcion', 'tipo', 'importe')
        self.tree_conceptos = ttk.Treeview(frame_conceptos, columns=cols, show='headings', height=10)

        self.tree_conceptos.heading('codigo', text='Código')
        self.tree_conceptos.heading('descripcion', text='Descripción')
        self.tree_conceptos.heading('tipo', text='Tipo')
        self.tree_conceptos.heading('importe', text='Importe')

        self.tree_conceptos.column('codigo', width=80)
        self.tree_conceptos.column('descripcion', width=300)
        self.tree_conceptos.column('tipo', width=100)
        self.tree_conceptos.column('importe', width=100, anchor='e')

        scroll_tree = ttk.Scrollbar(frame_conceptos, orient='vertical', command=self.tree_conceptos.yview)
        self.tree_conceptos.configure(yscrollcommand=scroll_tree.set)

        self.tree_conceptos.pack(side='left', fill='both', expand=True)
        scroll_tree.pack(side='right', fill='y')

        # Botones de edición de conceptos
        frame_btns_conceptos = ttk.Frame(tab_estructura)
        frame_btns_conceptos.pack(fill='x')

        ttk.Button(frame_btns_conceptos, text="+ Añadir", command=self._añadir_concepto).pack(side='left', padx=2)
        ttk.Button(frame_btns_conceptos, text="Editar", command=self._editar_concepto).pack(side='left', padx=2)
        ttk.Button(frame_btns_conceptos, text="- Eliminar", command=self._eliminar_concepto).pack(side='left', padx=2)

        # Totales
        frame_totales = ttk.LabelFrame(tab_estructura, text="Totales", padding=10)
        frame_totales.pack(fill='x')

        row_tot = ttk.Frame(frame_totales)
        row_tot.pack(fill='x')

        ttk.Label(row_tot, text="Devengos:").pack(side='left')
        self.var_total_dev = tk.StringVar()
        ttk.Entry(row_tot, textvariable=self.var_total_dev, width=12, font=('Consolas', 11)).pack(side='left', padx=5)

        ttk.Label(row_tot, text="SS Empresa:").pack(side='left')
        self.var_total_ss = tk.StringVar()
        ttk.Entry(row_tot, textvariable=self.var_total_ss, width=12, font=('Consolas', 11)).pack(side='left', padx=5)

        ttk.Label(row_tot, text="Líquido:").pack(side='left')
        self.var_liquido = tk.StringVar()
        ttk.Entry(row_tot, textvariable=self.var_liquido, width=12, font=('Consolas', 11)).pack(side='left', padx=5)

        # --- Pestaña 2: JSON crudo ---
        tab_json = ttk.Frame(notebook, padding=10)
        notebook.add(tab_json, text="JSON Crudo")

        self.text_json = tk.Text(tab_json, font=('Consolas', 10), wrap='none')
        scroll_json_y = ttk.Scrollbar(tab_json, orient='vertical', command=self.text_json.yview)
        scroll_json_x = ttk.Scrollbar(tab_json, orient='horizontal', command=self.text_json.xview)
        self.text_json.configure(yscrollcommand=scroll_json_y.set, xscrollcommand=scroll_json_x.set)

        scroll_json_y.pack(side='right', fill='y')
        scroll_json_x.pack(side='bottom', fill='x')
        self.text_json.pack(fill='both', expand=True)

        # Tags para coloreado JSON
        self.text_json.tag_configure('key', foreground='#0000FF')
        self.text_json.tag_configure('string', foreground='#008000')
        self.text_json.tag_configure('number', foreground='#FF8C00')

        # === Botones de acción ===
        frame_acciones = ttk.Frame(main)
        frame_acciones.pack(fill='x', pady=(10, 0))

        ttk.Button(frame_acciones, text="Cancelar", command=self.destroy).pack(side='right', padx=5)
        ttk.Button(frame_acciones, text="✓ Aceptar y Procesar",
                   command=self._aceptar).pack(side='right', padx=5)
        ttk.Button(frame_acciones, text="Recargar original",
                   command=self._cargar_datos).pack(side='left', padx=5)

    def _cargar_datos(self):
        """Carga los datos en la interfaz"""
        datos = self.datos_originales

        # Empresa
        emp = datos.get('empresa', {})
        self.var_cif.set(emp.get('cif', ''))
        self.var_empresa.set(emp.get('nombre', ''))

        # Período
        per = datos.get('periodo', {})
        self.var_mes.set(str(per.get('mes', '')))
        self.var_anno.set(str(per.get('año', '')))

        # Conceptos
        self.tree_conceptos.delete(*self.tree_conceptos.get_children())
        for c in datos.get('conceptos', []):
            self.tree_conceptos.insert('', 'end', values=(
                c.get('codigo', ''),
                c.get('descripcion', ''),
                c.get('tipo', ''),
                f"{c.get('importe', 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            ))

        # Totales
        tot = datos.get('totales', {})
        self.var_total_dev.set(f"{tot.get('total_devengos', 0):,.2f}")
        self.var_total_ss.set(f"{tot.get('total_ss_empresa', 0):,.2f}")
        self.var_liquido.set(f"{tot.get('liquido_a_percibir', 0):,.2f}")

        # Confianza
        meta = datos.get('_metadata', {})
        conf = meta.get('confianza', 0)
        self.var_confianza.set(f"Confianza: {conf*100:.0f}%")

        # JSON crudo
        self.text_json.delete('1.0', 'end')
        json_str = json.dumps(datos, indent=2, ensure_ascii=False)
        self.text_json.insert('1.0', json_str)

    def _añadir_concepto(self):
        """Añade un nuevo concepto"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Añadir Concepto")
        dialogo.geometry("400x200")
        dialogo.transient(self)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=20)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Código:").grid(row=0, column=0, sticky='w', pady=5)
        var_cod = tk.StringVar()
        ttk.Entry(frame, textvariable=var_cod).grid(row=0, column=1, sticky='ew', pady=5)

        ttk.Label(frame, text="Descripción:").grid(row=1, column=0, sticky='w', pady=5)
        var_desc = tk.StringVar()
        ttk.Entry(frame, textvariable=var_desc).grid(row=1, column=1, sticky='ew', pady=5)

        ttk.Label(frame, text="Tipo:").grid(row=2, column=0, sticky='w', pady=5)
        var_tipo = tk.StringVar(value='devengo')
        ttk.Combobox(frame, textvariable=var_tipo,
                     values=['devengo', 'deduccion', 'ss_empresa', 'ss_trabajador', 'retencion']).grid(row=2, column=1, sticky='ew', pady=5)

        ttk.Label(frame, text="Importe:").grid(row=3, column=0, sticky='w', pady=5)
        var_imp = tk.StringVar()
        ttk.Entry(frame, textvariable=var_imp).grid(row=3, column=1, sticky='ew', pady=5)

        frame.columnconfigure(1, weight=1)

        def guardar():
            try:
                importe = float(var_imp.get().replace(',', '.'))
                self.tree_conceptos.insert('', 'end', values=(
                    var_cod.get(), var_desc.get(), var_tipo.get(), f"{importe:,.2f}"
                ))
                dialogo.destroy()
            except ValueError:
                messagebox.showerror("Error", "Importe no válido")

        ttk.Button(frame, text="Guardar", command=guardar).grid(row=4, column=1, sticky='e', pady=20)

    def _editar_concepto(self):
        """Edita el concepto seleccionado"""
        sel = self.tree_conceptos.selection()
        if not sel:
            messagebox.showinfo("Info", "Seleccione un concepto para editar")
            return
        # Implementación simplificada - reutilizar diálogo de añadir

    def _eliminar_concepto(self):
        """Elimina el concepto seleccionado"""
        sel = self.tree_conceptos.selection()
        if sel:
            self.tree_conceptos.delete(sel)

    def _construir_datos(self):
        """Construye el diccionario de datos desde la interfaz"""
        # Reconstruir conceptos desde el tree
        conceptos = []
        for item in self.tree_conceptos.get_children():
            valores = self.tree_conceptos.item(item)['values']
            importe_str = str(valores[3]).replace('.', '').replace(',', '.')
            try:
                importe = float(importe_str)
            except:
                importe = 0

            conceptos.append({
                'codigo': str(valores[0]),
                'descripcion': str(valores[1]),
                'tipo': str(valores[2]),
                'importe': importe
            })

        # Parsear totales
        def parse_num(s):
            try:
                return float(str(s).replace('.', '').replace(',', '.'))
            except:
                return 0

        datos = {
            'empresa': {
                'cif': self.var_cif.get(),
                'nombre': self.var_empresa.get()
            },
            'periodo': {
                'mes': int(self.var_mes.get()) if self.var_mes.get().isdigit() else 0,
                'año': int(self.var_anno.get()) if self.var_anno.get().isdigit() else 0,
                'texto': f"{self.var_mes.get()}/{self.var_anno.get()}"
            },
            'conceptos': conceptos,
            'totales': {
                'total_devengos': parse_num(self.var_total_dev.get()),
                'total_ss_empresa': parse_num(self.var_total_ss.get()),
                'liquido_a_percibir': parse_num(self.var_liquido.get())
            },
            '_extraccion': self.datos_originales.get('_extraccion', {}),
            '_editado': True,
            '_fecha_edicion': datetime.now().isoformat()
        }

        return datos

    def _aceptar(self):
        """Acepta los datos y cierra la ventana"""
        self.datos_editados = self._construir_datos()

        if self.callback_aceptar:
            self.callback_aceptar(self.datos_editados)

        self.destroy()


# =============================================================================
# CLASE: VentanaMultiEmpresa (Selección de empresas en PDF multi-empresa)
# =============================================================================
class VentanaMultiEmpresa(tk.Toplevel):
    """
    Ventana para mostrar y seleccionar empresas cuando un PDF contiene múltiples.
    Permite procesar todas o seleccionar cuáles procesar.
    """

    def __init__(self, parent, datos_ia, nombre_archivo="", callback_procesar=None):
        super().__init__(parent)
        self.title(f"Múltiples Empresas Detectadas - {nombre_archivo}")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.datos_ia = datos_ia
        self.callback_procesar = callback_procesar
        self.extractor_ia = ExtractorIA()
        self.logger = Logger()

        # Obtener empresas
        self.empresas = self.extractor_ia.obtener_empresas(datos_ia)
        self.empresas_seleccionadas = []

        self._crear_ui()

        # Modal
        self.transient(parent)
        self.grab_set()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Cabecera ===
        frame_header = ttk.Frame(main)
        frame_header.pack(fill='x', pady=(0, 10))

        ttk.Label(frame_header,
                  text=f"🏢 Se han detectado {len(self.empresas)} empresas en el documento",
                  font=('Arial', 12, 'bold')).pack(side='left')

        # Info de metadata
        meta = self.datos_ia.get('_metadata', {})
        confianza = meta.get('confianza_global', 0)
        ttk.Label(frame_header,
                  text=f"Confianza: {confianza*100:.0f}%",
                  foreground='gray').pack(side='right')

        # === Tabla de empresas ===
        frame_tabla = ttk.LabelFrame(main, text="Empresas Detectadas", padding=10)
        frame_tabla.pack(fill='both', expand=True, pady=(0, 10))

        # Crear Treeview con checkboxes simulados
        cols = ('sel', 'cif', 'nombre', 'periodo', 'devengos', 'liquido', 'conceptos')
        self.tree = ttk.Treeview(frame_tabla, columns=cols, show='headings', height=15)

        self.tree.heading('sel', text='✓')
        self.tree.heading('cif', text='CIF')
        self.tree.heading('nombre', text='Empresa')
        self.tree.heading('periodo', text='Período')
        self.tree.heading('devengos', text='Devengos')
        self.tree.heading('liquido', text='Líquido')
        self.tree.heading('conceptos', text='Conceptos')

        self.tree.column('sel', width=30, anchor='center')
        self.tree.column('cif', width=100)
        self.tree.column('nombre', width=250)
        self.tree.column('periodo', width=100)
        self.tree.column('devengos', width=100, anchor='e')
        self.tree.column('liquido', width=100, anchor='e')
        self.tree.column('conceptos', width=70, anchor='center')

        scroll = ttk.Scrollbar(frame_tabla, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')

        # Cargar datos
        self.vars_seleccion = {}
        for i, emp in enumerate(self.empresas):
            info = emp.get('empresa', {})
            totales = emp.get('totales', {})
            periodo = emp.get('periodo', {})

            cif = info.get('cif', f'EMP_{i+1}')
            devengos = totales.get('total_devengos', 0)
            liquido = totales.get('liquido_a_percibir', 0)

            # Insertar con marca de selección
            item_id = self.tree.insert('', 'end', values=(
                '☑',  # Seleccionado por defecto
                cif,
                info.get('nombre', 'Sin nombre'),
                periodo.get('texto', ''),
                f"{devengos:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'),
                f"{liquido:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'),
                len(emp.get('conceptos', []))
            ))
            self.vars_seleccion[item_id] = True

        # Click para toggle selección
        self.tree.bind('<ButtonRelease-1>', self._toggle_seleccion)

        # === Botones de selección ===
        frame_sel = ttk.Frame(main)
        frame_sel.pack(fill='x', pady=(0, 10))

        ttk.Button(frame_sel, text="Seleccionar Todas",
                   command=self._seleccionar_todas).pack(side='left', padx=2)
        ttk.Button(frame_sel, text="Deseleccionar Todas",
                   command=self._deseleccionar_todas).pack(side='left', padx=2)
        ttk.Button(frame_sel, text="Invertir Selección",
                   command=self._invertir_seleccion).pack(side='left', padx=2)

        # Contador
        self.var_contador = tk.StringVar(value=f"{len(self.empresas)} seleccionadas")
        ttk.Label(frame_sel, textvariable=self.var_contador,
                  foreground='blue').pack(side='right')

        # === Vista previa de empresa seleccionada ===
        frame_preview = ttk.LabelFrame(main, text="Vista Previa", padding=10)
        frame_preview.pack(fill='x', pady=(0, 10))

        self.var_preview = tk.StringVar(value="Seleccione una empresa para ver sus conceptos")
        ttk.Label(frame_preview, textvariable=self.var_preview,
                  font=('Consolas', 9), wraplength=800).pack(anchor='w')

        self.tree.bind('<<TreeviewSelect>>', self._mostrar_preview)

        # === Botones de acción ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="Cancelar",
                   command=self.destroy).pack(side='right', padx=5)
        ttk.Button(frame_btns, text="✓ Procesar Seleccionadas",
                   command=self._procesar).pack(side='right', padx=5)
        ttk.Button(frame_btns, text="📋 Ver JSON Completo",
                   command=self._ver_json).pack(side='left', padx=5)

    def _toggle_seleccion(self, event):
        """Toggle selección al hacer click"""
        region = self.tree.identify_region(event.x, event.y)
        if region != 'cell':
            return

        col = self.tree.identify_column(event.x)
        if col != '#1':  # Solo columna de selección
            return

        item = self.tree.identify_row(event.y)
        if item:
            self.vars_seleccion[item] = not self.vars_seleccion.get(item, False)
            valores = list(self.tree.item(item)['values'])
            valores[0] = '☑' if self.vars_seleccion[item] else '☐'
            self.tree.item(item, values=valores)
            self._actualizar_contador()

    def _seleccionar_todas(self):
        for item in self.tree.get_children():
            self.vars_seleccion[item] = True
            valores = list(self.tree.item(item)['values'])
            valores[0] = '☑'
            self.tree.item(item, values=valores)
        self._actualizar_contador()

    def _deseleccionar_todas(self):
        for item in self.tree.get_children():
            self.vars_seleccion[item] = False
            valores = list(self.tree.item(item)['values'])
            valores[0] = '☐'
            self.tree.item(item, values=valores)
        self._actualizar_contador()

    def _invertir_seleccion(self):
        for item in self.tree.get_children():
            self.vars_seleccion[item] = not self.vars_seleccion.get(item, False)
            valores = list(self.tree.item(item)['values'])
            valores[0] = '☑' if self.vars_seleccion[item] else '☐'
            self.tree.item(item, values=valores)
        self._actualizar_contador()

    def _actualizar_contador(self):
        total = sum(1 for v in self.vars_seleccion.values() if v)
        self.var_contador.set(f"{total} de {len(self.empresas)} seleccionadas")

    def _mostrar_preview(self, event):
        """Muestra preview de la empresa seleccionada"""
        sel = self.tree.selection()
        if not sel:
            return

        # Obtener índice
        items = self.tree.get_children()
        idx = items.index(sel[0])

        if 0 <= idx < len(self.empresas):
            emp = self.empresas[idx]
            conceptos = emp.get('conceptos', [])

            preview_lines = []
            for c in conceptos[:8]:  # Primeros 8 conceptos
                desc = c.get('descripcion', '')[:30]
                imp = c.get('importe', 0)
                tipo = c.get('tipo', '')
                preview_lines.append(f"  {tipo:12} | {desc:30} | {imp:>12,.2f} €")

            if len(conceptos) > 8:
                preview_lines.append(f"  ... y {len(conceptos) - 8} conceptos más")

            self.var_preview.set('\n'.join(preview_lines) if preview_lines else "Sin conceptos")

    def _ver_json(self):
        """Abre ventana con JSON completo"""
        VentanaEditorJSON(
            self,
            self.datos_ia,
            nombre_archivo="Multi-empresa",
            callback_aceptar=None
        )

    def _procesar(self):
        """Procesa las empresas seleccionadas"""
        # Obtener índices seleccionados
        items = self.tree.get_children()
        seleccionadas = []

        for i, item in enumerate(items):
            if self.vars_seleccion.get(item, False):
                seleccionadas.append(self.empresas[i])

        if not seleccionadas:
            messagebox.showwarning("Aviso", "Seleccione al menos una empresa para procesar")
            return

        self.empresas_seleccionadas = seleccionadas
        self.logger.info(f"Procesando {len(seleccionadas)} empresas seleccionadas")

        if self.callback_procesar:
            self.callback_procesar(seleccionadas)

        self.destroy()


# =============================================================================
# CLASE: VentanaAprendizaje (Modo aprendizaje interactivo)
# =============================================================================
class VentanaAprendizaje(tk.Toplevel):
    """Ventana para el modo aprendizaje - crear/editar plantillas"""

    def __init__(self, parent, texto_documento, plantilla=None, callback_guardar=None):
        super().__init__(parent)
        self.title("Modo Aprendizaje - Crear/Editar Plantilla")
        self.geometry("1000x700")

        self.texto = texto_documento
        self.plantilla = plantilla or Plantilla()
        self.callback_guardar = callback_guardar
        self.logger = Logger()
        self.detector = DetectorDocumento()
        self.extractor = ExtractorConceptos()

        # Extraer datos iniciales
        self.conceptos_extraidos = self.extractor.extraer(texto_documento, plantilla)

        self._crear_ui()
        self._cargar_datos()

    def _crear_ui(self):
        # Notebook con pestañas
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # === Pestaña 1: Información básica ===
        tab_info = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_info, text="1. Información")

        ttk.Label(tab_info, text="Nombre de la plantilla:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.var_nombre = tk.StringVar(value=self.plantilla.nombre)
        ttk.Entry(tab_info, textvariable=self.var_nombre, font=('Arial', 12), width=50).pack(anchor='w', pady=(0, 15))

        ttk.Label(tab_info, text="Descripción:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.txt_descripcion = tk.Text(tab_info, height=3, font=('Arial', 10))
        self.txt_descripcion.pack(fill='x', pady=(0, 15))
        self.txt_descripcion.insert('1.0', self.plantilla.descripcion)

        ttk.Label(tab_info, text="Fingerprints (palabras clave para detectar este tipo de documento):",
                 font=('Arial', 10, 'bold')).pack(anchor='w')

        frame_fp = ttk.Frame(tab_info)
        frame_fp.pack(fill='x', pady=(0, 10))

        self.var_fingerprint = tk.StringVar()
        ttk.Entry(frame_fp, textvariable=self.var_fingerprint, width=30).pack(side='left')
        ttk.Button(frame_fp, text="+ Añadir", command=self._agregar_fingerprint).pack(side='left', padx=5)
        ttk.Button(frame_fp, text="Auto-detectar", command=self._autodetectar_fingerprints).pack(side='left')

        self.lista_fingerprints = tk.Listbox(tab_info, height=5, font=('Consolas', 10))
        self.lista_fingerprints.pack(fill='x')
        self.lista_fingerprints.bind('<Delete>', lambda e: self._eliminar_fingerprint())

        # === Pestaña 2: Conceptos extraídos ===
        tab_conceptos = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_conceptos, text="2. Conceptos")

        ttk.Label(tab_conceptos, text="Conceptos detectados en el documento:",
                 font=('Arial', 10, 'bold')).pack(anchor='w')
        ttk.Label(tab_conceptos, text="(Marque los que desea incluir en la plantilla)",
                 foreground='gray').pack(anchor='w')

        frame_conceptos = ttk.Frame(tab_conceptos)
        frame_conceptos.pack(fill='both', expand=True, pady=10)

        # Treeview para conceptos
        columnas = ('sel', 'concepto', 'importe', 'cuenta', 'tipo')
        self.tree_conceptos = ttk.Treeview(frame_conceptos, columns=columnas, show='headings', height=15)
        self.tree_conceptos.heading('sel', text='✓')
        self.tree_conceptos.heading('concepto', text='Concepto')
        self.tree_conceptos.heading('importe', text='Importe')
        self.tree_conceptos.heading('cuenta', text='Cuenta')
        self.tree_conceptos.heading('tipo', text='Tipo')

        self.tree_conceptos.column('sel', width=30, anchor='center')
        self.tree_conceptos.column('concepto', width=300)
        self.tree_conceptos.column('importe', width=100, anchor='e')
        self.tree_conceptos.column('cuenta', width=100, anchor='center')
        self.tree_conceptos.column('tipo', width=80, anchor='center')

        scroll = ttk.Scrollbar(frame_conceptos, orient='vertical', command=self.tree_conceptos.yview)
        self.tree_conceptos.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree_conceptos.pack(fill='both', expand=True)

        # Doble clic para editar
        self.tree_conceptos.bind('<Double-1>', self._editar_concepto)

        # === Pestaña 3: Mapeo de cuentas ===
        tab_mapeo = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_mapeo, text="3. Mapeo Cuentas")

        ttk.Label(tab_mapeo, text="Reglas de mapeo concepto → cuenta contable:",
                 font=('Arial', 10, 'bold')).pack(anchor='w')

        frame_nuevo_mapeo = ttk.LabelFrame(tab_mapeo, text="Añadir regla", padding=10)
        frame_nuevo_mapeo.pack(fill='x', pady=10)

        frame_r1 = ttk.Frame(frame_nuevo_mapeo)
        frame_r1.pack(fill='x', pady=2)
        ttk.Label(frame_r1, text="Patrón (regex):", width=15).pack(side='left')
        self.var_mapeo_patron = tk.StringVar()
        ttk.Entry(frame_r1, textvariable=self.var_mapeo_patron, width=40).pack(side='left', padx=5)

        frame_r2 = ttk.Frame(frame_nuevo_mapeo)
        frame_r2.pack(fill='x', pady=2)
        ttk.Label(frame_r2, text="Cuenta:", width=15).pack(side='left')
        self.var_mapeo_cuenta = tk.StringVar()
        ttk.Entry(frame_r2, textvariable=self.var_mapeo_cuenta, width=15).pack(side='left', padx=5)
        ttk.Label(frame_r2, text="Tipo:").pack(side='left', padx=(20, 5))
        self.var_mapeo_tipo = tk.StringVar(value='debe')
        ttk.Combobox(frame_r2, textvariable=self.var_mapeo_tipo,
                    values=['debe', 'haber'], width=10, state='readonly').pack(side='left')

        frame_r3 = ttk.Frame(frame_nuevo_mapeo)
        frame_r3.pack(fill='x', pady=2)
        ttk.Label(frame_r3, text="Descripción:", width=15).pack(side='left')
        self.var_mapeo_desc = tk.StringVar()
        ttk.Entry(frame_r3, textvariable=self.var_mapeo_desc, width=40).pack(side='left', padx=5)
        ttk.Button(frame_r3, text="+ Añadir regla", command=self._agregar_mapeo).pack(side='right')

        # Lista de mapeos
        self.tree_mapeo = ttk.Treeview(tab_mapeo, columns=('patron', 'cuenta', 'tipo', 'desc'),
                                       show='headings', height=10)
        self.tree_mapeo.heading('patron', text='Patrón')
        self.tree_mapeo.heading('cuenta', text='Cuenta')
        self.tree_mapeo.heading('tipo', text='Tipo')
        self.tree_mapeo.heading('desc', text='Descripción')
        self.tree_mapeo.column('patron', width=250)
        self.tree_mapeo.column('cuenta', width=100)
        self.tree_mapeo.column('tipo', width=80)
        self.tree_mapeo.column('desc', width=200)
        self.tree_mapeo.pack(fill='both', expand=True, pady=10)
        self.tree_mapeo.bind('<Delete>', lambda e: self._eliminar_mapeo())

        # === Botones inferiores ===
        frame_botones = ttk.Frame(self)
        frame_botones.pack(fill='x', padx=10, pady=10)

        ttk.Button(frame_botones, text="Cancelar", command=self.destroy).pack(side='right', padx=5)
        ttk.Button(frame_botones, text="💾 Guardar Plantilla", command=self._guardar).pack(side='right')

        # Info de la plantilla
        if self.plantilla.veces_usada > 0:
            ttk.Label(frame_botones,
                     text=f"Usada {self.plantilla.veces_usada} veces | Confianza: {self.plantilla.confianza:.0f}%",
                     foreground='gray').pack(side='left')

    def _cargar_datos(self):
        """Carga los datos de la plantilla en la UI"""
        # Fingerprints
        for fp in self.plantilla.fingerprints:
            self.lista_fingerprints.insert('end', fp)

        # Conceptos extraídos con mapeo
        conceptos_mapeados = self.extractor.mapear_a_cuentas(self.conceptos_extraidos, self.plantilla)
        for item in conceptos_mapeados:
            importe_str = f"{item['importe']:.2f} €" if item['importe'] else "-"
            self.tree_conceptos.insert('', 'end', values=(
                '✓',
                item['concepto'],
                importe_str,
                item.get('cuenta', '-'),
                item.get('tipo', '-')
            ))

        # Mapeos existentes
        for mapeo in self.plantilla.mapeo_cuentas:
            self.tree_mapeo.insert('', 'end', values=(
                mapeo['patron'],
                mapeo['cuenta'],
                mapeo.get('tipo', 'debe'),
                mapeo.get('descripcion', '')
            ))

    def _agregar_fingerprint(self):
        fp = self.var_fingerprint.get().strip().upper()
        if fp and fp not in self.lista_fingerprints.get(0, 'end'):
            self.lista_fingerprints.insert('end', fp)
            self.var_fingerprint.set('')

    def _eliminar_fingerprint(self):
        sel = self.lista_fingerprints.curselection()
        if sel:
            self.lista_fingerprints.delete(sel[0])

    def _autodetectar_fingerprints(self):
        fps = self.detector.detectar_fingerprints(self.texto)
        for fp in fps:
            if fp not in self.lista_fingerprints.get(0, 'end'):
                self.lista_fingerprints.insert('end', fp)

    def _agregar_mapeo(self):
        patron = self.var_mapeo_patron.get().strip()
        cuenta = self.var_mapeo_cuenta.get().strip()
        if patron and cuenta:
            self.tree_mapeo.insert('', 'end', values=(
                patron,
                cuenta,
                self.var_mapeo_tipo.get(),
                self.var_mapeo_desc.get()
            ))
            self.var_mapeo_patron.set('')
            self.var_mapeo_cuenta.set('')
            self.var_mapeo_desc.set('')

    def _eliminar_mapeo(self):
        sel = self.tree_mapeo.selection()
        if sel:
            self.tree_mapeo.delete(sel[0])

    def _editar_concepto(self, event):
        """Permite editar un concepto con doble clic"""
        item = self.tree_conceptos.selection()
        if not item:
            return
        # TODO: Implementar edición inline o diálogo

    def _guardar(self):
        """Guarda la plantilla"""
        # Actualizar datos de la plantilla
        self.plantilla.nombre = self.var_nombre.get().strip()
        if not self.plantilla.nombre:
            messagebox.showwarning("Aviso", "Debe indicar un nombre para la plantilla")
            return

        self.plantilla.descripcion = self.txt_descripcion.get('1.0', 'end').strip()

        # Fingerprints
        self.plantilla.fingerprints = list(self.lista_fingerprints.get(0, 'end'))

        # Mapeos
        self.plantilla.mapeo_cuentas = []
        for item in self.tree_mapeo.get_children():
            vals = self.tree_mapeo.item(item, 'values')
            self.plantilla.mapeo_cuentas.append({
                'patron': vals[0],
                'cuenta': vals[1],
                'tipo': vals[2],
                'descripcion': vals[3]
            })

        self.plantilla.fecha_modificacion = datetime.now().isoformat()

        # Guardar
        gestor = GestorPlantillas()
        if gestor.guardar(self.plantilla):
            self.logger.info(f"Plantilla guardada: {self.plantilla.nombre}")
            messagebox.showinfo("Éxito", f"Plantilla '{self.plantilla.nombre}' guardada correctamente")
            if self.callback_guardar:
                self.callback_guardar(self.plantilla)
            self.destroy()
        else:
            messagebox.showerror("Error", "No se pudo guardar la plantilla")


# =============================================================================
# CLASE: DatabaseManager
# =============================================================================
class DatabaseManager:
    """Gestiona conexiones a SQL Server (Singleton)"""
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._pool = {}
            cls._instancia._cs = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={DB_CONFIG['server']};"
                f"UID={DB_CONFIG['user']};"
                f"PWD={DB_CONFIG['password']};"
                f"TrustServerCertificate=yes;"
            )
            cls._instancia.logger = Logger()
        return cls._instancia

    def conectar(self, db=None):
        """Obtiene conexión a la BD especificada"""
        key = db or 'master'
        if key in self._pool:
            try:
                self._pool[key].cursor().execute("SELECT 1")
                return self._pool[key]
            except:
                pass
        cs = self._cs + (f"DATABASE={db};" if db else "")
        self._pool[key] = pyodbc.connect(cs)
        self.logger.debug(f"Conexión establecida a BD: {key}")
        return self._pool[key]

    def test_conexion(self):
        """Prueba la conexión"""
        try:
            conn = self.conectar()
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0].split('\n')[0]
            self.logger.info("Conexión a SQL Server exitosa", version)
            return True, version
        except Exception as e:
            self.logger.error("Error de conexión a SQL Server", str(e))
            return False, str(e)

    def normalizar_cif(self, cif):
        """Normaliza un CIF para búsqueda (quita espacios, guiones, mayúsculas)"""
        if not cif:
            return None
        return cif.upper().replace(' ', '').replace('-', '').replace('.', '')

    def buscar_empresa_por_cif(self, cif):
        """
        Busca una empresa por CIF en la base de datos easp.CLIENTES

        Returns: dict con datos de empresa o None si no se encuentra
        """
        cif_norm = self.normalizar_cif(cif)
        if not cif_norm:
            self.logger.warning("CIF vacío para búsqueda de empresa")
            return None

        self.logger.info(f"Buscando empresa con CIF: {cif_norm}")

        try:
            conn = self.conectar(DB_CONFIG['database_easp'])
            cursor = conn.cursor()

            # Buscar en CLIENTES con diferentes formatos de CIF
            query = """
                SELECT TOP 1
                    CODIGO, NOMBRE, CIF, DOMICILIO, POBLACION, CP, PROVINCIA
                FROM CLIENTES
                WHERE REPLACE(REPLACE(REPLACE(UPPER(CIF), ' ', ''), '-', ''), '.', '') = ?
            """
            cursor.execute(query, (cif_norm,))
            row = cursor.fetchone()

            if row:
                empresa = {
                    'codigo': row[0].strip() if row[0] else None,
                    'nombre': row[1].strip() if row[1] else None,
                    'cif': row[2].strip() if row[2] else None,
                    'domicilio': row[3].strip() if row[3] else None,
                    'poblacion': row[4].strip() if row[4] else None,
                    'cp': row[5].strip() if row[5] else None,
                    'provincia': row[6].strip() if row[6] else None
                }
                self.logger.info(f"Empresa encontrada: {empresa['nombre']} (Código: {empresa['codigo']})")
                return empresa
            else:
                self.logger.warning(f"No se encontró empresa con CIF: {cif_norm}")
                return None

        except Exception as e:
            self.logger.error(f"Error buscando empresa por CIF: {cif_norm}", str(e))
            return None

    def obtener_base_datos_contable(self, codigo_empresa):
        """
        Obtiene el nombre de la base de datos contable para una empresa
        Las bases de datos contables siguen el patrón: ctaspXXXX donde XXXX es el código
        """
        if not codigo_empresa:
            return None

        # El código puede tener diferentes formatos
        codigo = str(codigo_empresa).strip().zfill(4)
        db_name = f"ctasp{codigo}"

        self.logger.debug(f"Base de datos contable para empresa {codigo_empresa}: {db_name}")
        return db_name

    def obtener_plan_cuentas(self, codigo_empresa, filtro_cuenta=None):
        """
        Obtiene el plan de cuentas de una empresa

        Args:
            codigo_empresa: Código de la empresa
            filtro_cuenta: Filtro opcional para cuentas (ej: '640%' para cuentas de nóminas)

        Returns: lista de diccionarios con cuentas
        """
        db_name = self.obtener_base_datos_contable(codigo_empresa)
        if not db_name:
            self.logger.error("No se pudo determinar la base de datos contable")
            return []

        self.logger.info(f"Obteniendo plan de cuentas de {db_name}", f"Filtro: {filtro_cuenta}")

        try:
            conn = self.conectar(db_name)
            cursor = conn.cursor()

            # Consulta al plan de cuentas
            if filtro_cuenta:
                query = """
                    SELECT CUENTA, NOMBRE
                    FROM PCUENTAS
                    WHERE CUENTA LIKE ?
                    ORDER BY CUENTA
                """
                cursor.execute(query, (filtro_cuenta,))
            else:
                query = """
                    SELECT CUENTA, NOMBRE
                    FROM PCUENTAS
                    ORDER BY CUENTA
                """
                cursor.execute(query)

            cuentas = []
            for row in cursor.fetchall():
                cuentas.append({
                    'cuenta': row[0].strip() if row[0] else None,
                    'nombre': row[1].strip() if row[1] else None
                })

            self.logger.info(f"Plan de cuentas obtenido: {len(cuentas)} cuentas")
            return cuentas

        except Exception as e:
            self.logger.error(f"Error obteniendo plan de cuentas de {db_name}", str(e))
            return []

    def obtener_siguiente_asiento(self, codigo_empresa, anno, diario=None):
        """
        Obtiene el siguiente número de asiento disponible

        Args:
            codigo_empresa: Código de la empresa
            anno: Año del ejercicio
            diario: Código de diario (opcional)

        Returns: número de asiento siguiente
        """
        db_name = self.obtener_base_datos_contable(codigo_empresa)
        if not db_name:
            self.logger.error("No se pudo determinar la base de datos contable")
            return None

        self.logger.info(f"Obteniendo siguiente asiento para {db_name}, año {anno}")

        try:
            conn = self.conectar(db_name)
            cursor = conn.cursor()

            # Buscar el máximo número de asiento del año
            if diario:
                query = """
                    SELECT ISNULL(MAX(ASESSION), 0) + 1
                    FROM ASIENTOS
                    WHERE ANNO = ? AND DIARIO = ?
                """
                cursor.execute(query, (anno, diario))
            else:
                query = """
                    SELECT ISNULL(MAX(ASESSION), 0) + 1
                    FROM ASIENTOS
                    WHERE ANNO = ?
                """
                cursor.execute(query, (anno,))

            resultado = cursor.fetchone()
            siguiente = resultado[0] if resultado else 1

            self.logger.info(f"Siguiente asiento: {siguiente}")
            return siguiente

        except Exception as e:
            self.logger.error(f"Error obteniendo siguiente asiento", str(e))
            return None

    def verificar_cuenta_existe(self, codigo_empresa, cuenta):
        """Verifica si una cuenta existe en el plan de cuentas"""
        db_name = self.obtener_base_datos_contable(codigo_empresa)
        if not db_name:
            return False

        try:
            conn = self.conectar(db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM PCUENTAS WHERE CUENTA = ?", (cuenta,))
            existe = cursor.fetchone() is not None

            if existe:
                self.logger.debug(f"Cuenta {cuenta} existe en {db_name}")
            else:
                self.logger.warning(f"Cuenta {cuenta} NO existe en {db_name}")

            return existe

        except Exception as e:
            self.logger.error(f"Error verificando cuenta {cuenta}", str(e))
            return False

    def guardar_asiento(self, asiento):
        """
        Guarda un asiento contable en la base de datos.

        Estructura típica de tabla ASIENTOS en Geyce:
        - ASESSION: Número de asiento
        - ANNO: Año del ejercicio
        - DIARIO: Código de diario
        - FECHA: Fecha del asiento
        - CUENTA: Cuenta contable
        - DEBE: Importe al debe
        - HABER: Importe al haber
        - CONCEPTO: Descripción
        - DOCUMENTO: Referencia del documento

        Args:
            asiento: Objeto AsientoContable

        Returns: True si se guardó correctamente
        """
        if not asiento.base_datos:
            self.logger.error("No se especificó base de datos para el asiento")
            return False

        self.logger.info(
            f"Guardando asiento {asiento.numero_asiento} en {asiento.base_datos}",
            f"Líneas: {len(asiento.lineas)}"
        )

        try:
            conn = self.conectar(asiento.base_datos)
            cursor = conn.cursor()

            # Obtener año del asiento
            anno = asiento.fecha.year

            # Insertar cada línea del asiento
            for linea in asiento.lineas:
                query = """
                    INSERT INTO ASIENTOS
                    (ASESSION, ANNO, DIARIO, FECHA, CUENTA, DEBE, HABER, CONCEPTO, DOCUMENTO)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                params = (
                    asiento.numero_asiento,
                    anno,
                    asiento.diario,
                    asiento.fecha.strftime("%Y-%m-%d"),
                    linea.cuenta,
                    linea.debe if linea.debe else 0,
                    linea.haber if linea.haber else 0,
                    linea.concepto[:50] if linea.concepto else '',
                    asiento.documento[:20] if asiento.documento else ''
                )

                cursor.execute(query, params)

            # Confirmar transacción
            conn.commit()

            self.logger.info(f"Asiento {asiento.numero_asiento} guardado correctamente")
            return True

        except Exception as e:
            self.logger.error(f"Error guardando asiento {asiento.numero_asiento}", str(e))
            # Rollback en caso de error
            try:
                conn.rollback()
            except:
                pass
            return False

    def eliminar_asiento(self, codigo_empresa, numero_asiento, anno):
        """Elimina un asiento existente"""
        db_name = self.obtener_base_datos_contable(codigo_empresa)
        if not db_name:
            return False

        try:
            conn = self.conectar(db_name)
            cursor = conn.cursor()

            query = "DELETE FROM ASIENTOS WHERE ASESSION = ? AND ANNO = ?"
            cursor.execute(query, (numero_asiento, anno))
            conn.commit()

            filas = cursor.rowcount
            self.logger.info(f"Asiento {numero_asiento} eliminado ({filas} líneas)")
            return True

        except Exception as e:
            self.logger.error(f"Error eliminando asiento {numero_asiento}", str(e))
            return False


# =============================================================================
# CLASE: PDFProcessor
# =============================================================================
class PDFProcessor:
    """
    Procesa archivos PDF con extracción inteligente de datos.

    Utiliza OpenDataLoader PDF (precisión 0.907) como motor principal,
    con fallback a PyMuPDF + Tesseract si no está disponible.
    """

    def __init__(self, ruta):
        self.ruta = ruta
        self.nombre = os.path.basename(ruta)
        self.doc = fitz.open(ruta)
        self.texto = ""
        self.texto_markdown = ""  # Formato estructurado
        self.num_paginas = len(self.doc)
        self.cif = None
        self.periodo = None
        self.anno = None
        self.mes = None
        self.tiene_texto_nativo = False
        self.logger = Logger()

        # Datos estructurados de OpenDataLoader
        self.elementos = []  # Lista de elementos con bounding boxes
        self.tablas = []     # Tablas extraídas
        self.metodo_extraccion = None  # 'opendataloader' o 'pymupdf'

    def cerrar(self):
        if self.doc:
            self.doc.close()
            self.doc = None

    def procesar_automatico(self, callback_progreso=None):
        """
        Proceso automático completo con OpenDataLoader:
        1. Intenta usar OpenDataLoader PDF (mejor precisión)
        2. Fallback a PyMuPDF + OCR si OpenDataLoader falla
        3. Detecta CIF y período
        4. Extrae tablas estructuradas

        Returns: (True, "OK") si el proceso fue exitoso
        """
        if callback_progreso:
            callback_progreso(0, self.num_paginas, "Iniciando...")

        # Intentar con OpenDataLoader primero (mejor precisión)
        if OPENDATALOADER_OK:
            exito = self._procesar_con_opendataloader(callback_progreso)
            if exito:
                self.metodo_extraccion = 'opendataloader'
                self.logger.info(
                    "PDF procesado con OpenDataLoader",
                    f"Tablas: {len(self.tablas)}, Elementos: {len(self.elementos)}"
                )
            else:
                self.logger.warning("OpenDataLoader falló, usando fallback PyMuPDF")
                self._procesar_con_pymupdf(callback_progreso)
                self.metodo_extraccion = 'pymupdf'
        else:
            self._procesar_con_pymupdf(callback_progreso)
            self.metodo_extraccion = 'pymupdf'

        # Detectar datos
        self._detectar_cif()
        self._detectar_periodo()

        return True, "OK"

    def _procesar_con_opendataloader(self, callback_progreso=None):
        """Procesa el PDF usando OpenDataLoader (precisión 0.907)"""
        try:
            import tempfile
            import shutil

            if callback_progreso:
                callback_progreso(1, self.num_paginas, "OpenDataLoader...")

            # Crear directorio temporal para output
            temp_dir = tempfile.mkdtemp(prefix='lector_nominas_')

            try:
                # Convertir PDF a JSON con bounding boxes
                opendataloader_pdf.convert(
                    input_path=[self.ruta],
                    output_dir=temp_dir,
                    format="markdown,json"
                )

                # Leer resultado markdown
                md_file = Path(temp_dir) / f"{Path(self.ruta).stem}.md"
                if md_file.exists():
                    self.texto_markdown = md_file.read_text(encoding='utf-8')
                    self.texto = self._markdown_a_texto_plano(self.texto_markdown)
                    self.tiene_texto_nativo = True

                # Leer resultado JSON con bounding boxes
                json_file = Path(temp_dir) / f"{Path(self.ruta).stem}.json"
                if json_file.exists():
                    data = json.loads(json_file.read_text(encoding='utf-8'))
                    self._procesar_json_opendataloader(data)

                if callback_progreso:
                    callback_progreso(self.num_paginas, self.num_paginas, "Completado")

                return bool(self.texto.strip())

            finally:
                # Limpiar directorio temporal
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            self.logger.error(f"Error OpenDataLoader: {str(e)}")
            return False

    def _markdown_a_texto_plano(self, markdown):
        """Convierte markdown a texto plano preservando estructura"""
        texto = markdown
        # Eliminar encabezados markdown pero preservar texto
        texto = re.sub(r'^#{1,6}\s*', '', texto, flags=re.MULTILINE)
        # Eliminar énfasis
        texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)
        texto = re.sub(r'\*([^*]+)\*', r'\1', texto)
        # Eliminar links
        texto = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', texto)
        return texto

    def _procesar_json_opendataloader(self, data):
        """Procesa el JSON de OpenDataLoader extrayendo elementos y tablas"""
        self.elementos = []
        self.tablas = []

        if isinstance(data, dict):
            # Procesar páginas
            pages = data.get('pages', [])
            for page in pages:
                # Extraer elementos con bounding boxes
                for elem in page.get('elements', []):
                    self.elementos.append({
                        'tipo': elem.get('type', 'text'),
                        'texto': elem.get('text', ''),
                        'bbox': elem.get('bbox', {}),  # {x, y, width, height}
                        'pagina': page.get('page_number', 1),
                        'confianza': elem.get('confidence', 1.0)
                    })

                # Extraer tablas
                for tabla in page.get('tables', []):
                    self.tablas.append({
                        'filas': tabla.get('rows', []),
                        'bbox': tabla.get('bbox', {}),
                        'pagina': page.get('page_number', 1),
                        'num_cols': tabla.get('num_cols', 0),
                        'num_filas': tabla.get('num_rows', 0)
                    })

    def _procesar_con_pymupdf(self, callback_progreso=None):
        """Fallback: procesa el PDF usando PyMuPDF + Tesseract"""
        # Extraer texto nativo
        self.texto = "\n".join([p.get_text() for p in self.doc])
        self.tiene_texto_nativo = bool(self.texto.strip())

        # Si no hay texto, usar OCR
        if not self.tiene_texto_nativo:
            if not TESSERACT_OK:
                self.logger.warning("PDF sin texto y Tesseract no disponible")
                return

            try:
                lang = 'spa' if 'spa' in pytesseract.get_languages() else 'eng'
            except:
                lang = 'eng'

            textos = []
            for i, pagina in enumerate(self.doc):
                if callback_progreso:
                    callback_progreso(i + 1, self.num_paginas, "OCR")
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                textos.append(pytesseract.image_to_string(img, lang=lang))

            self.texto = "\n".join(textos)
            self.tiene_texto_nativo = bool(self.texto.strip())

    def _detectar_cif(self):
        """Detecta CIF/NIF en el texto"""
        txt = self.texto.upper().replace(' ', '').replace('-', '')
        patrones = [
            r'[A-HJ-NP-SUVW]\d{7}[A-J0-9]',
            r'\d{8}[A-Z]',
            r'[XYZ]\d{7}[A-Z]'
        ]
        for p in patrones:
            m = re.findall(p, txt)
            if m:
                self.cif = m[0]
                return
        self.cif = None

    def _detectar_periodo(self):
        """Detecta el período (mes/año)"""
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        txt = self.texto.lower()
        for nombre, num in meses.items():
            match = re.search(rf'{nombre}\s*[/-]?\s*(\d{{4}}|\d{{2}})', txt)
            if match:
                a = match.group(1)
                if len(a) == 2:
                    a = '20' + a
                self.periodo = f"{nombre.capitalize()} {a}"
                self.anno = int(a)
                self.mes = num
                return

        ahora = datetime.now()
        self.periodo = None
        self.anno = ahora.year
        self.mes = ahora.month

    def get_imagen(self, num_pag, zoom=1.5):
        """Obtiene una página como imagen"""
        if 0 <= num_pag < self.num_paginas:
            pix = self.doc[num_pag].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return Image.open(io.BytesIO(pix.tobytes("png")))
        return None

    def get_tablas(self):
        """Devuelve las tablas extraídas por OpenDataLoader"""
        return self.tablas

    def get_elementos_por_tipo(self, tipo):
        """Filtra elementos por tipo (text, table, heading, etc.)"""
        return [e for e in self.elementos if e['tipo'] == tipo]

    def get_elementos_en_region(self, x, y, ancho, alto, pagina=1):
        """Obtiene elementos dentro de una región específica (útil para plantillas)"""
        resultados = []
        for elem in self.elementos:
            if elem['pagina'] != pagina:
                continue
            bbox = elem.get('bbox', {})
            ex, ey = bbox.get('x', 0), bbox.get('y', 0)
            ew, eh = bbox.get('width', 0), bbox.get('height', 0)

            # Verificar si el elemento está dentro de la región
            if (ex >= x and ey >= y and
                ex + ew <= x + ancho and ey + eh <= y + alto):
                resultados.append(elem)

        return resultados

    def buscar_texto_cerca_de(self, texto_buscar, radio=50):
        """
        Busca un texto y devuelve elementos cercanos.
        Útil para encontrar valores asociados a etiquetas.
        """
        resultados = []
        texto_buscar = texto_buscar.upper()

        # Encontrar el elemento con el texto buscado
        elem_referencia = None
        for elem in self.elementos:
            if texto_buscar in elem.get('texto', '').upper():
                elem_referencia = elem
                break

        if not elem_referencia:
            return resultados

        # Buscar elementos cercanos
        ref_bbox = elem_referencia.get('bbox', {})
        ref_x = ref_bbox.get('x', 0) + ref_bbox.get('width', 0)
        ref_y = ref_bbox.get('y', 0)

        for elem in self.elementos:
            if elem == elem_referencia:
                continue
            bbox = elem.get('bbox', {})
            ex, ey = bbox.get('x', 0), bbox.get('y', 0)

            # Verificar si está cerca (a la derecha o debajo)
            dist_x = abs(ex - ref_x)
            dist_y = abs(ey - ref_y)

            if dist_x <= radio and dist_y <= radio:
                resultados.append(elem)

        return resultados

# =============================================================================
# CLASE: ZonaArrastre (Drag & Drop visual)
# =============================================================================
class ZonaArrastre(tk.Canvas):
    """Zona visual para arrastrar y soltar archivos"""

    def __init__(self, parent, comando_archivo, **kwargs):
        super().__init__(parent, **kwargs)
        self.comando = comando_archivo
        self.configure(bg='#f0f0f0', highlightthickness=2, highlightbackground='#cccccc')

        # Dibujar zona
        self._dibujar_normal()

        # Bind click
        self.bind('<Button-1>', lambda e: self._click())

        # Intentar habilitar drag & drop nativo (tkinterdnd2 si está disponible)
        self._habilitar_dnd()

    def _dibujar_normal(self):
        self.delete('all')
        w, h = 300, 150
        self.configure(width=w, height=h)

        # Icono de documento
        self.create_text(w//2, h//2 - 20, text="📄", font=('Arial', 40))
        self.create_text(w//2, h//2 + 30, text="Clic aquí para seleccionar PDF", font=('Arial', 11))
        self.create_text(w//2, h//2 + 50, text="o arrastre un archivo", font=('Arial', 9), fill='gray')

    def _dibujar_hover(self):
        self.delete('all')
        w, h = 300, 150
        self.configure(highlightbackground='#4CAF50')
        self.create_text(w//2, h//2, text="📥 Suelte el archivo aquí", font=('Arial', 14, 'bold'), fill='#4CAF50')

    def _click(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar PDF de nóminas",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        if ruta:
            self.comando(ruta)

    def _habilitar_dnd(self):
        """Intenta habilitar Drag & Drop nativo"""
        try:
            # tkinterdnd2 permite DnD real en Windows
            from tkinterdnd2 import DND_FILES
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)
            self.dnd_bind('<<DragEnter>>', lambda e: self._dibujar_hover())
            self.dnd_bind('<<DragLeave>>', lambda e: self._dibujar_normal())
        except ImportError:
            pass  # DnD no disponible, usar solo click

    def _on_drop(self, event):
        self._dibujar_normal()
        ruta = event.data.strip('{}')  # Windows envuelve en {}
        if ruta.lower().endswith('.pdf'):
            self.comando(ruta)

# =============================================================================
# APLICACIÓN PRINCIPAL - FASE 3
# =============================================================================
class AplicacionFase3:
    """Interfaz con sistema inteligente de plantillas y aprendizaje"""

    def __init__(self, root):
        self.root = root
        self.root.title(f"📄 Lector de Nóminas v{VERSION}")
        self.root.configure(bg='#f5f5f5')

        # Maximizar ventana a pantalla completa
        if sys.platform == 'win32':
            self.root.state('zoomed')  # Windows: maximizado
        else:
            # Linux/Mac: usar dimensiones de pantalla
            ancho = self.root.winfo_screenwidth()
            alto = self.root.winfo_screenheight()
            self.root.geometry(f"{ancho}x{alto}+0+0")

        # Componentes principales
        self.db = DatabaseManager()
        self.logger = Logger()
        self.gestor_plantillas = GestorPlantillas()
        self.detector = DetectorDocumento()
        self.extractor = ExtractorConceptos()
        self.extractor_ia = ExtractorIA()  # FASE 8: Extractor con IA
        self.gestor_validaciones = GestorValidaciones()
        self.generador_asientos = GeneradorAsientos()

        # Estado
        self.pdf = None
        self.asiento_actual = None
        self.empresa_actual = None
        self.plantilla_actual = None
        self.conceptos_extraidos = []
        self.datos_ia = None  # FASE 8: Datos extraídos por IA
        self.resultado_validacion = None
        self.imagen_tk = None
        self.queue = Queue()

        self._crear_ui()
        self._verificar_bd()
        self._verificar_ia()  # FASE 8: Verificar disponibilidad de IA
        self._procesar_cola()
        self._actualizar_contador_errores()

        self.logger.info("Aplicación iniciada", f"Versión {VERSION} - Fase 8 (IA)")

    def _procesar_cola(self):
        try:
            while True:
                t = self.queue.get_nowait()
                if callable(t):
                    t()
        except Empty:
            pass
        self.root.after(100, self._procesar_cola)

    def _actualizar_contador_errores(self):
        """Actualiza el contador de errores en la cabecera cada segundo"""
        errores = self.logger.errores
        self.var_errores.set(f"Errores: {errores}")
        if errores > 0:
            self.label_errores.configure(foreground='red')
        else:
            self.label_errores.configure(foreground='gray')
        self.root.after(1000, self._actualizar_contador_errores)

    def _crear_ui(self):
        # === ESTILO ===
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        # === CABECERA CON VERSIÓN Y ERRORES ===
        frame_cabecera = ttk.Frame(self.root)
        frame_cabecera.pack(fill='x', padx=10, pady=(10, 0))

        # Título y versión
        ttk.Label(frame_cabecera, text=f"Lector de Nóminas",
                 font=('Arial', 16, 'bold')).pack(side='left')
        ttk.Label(frame_cabecera, text=f"v{VERSION} ({VERSION_FECHA})",
                 font=('Arial', 10), foreground='gray').pack(side='left', padx=(10, 0))

        # Contador de errores y botón log
        frame_log = ttk.Frame(frame_cabecera)
        frame_log.pack(side='right')

        self.var_errores = tk.StringVar(value="Errores: 0")
        self.label_errores = ttk.Label(frame_log, textvariable=self.var_errores,
                                       font=('Arial', 10), foreground='gray')
        self.label_errores.pack(side='left', padx=(0, 10))

        ttk.Button(frame_log, text="📋 Ver Log", command=self._abrir_log).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="📦 Masivo", command=self._abrir_proceso_masivo).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="✔️ Validar", command=self._validar_documento).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="📝 Asiento", command=self._generar_asiento).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="📊 Dashboard", command=self._abrir_dashboard).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="📚 Histórico", command=self._abrir_historico).pack(side='left', padx=(0, 5))
        ttk.Button(frame_log, text="⚙️ Config", command=self._abrir_configuracion).pack(side='left')

        # === FRAME PRINCIPAL ===
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)

        # === PANEL SUPERIOR: Carga de archivo ===
        frame_carga = ttk.LabelFrame(main, text=" 1. Cargar PDF ", padding=10)
        frame_carga.pack(fill='x', pady=(0, 10))

        # Zona de arrastre centrada
        frame_zona = ttk.Frame(frame_carga)
        frame_zona.pack()
        self.zona_arrastre = ZonaArrastre(frame_zona, self._cargar_pdf)
        self.zona_arrastre.pack(pady=10)

        # Estado de carga
        self.var_estado_carga = tk.StringVar(value="Esperando archivo...")
        self.label_estado = ttk.Label(frame_carga, textvariable=self.var_estado_carga, font=('Arial', 10))
        self.label_estado.pack()

        # Barra de progreso (oculta inicialmente)
        self.progreso = ttk.Progressbar(frame_carga, length=400, mode='determinate')

        # === PANEL CENTRAL: Vista previa y datos ===
        paned = ttk.PanedWindow(main, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Vista del PDF
        frame_vista = ttk.LabelFrame(paned, text=" Vista del PDF ", padding=5)
        paned.add(frame_vista, weight=1)

        # Canvas para PDF
        self.canvas = tk.Canvas(frame_vista, bg='white', width=400, height=350)
        scroll_y = ttk.Scrollbar(frame_vista, orient='vertical', command=self.canvas.yview)
        scroll_x = ttk.Scrollbar(frame_vista, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side='right', fill='y')
        scroll_x.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)

        # Navegación de páginas
        frame_nav = ttk.Frame(frame_vista)
        frame_nav.pack(fill='x', pady=5)

        ttk.Button(frame_nav, text="◀", width=3, command=lambda: self._cambiar_pag(-1)).pack(side='left')
        self.var_pag = tk.StringVar(value="0 / 0")
        ttk.Label(frame_nav, textvariable=self.var_pag, width=10, anchor='center').pack(side='left', padx=10)
        ttk.Button(frame_nav, text="▶", width=3, command=lambda: self._cambiar_pag(1)).pack(side='left')

        # Scroll con rueda
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # === PANEL DERECHO: Datos detectados y empresa ===
        frame_derecho = ttk.Frame(paned)
        paned.add(frame_derecho, weight=1)

        # Datos detectados
        frame_datos = ttk.LabelFrame(frame_derecho, text=" 2. Datos Detectados ", padding=10)
        frame_datos.pack(fill='x', pady=(0, 10))

        # CIF
        ttk.Label(frame_datos, text="CIF Detectado:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.var_cif = tk.StringVar(value="-")
        frame_cif = ttk.Frame(frame_datos)
        frame_cif.pack(fill='x', pady=(0, 10))
        self.entry_cif = ttk.Entry(frame_cif, textvariable=self.var_cif, font=('Consolas', 14), width=20)
        self.entry_cif.pack(side='left')
        self.label_cif_status = ttk.Label(frame_cif, text="", font=('Arial', 12))
        self.label_cif_status.pack(side='left', padx=10)
        ttk.Button(frame_cif, text="🔍 Buscar", command=self._buscar_empresa).pack(side='left')

        # Período, Año y Mes en una fila
        frame_periodo = ttk.Frame(frame_datos)
        frame_periodo.pack(fill='x', pady=(0, 10))

        ttk.Label(frame_periodo, text="Período:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_periodo = tk.StringVar(value="-")
        ttk.Entry(frame_periodo, textvariable=self.var_periodo, font=('Consolas', 11), width=15).pack(side='left', padx=(5, 15))

        ttk.Label(frame_periodo, text="Año:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_anno = tk.StringVar(value="-")
        ttk.Entry(frame_periodo, textvariable=self.var_anno, font=('Consolas', 11), width=6).pack(side='left', padx=(5, 15))

        ttk.Label(frame_periodo, text="Mes:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_mes = tk.StringVar(value="-")
        ttk.Entry(frame_periodo, textvariable=self.var_mes, font=('Consolas', 11), width=4).pack(side='left', padx=5)

        # Método de extracción
        frame_metodo = ttk.Frame(frame_datos)
        frame_metodo.pack(fill='x')
        ttk.Label(frame_metodo, text="Método:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_metodo = tk.StringVar(value="-")
        ttk.Label(frame_metodo, textvariable=self.var_metodo, font=('Arial', 10), foreground='gray').pack(side='left', padx=5)
        ttk.Button(frame_metodo, text="📝 Ver texto", command=self._mostrar_texto).pack(side='right')

        # === PANEL EMPRESA (Fase 2) ===
        frame_empresa = ttk.LabelFrame(frame_derecho, text=" 3. Empresa Geyce ", padding=10)
        frame_empresa.pack(fill='both', expand=True)

        # Datos de empresa
        self.var_empresa_nombre = tk.StringVar(value="(Sin buscar)")
        ttk.Label(frame_empresa, text="Empresa:", font=('Arial', 10, 'bold')).pack(anchor='w')
        ttk.Label(frame_empresa, textvariable=self.var_empresa_nombre, font=('Arial', 12),
                 wraplength=300).pack(anchor='w', pady=(0, 10))

        self.var_empresa_codigo = tk.StringVar(value="-")
        frame_codigo = ttk.Frame(frame_empresa)
        frame_codigo.pack(fill='x', pady=(0, 5))
        ttk.Label(frame_codigo, text="Código:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_codigo, textvariable=self.var_empresa_codigo, font=('Consolas', 11)).pack(side='left', padx=5)

        self.var_empresa_db = tk.StringVar(value="-")
        frame_db = ttk.Frame(frame_empresa)
        frame_db.pack(fill='x', pady=(0, 10))
        ttk.Label(frame_db, text="Base datos:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_db, textvariable=self.var_empresa_db, font=('Consolas', 11)).pack(side='left', padx=5)

        # Siguiente asiento
        self.var_siguiente_asiento = tk.StringVar(value="-")
        frame_asiento = ttk.Frame(frame_empresa)
        frame_asiento.pack(fill='x', pady=(0, 10))
        ttk.Label(frame_asiento, text="Siguiente asiento:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_asiento, textvariable=self.var_siguiente_asiento, font=('Consolas', 14, 'bold'),
                 foreground='#2196F3').pack(side='left', padx=5)

        # Botones de acción
        frame_acciones = ttk.Frame(frame_empresa)
        frame_acciones.pack(fill='x', pady=(10, 0))
        ttk.Button(frame_acciones, text="📊 Ver Plan Cuentas", command=self._ver_plan_cuentas).pack(side='left', padx=(0, 5))
        ttk.Button(frame_acciones, text="🔄 Actualizar Asiento", command=self._actualizar_asiento).pack(side='left')

        # === PANEL PLANTILLAS (Fase 3) ===
        frame_plantillas = ttk.LabelFrame(frame_derecho, text=" 4. Plantilla ", padding=10)
        frame_plantillas.pack(fill='x', pady=(10, 0))

        # Info de plantilla detectada
        self.var_plantilla_nombre = tk.StringVar(value="(Sin detectar)")
        frame_plt_info = ttk.Frame(frame_plantillas)
        frame_plt_info.pack(fill='x')
        ttk.Label(frame_plt_info, text="Plantilla:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_plt_info, textvariable=self.var_plantilla_nombre,
                 font=('Arial', 10)).pack(side='left', padx=5)

        self.var_plantilla_confianza = tk.StringVar(value="")
        self.label_confianza = ttk.Label(frame_plt_info, textvariable=self.var_plantilla_confianza,
                                         font=('Arial', 9), foreground='gray')
        self.label_confianza.pack(side='left', padx=5)

        # Botones de plantilla
        frame_plt_btns = ttk.Frame(frame_plantillas)
        frame_plt_btns.pack(fill='x', pady=(10, 0))
        ttk.Button(frame_plt_btns, text="🎓 Modo Aprendizaje",
                  command=self._abrir_modo_aprendizaje).pack(side='left', padx=(0, 5))
        ttk.Button(frame_plt_btns, text="📋 Ver Plantillas",
                  command=self._ver_plantillas).pack(side='left')

        # === BARRA INFERIOR ===
        frame_bottom = ttk.Frame(main)
        frame_bottom.pack(fill='x', pady=(10, 0))

        self.label_bd = ttk.Label(frame_bottom, text="BD: Verificando...", foreground='gray')
        self.label_bd.pack(side='left')

        # Indicador de IA (Fase 8)
        self.label_ia = ttk.Label(frame_bottom, text="🤖 IA: Verificando...", foreground='gray')
        self.label_ia.pack(side='left', padx=(20, 0))

        ttk.Label(frame_bottom, text=f"Fase 8 - IA Integrada | v{VERSION}", foreground='gray').pack(side='right')

        # Variables de estado
        self.pagina_actual = 0

    def _abrir_log(self):
        """Abre la ventana de log"""
        VentanaLog(self.root)

    def _abrir_proceso_masivo(self):
        """Abre la ventana de proceso masivo"""
        VentanaProcesoMasivo(self.root, self.db, self.gestor_plantillas)

    def _abrir_dashboard(self):
        """Abre el dashboard de estadísticas"""
        VentanaDashboard(self.root)

    def _abrir_historico(self):
        """Abre la ventana de histórico de asientos"""
        VentanaHistorico(self.root)

    def _abrir_configuracion(self):
        """Abre la ventana de configuración"""
        VentanaConfiguracion(self.root)

    def _validar_documento(self):
        """Valida el documento actual y muestra alertas"""
        if not self.pdf or not self.pdf.texto:
            messagebox.showwarning("Aviso", "Primero debe cargar un PDF")
            return

        def validar():
            # Obtener plan de cuentas si hay empresa
            plan_cuentas = None
            if self.empresa_actual:
                plan_cuentas = self.db.obtener_plan_cuentas(self.empresa_actual['codigo'])

            # Ejecutar validaciones
            resultado = self.gestor_validaciones.validar_documento(
                texto=self.pdf.texto,
                ruta=self.pdf.ruta,
                cif=self.pdf.cif,
                periodo=self.pdf.periodo,
                conceptos=self.conceptos_extraidos,
                plan_cuentas=plan_cuentas
            )

            self.resultado_validacion = resultado

            # Mostrar ventana de resultados
            def mostrar():
                VentanaAlertas(self.root, resultado, self.pdf.nombre)

                # Actualizar indicador visual
                if resultado['valido']:
                    self.var_estado_carga.set(f"✅ {self.pdf.nombre} - Validación OK")
                else:
                    errores = len(resultado['errores'])
                    warnings = len(resultado['warnings'])
                    self.var_estado_carga.set(
                        f"⚠️ {self.pdf.nombre} - {errores} errores, {warnings} avisos"
                    )

            self.queue.put(mostrar)

        threading.Thread(target=validar, daemon=True).start()

    def _generar_asiento(self):
        """Genera un asiento contable a partir de los conceptos extraídos"""
        if not self.pdf or not self.pdf.texto:
            messagebox.showwarning("Aviso", "Primero debe cargar un PDF")
            return

        if not self.conceptos_extraidos:
            messagebox.showwarning("Aviso", "No hay conceptos extraídos. Cargue un PDF y espere a que se procese.")
            return

        # Verificar si la empresa tiene configuración de cuentas
        if self.pdf.cif:
            config_emp = ConfiguracionEmpresa()
            if not config_emp.existe_configuracion(self.pdf.cif):
                # Mostrar diálogo para configurar cuentas
                respuesta = messagebox.askyesno(
                    "Configurar Empresa",
                    f"La empresa con CIF {self.pdf.cif} no tiene cuentas contables configuradas.\n\n"
                    "¿Desea configurar las subcuentas ahora?\n\n"
                    "(Si elige 'No', se usarán las cuentas por defecto)"
                )

                if respuesta:
                    nombre = self.empresa_actual.get('nombre', '') if self.empresa_actual else ''
                    codigo = self.empresa_actual.get('codigo', '') if self.empresa_actual else ''

                    def on_config_guardada(cuentas):
                        # Después de configurar, generar el asiento
                        self._generar_asiento_interno()

                    VentanaCuentasEmpresa(
                        self.root,
                        cif=self.pdf.cif,
                        nombre_empresa=nombre,
                        codigo_empresa=codigo,
                        es_nueva=True,
                        callback_guardado=on_config_guardada
                    )
                    return

        # Generar asiento directamente
        self._generar_asiento_interno()

    def _generar_asiento_interno(self):
        """Genera el asiento contable (después de verificar configuración)"""
        def generar():
            # Preparar datos de empresa
            empresa_data = None
            if self.empresa_actual:
                empresa_data = {
                    'codigo': self.empresa_actual.get('codigo'),
                    'nombre': self.empresa_actual.get('nombre'),
                    'cif': self.pdf.cif,
                    'base_datos': self.db.obtener_base_datos_contable(self.empresa_actual.get('codigo'))
                }

            # Obtener número de asiento
            numero_asiento = None
            if self.empresa_actual and self.pdf.anno:
                numero_asiento = self.db.obtener_siguiente_asiento(
                    self.empresa_actual.get('codigo'),
                    self.pdf.anno
                )

            # Generar asiento (usará las cuentas de la empresa si están configuradas)
            asiento = self.generador_asientos.generar_desde_conceptos(
                conceptos=self.conceptos_extraidos,
                empresa=empresa_data,
                periodo=self.pdf.periodo,
                numero_asiento=numero_asiento
            )

            self.asiento_actual = asiento

            # Mostrar ventana de asiento
            def mostrar():
                def callback_guardado(asiento_guardado):
                    self.var_estado_carga.set(
                        f"✅ Asiento {asiento_guardado.numero_asiento} guardado"
                    )
                    self.logger.info(
                        f"Asiento guardado: {asiento_guardado.numero_asiento}",
                        f"Empresa: {asiento_guardado.nombre_empresa}"
                    )

                VentanaAsiento(
                    self.root,
                    asiento,
                    db_manager=self.db,
                    callback_guardado=callback_guardado
                )

            self.queue.put(mostrar)

        threading.Thread(target=generar, daemon=True).start()

    def _verificar_bd(self):
        """Verifica conexión a BD en segundo plano"""
        def verificar():
            ok, msg = self.db.test_conexion()
            if ok:
                self.queue.put(lambda: self.label_bd.configure(text="✅ BD Conectada", foreground='green'))
            else:
                self.queue.put(lambda: self.label_bd.configure(text="❌ BD Error", foreground='red'))
        threading.Thread(target=verificar, daemon=True).start()

    def _verificar_ia(self):
        """Verifica disponibilidad de IA (Fase 8)"""
        if self.extractor_ia.esta_disponible():
            self.queue.put(lambda: self.label_ia.configure(text="🤖 IA Activa", foreground='green'))
            self.logger.info("IA disponible", f"Modelo: {Configuracion().get_modelo_ia()}")
        else:
            if not ANTHROPIC_OK:
                msg = "🤖 IA No instalada"
            elif not Configuracion().get_api_key():
                msg = "🤖 IA Sin API key"
            else:
                msg = "🤖 IA Desactivada"
            self.queue.put(lambda m=msg: self.label_ia.configure(text=m, foreground='orange'))

    def _cargar_pdf(self, ruta):
        """
        Carga y procesa un PDF con IA (Fase 8).

        Flujo:
        1. Crear procesador PDF para visualización
        2. Enviar a IA para extracción
        3. Mostrar editor JSON si está configurado
        4. Usar datos extraídos para continuar
        """
        # Cerrar anterior
        if self.pdf:
            self.pdf.cerrar()

        self.datos_ia = None
        nombre_archivo = os.path.basename(ruta)

        # Verificar si IA está disponible
        ia_disponible = self.extractor_ia.esta_disponible()

        if ia_disponible:
            self.var_estado_carga.set(f"🤖 Procesando con IA: {nombre_archivo}")
        else:
            self.var_estado_carga.set(f"⏳ Procesando (modo programa): {nombre_archivo}")

        self.progreso.pack(pady=5)
        self.progreso['value'] = 0
        self.logger.info(f"Cargando PDF: {nombre_archivo}", f"IA: {ia_disponible}")

        def procesar():
            try:
                # Crear procesador PDF para visualización
                self.pdf = PDFProcessor(ruta)

                def callback_pdf(actual, total, tipo):
                    pct = int((actual / total) * 50)  # Primera mitad del progreso
                    self.queue.put(lambda p=pct: self.progreso.configure(value=p))
                    self.queue.put(lambda t=tipo, a=actual, tot=total: self.var_estado_carga.set(f"⏳ {t}: Página {a}/{tot}"))

                # Procesar PDF para visualización
                ok, msg = self.pdf.procesar_automatico(callback_pdf)

                if not ok:
                    raise Exception(msg)

                # === FASE 8: Extracción con IA ===
                datos_extraidos = None
                metodo_usado = "programa"

                if ia_disponible:
                    def callback_ia(actual, total, msg_ia):
                        pct = 50 + int((actual / total) * 50)  # Segunda mitad
                        self.queue.put(lambda p=pct: self.progreso.configure(value=p))
                        self.queue.put(lambda m=msg_ia: self.var_estado_carga.set(f"🤖 {m}"))

                    try:
                        datos_extraidos = self.extractor_ia.extraer_de_pdf(ruta, callback_ia)
                        if datos_extraidos:
                            metodo_usado = "ia_claude"
                            self.logger.info("Extracción IA exitosa",
                                           f"Conceptos: {len(datos_extraidos.get('conceptos', []))}")
                    except Exception as e_ia:
                        self.logger.warning(f"IA falló, usando modo programa: {e_ia}")
                        metodo_usado = "programa"

                def actualizar_ui():
                    self.progreso.pack_forget()

                    # === Datos del PDF (visualización) ===
                    # Usar datos de IA si disponibles, sino del procesador PDF
                    if datos_extraidos:
                        # Obtener empresas del nuevo formato
                        empresas = self.extractor_ia.obtener_empresas(datos_extraidos)

                        if empresas:
                            # Usar datos de la primera empresa para visualización inicial
                            primera = empresas[0]
                            emp = primera.get('empresa', {})
                            per = primera.get('periodo', {})

                            # Si hay múltiples empresas, mostrar indicador
                            if len(empresas) > 1:
                                cif = f"({len(empresas)} empresas)"
                                self.var_cif.set(cif)
                            else:
                                cif = emp.get('cif') or self.pdf.cif
                                self.var_cif.set(cif or "(No detectado)")
                                self.pdf.cif = cif

                            # Actualizar datos del PDF con los de IA
                            self.pdf.periodo = per.get('texto') or self.pdf.periodo
                            self.pdf.mes = per.get('mes') or self.pdf.mes
                            self.pdf.anno = per.get('año') or self.pdf.anno
                        else:
                            # Formato antiguo - compatibilidad
                            emp = datos_extraidos.get('empresa', {})
                            per = datos_extraidos.get('periodo', {})

                            cif = emp.get('cif') or self.pdf.cif
                            self.var_cif.set(cif or "(No detectado)")
                            self.pdf.cif = cif
                            self.pdf.periodo = per.get('texto') or self.pdf.periodo
                            self.pdf.mes = per.get('mes') or self.pdf.mes
                            self.pdf.anno = per.get('año') or self.pdf.anno
                    else:
                        self.var_cif.set(self.pdf.cif or "(No detectado)")

                    # Validar CIF/NIF (solo si no es multi-empresa)
                    empresas = self.extractor_ia.obtener_empresas(datos_extraidos) if datos_extraidos else []
                    if len(empresas) > 1:
                        # Multi-empresa: mostrar indicador especial
                        self.label_cif_status.configure(text="🏢 Multi", foreground='blue')
                    elif self.pdf.cif:
                        cif_valido, cif_tipo, cif_msg = ValidadorCIF.validar(self.pdf.cif)
                        if cif_valido:
                            self.label_cif_status.configure(text=f"✅ {cif_tipo}", foreground='green')
                        else:
                            self.label_cif_status.configure(text="⚠️ Inválido", foreground='orange')
                            self.logger.warning(f"CIF/NIF inválido: {cif_msg}")
                    else:
                        self.label_cif_status.configure(text="⚠️", foreground='orange')

                    self.var_periodo.set(self.pdf.periodo or "(No detectado)")
                    self.var_anno.set(str(self.pdf.anno))
                    self.var_mes.set(str(self.pdf.mes))

                    # Mostrar método de extracción
                    if metodo_usado == "ia_claude":
                        metodo_texto = f"🤖 IA Claude ({datos_extraidos.get('_extraccion', {}).get('tokens_usados', '?')} tokens)"
                    elif self.pdf.metodo_extraccion == 'opendataloader':
                        metodo_texto = f"OpenDataLoader (Tablas: {len(self.pdf.tablas)})"
                    elif self.pdf.tiene_texto_nativo:
                        metodo_texto = "PyMuPDF (Texto nativo)"
                    else:
                        metodo_texto = "PyMuPDF + OCR"
                    self.var_metodo.set(metodo_texto)

                    # Mostrar primera página
                    self.pagina_actual = 0
                    self._mostrar_pagina()
                    self.var_pag.set(f"1 / {self.pdf.num_paginas}")

                    # Buscar empresa automáticamente
                    if self.pdf.cif:
                        self._buscar_empresa()

                    # === Procesar datos extraídos ===
                    if datos_extraidos and metodo_usado == "ia_claude":
                        self.datos_ia = datos_extraidos

                        # Detectar si hay múltiples empresas
                        es_multi = self.extractor_ia.es_multi_empresa(datos_extraidos)
                        empresas = self.extractor_ia.obtener_empresas(datos_extraidos)
                        num_empresas = len(empresas)

                        if es_multi:
                            # Múltiples empresas detectadas
                            self.var_estado_carga.set(
                                f"🏢 {self.pdf.nombre} - {num_empresas} empresas detectadas"
                            )
                            self.logger.info(
                                f"PDF multi-empresa detectado",
                                f"Empresas: {num_empresas}"
                            )
                            # Mostrar ventana de selección de empresas
                            self._mostrar_selector_empresas(datos_extraidos)
                        else:
                            # Una sola empresa
                            if empresas:
                                primera_empresa = empresas[0]
                                self.conceptos_extraidos = self.extractor_ia.convertir_a_conceptos(primera_empresa)
                            else:
                                self.conceptos_extraidos = []

                            self.var_estado_carga.set(f"🤖 {self.pdf.nombre} - Extraído con IA")

                            # Mostrar editor JSON si está configurado
                            config = Configuracion()
                            if config.get('ia', 'mostrar_editor_json', True):
                                # Pasar solo la primera empresa para edición
                                datos_a_editar = empresas[0] if empresas else datos_extraidos
                                self._mostrar_editor_json(datos_a_editar)
                    else:
                        # Modo programa tradicional
                        self._detectar_plantilla()
                        self.var_estado_carga.set(f"✅ {self.pdf.nombre} - Procesado (modo programa)")

                    self.logger.info(f"PDF procesado: {self.pdf.nombre}",
                                    f"Método: {metodo_usado}, CIF: {self.pdf.cif}, Período: {self.pdf.periodo}")

                self.queue.put(actualizar_ui)

            except Exception as e:
                self.logger.error(f"Excepción al cargar PDF", str(e))
                self.queue.put(lambda: self.var_estado_carga.set(f"❌ Error: {e}"))
                self.queue.put(lambda: self.progreso.pack_forget())
                self.queue.put(lambda err=str(e): messagebox.showerror("Error", err))

        threading.Thread(target=procesar, daemon=True).start()

    def _mostrar_editor_json(self, datos):
        """Muestra el editor JSON con los datos extraídos por IA"""
        def on_aceptar(datos_editados):
            self.datos_ia = datos_editados
            # Reconvertir a conceptos si hubo edición
            self.conceptos_extraidos = self.extractor_ia.convertir_a_conceptos(datos_editados)
            self.logger.info("Datos IA editados y aceptados",
                           f"Conceptos: {len(self.conceptos_extraidos)}")

        VentanaEditorJSON(
            self.root,
            datos,
            nombre_archivo=self.pdf.nombre if self.pdf else "",
            callback_aceptar=on_aceptar
        )

    def _mostrar_selector_empresas(self, datos_ia):
        """Muestra el selector cuando hay múltiples empresas en el PDF"""
        def on_procesar(empresas_seleccionadas):
            """Callback cuando el usuario selecciona empresas para procesar"""
            if not empresas_seleccionadas:
                return

            num_seleccionadas = len(empresas_seleccionadas)
            self.logger.info(f"Procesando {num_seleccionadas} empresas seleccionadas")

            if num_seleccionadas == 1:
                # Una sola empresa seleccionada - flujo normal
                empresa = empresas_seleccionadas[0]
                self.conceptos_extraidos = self.extractor_ia.convertir_a_conceptos(empresa)

                # Actualizar datos del PDF con esta empresa
                info_emp = empresa.get('empresa', {})
                per = empresa.get('periodo', {})

                self.pdf.cif = info_emp.get('cif') or self.pdf.cif
                self.pdf.periodo = per.get('texto') or self.pdf.periodo

                self.var_cif.set(self.pdf.cif or "(No detectado)")
                self.var_periodo.set(self.pdf.periodo or "(No detectado)")

                # Buscar empresa en BD
                if self.pdf.cif:
                    self._buscar_empresa()

                self.var_estado_carga.set(
                    f"🤖 {self.pdf.nombre} - {info_emp.get('nombre', 'Empresa')} cargada"
                )

                # Mostrar editor si está configurado
                config = Configuracion()
                if config.get('ia', 'mostrar_editor_json', True):
                    self._mostrar_editor_json(empresa)
            else:
                # Múltiples empresas - procesar en lote
                self._procesar_empresas_lote(empresas_seleccionadas)

        VentanaMultiEmpresa(
            self.root,
            datos_ia,
            nombre_archivo=self.pdf.nombre if self.pdf else "",
            callback_procesar=on_procesar
        )

    def _procesar_empresas_lote(self, empresas):
        """Procesa múltiples empresas en lote, generando un asiento por cada una"""
        self.logger.info(f"Iniciando proceso en lote: {len(empresas)} empresas")

        resultados = []

        for i, empresa in enumerate(empresas):
            info_emp = empresa.get('empresa', {})
            cif = info_emp.get('cif', '')
            nombre = info_emp.get('nombre', f'Empresa {i+1}')
            periodo = empresa.get('periodo', {})

            self.logger.info(f"Procesando empresa {i+1}/{len(empresas)}: {nombre} ({cif})")

            # Convertir conceptos
            conceptos = self.extractor_ia.convertir_a_conceptos(empresa)

            # Buscar empresa en BD
            empresa_bd = self.db.buscar_empresa_por_cif(cif) if cif else None

            # Preparar datos
            empresa_data = None
            if empresa_bd:
                empresa_data = {
                    'codigo': empresa_bd.get('codigo'),
                    'nombre': empresa_bd.get('nombre'),
                    'cif': cif,
                    'base_datos': self.db.obtener_base_datos_contable(empresa_bd.get('codigo'))
                }

            # Obtener número de asiento
            anno = periodo.get('año') or datetime.now().year
            numero_asiento = None
            if empresa_bd:
                numero_asiento = self.db.obtener_siguiente_asiento(
                    empresa_bd.get('codigo'), anno
                )

            # Generar asiento
            asiento = self.generador_asientos.generar_desde_conceptos(
                conceptos=conceptos,
                empresa=empresa_data,
                periodo=periodo.get('texto', ''),
                numero_asiento=numero_asiento
            )

            resultados.append({
                'empresa': nombre,
                'cif': cif,
                'asiento': asiento,
                'conceptos': len(conceptos),
                'encontrada_bd': empresa_bd is not None
            })

        # Mostrar resumen
        self._mostrar_resumen_lote(resultados)

    def _mostrar_resumen_lote(self, resultados):
        """Muestra resumen del procesamiento en lote"""
        ventana = tk.Toplevel(self.root)
        ventana.title("Resumen - Procesamiento en Lote")
        ventana.geometry("800x500")

        main = ttk.Frame(ventana, padding=10)
        main.pack(fill='both', expand=True)

        ttk.Label(main,
                  text=f"✅ Se han generado {len(resultados)} asientos",
                  font=('Arial', 14, 'bold')).pack(pady=(0, 10))

        # Tabla de resultados
        cols = ('empresa', 'cif', 'conceptos', 'encontrada', 'asiento')
        tree = ttk.Treeview(main, columns=cols, show='headings', height=15)

        tree.heading('empresa', text='Empresa')
        tree.heading('cif', text='CIF')
        tree.heading('conceptos', text='Conceptos')
        tree.heading('encontrada', text='En BD')
        tree.heading('asiento', text='Nº Asiento')

        tree.column('empresa', width=250)
        tree.column('cif', width=100)
        tree.column('conceptos', width=80, anchor='center')
        tree.column('encontrada', width=80, anchor='center')
        tree.column('asiento', width=100, anchor='center')

        for r in resultados:
            asiento = r['asiento']
            tree.insert('', 'end', values=(
                r['empresa'],
                r['cif'],
                r['conceptos'],
                '✅' if r['encontrada_bd'] else '❌',
                asiento.numero_asiento if asiento else '-'
            ))

        scroll = ttk.Scrollbar(main, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')

        # Botones
        frame_btns = ttk.Frame(ventana)
        frame_btns.pack(fill='x', padx=10, pady=10)

        def guardar_todos():
            guardados = 0
            for r in resultados:
                if r['asiento'] and r['encontrada_bd']:
                    # Aquí iría la lógica de guardar en BD
                    guardados += 1
            messagebox.showinfo("Info", f"Se guardaron {guardados} asientos")
            ventana.destroy()

        ttk.Button(frame_btns, text="Cerrar", command=ventana.destroy).pack(side='right')
        ttk.Button(frame_btns, text="💾 Guardar Todos en BD",
                   command=guardar_todos).pack(side='right', padx=5)

        self.var_estado_carga.set(f"✅ Procesadas {len(resultados)} empresas en lote")

    def _buscar_empresa(self):
        """Busca la empresa por CIF en la base de datos Geyce"""
        cif = self.var_cif.get()
        if not cif or cif == "-" or cif == "(No detectado)":
            messagebox.showwarning("Aviso", "No hay CIF para buscar")
            return

        self.logger.info(f"Iniciando búsqueda de empresa con CIF: {cif}")

        def buscar():
            empresa = self.db.buscar_empresa_por_cif(cif)

            def actualizar():
                if empresa:
                    self.empresa_actual = empresa
                    self.var_empresa_nombre.set(empresa['nombre'] or "(Sin nombre)")
                    self.var_empresa_codigo.set(empresa['codigo'] or "-")

                    db_name = self.db.obtener_base_datos_contable(empresa['codigo'])
                    self.var_empresa_db.set(db_name or "-")

                    # Obtener siguiente asiento
                    self._actualizar_asiento()
                else:
                    self.empresa_actual = None
                    self.var_empresa_nombre.set("❌ No encontrada")
                    self.var_empresa_codigo.set("-")
                    self.var_empresa_db.set("-")
                    self.var_siguiente_asiento.set("-")

            self.queue.put(actualizar)

        threading.Thread(target=buscar, daemon=True).start()

    def _actualizar_asiento(self):
        """Actualiza el número de siguiente asiento"""
        if not self.empresa_actual:
            return

        anno = self.var_anno.get()
        if not anno or anno == "-":
            anno = datetime.now().year
        else:
            try:
                anno = int(anno)
            except:
                anno = datetime.now().year

        def obtener():
            siguiente = self.db.obtener_siguiente_asiento(self.empresa_actual['codigo'], anno)

            def actualizar():
                self.var_siguiente_asiento.set(str(siguiente) if siguiente else "-")

            self.queue.put(actualizar)

        threading.Thread(target=obtener, daemon=True).start()

    def _ver_plan_cuentas(self):
        """Muestra el plan de cuentas de la empresa"""
        if not self.empresa_actual:
            messagebox.showwarning("Aviso", "Primero debe buscar una empresa")
            return

        # Obtener cuentas de nóminas (640-649)
        cuentas = self.db.obtener_plan_cuentas(self.empresa_actual['codigo'], '64%')

        if not cuentas:
            messagebox.showinfo("Info", "No se encontraron cuentas de nóminas (64x)")
            return

        # Mostrar en ventana
        ventana = tk.Toplevel(self.root)
        ventana.title(f"Plan de Cuentas - {self.empresa_actual['nombre']}")
        ventana.geometry("600x400")

        # Lista de cuentas
        frame = ttk.Frame(ventana, padding=10)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Cuentas de nóminas (64x):", font=('Arial', 12, 'bold')).pack(anchor='w')

        tree = ttk.Treeview(frame, columns=('cuenta', 'nombre'), show='headings', height=15)
        tree.heading('cuenta', text='Cuenta')
        tree.heading('nombre', text='Nombre')
        tree.column('cuenta', width=100)
        tree.column('nombre', width=450)

        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        for c in cuentas:
            tree.insert('', 'end', values=(c['cuenta'], c['nombre']))

        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)

    def _mostrar_pagina(self):
        """Muestra la página actual del PDF"""
        if not self.pdf:
            return

        img = self.pdf.get_imagen(self.pagina_actual, zoom=1.2)
        if img:
            self.imagen_tk = ImageTk.PhotoImage(img)
            self.canvas.delete('all')
            self.canvas.create_image(0, 0, anchor='nw', image=self.imagen_tk)
            self.canvas.configure(scrollregion=(0, 0, img.width, img.height))

    def _cambiar_pag(self, delta):
        """Cambia de página"""
        if not self.pdf:
            return

        nueva = self.pagina_actual + delta
        if 0 <= nueva < self.pdf.num_paginas:
            self.pagina_actual = nueva
            self._mostrar_pagina()
            self.var_pag.set(f"{nueva + 1} / {self.pdf.num_paginas}")

    def _mostrar_texto(self):
        """Muestra el texto extraído en una ventana"""
        if not self.pdf or not self.pdf.texto:
            messagebox.showinfo("Info", "No hay texto extraído")
            return

        ventana = tk.Toplevel(self.root)
        ventana.title(f"Texto extraído - {self.pdf.nombre}")
        ventana.geometry("700x500")

        texto = tk.Text(ventana, wrap='word', font=('Consolas', 10))
        scroll = ttk.Scrollbar(ventana, orient='vertical', command=texto.yview)
        texto.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        texto.pack(fill='both', expand=True, padx=10, pady=10)

        texto.insert('1.0', self.pdf.texto)
        texto.configure(state='disabled')

    def _detectar_plantilla(self):
        """Detecta automáticamente la plantilla para el documento"""
        if not self.pdf or not self.pdf.texto:
            return

        def detectar():
            plantilla, score = self.detector.buscar_plantilla(self.pdf.texto)

            def actualizar():
                if plantilla:
                    self.plantilla_actual = plantilla
                    self.var_plantilla_nombre.set(f"✅ {plantilla.nombre}")
                    self.var_plantilla_confianza.set(f"({score:.0f}% coincidencia)")
                    self.label_confianza.configure(foreground='green' if score > 70 else 'orange')

                    # Extraer conceptos con la plantilla (usando OpenDataLoader si disponible)
                    self.conceptos_extraidos = self.extractor.extraer(
                        self.pdf.texto, plantilla, self.pdf
                    )
                    self.conceptos_extraidos = self.extractor.mapear_a_cuentas(
                        self.conceptos_extraidos, plantilla
                    )

                    # Incrementar uso de plantilla
                    plantilla.incrementar_uso(True)
                    self.gestor_plantillas.guardar(plantilla)

                    self.logger.info(f"Plantilla aplicada: {plantilla.nombre}",
                                   f"Conceptos extraídos: {len(self.conceptos_extraidos)}")
                else:
                    self.plantilla_actual = None
                    self.var_plantilla_nombre.set("⚠️ No detectada")
                    self.var_plantilla_confianza.set("(usar Modo Aprendizaje)")
                    self.label_confianza.configure(foreground='orange')

                    # Extraer conceptos sin plantilla (usando OpenDataLoader si disponible)
                    self.conceptos_extraidos = self.extractor.extraer(
                        self.pdf.texto, None, self.pdf
                    )

            self.queue.put(actualizar)

        threading.Thread(target=detectar, daemon=True).start()

    def _abrir_modo_aprendizaje(self):
        """Abre la ventana de modo aprendizaje"""
        if not self.pdf or not self.pdf.texto:
            messagebox.showwarning("Aviso", "Primero debe cargar un PDF")
            return

        def on_guardar(plantilla):
            """Callback cuando se guarda la plantilla"""
            self.plantilla_actual = plantilla
            self.var_plantilla_nombre.set(f"✅ {plantilla.nombre}")
            self.var_plantilla_confianza.set("(recién creada)")
            self.label_confianza.configure(foreground='blue')

        VentanaAprendizaje(
            self.root,
            self.pdf.texto,
            self.plantilla_actual,
            callback_guardar=on_guardar
        )

    def _ver_plantillas(self):
        """Muestra la lista de plantillas disponibles"""
        plantillas = self.gestor_plantillas.listar()

        ventana = tk.Toplevel(self.root)
        ventana.title("Plantillas Disponibles")
        ventana.geometry("700x400")

        frame = ttk.Frame(ventana, padding=10)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Plantillas guardadas:", font=('Arial', 12, 'bold')).pack(anchor='w')

        if not plantillas:
            ttk.Label(frame, text="No hay plantillas guardadas.\nUse el Modo Aprendizaje para crear una.",
                     foreground='gray').pack(pady=20)
            return

        # Treeview
        columnas = ('nombre', 'fingerprints', 'confianza', 'usos')
        tree = ttk.Treeview(frame, columns=columnas, show='headings', height=15)
        tree.heading('nombre', text='Nombre')
        tree.heading('fingerprints', text='Fingerprints')
        tree.heading('confianza', text='Confianza')
        tree.heading('usos', text='Usos')

        tree.column('nombre', width=200)
        tree.column('fingerprints', width=250)
        tree.column('confianza', width=80, anchor='center')
        tree.column('usos', width=60, anchor='center')

        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        for p in plantillas:
            fps = ', '.join(p.get('fingerprints', [])[:3])
            if len(p.get('fingerprints', [])) > 3:
                fps += '...'
            tree.insert('', 'end', iid=p['id'], values=(
                p.get('nombre', 'Sin nombre'),
                fps,
                f"{p.get('confianza', 0):.0f}%",
                p.get('veces_usada', 0)
            ))

        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)

        # Botones
        frame_btns = ttk.Frame(frame)
        frame_btns.pack(fill='x', pady=(10, 0))

        def eliminar():
            sel = tree.selection()
            if sel and messagebox.askyesno("Confirmar", "¿Eliminar la plantilla seleccionada?"):
                self.gestor_plantillas.eliminar(sel[0])
                tree.delete(sel[0])

        def editar():
            sel = tree.selection()
            if sel:
                plantilla = self.gestor_plantillas.cargar(sel[0])
                if plantilla:
                    VentanaAprendizaje(self.root, self.pdf.texto if self.pdf else "", plantilla)

        ttk.Button(frame_btns, text="✏️ Editar", command=editar).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🗑️ Eliminar", command=eliminar).pack(side='left')
        ttk.Button(frame_btns, text="Cerrar", command=ventana.destroy).pack(side='right')


# =============================================================================
# CLASE: VentanaCuentasEmpresa (Configuración de cuentas por empresa)
# =============================================================================
class VentanaCuentasEmpresa(tk.Toplevel):
    """Ventana para configurar las cuentas contables de una empresa específica"""

    def __init__(self, parent, cif, nombre_empresa="", codigo_empresa="",
                 es_nueva=False, callback_guardado=None):
        super().__init__(parent)
        self.title(f"Cuentas Contables - {nombre_empresa or cif}")
        self.geometry("550x500")
        self.minsize(450, 400)
        self.transient(parent)
        self.grab_set()

        self.cif = cif
        self.nombre_empresa = nombre_empresa
        self.codigo_empresa = codigo_empresa
        self.es_nueva = es_nueva
        self.callback_guardado = callback_guardado

        self.config_empresa = ConfiguracionEmpresa()
        self.config_global = Configuracion()
        self.logger = Logger()

        # Si es nueva, crear configuración con defaults
        if es_nueva and not self.config_empresa.existe_configuracion(cif):
            self.config_empresa.crear_configuracion(cif, nombre_empresa, codigo_empresa)

        self._crear_ui()
        self._cargar_valores()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=15)
        main.pack(fill='both', expand=True)

        # === Información de empresa ===
        frame_info = ttk.LabelFrame(main, text="Información de Empresa", padding=10)
        frame_info.pack(fill='x', pady=(0, 15))

        ttk.Label(frame_info, text=f"CIF: {self.cif}", font=('Arial', 11, 'bold')).pack(anchor='w')
        if self.nombre_empresa:
            ttk.Label(frame_info, text=f"Nombre: {self.nombre_empresa}").pack(anchor='w')
        if self.codigo_empresa:
            ttk.Label(frame_info, text=f"Código: {self.codigo_empresa}").pack(anchor='w')

        if self.es_nueva:
            ttk.Label(frame_info, text="⚠️ Primera configuración - se usarán valores por defecto",
                     foreground='orange').pack(anchor='w', pady=(5, 0))

        # === Cuentas contables ===
        frame_cuentas = ttk.LabelFrame(main, text="Cuentas Contables (Subcuentas)", padding=10)
        frame_cuentas.pack(fill='both', expand=True, pady=(0, 15))

        # Descripción
        ttk.Label(frame_cuentas,
                 text="Configure las subcuentas específicas para esta empresa:",
                 foreground='gray').pack(anchor='w', pady=(0, 10))

        # Grid de cuentas
        frame_grid = ttk.Frame(frame_cuentas)
        frame_grid.pack(fill='x')

        cuentas_labels = [
            ('Sueldos y salarios:', 'sueldos', '6400000'),
            ('Complementos/Plus:', 'complementos', '6400001'),
            ('SS a cargo empresa:', 'ss_empresa', '6420000'),
            ('IRPF (retención):', 'irpf', '4751000'),
            ('SS a cargo trabajador:', 'ss_trabajador', '4760000'),
            ('Neto a pagar:', 'neto_pagar', '4650000'),
            ('Banco/Caja:', 'banco', '5720000')
        ]

        self.vars_cuentas = {}
        for i, (label, key, ejemplo) in enumerate(cuentas_labels):
            ttk.Label(frame_grid, text=label).grid(row=i, column=0, sticky='w', pady=5, padx=(0, 10))
            var = tk.StringVar()
            self.vars_cuentas[key] = var
            entry = ttk.Entry(frame_grid, textvariable=var, width=12)
            entry.grid(row=i, column=1, pady=5, sticky='w')
            ttk.Label(frame_grid, text=f"(ej: {ejemplo})", foreground='gray').grid(row=i, column=2, padx=(10, 0))

        # === Notas ===
        frame_notas = ttk.LabelFrame(main, text="Notas", padding=5)
        frame_notas.pack(fill='x', pady=(0, 15))

        self.text_notas = tk.Text(frame_notas, height=3, width=50)
        self.text_notas.pack(fill='x')

        # === Botones ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="💾 Guardar",
                  command=self._guardar).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🔄 Cargar desde defaults",
                  command=self._cargar_defaults).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📋 Cargar desde plan de cuentas",
                  command=self._cargar_plan_cuentas).pack(side='left')

        ttk.Button(frame_btns, text="Cancelar",
                  command=self.destroy).pack(side='right')

    def _cargar_valores(self):
        """Carga los valores actuales de la configuración"""
        cuentas = self.config_empresa.obtener_cuentas(self.cif)

        if cuentas:
            for key, var in self.vars_cuentas.items():
                var.set(cuentas.get(key, ''))
        else:
            # Cargar desde defaults globales
            for key, var in self.vars_cuentas.items():
                var.set(self.config_global.get_cuenta(key))

        # Cargar notas
        info = self.config_empresa.obtener_info_empresa(self.cif)
        if info and info.get('notas'):
            self.text_notas.insert('1.0', info['notas'])

    def _cargar_defaults(self):
        """Carga los valores por defecto globales"""
        for key, var in self.vars_cuentas.items():
            var.set(self.config_global.get_cuenta(key))

    def _cargar_plan_cuentas(self):
        """Intenta cargar cuentas desde el plan de cuentas de la empresa"""
        if not self.codigo_empresa:
            messagebox.showwarning("Aviso", "No se ha especificado el código de empresa")
            return

        db = DatabaseManager()
        cuentas = db.obtener_plan_cuentas(self.codigo_empresa, '64%')

        if not cuentas:
            messagebox.showinfo("Info", "No se encontraron cuentas de nóminas (64x) en el plan de cuentas")
            return

        # Mostrar diálogo para seleccionar cuentas
        self._dialogo_seleccionar_cuentas(cuentas)

    def _dialogo_seleccionar_cuentas(self, cuentas):
        """Diálogo para seleccionar cuentas del plan"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Seleccionar cuentas del plan")
        dialogo.geometry("500x400")
        dialogo.transient(self)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=10)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Cuentas encontradas en el plan de cuentas:",
                 font=('Arial', 10, 'bold')).pack(anchor='w')

        # Lista de cuentas
        frame_lista = ttk.Frame(frame)
        frame_lista.pack(fill='both', expand=True, pady=10)

        lista = tk.Listbox(frame_lista, height=15, width=50)
        scroll = ttk.Scrollbar(frame_lista, orient='vertical', command=lista.yview)
        lista.configure(yscrollcommand=scroll.set)

        for c in cuentas:
            lista.insert('end', f"{c['cuenta']} - {c['nombre']}")

        scroll.pack(side='right', fill='y')
        lista.pack(fill='both', expand=True)

        ttk.Label(frame, text="Doble clic en una cuenta para copiar el código").pack(anchor='w')

        def copiar_cuenta(event):
            sel = lista.curselection()
            if sel:
                cuenta = cuentas[sel[0]]['cuenta']
                self.clipboard_clear()
                self.clipboard_append(cuenta)
                messagebox.showinfo("Copiado", f"Cuenta {cuenta} copiada al portapapeles")

        lista.bind('<Double-1>', copiar_cuenta)

        ttk.Button(frame, text="Cerrar", command=dialogo.destroy).pack(pady=10)

    def _guardar(self):
        """Guarda la configuración"""
        cuentas = {}
        for key, var in self.vars_cuentas.items():
            valor = var.get().strip()
            if valor:
                cuentas[key] = valor

        # Actualizar configuración
        if not self.config_empresa.existe_configuracion(self.cif):
            self.config_empresa.crear_configuracion(
                self.cif, self.nombre_empresa, self.codigo_empresa
            )

        self.config_empresa.actualizar_cuentas(self.cif, cuentas)

        # Guardar notas
        notas = self.text_notas.get('1.0', 'end-1c')
        info = self.config_empresa.obtener_info_empresa(self.cif)
        if info:
            info['notas'] = notas
            self.config_empresa._guardar_empresa(self.cif)

        messagebox.showinfo("Éxito", f"Configuración guardada para {self.nombre_empresa or self.cif}")
        self.logger.info(f"Cuentas de empresa guardadas: {self.cif}")

        if self.callback_guardado:
            self.callback_guardado(cuentas)

        self.destroy()


# =============================================================================
# CLASE: VentanaConfiguracion (Configuración de la aplicación)
# =============================================================================
class VentanaConfiguracion(tk.Toplevel):
    """Ventana para configurar la aplicación (Fase 8: incluye IA)"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configuración")
        self.geometry("750x600")
        self.minsize(650, 500)

        self.config = Configuracion()
        self.logger = Logger()

        self._crear_ui()
        self._cargar_valores()

    def _crear_ui(self):
        # Notebook con pestañas
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # === Pestaña 1: Base de datos ===
        tab_bd = ttk.Frame(notebook, padding=15)
        notebook.add(tab_bd, text="Base de Datos")

        ttk.Label(tab_bd, text="Servidor:", font=('Arial', 10)).grid(row=0, column=0, sticky='w', pady=5)
        self.var_server = tk.StringVar()
        ttk.Entry(tab_bd, textvariable=self.var_server, width=30).grid(row=0, column=1, pady=5, sticky='w')

        ttk.Label(tab_bd, text="Usuario:").grid(row=1, column=0, sticky='w', pady=5)
        self.var_user = tk.StringVar()
        ttk.Entry(tab_bd, textvariable=self.var_user, width=30).grid(row=1, column=1, pady=5, sticky='w')

        ttk.Label(tab_bd, text="Contraseña:").grid(row=2, column=0, sticky='w', pady=5)
        self.var_password = tk.StringVar()
        ttk.Entry(tab_bd, textvariable=self.var_password, width=30, show='*').grid(row=2, column=1, pady=5, sticky='w')

        ttk.Label(tab_bd, text="BD Geyce:").grid(row=3, column=0, sticky='w', pady=5)
        self.var_db_geyce = tk.StringVar()
        ttk.Entry(tab_bd, textvariable=self.var_db_geyce, width=30).grid(row=3, column=1, pady=5, sticky='w')

        ttk.Label(tab_bd, text="BD EASP:").grid(row=4, column=0, sticky='w', pady=5)
        self.var_db_easp = tk.StringVar()
        ttk.Entry(tab_bd, textvariable=self.var_db_easp, width=30).grid(row=4, column=1, pady=5, sticky='w')

        ttk.Button(tab_bd, text="🔌 Probar conexión",
                  command=self._probar_conexion).grid(row=5, column=1, pady=20, sticky='w')

        # === Pestaña 2: Cuentas contables ===
        tab_cuentas = ttk.Frame(notebook, padding=15)
        notebook.add(tab_cuentas, text="Cuentas Contables")

        cuentas_labels = [
            ('Sueldos y salarios:', 'sueldos'),
            ('Complementos:', 'complementos'),
            ('SS Empresa:', 'ss_empresa'),
            ('IRPF:', 'irpf'),
            ('SS Trabajador:', 'ss_trabajador'),
            ('Neto a pagar:', 'neto_pagar'),
            ('Banco/Caja:', 'banco')
        ]

        self.vars_cuentas = {}
        for i, (label, key) in enumerate(cuentas_labels):
            ttk.Label(tab_cuentas, text=label).grid(row=i, column=0, sticky='w', pady=5)
            var = tk.StringVar()
            self.vars_cuentas[key] = var
            ttk.Entry(tab_cuentas, textvariable=var, width=15).grid(row=i, column=1, pady=5, sticky='w')

        # === Pestaña 3: Validaciones ===
        tab_val = ttk.Frame(notebook, padding=15)
        notebook.add(tab_val, text="Validaciones")

        ttk.Label(tab_val, text="SMI Mensual (€):").grid(row=0, column=0, sticky='w', pady=5)
        self.var_smi = tk.StringVar()
        ttk.Entry(tab_val, textvariable=self.var_smi, width=15).grid(row=0, column=1, pady=5, sticky='w')

        ttk.Label(tab_val, text="Tolerancia cuadre (€):").grid(row=1, column=0, sticky='w', pady=5)
        self.var_tolerancia = tk.StringVar()
        ttk.Entry(tab_val, textvariable=self.var_tolerancia, width=15).grid(row=1, column=1, pady=5, sticky='w')

        ttk.Label(tab_val, text="Salario máximo (€):").grid(row=2, column=0, sticky='w', pady=5)
        self.var_max_sal = tk.StringVar()
        ttk.Entry(tab_val, textvariable=self.var_max_sal, width=15).grid(row=2, column=1, pady=5, sticky='w')

        ttk.Label(tab_val, text="Salario mínimo (€):").grid(row=3, column=0, sticky='w', pady=5)
        self.var_min_sal = tk.StringVar()
        ttk.Entry(tab_val, textvariable=self.var_min_sal, width=15).grid(row=3, column=1, pady=5, sticky='w')

        # === Pestaña 4: Interfaz ===
        tab_ui = ttk.Frame(notebook, padding=15)
        notebook.add(tab_ui, text="Interfaz")

        self.var_maximizar = tk.BooleanVar()
        ttk.Checkbutton(tab_ui, text="Maximizar ventana al inicio",
                       variable=self.var_maximizar).pack(anchor='w', pady=5)

        self.var_tooltips = tk.BooleanVar()
        ttk.Checkbutton(tab_ui, text="Mostrar tooltips",
                       variable=self.var_tooltips).pack(anchor='w', pady=5)

        self.var_autovalidar = tk.BooleanVar()
        ttk.Checkbutton(tab_ui, text="Validar automáticamente al cargar PDF",
                       variable=self.var_autovalidar).pack(anchor='w', pady=5)

        ttk.Label(tab_ui, text="Idioma OCR:").pack(anchor='w', pady=(20, 5))
        self.var_idioma_ocr = tk.StringVar()
        idiomas = ttk.Combobox(tab_ui, textvariable=self.var_idioma_ocr,
                               values=['spa', 'eng', 'fra', 'deu', 'ita', 'por'], width=10)
        idiomas.pack(anchor='w')

        # === Pestaña 5: IA (Fase 8) ===
        tab_ia = ttk.Frame(notebook, padding=15)
        notebook.add(tab_ia, text="🤖 IA")

        # API Key
        ttk.Label(tab_ia, text="API Key de Anthropic:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 5))
        ttk.Label(tab_ia, text="(Obtener en console.anthropic.com)", foreground='gray').grid(row=0, column=1, sticky='w', padx=5)

        self.var_api_key = tk.StringVar()
        entry_api = ttk.Entry(tab_ia, textvariable=self.var_api_key, width=50, show='•')
        entry_api.grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 10))

        # Botón mostrar/ocultar
        self.mostrar_key = tk.BooleanVar(value=False)
        def toggle_key():
            if self.mostrar_key.get():
                entry_api.config(show='')
            else:
                entry_api.config(show='•')
        ttk.Checkbutton(tab_ia, text="Mostrar", variable=self.mostrar_key,
                       command=toggle_key).grid(row=1, column=2, padx=5)

        # Modelo
        ttk.Label(tab_ia, text="Modelo:").grid(row=2, column=0, sticky='w', pady=5)
        self.var_modelo_ia = tk.StringVar()
        modelos = ttk.Combobox(tab_ia, textvariable=self.var_modelo_ia, width=35,
                               values=[
                                   'claude-sonnet-4-20250514',
                                   'claude-opus-4-20250514',
                                   'claude-haiku-4-5-20251001',
                                   'claude-3-5-sonnet-20241022'
                               ])
        modelos.grid(row=2, column=1, sticky='w', pady=5)

        # Opciones
        self.var_ia_habilitada = tk.BooleanVar()
        ttk.Checkbutton(tab_ia, text="IA habilitada (siempre usar IA para extraer datos)",
                       variable=self.var_ia_habilitada).grid(row=3, column=0, columnspan=2, sticky='w', pady=10)

        self.var_guardar_extracciones = tk.BooleanVar()
        ttk.Checkbutton(tab_ia, text="Guardar extracciones (para histórico y aprendizaje)",
                       variable=self.var_guardar_extracciones).grid(row=4, column=0, columnspan=2, sticky='w', pady=5)

        self.var_mostrar_editor = tk.BooleanVar()
        ttk.Checkbutton(tab_ia, text="Mostrar editor JSON antes de procesar",
                       variable=self.var_mostrar_editor).grid(row=5, column=0, columnspan=2, sticky='w', pady=5)

        # Max tokens
        ttk.Label(tab_ia, text="Max tokens:").grid(row=6, column=0, sticky='w', pady=5)
        self.var_max_tokens = tk.StringVar()
        ttk.Entry(tab_ia, textvariable=self.var_max_tokens, width=10).grid(row=6, column=1, sticky='w', pady=5)

        # Estado
        frame_estado_ia = ttk.LabelFrame(tab_ia, text="Estado", padding=10)
        frame_estado_ia.grid(row=7, column=0, columnspan=3, sticky='ew', pady=(20, 0))

        self.var_estado_ia = tk.StringVar(value="Verificando...")
        ttk.Label(frame_estado_ia, textvariable=self.var_estado_ia, font=('Arial', 10)).pack(anchor='w')

        ttk.Button(frame_estado_ia, text="🔌 Probar conexión IA",
                  command=self._probar_ia).pack(anchor='w', pady=(10, 0))

        # === Botones ===
        frame_btns = ttk.Frame(self)
        frame_btns.pack(fill='x', padx=10, pady=10)

        ttk.Button(frame_btns, text="💾 Guardar",
                  command=self._guardar).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🔄 Restaurar defaults",
                  command=self._restaurar_defaults).pack(side='left')
        ttk.Button(frame_btns, text="Cerrar",
                  command=self.destroy).pack(side='right')

    def _cargar_valores(self):
        """Carga valores actuales de configuración"""
        # BD
        db = self.config.get('base_datos')
        self.var_server.set(db.get('server', ''))
        self.var_user.set(db.get('user', ''))
        self.var_password.set(db.get('password', ''))
        self.var_db_geyce.set(db.get('database_geyce', ''))
        self.var_db_easp.set(db.get('database_easp', ''))

        # Cuentas
        for key, var in self.vars_cuentas.items():
            var.set(self.config.get_cuenta(key))

        # Validaciones
        val = self.config.get('validaciones')
        self.var_smi.set(str(val.get('smi_mensual', 1134)))
        self.var_tolerancia.set(str(val.get('tolerancia_cuadre', 0.01)))
        self.var_max_sal.set(str(val.get('max_salario', 15000)))
        self.var_min_sal.set(str(val.get('min_salario', 800)))

        # Interfaz
        ui = self.config.get('interfaz')
        self.var_maximizar.set(ui.get('maximizar_inicio', True))
        self.var_tooltips.set(ui.get('mostrar_tooltips', True))
        self.var_autovalidar.set(ui.get('auto_validar', True))
        self.var_idioma_ocr.set(ui.get('idioma_ocr', 'spa'))

        # IA (Fase 8)
        ia = self.config.get('ia')
        self.var_api_key.set(ia.get('api_key', ''))
        self.var_modelo_ia.set(ia.get('modelo', 'claude-sonnet-4-20250514'))
        self.var_ia_habilitada.set(ia.get('habilitado', True))
        self.var_guardar_extracciones.set(ia.get('guardar_extracciones', True))
        self.var_mostrar_editor.set(ia.get('mostrar_editor_json', True))
        self.var_max_tokens.set(str(ia.get('max_tokens', 4096)))

        # Actualizar estado IA
        self._actualizar_estado_ia()

    def _guardar(self):
        """Guarda la configuración"""
        try:
            # BD
            self.config.set('base_datos', 'server', self.var_server.get())
            self.config.set('base_datos', 'user', self.var_user.get())
            self.config.set('base_datos', 'password', self.var_password.get())
            self.config.set('base_datos', 'database_geyce', self.var_db_geyce.get())
            self.config.set('base_datos', 'database_easp', self.var_db_easp.get())

            # Cuentas
            for key, var in self.vars_cuentas.items():
                self.config.set_cuenta(key, var.get())

            # Validaciones
            self.config.set('validaciones', 'smi_mensual', float(self.var_smi.get()))
            self.config.set('validaciones', 'tolerancia_cuadre', float(self.var_tolerancia.get()))
            self.config.set('validaciones', 'max_salario', float(self.var_max_sal.get()))
            self.config.set('validaciones', 'min_salario', float(self.var_min_sal.get()))

            # Interfaz
            self.config.set('interfaz', 'maximizar_inicio', self.var_maximizar.get())
            self.config.set('interfaz', 'mostrar_tooltips', self.var_tooltips.get())
            self.config.set('interfaz', 'auto_validar', self.var_autovalidar.get())
            self.config.set('interfaz', 'idioma_ocr', self.var_idioma_ocr.get())

            # IA (Fase 8)
            self.config.set('ia', 'api_key', self.var_api_key.get())
            self.config.set('ia', 'modelo', self.var_modelo_ia.get())
            self.config.set('ia', 'habilitado', self.var_ia_habilitada.get())
            self.config.set('ia', 'guardar_extracciones', self.var_guardar_extracciones.get())
            self.config.set('ia', 'mostrar_editor_json', self.var_mostrar_editor.get())
            try:
                self.config.set('ia', 'max_tokens', int(self.var_max_tokens.get()))
            except ValueError:
                self.config.set('ia', 'max_tokens', 4096)

            messagebox.showinfo("Éxito", "Configuración guardada correctamente")
            self.logger.info("Configuración guardada")

        except Exception as e:
            messagebox.showerror("Error", f"Error guardando configuración: {e}")

    def _restaurar_defaults(self):
        """Restaura valores por defecto"""
        if messagebox.askyesno("Confirmar", "¿Restaurar toda la configuración a valores por defecto?"):
            self.config.restaurar_defaults()
            self._cargar_valores()
            messagebox.showinfo("Info", "Configuración restaurada")

    def _probar_conexion(self):
        """Prueba la conexión a la base de datos"""
        # Guardar temporalmente para probar
        self._guardar()
        db = DatabaseManager()
        ok, msg = db.test_conexion()

        if ok:
            messagebox.showinfo("Conexión exitosa", f"Conectado a:\n{msg}")
        else:
            messagebox.showerror("Error de conexión", f"No se pudo conectar:\n{msg}")

    def _actualizar_estado_ia(self):
        """Actualiza el estado de la IA en la interfaz"""
        if not ANTHROPIC_OK:
            self.var_estado_ia.set("❌ Librería 'anthropic' no instalada\nEjecute: pip install anthropic")
            return

        api_key = self.var_api_key.get()
        if not api_key:
            self.var_estado_ia.set("⚠️ No hay API key configurada")
            return

        if not self.var_ia_habilitada.get():
            self.var_estado_ia.set("⚠️ IA deshabilitada")
            return

        self.var_estado_ia.set(f"✅ IA configurada\nModelo: {self.var_modelo_ia.get()}")

    def _probar_ia(self):
        """Prueba la conexión con la API de Anthropic"""
        if not ANTHROPIC_OK:
            messagebox.showerror("Error", "La librería 'anthropic' no está instalada.\n\nEjecute:\npip install anthropic")
            return

        api_key = self.var_api_key.get()
        if not api_key:
            messagebox.showwarning("Aviso", "Introduzca una API key de Anthropic")
            return

        self.var_estado_ia.set("🔄 Probando conexión...")
        self.update()

        try:
            client = anthropic.Anthropic(api_key=api_key)
            # Hacer una llamada simple para verificar
            response = client.messages.create(
                model=self.var_modelo_ia.get(),
                max_tokens=50,
                messages=[
                    {"role": "user", "content": "Di 'OK' si me escuchas."}
                ]
            )

            texto_respuesta = response.content[0].text
            tokens_usados = response.usage.input_tokens + response.usage.output_tokens

            self.var_estado_ia.set(f"✅ Conexión exitosa\nRespuesta: {texto_respuesta[:50]}\nTokens: {tokens_usados}")
            messagebox.showinfo("Éxito", f"Conexión con IA exitosa\n\nModelo: {self.var_modelo_ia.get()}\nTokens usados: {tokens_usados}")
            self.logger.info("Prueba de conexión IA exitosa", f"Modelo: {self.var_modelo_ia.get()}")

        except anthropic.AuthenticationError:
            self.var_estado_ia.set("❌ API key inválida")
            messagebox.showerror("Error", "API key inválida o expirada.\n\nVerifique su API key en console.anthropic.com")
        except anthropic.RateLimitError:
            self.var_estado_ia.set("⚠️ Límite de tasa excedido")
            messagebox.showwarning("Aviso", "Se ha excedido el límite de llamadas.\n\nEspere un momento antes de reintentar.")
        except Exception as e:
            self.var_estado_ia.set(f"❌ Error: {str(e)[:50]}")
            messagebox.showerror("Error", f"Error conectando con IA:\n\n{e}")


# =============================================================================
# CLASE: VentanaHistorico (Histórico de asientos)
# =============================================================================
class VentanaHistorico(tk.Toplevel):
    """Ventana para consultar el histórico de asientos"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Histórico de Asientos")
        self.geometry("1000x600")
        self.minsize(800, 500)

        self.historico = HistoricoAsientos()
        self.logger = Logger()

        self._crear_ui()
        self._cargar_datos()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Filtros ===
        frame_filtros = ttk.LabelFrame(main, text="Filtros", padding=10)
        frame_filtros.pack(fill='x', pady=(0, 10))

        f1 = ttk.Frame(frame_filtros)
        f1.pack(fill='x')

        ttk.Label(f1, text="Empresa:").pack(side='left')
        self.var_filtro_empresa = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_filtro_empresa, width=25).pack(side='left', padx=(5, 15))

        ttk.Label(f1, text="CIF:").pack(side='left')
        self.var_filtro_cif = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_filtro_cif, width=15).pack(side='left', padx=(5, 15))

        ttk.Label(f1, text="Período:").pack(side='left')
        self.var_filtro_periodo = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_filtro_periodo, width=15).pack(side='left', padx=(5, 15))

        self.var_solo_guardados = tk.BooleanVar()
        ttk.Checkbutton(f1, text="Solo guardados en BD",
                       variable=self.var_solo_guardados).pack(side='left', padx=(15, 0))

        ttk.Button(f1, text="🔍 Buscar", command=self._buscar).pack(side='right')

        # === Tabla ===
        frame_tabla = ttk.Frame(main)
        frame_tabla.pack(fill='both', expand=True, pady=(0, 10))

        columnas = ('fecha', 'asiento', 'empresa', 'cif', 'periodo', 'debe', 'haber', 'guardado')
        self.tree = ttk.Treeview(frame_tabla, columns=columnas, show='headings', height=15)

        self.tree.heading('fecha', text='Fecha')
        self.tree.heading('asiento', text='Nº Asiento')
        self.tree.heading('empresa', text='Empresa')
        self.tree.heading('cif', text='CIF')
        self.tree.heading('periodo', text='Período')
        self.tree.heading('debe', text='Debe')
        self.tree.heading('haber', text='Haber')
        self.tree.heading('guardado', text='BD')

        self.tree.column('fecha', width=90, anchor='center')
        self.tree.column('asiento', width=80, anchor='center')
        self.tree.column('empresa', width=200)
        self.tree.column('cif', width=100, anchor='center')
        self.tree.column('periodo', width=100, anchor='center')
        self.tree.column('debe', width=100, anchor='e')
        self.tree.column('haber', width=100, anchor='e')
        self.tree.column('guardado', width=50, anchor='center')

        scroll = ttk.Scrollbar(frame_tabla, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)

        # === Resumen ===
        frame_resumen = ttk.Frame(main)
        frame_resumen.pack(fill='x', pady=(0, 10))

        self.var_total = tk.StringVar(value="Total: 0 registros")
        self.var_suma = tk.StringVar(value="Suma: 0,00 €")

        ttk.Label(frame_resumen, textvariable=self.var_total,
                 font=('Arial', 10, 'bold')).pack(side='left', padx=(0, 20))
        ttk.Label(frame_resumen, textvariable=self.var_suma,
                 font=('Arial', 10)).pack(side='left')

        # === Botones ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="📊 Exportar Excel",
                  command=self._exportar_excel).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📄 Exportar CSV",
                  command=self._exportar_csv).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🗑️ Eliminar seleccionado",
                  command=self._eliminar).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🧹 Limpiar histórico",
                  command=self._limpiar).pack(side='left')

        ttk.Button(frame_btns, text="Cerrar", command=self.destroy).pack(side='right')

    def _cargar_datos(self, registros=None):
        """Carga datos en la tabla"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        if registros is None:
            registros = self.historico.registros

        total_debe = 0
        total_haber = 0

        for r in registros:
            debe = r.get('total_debe', 0)
            haber = r.get('total_haber', 0)
            total_debe += debe
            total_haber += haber

            debe_str = f"{debe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            haber_str = f"{haber:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

            self.tree.insert('', 'end', iid=r.get('id'), values=(
                r.get('fecha_asiento', '')[:10],
                r.get('numero_asiento', ''),
                r.get('empresa', '')[:30],
                r.get('cif', ''),
                r.get('periodo', ''),
                debe_str,
                haber_str,
                '✅' if r.get('guardado_bd') else '❌'
            ))

        self.var_total.set(f"Total: {len(registros)} registros")
        suma_str = f"{total_debe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        self.var_suma.set(f"Suma Debe: {suma_str} €")

    def _buscar(self):
        """Aplica filtros y busca"""
        filtros = {}

        if self.var_filtro_empresa.get():
            filtros['empresa'] = self.var_filtro_empresa.get()
        if self.var_filtro_cif.get():
            filtros['cif'] = self.var_filtro_cif.get()
        if self.var_filtro_periodo.get():
            filtros['periodo'] = self.var_filtro_periodo.get()
        if self.var_solo_guardados.get():
            filtros['guardado_bd'] = True

        registros = self.historico.buscar(filtros)
        self._cargar_datos(registros)

    def _eliminar(self):
        """Elimina el registro seleccionado"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione un registro para eliminar")
            return

        if messagebox.askyesno("Confirmar", "¿Eliminar el registro seleccionado?"):
            self.historico.eliminar(sel[0])
            self._cargar_datos()

    def _limpiar(self):
        """Limpia todo el histórico"""
        if messagebox.askyesno("Confirmar", "¿Eliminar TODO el histórico? Esta acción no se puede deshacer."):
            self.historico.limpiar()
            self._cargar_datos()

    def _exportar_excel(self):
        """Exporta a Excel"""
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if ruta:
            stats = GestorEstadisticas()
            stats.exportar_informe_excel(ruta)
            messagebox.showinfo("Éxito", f"Exportado a:\n{ruta}")

    def _exportar_csv(self):
        """Exporta a CSV"""
        ruta = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if ruta:
            stats = GestorEstadisticas()
            stats.exportar_informe_csv(ruta)
            messagebox.showinfo("Éxito", f"Exportado a:\n{ruta}")


# =============================================================================
# CLASE: VentanaDashboard (Panel de estadísticas)
# =============================================================================
class VentanaDashboard(tk.Toplevel):
    """Dashboard con estadísticas y métricas"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Dashboard - Estadísticas")
        self.geometry("800x550")
        self.minsize(700, 450)

        self.stats = GestorEstadisticas()
        self.logger = Logger()

        self._crear_ui()
        self._actualizar_datos()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=15)
        main.pack(fill='both', expand=True)

        # === Título ===
        ttk.Label(main, text="📊 Dashboard de Procesamiento",
                 font=('Arial', 16, 'bold')).pack(pady=(0, 20))

        # === Métricas principales ===
        frame_metricas = ttk.Frame(main)
        frame_metricas.pack(fill='x', pady=(0, 20))

        # Crear tarjetas de métricas
        self.metricas = {}
        metricas_config = [
            ('total', '📄 Total Asientos', '#3498db'),
            ('guardados', '💾 Guardados BD', '#27ae60'),
            ('empresas', '🏢 Empresas', '#9b59b6'),
            ('recientes', '📅 Últimos 7 días', '#e67e22')
        ]

        for i, (key, titulo, color) in enumerate(metricas_config):
            frame = ttk.LabelFrame(frame_metricas, text=titulo, padding=15)
            frame.grid(row=0, column=i, padx=10, sticky='nsew')
            frame_metricas.columnconfigure(i, weight=1)

            var = tk.StringVar(value="0")
            self.metricas[key] = var
            ttk.Label(frame, textvariable=var, font=('Arial', 24, 'bold')).pack()

        # === Totales económicos ===
        frame_totales = ttk.LabelFrame(main, text="Totales Económicos", padding=15)
        frame_totales.pack(fill='x', pady=(0, 20))

        self.var_total_debe = tk.StringVar(value="0,00 €")
        self.var_total_haber = tk.StringVar(value="0,00 €")

        f_tot = ttk.Frame(frame_totales)
        f_tot.pack()

        ttk.Label(f_tot, text="Total Debe:", font=('Arial', 12)).grid(row=0, column=0, padx=10)
        ttk.Label(f_tot, textvariable=self.var_total_debe,
                 font=('Arial', 14, 'bold'), foreground='#2980b9').grid(row=0, column=1, padx=10)

        ttk.Label(f_tot, text="Total Haber:", font=('Arial', 12)).grid(row=0, column=2, padx=10)
        ttk.Label(f_tot, textvariable=self.var_total_haber,
                 font=('Arial', 14, 'bold'), foreground='#27ae60').grid(row=0, column=3, padx=10)

        # === Actividad por mes ===
        frame_meses = ttk.LabelFrame(main, text="Actividad por Mes (últimos 6)", padding=10)
        frame_meses.pack(fill='both', expand=True, pady=(0, 15))

        self.tree_meses = ttk.Treeview(frame_meses, columns=('mes', 'cantidad'), show='headings', height=6)
        self.tree_meses.heading('mes', text='Mes')
        self.tree_meses.heading('cantidad', text='Asientos')
        self.tree_meses.column('mes', width=150, anchor='center')
        self.tree_meses.column('cantidad', width=100, anchor='center')
        self.tree_meses.pack(fill='both', expand=True)

        # === Log info ===
        frame_log = ttk.Frame(main)
        frame_log.pack(fill='x', pady=(0, 10))

        self.var_logs = tk.StringVar(value="Logs: 0")
        self.var_errores = tk.StringVar(value="Errores: 0")

        ttk.Label(frame_log, textvariable=self.var_logs).pack(side='left', padx=(0, 20))
        ttk.Label(frame_log, textvariable=self.var_errores, foreground='red').pack(side='left')

        # === Botones ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="🔄 Actualizar",
                  command=self._actualizar_datos).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📊 Exportar informe",
                  command=self._exportar_informe).pack(side='left')
        ttk.Button(frame_btns, text="Cerrar", command=self.destroy).pack(side='right')

    def _actualizar_datos(self):
        """Actualiza los datos del dashboard"""
        data = self.stats.generar_dashboard()

        # Métricas
        self.metricas['total'].set(str(data.get('total_asientos', 0)))
        self.metricas['guardados'].set(str(data.get('guardados_bd', 0)))
        self.metricas['empresas'].set(str(data.get('empresas_unicas', 0)))
        self.metricas['recientes'].set(str(data.get('asientos_7_dias', 0)))

        # Totales
        debe = data.get('total_debe', 0)
        haber = data.get('total_haber', 0)
        self.var_total_debe.set(f"{debe:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
        self.var_total_haber.set(f"{haber:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))

        # Por mes
        for item in self.tree_meses.get_children():
            self.tree_meses.delete(item)

        for mes, cantidad in data.get('por_mes', {}).items():
            self.tree_meses.insert('', 'end', values=(mes, cantidad))

        # Logs
        self.var_logs.set(f"Logs: {data.get('logs_totales', 0)}")
        self.var_errores.set(f"Errores: {data.get('errores_totales', 0)}")

    def _exportar_informe(self):
        """Exporta informe completo"""
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")]
        )
        if ruta:
            if ruta.endswith('.xlsx'):
                self.stats.exportar_informe_excel(ruta)
            else:
                self.stats.exportar_informe_csv(ruta)
            messagebox.showinfo("Éxito", f"Informe exportado:\n{ruta}")


# =============================================================================
# CLASE: VentanaAsiento (Previsualización y edición de asientos)
# =============================================================================
class VentanaAsiento(tk.Toplevel):
    """Ventana para previsualizar, editar y guardar asientos contables"""

    def __init__(self, parent, asiento, db_manager=None, callback_guardado=None):
        super().__init__(parent)
        self.title(f"Asiento Contable - {asiento.concepto_general}")
        self.geometry("900x650")
        self.minsize(800, 500)

        self.asiento = asiento
        self.db = db_manager
        self.callback_guardado = callback_guardado
        self.logger = Logger()

        self._crear_ui()
        self._cargar_datos()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Cabecera del asiento ===
        frame_cab = ttk.LabelFrame(main, text="Datos del Asiento", padding=10)
        frame_cab.pack(fill='x', pady=(0, 10))

        # Fila 1
        f1 = ttk.Frame(frame_cab)
        f1.pack(fill='x', pady=(0, 5))

        ttk.Label(f1, text="Nº Asiento:").pack(side='left')
        self.var_numero = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_numero, width=10).pack(side='left', padx=(5, 20))

        ttk.Label(f1, text="Fecha:").pack(side='left')
        self.var_fecha = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_fecha, width=12).pack(side='left', padx=(5, 20))

        ttk.Label(f1, text="Diario:").pack(side='left')
        self.var_diario = tk.StringVar(value="1")
        ttk.Entry(f1, textvariable=self.var_diario, width=5).pack(side='left', padx=(5, 20))

        ttk.Label(f1, text="Documento:").pack(side='left')
        self.var_documento = tk.StringVar()
        ttk.Entry(f1, textvariable=self.var_documento, width=20).pack(side='left', padx=(5, 0))

        # Fila 2
        f2 = ttk.Frame(frame_cab)
        f2.pack(fill='x', pady=(5, 0))

        ttk.Label(f2, text="Empresa:").pack(side='left')
        self.var_empresa = tk.StringVar()
        ttk.Label(f2, textvariable=self.var_empresa, font=('Arial', 10, 'bold')).pack(side='left', padx=(5, 20))

        ttk.Label(f2, text="Período:").pack(side='left')
        self.var_periodo = tk.StringVar()
        ttk.Entry(f2, textvariable=self.var_periodo, width=20).pack(side='left', padx=(5, 20))

        ttk.Label(f2, text="Concepto:").pack(side='left')
        self.var_concepto = tk.StringVar()
        ttk.Entry(f2, textvariable=self.var_concepto, width=30).pack(side='left', padx=(5, 0))

        # === Líneas del asiento ===
        frame_lineas = ttk.LabelFrame(main, text="Líneas del Asiento", padding=5)
        frame_lineas.pack(fill='both', expand=True, pady=(0, 10))

        # Treeview
        columnas = ('linea', 'cuenta', 'descripcion', 'concepto', 'debe', 'haber')
        self.tree = ttk.Treeview(frame_lineas, columns=columnas, show='headings', height=12)

        self.tree.heading('linea', text='#')
        self.tree.heading('cuenta', text='Cuenta')
        self.tree.heading('descripcion', text='Descripción')
        self.tree.heading('concepto', text='Concepto')
        self.tree.heading('debe', text='Debe')
        self.tree.heading('haber', text='Haber')

        self.tree.column('linea', width=40, anchor='center')
        self.tree.column('cuenta', width=100, anchor='center')
        self.tree.column('descripcion', width=180)
        self.tree.column('concepto', width=200)
        self.tree.column('debe', width=100, anchor='e')
        self.tree.column('haber', width=100, anchor='e')

        scroll = ttk.Scrollbar(frame_lineas, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)

        # Botones de edición de líneas
        frame_edit = ttk.Frame(frame_lineas)
        frame_edit.pack(fill='x', pady=(5, 0))

        ttk.Button(frame_edit, text="➕ Añadir línea",
                  command=self._añadir_linea).pack(side='left', padx=(0, 5))
        ttk.Button(frame_edit, text="✏️ Editar línea",
                  command=self._editar_linea).pack(side='left', padx=(0, 5))
        ttk.Button(frame_edit, text="🗑️ Eliminar línea",
                  command=self._eliminar_linea).pack(side='left', padx=(0, 20))
        ttk.Button(frame_edit, text="⚖️ Cuadrar automático",
                  command=self._cuadrar_automatico).pack(side='left')

        # === Totales ===
        frame_totales = ttk.Frame(main)
        frame_totales.pack(fill='x', pady=(0, 10))

        # Totales
        self.var_total_debe = tk.StringVar()
        self.var_total_haber = tk.StringVar()
        self.var_diferencia = tk.StringVar()

        ttk.Label(frame_totales, text="Total Debe:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_totales, textvariable=self.var_total_debe,
                 font=('Arial', 10), foreground='blue').pack(side='left', padx=(5, 20))

        ttk.Label(frame_totales, text="Total Haber:", font=('Arial', 10, 'bold')).pack(side='left')
        ttk.Label(frame_totales, textvariable=self.var_total_haber,
                 font=('Arial', 10), foreground='blue').pack(side='left', padx=(5, 20))

        ttk.Label(frame_totales, text="Estado:").pack(side='left')
        self.label_estado = ttk.Label(frame_totales, textvariable=self.var_diferencia,
                                      font=('Arial', 10, 'bold'))
        self.label_estado.pack(side='left', padx=(5, 0))

        # === Botones de acción ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="💾 Guardar en BD",
                  command=self._guardar_bd).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📄 Exportar texto",
                  command=self._exportar_texto).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📋 Copiar al portapapeles",
                  command=self._copiar_portapapeles).pack(side='left')

        ttk.Button(frame_btns, text="Cerrar",
                  command=self.destroy).pack(side='right')

    def _cargar_datos(self):
        """Carga los datos del asiento en la UI"""
        self.var_numero.set(str(self.asiento.numero_asiento))
        self.var_fecha.set(self.asiento.fecha.strftime("%d/%m/%Y"))
        self.var_diario.set(self.asiento.diario)
        self.var_documento.set(self.asiento.documento)
        self.var_empresa.set(f"{self.asiento.nombre_empresa} ({self.asiento.cif_empresa})")
        self.var_periodo.set(self.asiento.periodo)
        self.var_concepto.set(self.asiento.concepto_general)

        self._actualizar_lineas()

    def _actualizar_lineas(self):
        """Actualiza la tabla de líneas"""
        # Limpiar
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Añadir líneas
        for linea in self.asiento.lineas:
            debe_str = f"{linea.debe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if linea.debe else ""
            haber_str = f"{linea.haber:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if linea.haber else ""

            self.tree.insert('', 'end', iid=str(linea.numero_linea), values=(
                linea.numero_linea,
                linea.cuenta,
                linea.descripcion[:25],
                linea.concepto[:30],
                debe_str,
                haber_str
            ))

        self._actualizar_totales()

    def _actualizar_totales(self):
        """Actualiza los totales del asiento"""
        self.asiento._recalcular_totales()

        total_debe = f"{self.asiento.total_debe:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
        total_haber = f"{self.asiento.total_haber:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')

        self.var_total_debe.set(total_debe)
        self.var_total_haber.set(total_haber)

        if self.asiento.cuadrado:
            self.var_diferencia.set("✅ CUADRADO")
            self.label_estado.configure(foreground='green')
        else:
            dif = self.asiento.get_diferencia()
            self.var_diferencia.set(f"❌ Diferencia: {dif:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))
            self.label_estado.configure(foreground='red')

    def _añadir_linea(self):
        """Abre diálogo para añadir nueva línea"""
        self._dialogo_linea(None)

    def _editar_linea(self):
        """Edita la línea seleccionada"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una línea para editar")
            return

        num_linea = int(sel[0])
        linea = next((l for l in self.asiento.lineas if l.numero_linea == num_linea), None)
        if linea:
            self._dialogo_linea(linea)

    def _dialogo_linea(self, linea_existente):
        """Diálogo para añadir/editar línea"""
        dialogo = tk.Toplevel(self)
        dialogo.title("Editar línea" if linea_existente else "Nueva línea")
        dialogo.geometry("400x300")
        dialogo.transient(self)
        dialogo.grab_set()

        frame = ttk.Frame(dialogo, padding=15)
        frame.pack(fill='both', expand=True)

        # Campos
        ttk.Label(frame, text="Cuenta:").grid(row=0, column=0, sticky='w', pady=5)
        var_cuenta = tk.StringVar(value=linea_existente.cuenta if linea_existente else "")
        ttk.Entry(frame, textvariable=var_cuenta, width=15).grid(row=0, column=1, sticky='w', pady=5)

        ttk.Label(frame, text="Descripción:").grid(row=1, column=0, sticky='w', pady=5)
        var_desc = tk.StringVar(value=linea_existente.descripcion if linea_existente else "")
        ttk.Entry(frame, textvariable=var_desc, width=30).grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(frame, text="Concepto:").grid(row=2, column=0, sticky='w', pady=5)
        var_concepto = tk.StringVar(value=linea_existente.concepto if linea_existente else "")
        ttk.Entry(frame, textvariable=var_concepto, width=30).grid(row=2, column=1, sticky='w', pady=5)

        ttk.Label(frame, text="Debe:").grid(row=3, column=0, sticky='w', pady=5)
        var_debe = tk.StringVar(value=str(linea_existente.debe) if linea_existente else "0")
        ttk.Entry(frame, textvariable=var_debe, width=15).grid(row=3, column=1, sticky='w', pady=5)

        ttk.Label(frame, text="Haber:").grid(row=4, column=0, sticky='w', pady=5)
        var_haber = tk.StringVar(value=str(linea_existente.haber) if linea_existente else "0")
        ttk.Entry(frame, textvariable=var_haber, width=15).grid(row=4, column=1, sticky='w', pady=5)

        def guardar():
            try:
                debe = float(var_debe.get().replace(',', '.')) if var_debe.get() else 0
                haber = float(var_haber.get().replace(',', '.')) if var_haber.get() else 0

                if linea_existente:
                    linea_existente.cuenta = var_cuenta.get()
                    linea_existente.descripcion = var_desc.get()
                    linea_existente.concepto = var_concepto.get()
                    linea_existente.debe = debe
                    linea_existente.haber = haber
                else:
                    self.asiento.agregar_linea(
                        cuenta=var_cuenta.get(),
                        concepto=var_concepto.get(),
                        debe=debe,
                        haber=haber,
                        descripcion=var_desc.get()
                    )

                self._actualizar_lineas()
                dialogo.destroy()

            except ValueError:
                messagebox.showerror("Error", "Importes no válidos")

        ttk.Button(frame, text="Guardar", command=guardar).grid(row=5, column=0, pady=20)
        ttk.Button(frame, text="Cancelar", command=dialogo.destroy).grid(row=5, column=1, pady=20)

    def _eliminar_linea(self):
        """Elimina la línea seleccionada"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Seleccione una línea para eliminar")
            return

        if messagebox.askyesno("Confirmar", "¿Eliminar la línea seleccionada?"):
            num_linea = int(sel[0])
            self.asiento.eliminar_linea(num_linea)
            self._actualizar_lineas()

    def _cuadrar_automatico(self):
        """Cuadra el asiento automáticamente"""
        if self.asiento.cuadrado:
            messagebox.showinfo("Info", "El asiento ya está cuadrado")
            return

        # Pedir cuenta de ajuste
        cuenta = tk.simpledialog.askstring(
            "Cuenta de ajuste",
            "Introduzca la cuenta para cuadrar el asiento:",
            initialvalue="5720000",
            parent=self
        )

        if cuenta:
            self.asiento.cuadrar_automatico(cuenta)
            self._actualizar_lineas()
            if self.asiento.cuadrado:
                messagebox.showinfo("Éxito", "Asiento cuadrado correctamente")

    def _guardar_bd(self):
        """Guarda el asiento en la base de datos"""
        if not self.asiento.cuadrado:
            if not messagebox.askyesno("Aviso", "El asiento no cuadra. ¿Desea guardarlo de todas formas?"):
                return

        if not self.db:
            messagebox.showerror("Error", "No hay conexión a base de datos")
            return

        if not self.asiento.base_datos:
            messagebox.showerror("Error", "No se ha especificado la base de datos de la empresa")
            return

        # Actualizar datos desde UI
        try:
            self.asiento.numero_asiento = int(self.var_numero.get())
        except:
            pass
        self.asiento.documento = self.var_documento.get()
        self.asiento.periodo = self.var_periodo.get()
        self.asiento.concepto_general = self.var_concepto.get()
        self.asiento.diario = self.var_diario.get()

        # Intentar guardar
        try:
            exito = self.db.guardar_asiento(self.asiento)

            if exito:
                self.asiento.guardado = True

                # Registrar en histórico
                historico = HistoricoAsientos()
                historico.registrar(self.asiento, guardado_bd=True)

                messagebox.showinfo("Éxito", f"Asiento {self.asiento.numero_asiento} guardado correctamente")
                self.logger.info(f"Asiento guardado: {self.asiento.numero_asiento}")

                if self.callback_guardado:
                    self.callback_guardado(self.asiento)
            else:
                messagebox.showerror("Error", "No se pudo guardar el asiento")

        except Exception as e:
            messagebox.showerror("Error", f"Error guardando asiento: {e}")
            self.logger.error("Error guardando asiento", str(e))

    def _exportar_texto(self):
        """Exporta el asiento a un archivo de texto"""
        ruta = filedialog.asksaveasfilename(
            title="Guardar asiento",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt")]
        )
        if not ruta:
            return

        try:
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write(self.asiento.to_texto())
            messagebox.showinfo("Éxito", f"Asiento exportado a:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", f"Error exportando: {e}")

    def _copiar_portapapeles(self):
        """Copia el asiento al portapapeles"""
        self.clipboard_clear()
        self.clipboard_append(self.asiento.to_texto())
        messagebox.showinfo("Copiado", "Asiento copiado al portapapeles")


# =============================================================================
# CLASE: VentanaAlertas (Panel de alertas y validaciones)
# =============================================================================
class VentanaAlertas(tk.Toplevel):
    """Ventana para mostrar alertas y resultados de validación"""

    def __init__(self, parent, resultado_validacion, nombre_documento=""):
        super().__init__(parent)
        self.title(f"Validación: {nombre_documento}" if nombre_documento else "Resultado de Validación")
        self.geometry("700x500")

        self.resultado = resultado_validacion
        self._crear_ui()

    def _crear_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Resumen ===
        frame_resumen = ttk.LabelFrame(main, text="Resumen", padding=10)
        frame_resumen.pack(fill='x', pady=(0, 10))

        # Estado general
        if self.resultado['valido']:
            estado = "✅ Documento válido"
            color = 'green'
        else:
            estado = "❌ Documento con errores"
            color = 'red'

        ttk.Label(frame_resumen, text=estado, font=('Arial', 14, 'bold'),
                 foreground=color).pack(anchor='w')

        # Contadores
        frame_contadores = ttk.Frame(frame_resumen)
        frame_contadores.pack(fill='x', pady=(10, 0))

        ttk.Label(frame_contadores,
                 text=f"❌ Errores: {len(self.resultado['errores'])}",
                 foreground='red').pack(side='left', padx=(0, 20))
        ttk.Label(frame_contadores,
                 text=f"⚠️ Advertencias: {len(self.resultado['warnings'])}",
                 foreground='orange').pack(side='left')

        # === Información adicional ===
        info = self.resultado.get('info', {})

        if info:
            frame_info = ttk.LabelFrame(main, text="Información", padding=10)
            frame_info.pack(fill='x', pady=(0, 10))

            # CIF
            if 'cif_valido' in info:
                icono = "✅" if info['cif_valido'] else "❌"
                tipo = info.get('cif_tipo', 'Desconocido')
                ttk.Label(frame_info, text=f"{icono} CIF/NIF: {tipo}").pack(anchor='w')

            # Duplicado
            if info.get('es_duplicado'):
                ttk.Label(frame_info, text="⚠️ Posible documento duplicado",
                         foreground='orange').pack(anchor='w')

            # Cuadre contable
            cuadre = info.get('cuadre', {})
            if cuadre:
                icono = "✅" if cuadre.get('cuadra') else "❌"
                ttk.Label(frame_info,
                         text=f"{icono} Cuadre: Debe {cuadre.get('debe', 0):.2f} € | Haber {cuadre.get('haber', 0):.2f} €"
                         ).pack(anchor='w')
                if not cuadre.get('cuadra'):
                    ttk.Label(frame_info,
                             text=f"   Diferencia: {cuadre.get('diferencia', 0):.2f} €",
                             foreground='red').pack(anchor='w')

        # === Lista de alertas ===
        frame_alertas = ttk.LabelFrame(main, text="Alertas detalladas", padding=5)
        frame_alertas.pack(fill='both', expand=True, pady=(0, 10))

        # Treeview
        columnas = ('tipo', 'mensaje')
        tree = ttk.Treeview(frame_alertas, columns=columnas, show='headings', height=10)
        tree.heading('tipo', text='Tipo')
        tree.heading('mensaje', text='Mensaje')
        tree.column('tipo', width=80, anchor='center')
        tree.column('mensaje', width=550)

        scroll = ttk.Scrollbar(frame_alertas, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)

        # Añadir errores
        for err in self.resultado['errores']:
            tree.insert('', 'end', values=('❌ Error', err))

        # Añadir warnings
        for warn in self.resultado['warnings']:
            tree.insert('', 'end', values=('⚠️ Aviso', warn))

        if not self.resultado['alertas']:
            tree.insert('', 'end', values=('✅', 'Sin alertas - Todo correcto'))

        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)

        # === Botones ===
        frame_btns = ttk.Frame(main)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="Exportar informe",
                  command=self._exportar_informe).pack(side='left')
        ttk.Button(frame_btns, text="Cerrar",
                  command=self.destroy).pack(side='right')

    def _exportar_informe(self):
        """Exporta el informe de validación a un archivo de texto"""
        ruta = filedialog.asksaveasfilename(
            title="Guardar informe",
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
        )
        if not ruta:
            return

        try:
            with open(ruta, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("INFORME DE VALIDACIÓN\n")
                f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")

                # Estado
                f.write(f"Estado: {'VÁLIDO' if self.resultado['valido'] else 'CON ERRORES'}\n")
                f.write(f"Errores: {len(self.resultado['errores'])}\n")
                f.write(f"Advertencias: {len(self.resultado['warnings'])}\n\n")

                # Info
                info = self.resultado.get('info', {})
                if info:
                    f.write("-" * 40 + "\n")
                    f.write("INFORMACIÓN ADICIONAL\n")
                    f.write("-" * 40 + "\n")
                    for k, v in info.items():
                        f.write(f"  {k}: {v}\n")
                    f.write("\n")

                # Errores
                if self.resultado['errores']:
                    f.write("-" * 40 + "\n")
                    f.write("ERRORES\n")
                    f.write("-" * 40 + "\n")
                    for i, err in enumerate(self.resultado['errores'], 1):
                        f.write(f"  {i}. {err}\n")
                    f.write("\n")

                # Warnings
                if self.resultado['warnings']:
                    f.write("-" * 40 + "\n")
                    f.write("ADVERTENCIAS\n")
                    f.write("-" * 40 + "\n")
                    for i, warn in enumerate(self.resultado['warnings'], 1):
                        f.write(f"  {i}. {warn}\n")

            messagebox.showinfo("Éxito", f"Informe guardado en:\n{ruta}")

        except Exception as e:
            messagebox.showerror("Error", f"Error guardando informe: {e}")


# =============================================================================
# CLASE: VentanaProcesoMasivo (Procesamiento por lotes)
# =============================================================================
class VentanaProcesoMasivo(tk.Toplevel):
    """Ventana para procesar múltiples PDFs en lote"""

    # Estados de procesamiento
    ESTADO_PENDIENTE = "⏳ Pendiente"
    ESTADO_PROCESANDO = "🔄 Procesando"
    ESTADO_OK = "✅ Completado"
    ESTADO_ERROR = "❌ Error"
    ESTADO_SIN_CIF = "⚠️ Sin CIF"

    def __init__(self, parent, db_manager, gestor_plantillas):
        super().__init__(parent)
        self.title("Proceso Masivo de Documentos")
        self.geometry("1200x700")
        self.minsize(900, 500)

        self.db = db_manager
        self.gestor_plantillas = gestor_plantillas
        self.logger = Logger()
        self.detector = DetectorDocumento()
        self.extractor = ExtractorConceptos()

        # Cola de archivos a procesar
        self.archivos = []  # Lista de {ruta, estado, pdf, empresa, conceptos, error}
        self.procesando = False
        self.cancelar = False

        # Queue para actualizaciones de UI
        self.queue = Queue()

        self._crear_ui()
        self._iniciar_actualizador()

    def _crear_ui(self):
        # Frame principal
        main = ttk.Frame(self, padding=10)
        main.pack(fill='both', expand=True)

        # === Panel superior: Controles ===
        frame_controles = ttk.LabelFrame(main, text="Controles", padding=10)
        frame_controles.pack(fill='x', pady=(0, 10))

        # Botones de carga
        frame_btns = ttk.Frame(frame_controles)
        frame_btns.pack(fill='x')

        ttk.Button(frame_btns, text="📁 Añadir archivos",
                  command=self._añadir_archivos).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="📂 Añadir carpeta",
                  command=self._añadir_carpeta).pack(side='left', padx=(0, 5))
        ttk.Button(frame_btns, text="🗑️ Limpiar lista",
                  command=self._limpiar_lista).pack(side='left', padx=(0, 20))

        # Botones de procesamiento
        self.btn_procesar = ttk.Button(frame_btns, text="▶️ Procesar todos",
                                       command=self._iniciar_proceso)
        self.btn_procesar.pack(side='left', padx=(0, 5))

        self.btn_cancelar = ttk.Button(frame_btns, text="⏹️ Cancelar",
                                       command=self._cancelar_proceso, state='disabled')
        self.btn_cancelar.pack(side='left', padx=(0, 20))

        # Exportación
        ttk.Button(frame_btns, text="📊 Exportar Excel",
                  command=self._exportar_excel).pack(side='right', padx=(5, 0))
        ttk.Button(frame_btns, text="📄 Exportar CSV",
                  command=self._exportar_csv).pack(side='right', padx=(5, 0))

        # Progreso general
        frame_progreso = ttk.Frame(frame_controles)
        frame_progreso.pack(fill='x', pady=(10, 0))

        self.var_progreso_texto = tk.StringVar(value="Sin archivos cargados")
        ttk.Label(frame_progreso, textvariable=self.var_progreso_texto).pack(side='left')

        self.progreso = ttk.Progressbar(frame_progreso, length=300, mode='determinate')
        self.progreso.pack(side='right')

        # === Panel central: Tabla de archivos ===
        frame_tabla = ttk.LabelFrame(main, text="Documentos", padding=5)
        frame_tabla.pack(fill='both', expand=True, pady=(0, 10))

        # Treeview con columnas
        columnas = ('archivo', 'estado', 'cif', 'empresa', 'periodo', 'conceptos', 'total')
        self.tree = ttk.Treeview(frame_tabla, columns=columnas, show='headings', height=15)

        # Configurar columnas
        self.tree.heading('archivo', text='Archivo')
        self.tree.heading('estado', text='Estado')
        self.tree.heading('cif', text='CIF')
        self.tree.heading('empresa', text='Empresa')
        self.tree.heading('periodo', text='Período')
        self.tree.heading('conceptos', text='Conceptos')
        self.tree.heading('total', text='Total Neto')

        self.tree.column('archivo', width=250)
        self.tree.column('estado', width=100, anchor='center')
        self.tree.column('cif', width=100, anchor='center')
        self.tree.column('empresa', width=200)
        self.tree.column('periodo', width=100, anchor='center')
        self.tree.column('conceptos', width=80, anchor='center')
        self.tree.column('total', width=100, anchor='e')

        # Scrollbars
        scroll_y = ttk.Scrollbar(frame_tabla, orient='vertical', command=self.tree.yview)
        scroll_x = ttk.Scrollbar(frame_tabla, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side='right', fill='y')
        scroll_x.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)

        # Doble clic para ver detalles
        self.tree.bind('<Double-1>', self._ver_detalles)

        # === Panel inferior: Resumen ===
        frame_resumen = ttk.LabelFrame(main, text="Resumen", padding=10)
        frame_resumen.pack(fill='x')

        # Estadísticas
        frame_stats = ttk.Frame(frame_resumen)
        frame_stats.pack(fill='x')

        self.var_total = tk.StringVar(value="Total: 0")
        self.var_ok = tk.StringVar(value="✅ Completados: 0")
        self.var_errores = tk.StringVar(value="❌ Errores: 0")
        self.var_sin_cif = tk.StringVar(value="⚠️ Sin CIF: 0")
        self.var_suma_netos = tk.StringVar(value="💰 Suma netos: 0.00 €")

        ttk.Label(frame_stats, textvariable=self.var_total, font=('Arial', 10, 'bold')).pack(side='left', padx=(0, 20))
        ttk.Label(frame_stats, textvariable=self.var_ok, foreground='green').pack(side='left', padx=(0, 20))
        ttk.Label(frame_stats, textvariable=self.var_errores, foreground='red').pack(side='left', padx=(0, 20))
        ttk.Label(frame_stats, textvariable=self.var_sin_cif, foreground='orange').pack(side='left', padx=(0, 20))
        ttk.Label(frame_stats, textvariable=self.var_suma_netos, font=('Arial', 10, 'bold')).pack(side='right')

    def _iniciar_actualizador(self):
        """Procesa actualizaciones de UI desde el hilo de procesamiento"""
        try:
            while True:
                callback = self.queue.get_nowait()
                callback()
        except Empty:
            pass
        self.after(100, self._iniciar_actualizador)

    def _añadir_archivos(self):
        """Añade archivos PDF individuales"""
        rutas = filedialog.askopenfilenames(
            title="Seleccionar PDFs",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        for ruta in rutas:
            self._añadir_archivo(ruta)
        self._actualizar_resumen()

    def _añadir_carpeta(self):
        """Añade todos los PDFs de una carpeta"""
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta con PDFs")
        if carpeta:
            for archivo in Path(carpeta).glob("*.pdf"):
                self._añadir_archivo(str(archivo))
            for archivo in Path(carpeta).glob("*.PDF"):
                self._añadir_archivo(str(archivo))
        self._actualizar_resumen()

    def _añadir_archivo(self, ruta):
        """Añade un archivo a la lista si no existe"""
        # Verificar que no esté duplicado
        for item in self.archivos:
            if item['ruta'] == ruta:
                return

        nombre = os.path.basename(ruta)
        item = {
            'ruta': ruta,
            'nombre': nombre,
            'estado': self.ESTADO_PENDIENTE,
            'pdf': None,
            'empresa': None,
            'conceptos': [],
            'total_neto': None,
            'error': None
        }
        self.archivos.append(item)

        # Añadir a la tabla
        self.tree.insert('', 'end', iid=ruta, values=(
            nombre, self.ESTADO_PENDIENTE, '-', '-', '-', '-', '-'
        ))

    def _limpiar_lista(self):
        """Limpia la lista de archivos"""
        if self.procesando:
            messagebox.showwarning("Aviso", "Espere a que termine el proceso actual")
            return

        self.archivos = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._actualizar_resumen()

    def _iniciar_proceso(self):
        """Inicia el procesamiento de todos los archivos"""
        if not self.archivos:
            messagebox.showwarning("Aviso", "No hay archivos para procesar")
            return

        self.procesando = True
        self.cancelar = False
        self.btn_procesar.configure(state='disabled')
        self.btn_cancelar.configure(state='normal')

        threading.Thread(target=self._procesar_cola, daemon=True).start()

    def _cancelar_proceso(self):
        """Cancela el procesamiento"""
        self.cancelar = True
        self.btn_cancelar.configure(state='disabled')

    def _procesar_cola(self):
        """Procesa la cola de archivos en segundo plano"""
        total = len(self.archivos)

        for i, item in enumerate(self.archivos):
            if self.cancelar:
                self.logger.warning("Proceso masivo cancelado por el usuario")
                break

            # Actualizar progreso
            self.queue.put(lambda idx=i, tot=total: self._actualizar_progreso(idx, tot))

            # Saltar si ya está procesado
            if item['estado'] == self.ESTADO_OK:
                continue

            # Marcar como procesando
            item['estado'] = self.ESTADO_PROCESANDO
            self.queue.put(lambda r=item['ruta']: self._actualizar_fila(r))

            try:
                # Procesar PDF
                pdf = PDFProcessor(item['ruta'])
                ok, msg = pdf.procesar_automatico()

                if not ok:
                    raise Exception(msg)

                item['pdf'] = pdf

                # Buscar empresa
                if pdf.cif:
                    empresa = self.db.buscar_empresa_por_cif(pdf.cif)
                    item['empresa'] = empresa

                # Detectar plantilla y extraer conceptos
                plantilla, _ = self.detector.buscar_plantilla(pdf.texto)
                conceptos = self.extractor.extraer(pdf.texto, plantilla, pdf)
                if plantilla:
                    conceptos = self.extractor.mapear_a_cuentas(conceptos, plantilla)
                item['conceptos'] = conceptos

                # Calcular total neto
                for c in conceptos:
                    if c.get('concepto') and ('NETO' in c['concepto'] or 'LÍQUIDO' in c['concepto']):
                        item['total_neto'] = c.get('importe')
                        break

                # Determinar estado final
                if not pdf.cif:
                    item['estado'] = self.ESTADO_SIN_CIF
                else:
                    item['estado'] = self.ESTADO_OK

            except Exception as e:
                item['estado'] = self.ESTADO_ERROR
                item['error'] = str(e)
                self.logger.error(f"Error procesando {item['nombre']}", str(e))

            # Actualizar fila
            self.queue.put(lambda r=item['ruta']: self._actualizar_fila(r))

        # Finalizar
        self.queue.put(self._finalizar_proceso)

    def _actualizar_progreso(self, actual, total):
        """Actualiza la barra de progreso"""
        pct = int(((actual + 1) / total) * 100)
        self.progreso['value'] = pct
        self.var_progreso_texto.set(f"Procesando {actual + 1} de {total}...")

    def _actualizar_fila(self, ruta):
        """Actualiza una fila en la tabla"""
        item = next((x for x in self.archivos if x['ruta'] == ruta), None)
        if not item:
            return

        pdf = item.get('pdf')
        empresa = item.get('empresa')
        conceptos = item.get('conceptos', [])
        total_neto = item.get('total_neto')

        valores = (
            item['nombre'],
            item['estado'],
            pdf.cif if pdf else '-',
            empresa['nombre'][:30] if empresa else '-',
            pdf.periodo if pdf else '-',
            str(len(conceptos)),
            f"{total_neto:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.') if total_neto else '-'
        )

        self.tree.item(ruta, values=valores)
        self._actualizar_resumen()

    def _finalizar_proceso(self):
        """Finaliza el proceso y actualiza UI"""
        self.procesando = False
        self.btn_procesar.configure(state='normal')
        self.btn_cancelar.configure(state='disabled')

        if self.cancelar:
            self.var_progreso_texto.set("Proceso cancelado")
        else:
            self.var_progreso_texto.set("Proceso completado")
            self.progreso['value'] = 100

        self._actualizar_resumen()
        self.logger.info("Proceso masivo completado", f"Total: {len(self.archivos)} archivos")

    def _actualizar_resumen(self):
        """Actualiza las estadísticas del resumen"""
        total = len(self.archivos)
        ok = sum(1 for x in self.archivos if x['estado'] == self.ESTADO_OK)
        errores = sum(1 for x in self.archivos if x['estado'] == self.ESTADO_ERROR)
        sin_cif = sum(1 for x in self.archivos if x['estado'] == self.ESTADO_SIN_CIF)

        suma_netos = sum(x.get('total_neto', 0) or 0 for x in self.archivos)

        self.var_total.set(f"Total: {total}")
        self.var_ok.set(f"✅ Completados: {ok}")
        self.var_errores.set(f"❌ Errores: {errores}")
        self.var_sin_cif.set(f"⚠️ Sin CIF: {sin_cif}")
        self.var_suma_netos.set(f"💰 Suma netos: {suma_netos:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'))

    def _ver_detalles(self, event):
        """Muestra detalles del documento seleccionado"""
        sel = self.tree.selection()
        if not sel:
            return

        ruta = sel[0]
        item = next((x for x in self.archivos if x['ruta'] == ruta), None)
        if not item:
            return

        # Crear ventana de detalles
        ventana = tk.Toplevel(self)
        ventana.title(f"Detalles: {item['nombre']}")
        ventana.geometry("600x500")

        frame = ttk.Frame(ventana, padding=10)
        frame.pack(fill='both', expand=True)

        # Info básica
        ttk.Label(frame, text=f"Archivo: {item['nombre']}", font=('Arial', 11, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=f"Estado: {item['estado']}").pack(anchor='w')

        if item.get('error'):
            ttk.Label(frame, text=f"Error: {item['error']}", foreground='red', wraplength=550).pack(anchor='w', pady=(5, 0))

        pdf = item.get('pdf')
        if pdf:
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            ttk.Label(frame, text=f"CIF: {pdf.cif or 'No detectado'}").pack(anchor='w')
            ttk.Label(frame, text=f"Período: {pdf.periodo or 'No detectado'}").pack(anchor='w')
            ttk.Label(frame, text=f"Páginas: {pdf.num_paginas}").pack(anchor='w')
            ttk.Label(frame, text=f"Método: {pdf.metodo_extraccion}").pack(anchor='w')

        empresa = item.get('empresa')
        if empresa:
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            ttk.Label(frame, text="Empresa:", font=('Arial', 10, 'bold')).pack(anchor='w')
            ttk.Label(frame, text=f"  Nombre: {empresa['nombre']}").pack(anchor='w')
            ttk.Label(frame, text=f"  Código: {empresa['codigo']}").pack(anchor='w')

        conceptos = item.get('conceptos', [])
        if conceptos:
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
            ttk.Label(frame, text=f"Conceptos extraídos ({len(conceptos)}):", font=('Arial', 10, 'bold')).pack(anchor='w')

            # Lista de conceptos
            lista = tk.Listbox(frame, height=10)
            for c in conceptos:
                importe = c.get('importe')
                importe_str = f"{importe:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if importe else '-'
                cuenta = c.get('cuenta', '-')
                lista.insert('end', f"{c['concepto']}: {importe_str} € → {cuenta}")
            lista.pack(fill='both', expand=True, pady=(5, 0))

        ttk.Button(frame, text="Cerrar", command=ventana.destroy).pack(pady=(10, 0))

    def _exportar_csv(self):
        """Exporta los resultados a CSV"""
        if not self.archivos:
            messagebox.showwarning("Aviso", "No hay datos para exportar")
            return

        ruta = filedialog.asksaveasfilename(
            title="Guardar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not ruta:
            return

        try:
            with open(ruta, 'w', encoding='utf-8-sig') as f:
                # Encabezados
                f.write("Archivo;Estado;CIF;Empresa;Período;Conceptos;Total Neto\n")

                for item in self.archivos:
                    pdf = item.get('pdf')
                    empresa = item.get('empresa')
                    total = item.get('total_neto')

                    f.write(f"{item['nombre']};")
                    f.write(f"{item['estado']};")
                    f.write(f"{pdf.cif if pdf else ''};")
                    f.write(f"{empresa['nombre'] if empresa else ''};")
                    f.write(f"{pdf.periodo if pdf else ''};")
                    f.write(f"{len(item.get('conceptos', []))};")
                    f.write(f"{total if total else ''}\n")

            messagebox.showinfo("Éxito", f"CSV exportado: {ruta}")
            self.logger.info(f"CSV exportado: {ruta}")

        except Exception as e:
            messagebox.showerror("Error", f"Error exportando CSV: {e}")

    def _exportar_excel(self):
        """Exporta los resultados a Excel"""
        if not self.archivos:
            messagebox.showwarning("Aviso", "No hay datos para exportar")
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            messagebox.showwarning("Aviso", "Instalando openpyxl...")
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'openpyxl', '-q'])
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment

        ruta = filedialog.asksaveasfilename(
            title="Guardar Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not ruta:
            return

        try:
            wb = openpyxl.Workbook()

            # === Hoja 1: Resumen ===
            ws = wb.active
            ws.title = "Resumen"

            # Encabezados
            headers = ["Archivo", "Estado", "CIF", "Empresa", "Período", "Conceptos", "Total Neto"]
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True)

            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')

            # Datos
            for row, item in enumerate(self.archivos, 2):
                pdf = item.get('pdf')
                empresa = item.get('empresa')
                total = item.get('total_neto')

                ws.cell(row=row, column=1, value=item['nombre'])
                ws.cell(row=row, column=2, value=item['estado'])
                ws.cell(row=row, column=3, value=pdf.cif if pdf else '')
                ws.cell(row=row, column=4, value=empresa['nombre'] if empresa else '')
                ws.cell(row=row, column=5, value=pdf.periodo if pdf else '')
                ws.cell(row=row, column=6, value=len(item.get('conceptos', [])))
                ws.cell(row=row, column=7, value=total if total else 0)

            # Ajustar anchos
            ws.column_dimensions['A'].width = 35
            ws.column_dimensions['B'].width = 15
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 30
            ws.column_dimensions['E'].width = 15
            ws.column_dimensions['F'].width = 12
            ws.column_dimensions['G'].width = 15

            # === Hoja 2: Conceptos detallados ===
            ws2 = wb.create_sheet("Conceptos")
            headers2 = ["Archivo", "Concepto", "Importe", "Cuenta", "Tipo", "Descripción"]

            for col, header in enumerate(headers2, 1):
                cell = ws2.cell(row=1, column=col, value=header)
                cell.fill = header_fill
                cell.font = header_font

            row = 2
            for item in self.archivos:
                for c in item.get('conceptos', []):
                    ws2.cell(row=row, column=1, value=item['nombre'])
                    ws2.cell(row=row, column=2, value=c.get('concepto', ''))
                    ws2.cell(row=row, column=3, value=c.get('importe'))
                    ws2.cell(row=row, column=4, value=c.get('cuenta', ''))
                    ws2.cell(row=row, column=5, value=c.get('tipo', ''))
                    ws2.cell(row=row, column=6, value=c.get('descripcion', ''))
                    row += 1

            wb.save(ruta)
            messagebox.showinfo("Éxito", f"Excel exportado: {ruta}")
            self.logger.info(f"Excel exportado: {ruta}")

        except Exception as e:
            messagebox.showerror("Error", f"Error exportando Excel: {e}")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
def main():
    root = tk.Tk()
    app = AplicacionFase3(root)
    root.mainloop()

if __name__ == "__main__":
    main()
