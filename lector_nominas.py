#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LECTOR DE NÓMINAS - FASE 2: Integración con Geyce
Versión: 2.0.0
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
"""

VERSION = "2.0.0"
VERSION_FECHA = "2026-04-07"

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import re
import threading
import io
from datetime import datetime
from queue import Queue, Empty

# =============================================================================
# INSTALACIÓN AUTOMÁTICA DE DEPENDENCIAS
# =============================================================================
def instalar_dependencias():
    """Instala las dependencias necesarias si no están disponibles"""
    dependencias = {
        'fitz': 'PyMuPDF',
        'pytesseract': 'pytesseract',
        'PIL': 'Pillow',
        'pyodbc': 'pyodbc'
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
    """Procesa archivos PDF con extracción inteligente de datos"""

    def __init__(self, ruta):
        self.ruta = ruta
        self.nombre = os.path.basename(ruta)
        self.doc = fitz.open(ruta)
        self.texto = ""
        self.num_paginas = len(self.doc)
        self.cif = None
        self.periodo = None
        self.anno = None
        self.mes = None
        self.tiene_texto_nativo = False

    def cerrar(self):
        if self.doc:
            self.doc.close()
            self.doc = None

    def procesar_automatico(self, callback_progreso=None):
        """
        Proceso automático completo:
        1. Intenta extraer texto nativo
        2. Si no hay texto, ejecuta OCR
        3. Detecta CIF y período

        Returns: True si el proceso fue exitoso
        """
        # Paso 1: Extraer texto nativo
        self.texto = "\n".join([p.get_text() for p in self.doc])
        self.tiene_texto_nativo = bool(self.texto.strip())

        # Paso 2: Si no hay texto, usar OCR
        if not self.tiene_texto_nativo:
            if not TESSERACT_OK:
                return False, "PDF sin texto y Tesseract no disponible"

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

        # Paso 3: Detectar datos
        self._detectar_cif()
        self._detectar_periodo()

        return True, "OK"

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
# APLICACIÓN PRINCIPAL - FASE 2
# =============================================================================
class AplicacionFase2:
    """Interfaz con integración Geyce y sistema de logging"""

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

        self.db = DatabaseManager()
        self.logger = Logger()
        self.pdf = None
        self.empresa_actual = None
        self.imagen_tk = None
        self.queue = Queue()

        self._crear_ui()
        self._verificar_bd()
        self._procesar_cola()
        self._actualizar_contador_errores()

        self.logger.info("Aplicación iniciada", f"Versión {VERSION}")

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

        # === BARRA INFERIOR ===
        frame_bottom = ttk.Frame(main)
        frame_bottom.pack(fill='x', pady=(10, 0))

        self.label_bd = ttk.Label(frame_bottom, text="BD: Verificando...", foreground='gray')
        self.label_bd.pack(side='left')

        ttk.Label(frame_bottom, text=f"Fase 2 - Integración Geyce | v{VERSION}", foreground='gray').pack(side='right')

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
                        self.var_metodo.set("Texto nativo" if self.pdf.tiene_texto_nativo else "OCR (imagen)")

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

# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
def main():
    root = tk.Tk()
    app = AplicacionFase2(root)
    root.mainloop()

if __name__ == "__main__":
    main()
