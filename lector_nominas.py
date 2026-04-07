#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LECTOR DE NÓMINAS - FASE 1: Fundamentos y Lectura de PDFs
Autor: Claude para Jurado Asesores Tributarios - 2026

FUNCIONALIDADES FASE 1:
- Instalación automática de dependencias
- Arrastrar y soltar PDFs (Drag & Drop)
- OCR automático si no hay texto nativo
- Detección automática de CIF y período
- Interfaz intuitiva con mínima interacción
"""

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
        return self._pool[key]

    def test_conexion(self):
        """Prueba la conexión"""
        try:
            conn = self.conectar()
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            return True, cursor.fetchone()[0].split('\n')[0]
        except Exception as e:
            return False, str(e)

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
# APLICACIÓN PRINCIPAL - FASE 1
# =============================================================================
class AplicacionFase1:
    """Interfaz intuitiva con mínima interacción"""

    def __init__(self, root):
        self.root = root
        self.root.title("📄 Lector de Nóminas - Fase 1")
        self.root.geometry("1000x650")
        self.root.configure(bg='#f5f5f5')

        self.db = DatabaseManager()
        self.pdf = None
        self.imagen_tk = None
        self.queue = Queue()

        self._crear_ui()
        self._verificar_bd()
        self._procesar_cola()

    def _procesar_cola(self):
        try:
            while True:
                t = self.queue.get_nowait()
                if callable(t):
                    t()
        except Empty:
            pass
        self.root.after(100, self._procesar_cola)

    def _crear_ui(self):
        # === ESTILO ===
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        # === FRAME PRINCIPAL ===
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)

        # === PANEL IZQUIERDO: Carga de archivo ===
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

        # === PANEL DERECHO: Datos detectados ===
        frame_datos = ttk.LabelFrame(paned, text=" 2. Datos Detectados (automático) ", padding=15)
        paned.add(frame_datos, weight=1)

        # CIF
        ttk.Label(frame_datos, text="CIF Detectado:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.var_cif = tk.StringVar(value="-")
        frame_cif = ttk.Frame(frame_datos)
        frame_cif.pack(fill='x', pady=(0, 15))
        self.entry_cif = ttk.Entry(frame_cif, textvariable=self.var_cif, font=('Consolas', 14), width=20)
        self.entry_cif.pack(side='left')
        self.label_cif_status = ttk.Label(frame_cif, text="", font=('Arial', 12))
        self.label_cif_status.pack(side='left', padx=10)

        # Período
        ttk.Label(frame_datos, text="Período Detectado:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.var_periodo = tk.StringVar(value="-")
        self.entry_periodo = ttk.Entry(frame_datos, textvariable=self.var_periodo, font=('Consolas', 14), width=25)
        self.entry_periodo.pack(anchor='w', pady=(0, 15))

        # Año y Mes
        frame_fecha = ttk.Frame(frame_datos)
        frame_fecha.pack(fill='x', pady=(0, 15))

        ttk.Label(frame_fecha, text="Año:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_anno = tk.StringVar(value="-")
        ttk.Entry(frame_fecha, textvariable=self.var_anno, font=('Consolas', 12), width=6).pack(side='left', padx=(5, 20))

        ttk.Label(frame_fecha, text="Mes:", font=('Arial', 10, 'bold')).pack(side='left')
        self.var_mes = tk.StringVar(value="-")
        ttk.Entry(frame_fecha, textvariable=self.var_mes, font=('Consolas', 12), width=4).pack(side='left', padx=5)

        # Método de extracción
        ttk.Label(frame_datos, text="Método:", font=('Arial', 10, 'bold')).pack(anchor='w')
        self.var_metodo = tk.StringVar(value="-")
        ttk.Label(frame_datos, textvariable=self.var_metodo, font=('Arial', 10), foreground='gray').pack(anchor='w', pady=(0, 15))

        # Separador
        ttk.Separator(frame_datos, orient='horizontal').pack(fill='x', pady=10)

        # Texto extraído (colapsable)
        self.btn_ver_texto = ttk.Button(frame_datos, text="📝 Ver texto extraído", command=self._mostrar_texto)
        self.btn_ver_texto.pack(anchor='w')

        # === BARRA INFERIOR ===
        frame_bottom = ttk.Frame(main)
        frame_bottom.pack(fill='x', pady=(10, 0))

        self.label_bd = ttk.Label(frame_bottom, text="BD: Verificando...", foreground='gray')
        self.label_bd.pack(side='left')

        ttk.Label(frame_bottom, text="Fase 1 - Lectura de PDFs", foreground='gray').pack(side='right')

        # Variables de estado
        self.pagina_actual = 0

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
                    else:
                        self.var_estado_carga.set(f"❌ Error: {msg}")
                        messagebox.showerror("Error", msg)

                self.queue.put(actualizar)

            except Exception as e:
                self.queue.put(lambda: self.var_estado_carga.set(f"❌ Error: {e}"))
                self.queue.put(lambda: self.progreso.pack_forget())
                self.queue.put(lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=procesar, daemon=True).start()

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
    app = AplicacionFase1(root)
    root.mainloop()

if __name__ == "__main__":
    main()
