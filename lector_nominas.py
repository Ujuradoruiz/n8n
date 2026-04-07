#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LECTOR DE NÓMINAS - FASE 3.5: OpenDataLoader + Sistema Inteligente
Versión: 3.5.0
Fecha: 2026-04-07
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

FUNCIONALIDADES FASE 3.5 (NUEVA):
- Integración con OpenDataLoader PDF (precisión 0.907)
- Extracción avanzada de tablas con bounding boxes
- OCR mejorado con 80+ idiomas
- Detección de estructura basada en coordenadas
- Fallback a PyMuPDF si OpenDataLoader no disponible
"""

VERSION = "3.5.0"
VERSION_FECHA = "2026-04-07"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
        'opendataloader_pdf': 'opendataloader-pdf'
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
from PIL import Image, ImageTk

# OpenDataLoader - con fallback si no está disponible
try:
    import opendataloader_pdf
    OPENDATALOADER_OK = True
except ImportError:
    OPENDATALOADER_OK = False
    print("⚠️ OpenDataLoader no disponible. Usando PyMuPDF como fallback.")

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

        # Estado
        self.pdf = None
        self.empresa_actual = None
        self.plantilla_actual = None
        self.conceptos_extraidos = []
        self.imagen_tk = None
        self.queue = Queue()

        self._crear_ui()
        self._verificar_bd()
        self._procesar_cola()
        self._actualizar_contador_errores()

        self.logger.info("Aplicación iniciada", f"Versión {VERSION} - Fase 3")

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

        ttk.Button(frame_log, text="📋 Ver Log", command=self._abrir_log).pack(side='left')

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

        ttk.Label(frame_bottom, text=f"Fase 3 - Sistema Inteligente | v{VERSION}", foreground='gray').pack(side='right')

        # Variables de estado
        self.pagina_actual = 0

    def _abrir_log(self):
        """Abre la ventana de log"""
        VentanaLog(self.root)

    def _verificar_bd(self):
        """Verifica conexión a BD en segundo plano"""
        def verificar():
            ok, msg = self.db.test_conexion()
            if ok:
                self.queue.put(lambda: self.label_bd.configure(text="✅ BD Conectada", foreground='green'))
            else:
                self.queue.put(lambda: self.label_bd.configure(text="❌ BD Error", foreground='red'))
        threading.Thread(target=verificar, daemon=True).start()

    def _cargar_pdf(self, ruta):
        """Carga y procesa un PDF automáticamente"""
        # Cerrar anterior
        if self.pdf:
            self.pdf.cerrar()

        self.var_estado_carga.set(f"⏳ Procesando: {os.path.basename(ruta)}")
        self.progreso.pack(pady=5)
        self.progreso['value'] = 0
        self.logger.info(f"Cargando PDF: {os.path.basename(ruta)}")

        def procesar():
            try:
                # Crear procesador
                self.pdf = PDFProcessor(ruta)

                def callback(actual, total, tipo):
                    pct = int((actual / total) * 100)
                    self.queue.put(lambda p=pct: self.progreso.configure(value=p))
                    self.queue.put(lambda a=actual, t=total: self.var_estado_carga.set(f"⏳ {tipo}: Página {a}/{t}"))

                # Procesar
                ok, msg = self.pdf.procesar_automatico(callback)

                def actualizar():
                    self.progreso.pack_forget()

                    if ok:
                        # Mostrar datos
                        self.var_cif.set(self.pdf.cif or "(No detectado)")
                        self.label_cif_status.configure(
                            text="✅" if self.pdf.cif else "⚠️",
                            foreground='green' if self.pdf.cif else 'orange'
                        )
                        self.var_periodo.set(self.pdf.periodo or "(No detectado)")
                        self.var_anno.set(str(self.pdf.anno))
                        self.var_mes.set(str(self.pdf.mes))
                        # Mostrar método de extracción
                        if self.pdf.metodo_extraccion == 'opendataloader':
                            metodo = f"OpenDataLoader (Tablas: {len(self.pdf.tablas)})"
                        elif self.pdf.tiene_texto_nativo:
                            metodo = "PyMuPDF (Texto nativo)"
                        else:
                            metodo = "PyMuPDF + OCR"
                        self.var_metodo.set(metodo)

                        # Mostrar primera página
                        self.pagina_actual = 0
                        self._mostrar_pagina()
                        self.var_pag.set(f"1 / {self.pdf.num_paginas}")

                        self.var_estado_carga.set(f"✅ {self.pdf.nombre} - Procesado correctamente")
                        self.logger.info(f"PDF procesado: {self.pdf.nombre}",
                                        f"CIF: {self.pdf.cif}, Período: {self.pdf.periodo}")

                        # Buscar empresa automáticamente si hay CIF
                        if self.pdf.cif:
                            self._buscar_empresa()

                        # Detectar plantilla automáticamente
                        self._detectar_plantilla()
                    else:
                        self.var_estado_carga.set(f"❌ Error: {msg}")
                        self.logger.error(f"Error procesando PDF: {self.pdf.nombre}", msg)
                        messagebox.showerror("Error", msg)

                self.queue.put(actualizar)

            except Exception as e:
                self.logger.error(f"Excepción al cargar PDF", str(e))
                self.queue.put(lambda: self.var_estado_carga.set(f"❌ Error: {e}"))
                self.queue.put(lambda: self.progreso.pack_forget())
                self.queue.put(lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=procesar, daemon=True).start()

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
# PUNTO DE ENTRADA
# =============================================================================
def main():
    root = tk.Tk()
    app = AplicacionFase3(root)
    root.mainloop()

if __name__ == "__main__":
    main()
