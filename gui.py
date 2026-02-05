"""
Zabbix Metrics Extractor - GUI Module
Modern CustomTkinter interface with filtering and multi-select.
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
import logging
import os
import sys
from typing import Optional, List, Dict, Any, Callable

from zabbix_client import ZabbixClient
from chart_downloader import ChartDownloader
from trend_analyzer import TrendAnalyzer
from pdf_generator import PDFReportGenerator

# Configure logging
logger = logging.getLogger(__name__)


class ConsoleHandler(logging.Handler):
    """Custom logging handler that outputs to the GUI console."""
    
    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback
        self.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    
    def emit(self, record):
        msg = self.format(record)
        self.callback(msg)


class ZabbixExtractorApp(ctk.CTk):
    """Main application window for Zabbix Metrics Extractor."""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title("Zabbix Metrics Extractor")
        self.geometry("1200x800")
        self.minsize(1100, 700)
        
        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize components
        self.zabbix_client = ZabbixClient()
        self.chart_downloader: Optional[ChartDownloader] = None
        
        # Data storage
        self.templates: List[Dict[str, Any]] = []
        self.hosts: List[Dict[str, Any]] = []
        self.all_items: Dict[str, List[Dict[str, Any]]] = {}  # host_id -> items
        
        # Selection tracking
        self.selected_hosts: Dict[str, Dict[str, Any]] = {}  # host_id -> host
        self.selected_items: Dict[str, Dict[str, Any]] = {}  # item_id -> {item, host}
        
        # Build UI
        self._create_widgets()
        self._setup_logging()
        
        # Get base path for downloads
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # === Connection Section ===
        self._create_connection_frame()
        
        # === Main Content (4 columns: Templates/Hosts, Items, Summary, Console) ===
        content_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, pady=(10, 0))
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.columnconfigure(2, weight=1)
        content_frame.columnconfigure(3, weight=1)  # Console column
        content_frame.rowconfigure(0, weight=1)
        
        # Left column: Templates & Hosts
        self._create_left_column(content_frame)
        
        # Middle column: Items
        self._create_middle_column(content_frame)
        
        # Right column: Summary & Actions
        self._create_right_column(content_frame)
        
        # Far right column: Console
        self._create_console_frame(content_frame)
    
    def _create_connection_frame(self):
        """Create connection input fields."""
        conn_frame = ctk.CTkFrame(self.main_frame)
        conn_frame.pack(fill="x", pady=(0, 5))
        
        # Title
        ctk.CTkLabel(conn_frame, text="🔗 Conexión Zabbix", 
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        # Input fields container
        inputs_frame = ctk.CTkFrame(conn_frame, fg_color="transparent")
        inputs_frame.pack(fill="x", padx=10, pady=5)
        
        # URL
        ctk.CTkLabel(inputs_frame, text="URL:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.url_entry = ctk.CTkEntry(inputs_frame, width=280, placeholder_text="http://zabbix.ejemplo.com")
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # User
        ctk.CTkLabel(inputs_frame, text="Usuario:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.user_entry = ctk.CTkEntry(inputs_frame, width=120, placeholder_text="Admin")
        self.user_entry.grid(row=0, column=3, padx=5, pady=5)
        
        # Password
        ctk.CTkLabel(inputs_frame, text="Contraseña:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.password_entry = ctk.CTkEntry(inputs_frame, width=120, show="•", placeholder_text="••••••")
        self.password_entry.grid(row=0, column=5, padx=5, pady=5)
        
        # Connect Button
        self.connect_btn = ctk.CTkButton(inputs_frame, text="Conectar", width=100, 
                                         command=self._on_connect)
        self.connect_btn.grid(row=0, column=6, padx=10, pady=5)
        
        # Status indicator
        self.status_label = ctk.CTkLabel(inputs_frame, text="● Desconectado", text_color="gray")
        self.status_label.grid(row=0, column=7, padx=5, pady=5)
        
        inputs_frame.columnconfigure(1, weight=1)
    
    def _create_left_column(self, parent):
        """Create left column with templates and hosts."""
        left_frame = ctk.CTkFrame(parent)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        # === Templates Section ===
        ctk.CTkLabel(left_frame, text="📋 Templates", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Template search
        self.template_search = ctk.CTkEntry(left_frame, placeholder_text="🔍 Buscar template...")
        self.template_search.pack(fill="x", padx=10, pady=(0, 5))
        self.template_search.bind("<KeyRelease>", self._on_template_search)
        
        # Template list
        self.template_listbox = ctk.CTkScrollableFrame(left_frame, height=120)
        self.template_listbox.pack(fill="x", padx=10, pady=(0, 10))
        self.template_buttons: Dict[str, ctk.CTkButton] = {}
        
        # === Hosts Section ===
        ctk.CTkLabel(left_frame, text="🖥️ Hosts (selección múltiple)", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Host search
        self.host_search = ctk.CTkEntry(left_frame, placeholder_text="🔍 Buscar host...")
        self.host_search.pack(fill="x", padx=10, pady=(0, 5))
        self.host_search.bind("<KeyRelease>", self._on_host_search)
        
        # Host list with checkboxes
        self.host_listbox = ctk.CTkScrollableFrame(left_frame, height=200)
        self.host_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.host_checkboxes: Dict[str, tuple] = {}  # host_id -> (checkbox, var, host)
        
        # Host action buttons
        host_btn_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        host_btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(host_btn_frame, text="Seleccionar Todos", width=120,
                      command=self._select_all_hosts).pack(side="left", padx=2)
        ctk.CTkButton(host_btn_frame, text="Deseleccionar", width=100,
                      command=self._deselect_all_hosts).pack(side="left", padx=2)
        self.load_items_btn = ctk.CTkButton(host_btn_frame, text="Cargar Items →", width=110,
                                            command=self._load_items_for_selected_hosts, state="disabled",
                                            fg_color="green", hover_color="darkgreen")
        self.load_items_btn.pack(side="right", padx=2)
    
    def _create_middle_column(self, parent):
        """Create middle column with items."""
        middle_frame = ctk.CTkFrame(parent)
        middle_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        
        # === Common Items Section (for bulk selection) ===
        ctk.CTkLabel(middle_frame, text="⚡ Items Comunes (aplicar a todos)", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Info label
        self.common_items_info = ctk.CTkLabel(middle_frame, 
            text="Seleccione hosts y click 'Cargar Items' primero",
            text_color="gray60", font=ctk.CTkFont(size=11))
        self.common_items_info.pack(anchor="w", padx=10)
        
        # Search filter for common items
        self.common_items_search = ctk.CTkEntry(middle_frame, placeholder_text="🔍 Buscar item común...")
        self.common_items_search.pack(fill="x", padx=10, pady=(5, 0))
        self.common_items_search.bind("<KeyRelease>", self._on_common_items_search)
        
        # Common items list (compact)
        self.common_items_frame = ctk.CTkScrollableFrame(middle_frame, height=100)
        self.common_items_frame.pack(fill="x", padx=10, pady=(5, 5))
        self.common_item_checkboxes: Dict[str, tuple] = {}  # item_name -> (checkbox, var)
        self.all_common_items: List[str] = []  # Store all common items for filtering
        
        # Button to add common items to all hosts
        common_btn_frame = ctk.CTkFrame(middle_frame, fg_color="transparent")
        common_btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.add_common_btn = ctk.CTkButton(common_btn_frame, 
            text="➕ Añadir a TODOS los hosts", width=200,
            command=self._add_common_items_to_all_hosts,
            fg_color="#e65100", hover_color="#bf360c", state="disabled")
        self.add_common_btn.pack(side="left")
        
        # Separator
        ctk.CTkFrame(middle_frame, height=2, fg_color="gray40").pack(fill="x", padx=10, pady=5)
        
        # === Individual Items Section ===
        ctk.CTkLabel(middle_frame, text="📊 Items Individuales", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(5, 5))
        
        # Item search
        self.item_search = ctk.CTkEntry(middle_frame, placeholder_text="🔍 Buscar item...")
        self.item_search.pack(fill="x", padx=10, pady=(0, 5))
        self.item_search.bind("<KeyRelease>", self._on_item_search)
        
        # Items list with checkboxes
        self.item_listbox = ctk.CTkScrollableFrame(middle_frame)
        self.item_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.item_checkboxes: Dict[str, tuple] = {}  # unique_id -> (checkbox, var, item, host)
        
        # Item action buttons
        item_btn_frame = ctk.CTkFrame(middle_frame, fg_color="transparent")
        item_btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(item_btn_frame, text="Sel. Todos", width=80,
                      command=self._select_all_items).pack(side="left", padx=2)
        ctk.CTkButton(item_btn_frame, text="Deseleccionar", width=90,
                      command=self._deselect_all_items).pack(side="left", padx=2)
        ctk.CTkButton(item_btn_frame, text="Añadir →", width=80,
                      command=self._add_selected_items, fg_color="green", 
                      hover_color="darkgreen").pack(side="right", padx=2)
    def _create_right_column(self, parent):
        """Create right column with summary and actions - SCROLLABLE."""
        # Outer container for grid placement
        right_container = ctk.CTkFrame(parent)
        right_container.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        right_container.rowconfigure(0, weight=1)
        right_container.columnconfigure(0, weight=1)
        
        # Scrollable inner frame for all content
        right_frame = ctk.CTkScrollableFrame(right_container)
        right_frame.grid(row=0, column=0, sticky="nsew")
        
        # === Summary Section ===
        ctk.CTkLabel(right_frame, text="📝 Resumen de Descarga", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Summary text - reduced height to fit better
        self.summary_text = ctk.CTkTextbox(right_frame, height=150, 
                                           font=ctk.CTkFont(family="Consolas", size=11))
        self.summary_text.pack(fill="x", padx=10, pady=(0, 10))
        
        # Clear summary button
        ctk.CTkButton(right_frame, text="🗑️ Limpiar Selección", width=140,
                      command=self._clear_selection).pack(pady=(0, 10))
        
        # === Time Period Section ===
        ctk.CTkLabel(right_frame, text="📅 Período de Tiempo", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        time_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        time_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.time_period_var = ctk.StringVar(value="last_30_days")
        
        ctk.CTkRadioButton(time_frame, text="Últimos 30 días", 
                           variable=self.time_period_var, value="last_30_days").pack(anchor="w", pady=2)
        ctk.CTkRadioButton(time_frame, text="Mes anterior (completo)", 
                           variable=self.time_period_var, value="previous_month").pack(anchor="w", pady=2)
        ctk.CTkRadioButton(time_frame, text="Mes actual (hasta hoy)", 
                           variable=self.time_period_var, value="current_month").pack(anchor="w", pady=2)
        
        # === AI Conclusion Section ===
        ctk.CTkLabel(right_frame, text="🤖 Análisis con IA", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(15, 5))
        
        # Checkbox to enable conclusion
        self.conclusion_var = ctk.StringVar(value="0")
        self.conclusion_checkbox = ctk.CTkCheckBox(
            right_frame, text="Generar Conclusión (DeepSeek)",
            variable=self.conclusion_var, onvalue="1", offvalue="0",
            command=self._on_conclusion_toggle)
        self.conclusion_checkbox.pack(anchor="w", padx=10, pady=2)
        
        # API Key entry (hidden by default)
        self.api_key_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        self.api_key_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.api_key_frame, text="API Key:", 
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 5))
        self.api_key_entry = ctk.CTkEntry(self.api_key_frame, show="*", placeholder_text="sk-...", width=180)
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        
        # Info label
        self.ai_info_label = ctk.CTkLabel(right_frame, 
            text="• Genera CSV + estadísticas\n• Conclusión técnica vía LLM",
            text_color="gray60", font=ctk.CTkFont(size=10), justify="left")
        self.ai_info_label.pack(anchor="w", padx=10)
        
        # PDF Report checkbox
        self.pdf_var = ctk.StringVar(value="0")
        self.pdf_checkbox = ctk.CTkCheckBox(
            right_frame, text="📄 Generar Informe PDF Ejecutivo",
            variable=self.pdf_var, onvalue="1", offvalue="0",
            command=self._on_pdf_toggle)
        self.pdf_checkbox.pack(anchor="w", padx=10, pady=(10, 5))
        
        # PDF Config button - always visible, prominent styling
        self.pdf_config_btn = ctk.CTkButton(right_frame, 
            text="📝 Configurar Reporte por Host",
            width=220, height=36, 
            fg_color="#e65100", hover_color="#bf360c",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._show_report_config_dialog)
        self.pdf_config_btn.pack(anchor="w", padx=10, pady=(10, 10))
        
        ctk.CTkLabel(right_frame, 
            text="• Incidentes, riesgos por host\n• Uptime + dimensiones globales",
            text_color="gray60", font=ctk.CTkFont(size=10), justify="left").pack(anchor="w", padx=10)
        
        # Per-host report config (incidentes, riesgos, alertas per host)
        self.host_configs = {}  # host_name -> {incidentes, riesgos, alertas}
        
        # Global config (shared across all hosts)
        self.report_config = {
            'uptime_fecha': "",
            'uptime_servidor': "",
            'uptime_bd': "",
            'dim_rendimiento': "",
            'dim_contingencia': "",
            'dim_soporte': "",
            'dim_actualizaciones': "",
            'dim_respaldos': "",
        }
        self.report_defaults = {
            'incidentes': "No se presentan incidentes de servicio.",
            'riesgos': "No se registran riesgos del servicio durante el periodo.",
            'alertas': "No se evidencian alertas que afecten la continuidad operativa.",
            'dim_rendimiento': "Sin observaciones",
            'dim_contingencia': "Sin observaciones",
            'dim_soporte': "Sin observaciones",
            'dim_actualizaciones': "Sin observaciones",
            'dim_respaldos': "Sin observaciones",
        }
        
        # === Download Section ===
        self.download_btn = ctk.CTkButton(right_frame, text="⬇️ DESCARGAR GRÁFICOS", 
                                          height=50, font=ctk.CTkFont(size=16, weight="bold"),
                                          command=self._on_download, state="disabled",
                                          fg_color="#1a73e8", hover_color="#1557b0")
        self.download_btn.pack(fill="x", padx=10, pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(right_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.progress_bar.set(0)
        
        # Initialize summary after all widgets are created
        self._update_summary()
    
    def _create_console_frame(self, parent):
        """Create console output widget in 4th column."""
        # Console container with border
        self.console_outer_frame = ctk.CTkFrame(parent)
        self.console_outer_frame.grid(row=0, column=3, sticky="nsew", padx=(5, 0))
        
        # Title with toggle buttons
        header_frame = ctk.CTkFrame(self.console_outer_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(header_frame, text="📜 Consola de Logs", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        
        # Buttons in horizontal row
        btn_frame = ctk.CTkFrame(self.console_outer_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkButton(btn_frame, text="Limpiar", width=70,
                      command=self._clear_console).pack(side="left", padx=2)
        
        # Console text widget - fills the column
        self.console_text = ctk.CTkTextbox(self.console_outer_frame, 
                                           font=ctk.CTkFont(family="Consolas", size=11))
        self.console_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    
    def _minimize_console(self):
        """Minimize console to small size."""
        self.console_text.configure(height=80)
    
    def _maximize_console(self):
        """Maximize console to larger size."""
        self.console_text.configure(height=350)
    
    def _setup_logging(self):
        """Setup logging to console widget."""
        console_handler = ConsoleHandler(self._log_to_console)
        console_handler.setLevel(logging.INFO)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
    
    def _log_to_console(self, message: str):
        """Append message to console widget (thread-safe)."""
        def append():
            self.console_text.insert("end", message + "\n")
            self.console_text.see("end")
        self.after(0, append)
    
    def _clear_console(self):
        """Clear the console text."""
        self.console_text.delete("1.0", "end")
    
    # =========== CONNECTION ===========
    
    def _on_connect(self):
        """Handle connect button click."""
        url = self.url_entry.get().strip()
        user = self.user_entry.get().strip()
        password = self.password_entry.get()
        
        if not all([url, user, password]):
            messagebox.showerror("Error", "Por favor complete todos los campos de conexión.")
            return
        
        if not url.startswith(('http://', 'https://')):
            messagebox.showerror("Error", "La URL debe comenzar con http:// o https://")
            return
        
        self.connect_btn.configure(state="disabled", text="Conectando...")
        self._log_to_console("🔄 Intentando conexión a Zabbix...")
        self._log_to_console(f"📡 URL: {url}")
        
        def connect_thread():
            error_msg = None
            try:
                self.zabbix_client.connect(url, user, password)
                
                # Create ChartDownloader with web login (not API session)
                self.chart_downloader = ChartDownloader(
                    self.zabbix_client.get_base_url(),
                    user,
                    password
                )
                
                self.templates = self.zabbix_client.get_templates()
                self.after(0, self._on_connect_success)
                
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: self._on_connect_error(msg))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def _on_connect_success(self):
        """Handle successful connection."""
        self.status_label.configure(text="● Conectado", text_color="green")
        self.connect_btn.configure(state="normal", text="Reconectar")
        
        self._populate_templates()
        self._log_to_console(f"✅ Conexión exitosa. {len(self.templates)} templates encontrados.")
    
    def _on_connect_error(self, error: str):
        """Handle connection error."""
        self.status_label.configure(text="● Error", text_color="red")
        self.connect_btn.configure(state="normal", text="Conectar")
        self._log_to_console(f"❌ Error de conexión: {error}")
        messagebox.showerror("Error de Conexión", error)
    
    # =========== TEMPLATES ===========
    
    def _populate_templates(self):
        """Populate template list."""
        for widget in self.template_listbox.winfo_children():
            widget.destroy()
        self.template_buttons.clear()
        
        for template in self.templates:
            btn = ctk.CTkButton(self.template_listbox, text=template['name'],
                               anchor="w", fg_color="transparent", 
                               text_color=("gray10", "gray90"),
                               hover_color=("gray70", "gray30"),
                               command=lambda t=template: self._on_template_selected(t))
            btn.pack(fill="x", pady=1)
            self.template_buttons[template['templateid']] = btn
    
    def _on_template_search(self, event=None):
        """Filter templates based on search."""
        search_text = self.template_search.get().lower()
        
        for template_id, btn in self.template_buttons.items():
            template = next((t for t in self.templates if t['templateid'] == template_id), None)
            if template:
                if search_text == "" or template['name'].lower().startswith(search_text):
                    btn.pack(fill="x", pady=1)
                else:
                    btn.pack_forget()
    
    def _on_template_selected(self, template: Dict[str, Any]):
        """Handle template selection."""
        # Highlight selected template
        for tid, btn in self.template_buttons.items():
            if tid == template['templateid']:
                btn.configure(fg_color=("gray70", "gray30"))
            else:
                btn.configure(fg_color="transparent")
        
        self._log_to_console(f"📋 Cargando hosts para: {template['name']}")
        
        def fetch_hosts():
            try:
                self.hosts = self.zabbix_client.get_hosts_by_template(template['templateid'])
                self.after(0, self._populate_hosts)
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: self._log_to_console(f"❌ Error: {msg}"))
        
        threading.Thread(target=fetch_hosts, daemon=True).start()
    
    # =========== HOSTS ===========
    
    def _populate_hosts(self):
        """Populate host list with checkboxes."""
        for widget in self.host_listbox.winfo_children():
            widget.destroy()
        self.host_checkboxes.clear()
        
        if not self.hosts:
            ctk.CTkLabel(self.host_listbox, text="No hay hosts vinculados").pack(pady=10)
            return
        
        for host in self.hosts:
            var = ctk.StringVar(value="0")
            cb = ctk.CTkCheckBox(self.host_listbox, text=host['name'],
                                variable=var, onvalue="1", offvalue="0",
                                command=self._on_host_checkbox_change)
            cb.pack(anchor="w", pady=1)
            self.host_checkboxes[host['hostid']] = (cb, var, host)
        
        self._log_to_console(f"✅ {len(self.hosts)} hosts encontrados.")
    
    def _on_host_search(self, event=None):
        """Filter hosts based on search."""
        search_text = self.host_search.get().lower()
        
        for host_id, (cb, var, host) in self.host_checkboxes.items():
            if search_text == "" or search_text in host['name'].lower():
                cb.pack(anchor="w", pady=1)
            else:
                cb.pack_forget()
    
    def _on_host_checkbox_change(self):
        """Handle host checkbox change."""
        selected_count = sum(1 for _, (_, var, _) in self.host_checkboxes.items() if var.get() == "1")
        if selected_count > 0:
            self.load_items_btn.configure(state="normal", text=f"Cargar Items ({selected_count}) →")
        else:
            self.load_items_btn.configure(state="disabled", text="Cargar Items →")
    
    def _select_all_hosts(self):
        """Select all visible host checkboxes."""
        for host_id, (cb, var, host) in self.host_checkboxes.items():
            if cb.winfo_ismapped():
                var.set("1")
        self._on_host_checkbox_change()
    
    def _deselect_all_hosts(self):
        """Deselect all host checkboxes."""
        for host_id, (cb, var, host) in self.host_checkboxes.items():
            var.set("0")
        self._on_host_checkbox_change()
    
    def _load_items_for_selected_hosts(self):
        """Load items for all selected hosts."""
        selected_hosts = [(host_id, host) for host_id, (_, var, host) in self.host_checkboxes.items() if var.get() == "1"]
        
        if not selected_hosts:
            return
        
        self.load_items_btn.configure(state="disabled", text="Cargando...")
        self._log_to_console(f"📊 Cargando items para {len(selected_hosts)} hosts...")
        
        def fetch_all_items():
            try:
                self.all_items.clear()
                for host_id, host in selected_hosts:
                    items = self.zabbix_client.get_items_by_host(host_id)
                    self.all_items[host_id] = items
                    self._log_to_console(f"   ✓ {host['name']}: {len(items)} items")
                
                self.after(0, lambda: self._populate_items(selected_hosts))
                self.after(0, lambda: self._populate_common_items())
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: self._log_to_console(f"❌ Error: {msg}"))
            finally:
                self.after(0, lambda: self.load_items_btn.configure(state="normal", text="Cargar Items →"))
        
        threading.Thread(target=fetch_all_items, daemon=True).start()
    
    # =========== ITEMS ===========
    
    def _populate_items(self, selected_hosts: List[tuple]):
        """Populate items list grouped by host."""
        for widget in self.item_listbox.winfo_children():
            widget.destroy()
        self.item_checkboxes.clear()
        
        total_items = 0
        for host_id, host in selected_hosts:
            items = self.all_items.get(host_id, [])
            if not items:
                continue
            
            # Host header
            header = ctk.CTkLabel(self.item_listbox, text=f"── {host['name']} ──",
                                 font=ctk.CTkFont(weight="bold"), text_color="gray60")
            header.pack(anchor="w", pady=(8, 2))
            
            for item in items:
                var = ctk.StringVar(value="0")
                cb = ctk.CTkCheckBox(self.item_listbox, text=f"{item['name']}",
                                    variable=var, onvalue="1", offvalue="0",
                                    command=self._on_item_checkbox_change)
                cb.pack(anchor="w", padx=10, pady=1)
                unique_id = f"{host_id}_{item['itemid']}"
                self.item_checkboxes[unique_id] = (cb, var, item, host)
                total_items += 1
        
        self._log_to_console(f"✅ {total_items} items disponibles para selección.")
    
    def _on_item_search(self, event=None):
        """Filter items based on search."""
        search_text = self.item_search.get().lower()
        
        for unique_id, (cb, var, item, host) in self.item_checkboxes.items():
            if search_text == "" or search_text in item['name'].lower() or search_text in item.get('key_', '').lower():
                cb.pack(anchor="w", padx=10, pady=1)
            else:
                cb.pack_forget()
    
    def _on_item_checkbox_change(self):
        """Handle item checkbox change."""
        pass  # Could show count if needed
    
    def _select_all_items(self):
        """Select all visible item checkboxes."""
        for unique_id, (cb, var, item, host) in self.item_checkboxes.items():
            if cb.winfo_ismapped():
                var.set("1")
    
    def _deselect_all_items(self):
        """Deselect all item checkboxes."""
        for unique_id, (cb, var, item, host) in self.item_checkboxes.items():
            var.set("0")
    
    def _add_selected_items(self):
        """Add selected items to download queue."""
        added = 0
        for unique_id, (cb, var, item, host) in self.item_checkboxes.items():
            if var.get() == "1":
                if unique_id not in self.selected_items:
                    self.selected_items[unique_id] = {'item': item, 'host': host}
                    added += 1
        
        if added > 0:
            self._log_to_console(f"✅ {added} items añadidos a la cola de descarga.")
            self._update_summary()
            self._deselect_all_items()
    
    # =========== COMMON ITEMS ===========
    
    def _populate_common_items(self):
        """Populate common items section with items shared across all hosts."""
        # Clear existing
        for widget in self.common_items_frame.winfo_children():
            widget.destroy()
        self.common_item_checkboxes.clear()
        
        if not self.all_items:
            self.common_items_info.configure(text="Seleccione hosts y click 'Cargar Items' primero")
            self.add_common_btn.configure(state="disabled")
            return
        
        # Find items that exist in ALL hosts (by name)
        host_item_names = []
        for host_id, items in self.all_items.items():
            item_names = {item['name'] for item in items}
            host_item_names.append(item_names)
        
        if not host_item_names:
            return
        
        # Intersection of all item names
        common_names = host_item_names[0]
        for names in host_item_names[1:]:
            common_names = common_names.intersection(names)
        
        common_names = sorted(common_names)
        
        if not common_names:
            self.common_items_info.configure(text="No hay items comunes entre los hosts seleccionados")
            self.add_common_btn.configure(state="disabled")
            return
        
        # Update info label
        host_count = len(self.all_items)
        self.common_items_info.configure(
            text=f"✨ {len(common_names)} items comunes en {host_count} hosts:")
        
        # Store all common items for search filtering
        self.all_common_items = list(common_names)
        
        # Create checkboxes for common items
        for item_name in common_names:
            var = ctk.StringVar(value="0")
            cb = ctk.CTkCheckBox(self.common_items_frame, text=item_name,
                                variable=var, onvalue="1", offvalue="0",
                                font=ctk.CTkFont(size=12))
            cb.pack(anchor="w", pady=1)
            self.common_item_checkboxes[item_name] = (cb, var)
        
        self.add_common_btn.configure(state="normal")
    
    def _add_common_items_to_all_hosts(self):
        """Add selected common items to ALL hosts."""
        # Get selected common item names
        selected_names = []
        for item_name, (cb, var) in self.common_item_checkboxes.items():
            if var.get() == "1":
                selected_names.append(item_name)
        
        if not selected_names:
            messagebox.showwarning("Aviso", "Seleccione al menos un item común.")
            return
        
        added_count = 0
        hosts_count = 0
        
        # For each host, find items with matching names and add them
        for host_id, items in self.all_items.items():
            # Get host info
            host = None
            for h_id, (_, _, h) in self.host_checkboxes.items():
                if h_id == host_id:
                    host = h
                    break
            
            if not host:
                continue
            
            hosts_count += 1
            
            for item in items:
                if item['name'] in selected_names:
                    unique_id = f"{host_id}_{item['itemid']}"
                    if unique_id not in self.selected_items:
                        self.selected_items[unique_id] = {'item': item, 'host': host}
                        added_count += 1
        
        if added_count > 0:
            self._log_to_console(f"⚡ {added_count} items añadidos ({len(selected_names)} tipos x {hosts_count} hosts)")
            self._update_summary()
            
            # Deselect common checkboxes
            for item_name, (cb, var) in self.common_item_checkboxes.items():
                var.set("0")
        else:
            self._log_to_console("⚠️ No se añadieron items (ya estaban en la cola)")
    
    def _on_common_items_search(self, event=None):
        """Filter common items based on search text (LIKE '%text%' matching)."""
        search_text = self.common_items_search.get().lower().strip()
        
        for item_name, (cb, var) in self.common_item_checkboxes.items():
            # Match if search text is anywhere in item name (case insensitive)
            if search_text == "" or search_text in item_name.lower():
                cb.pack(anchor="w", pady=1)
            else:
                cb.pack_forget()
    
    # =========== SUMMARY ===========
    
    def _update_summary(self):
        """Update the download summary."""
        self.summary_text.delete("1.0", "end")
        
        if not self.selected_items:
            self.summary_text.insert("end", "No hay items seleccionados.\n\n")
            self.summary_text.insert("end", "Para añadir items:\n")
            self.summary_text.insert("end", "1. Seleccione un template\n")
            self.summary_text.insert("end", "2. Marque uno o más hosts\n")
            self.summary_text.insert("end", "3. Click 'Cargar Items'\n")
            self.summary_text.insert("end", "4. Seleccione items y click 'Añadir'\n")
            if hasattr(self, 'download_btn'):
                self.download_btn.configure(state="disabled")
            return
        
        # Group by host
        hosts_items: Dict[str, List] = {}
        for unique_id, data in self.selected_items.items():
            host_name = data['host']['name']
            if host_name not in hosts_items:
                hosts_items[host_name] = []
            hosts_items[host_name].append(data['item']['name'])
        
        # Write summary
        self.summary_text.insert("end", f"📊 TOTAL: {len(self.selected_items)} gráficos\n")
        self.summary_text.insert("end", f"🖥️ HOSTS: {len(hosts_items)}\n")
        self.summary_text.insert("end", "─" * 30 + "\n\n")
        
        for host_name, items in hosts_items.items():
            self.summary_text.insert("end", f"▶ {host_name}\n")
            for item_name in items:
                self.summary_text.insert("end", f"   • {item_name}\n")
            self.summary_text.insert("end", "\n")
        
        if hasattr(self, 'download_btn'):
            self.download_btn.configure(state="normal")
    
    def _clear_selection(self):
        """Clear all selected items."""
        self.selected_items.clear()
        self._update_summary()
        self._log_to_console("🗑️ Selección limpiada.")
    
    def _on_conclusion_toggle(self):
        """Handle conclusion checkbox toggle."""
        enabled = self.conclusion_var.get() == "1"
        if enabled:
            self.ai_info_label.configure(text="✅ Análisis habilitado\n• CSV + estadísticas + IA")
        else:
            self.ai_info_label.configure(text="• Genera CSV + estadísticas\n• Conclusión técnica vía LLM")
    
    def _on_pdf_toggle(self):
        """Handle PDF checkbox toggle - show/hide config button."""
        enabled = self.pdf_var.get() == "1"
        if enabled:
            self.pdf_config_btn.pack(anchor="w", padx=10, pady=(0, 5))
        else:
            self.pdf_config_btn.pack_forget()
    
    def _show_report_config_dialog(self):
        """Show dialog to configure report manual inputs with per-host support."""
        # Get unique hosts from selected items
        hosts_in_selection = set()
        for unique_id, data in self.selected_items.items():
            hosts_in_selection.add(data['host']['name'])
        
        if not hosts_in_selection:
            messagebox.showwarning("Aviso", "Primero seleccione items para descargar.")
            return
        
        hosts_list = sorted(hosts_in_selection)
        
        # Create dialog window - large and spacious
        dialog = ctk.CTkToplevel(self)
        dialog.title("📝 Configurar Reporte por Host")
        dialog.geometry("900x800")
        dialog.transient(self)
        dialog.grab_set()
        
        # Center it
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 900) // 2
        y = self.winfo_y() + (self.winfo_height() - 800) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Store current host entries
        self._current_host_entries = {}
        
        # === Host Selector ===
        host_selector_frame = ctk.CTkFrame(dialog)
        host_selector_frame.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(host_selector_frame, text="🖥️ Host:", 
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(10, 10))
        
        self._selected_host_var = ctk.StringVar(value=hosts_list[0])
        host_dropdown = ctk.CTkComboBox(host_selector_frame, values=hosts_list, 
                                         variable=self._selected_host_var, width=400,
                                         command=self._on_host_config_change)
        host_dropdown.pack(side="left", padx=10)
        
        ctk.CTkLabel(host_selector_frame, text=f"({len(hosts_list)} hosts)", 
                     text_color="gray60").pack(side="left")
        
        # Scrollable content
        scroll_frame = ctk.CTkScrollableFrame(dialog)
        scroll_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        # === Per-Host: Incidentes, Riesgos, Alertas ===
        ctk.CTkLabel(scroll_frame, text="📋 Texto Operativo (por Host)", 
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        ctk.CTkLabel(scroll_frame, text="Incidentes del Servicio:").pack(anchor="w")
        self._host_incidentes = ctk.CTkTextbox(scroll_frame, height=50)
        self._host_incidentes.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(scroll_frame, text="Riesgos del Servicio:").pack(anchor="w")
        self._host_riesgos = ctk.CTkTextbox(scroll_frame, height=50)
        self._host_riesgos.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(scroll_frame, text="Incidentes de Alerta:").pack(anchor="w")
        self._host_alertas = ctk.CTkTextbox(scroll_frame, height=50)
        self._host_alertas.pack(fill="x", pady=(0, 10))
        
        # Load current host data
        self._load_host_config(hosts_list[0])
        
        # === Global: Uptime ===
        ctk.CTkLabel(scroll_frame, text="⏱️ Uptime (Global)", 
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(15, 10))
        
        uptime_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        uptime_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(uptime_frame, text="Fecha Último Inicio:").grid(row=0, column=0, sticky="w", pady=2)
        self._uptime_fecha = ctk.CTkEntry(uptime_frame, placeholder_text="ej: 01/02/2026", width=200)
        self._uptime_fecha.grid(row=0, column=1, padx=10, pady=2)
        self._uptime_fecha.insert(0, self.report_config.get('uptime_fecha', ''))
        
        ctk.CTkLabel(uptime_frame, text="Uptime Servidor:").grid(row=1, column=0, sticky="w", pady=2)
        self._uptime_server = ctk.CTkEntry(uptime_frame, placeholder_text="ej: 99.95%", width=200)
        self._uptime_server.grid(row=1, column=1, padx=10, pady=2)
        self._uptime_server.insert(0, self.report_config.get('uptime_servidor', ''))
        
        ctk.CTkLabel(uptime_frame, text="Uptime BD:").grid(row=2, column=0, sticky="w", pady=2)
        self._uptime_bd = ctk.CTkEntry(uptime_frame, placeholder_text="ej: 99.99%", width=200)
        self._uptime_bd.grid(row=2, column=1, padx=10, pady=2)
        self._uptime_bd.insert(0, self.report_config.get('uptime_bd', ''))
        
        # === Global: Dimensiones ===
        ctk.CTkLabel(scroll_frame, text="📊 Dimensiones (Global)", 
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(15, 10))
        
        dim_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        dim_frame.pack(fill="x", pady=(0, 10))
        
        dims = [
            ("Rendimiento:", "dim_rendimiento"),
            ("Contingencia:", "dim_contingencia"),
            ("Soporte:", "dim_soporte"),
            ("Actualizaciones:", "dim_actualizaciones"),
            ("Respaldos:", "dim_respaldos"),
        ]
        
        self._dim_entries = {}
        for i, (label, key) in enumerate(dims):
            ctk.CTkLabel(dim_frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            entry = ctk.CTkEntry(dim_frame, placeholder_text="Sin observaciones", width=400)
            entry.grid(row=i, column=1, padx=10, pady=2)
            entry.insert(0, self.report_config.get(key, ''))
            self._dim_entries[key] = entry
        
        ctk.CTkLabel(scroll_frame, text="💡 Dejar vacío = valores por defecto | Cambiar host guarda automáticamente",
                     text_color="gray60", font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(10, 5))
        
        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=10)
        
        def save_all_and_close():
            # Save current host
            self._save_current_host_config()
            # Save global config
            self.report_config['uptime_fecha'] = self._uptime_fecha.get().strip()
            self.report_config['uptime_servidor'] = self._uptime_server.get().strip()
            self.report_config['uptime_bd'] = self._uptime_bd.get().strip()
            for key, entry in self._dim_entries.items():
                self.report_config[key] = entry.get().strip()
            
            self._log_to_console(f"✅ Config guardada para {len(self.host_configs)} hosts")
            dialog.destroy()
        
        ctk.CTkButton(btn_frame, text="💾 Guardar y Cerrar", fg_color="green", hover_color="darkgreen",
                      command=save_all_and_close, width=140).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="Cancelar", fg_color="gray50",
                      command=dialog.destroy, width=100).pack(side="right", padx=5)
    
    def _on_host_config_change(self, new_host: str):
        """Handle host dropdown change - save current and load new."""
        self._save_current_host_config()
        self._load_host_config(new_host)
    
    def _save_current_host_config(self):
        """Save current host's text fields to host_configs."""
        host = self._selected_host_var.get()
        self.host_configs[host] = {
            'incidentes': self._host_incidentes.get("1.0", "end-1c").strip(),
            'riesgos': self._host_riesgos.get("1.0", "end-1c").strip(),
            'alertas': self._host_alertas.get("1.0", "end-1c").strip(),
        }
    
    def _load_host_config(self, host_name: str):
        """Load host config into text fields."""
        config = self.host_configs.get(host_name, {})
        
        self._host_incidentes.delete("1.0", "end")
        self._host_incidentes.insert("1.0", config.get('incidentes', ''))
        
        self._host_riesgos.delete("1.0", "end")
        self._host_riesgos.insert("1.0", config.get('riesgos', ''))
        
        self._host_alertas.delete("1.0", "end")
        self._host_alertas.insert("1.0", config.get('alertas', ''))
    
    # =========== DOWNLOAD ===========
    
    def _on_download(self):
        """Handle download button click."""
        if not self.selected_items:
            messagebox.showwarning("Aviso", "No hay items seleccionados para descargar.")
            return
        
        if not self.chart_downloader:
            messagebox.showerror("Error", "No hay conexión activa con Zabbix.")
            return
        
        self.download_btn.configure(state="disabled", text="Descargando...")
        self.progress_bar.set(0)
        
        period_type = self.time_period_var.get()
        
        def download_thread():
            try:
                # Check if AI conclusion is enabled
                generate_conclusion = self.conclusion_var.get() == "1"
                api_key = self.api_key_entry.get().strip() if generate_conclusion else None
                trend_analyzer = None
                
                # Check if PDF report is enabled
                generate_pdf = self.pdf_var.get() == "1"
                pdf_generator = None
                
                if generate_conclusion:
                    self._log_to_console("🤖 Análisis con IA habilitado")
                    trend_analyzer = TrendAnalyzer(self.zabbix_client.api, api_key)
                
                output_dir = ChartDownloader.create_output_folder(self.base_path)
                self._log_to_console(f"📁 Carpeta de salida: {output_dir}")
                
                # Initialize PDF generator if enabled
                if generate_pdf:
                    self._log_to_console("📄 Generación de PDF habilitada")
                    pdf_generator = PDFReportGenerator(output_dir)
                    pdf_generator.set_report_config(self.report_config, self.report_defaults)
                    pdf_generator.set_host_configs(self.host_configs)
                
                time_from, time_to = ChartDownloader.calculate_time_range(period_type)
                period_names = {
                    'last_30_days': 'Últimos 30 días',
                    'previous_month': 'Mes anterior',
                    'current_month': 'Mes actual'
                }
                self._log_to_console(f"📅 Período: {period_names.get(period_type, period_type)}")
                self._log_to_console(f"⏱️ Rango: {time_from} → {time_to}")
                self._log_to_console(f"🔗 Base URL: {self.chart_downloader.base_url}")
                self._log_to_console(f"🔑 Web login: {'✓ OK' if self.chart_downloader.logged_in else '✗ Failed'}")
                self._log_to_console("─" * 50)
                
                total = len(self.selected_items)
                success_count = 0
                
                for i, (unique_id, data) in enumerate(self.selected_items.items()):
                    item = data['item']
                    host = data['host']
                    
                    self._log_to_console(f"")
                    self._log_to_console(f"⬇️ [{i+1}/{total}] {host['name']}: {item['name']}")
                    self._log_to_console(f"   Item ID: {item['itemid']}")
                    
                    image_bytes = self.chart_downloader.download_chart(
                        item['itemid'], time_from, time_to
                    )
                    
                    if image_bytes:
                        self._log_to_console(f"   📥 Recibidos: {len(image_bytes)} bytes")
                        # Use host_itemname for filename
                        filename = f"{host['name']}_{item['name']}"
                        chart_path, legend_path = self.chart_downloader.process_image(
                            image_bytes, filename, output_dir
                        )
                        self._log_to_console(f"   ✅ Gráfico: {os.path.basename(chart_path)}")
                        self._log_to_console(f"   ✅ Leyenda: {os.path.basename(legend_path)}")
                        success_count += 1
                        
                        # AI Analysis if enabled (also needed for PDF)
                        if generate_conclusion or generate_pdf:
                            self._log_to_console(f"   🤖 Analizando tendencias...")
                            try:
                                # Ensure trend_analyzer exists (create if only PDF is enabled)
                                if not trend_analyzer:
                                    trend_analyzer = TrendAnalyzer(self.zabbix_client.api, api_key)
                                
                                stats, conclusion, trends = trend_analyzer.analyze_item(
                                    item['itemid'], item['name'], host['name'],
                                    time_from, time_to, period_names.get(period_type, period_type),
                                    output_dir
                                )
                                
                                if stats:
                                    self._log_to_console(f"   📊 Estadísticas:")
                                    self._log_to_console(f"      Promedio: {stats.get('avg_monthly', 'N/A')}")
                                    self._log_to_console(f"      Máximo: {stats.get('max_absolute', 'N/A')}")
                                    self._log_to_console(f"      P95: {stats.get('p95', 'N/A')}")
                                    self._log_to_console(f"      Picos: {', '.join(stats.get('peak_hours', []))}")
                                
                                if conclusion:
                                    self._log_to_console(f"   💡 Conclusión IA:")
                                    for line in conclusion.split('\n'):
                                        if line.strip():
                                            self._log_to_console(f"      {line.strip()}")
                                elif api_key:
                                    self._log_to_console(f"   ⚠️ No se pudo obtener conclusión de DeepSeek")
                                
                                # Add data to PDF generator
                                if pdf_generator and trends:
                                    pdf_generator.add_item_data(
                                        host['name'], item['name'], trends, stats, conclusion
                                    )
                                    
                            except Exception as ae:
                                self._log_to_console(f"   ⚠️ Error en análisis: {str(ae)}")
                    else:
                        self._log_to_console(f"   ⚠️ No se pudo descargar - Sin datos de imagen")
                    
                    progress = (i + 1) / total
                    self.after(0, lambda p=progress: self.progress_bar.set(p))
                
                self._log_to_console("")
                self._log_to_console("─" * 50)
                self._log_to_console(f"🎉 Completado: {success_count}/{total} gráficos guardados")
                self._log_to_console(f"📂 Ubicación: {output_dir}")
                
                # Generate PDF report if enabled
                if pdf_generator and pdf_generator.items_data:
                    self._log_to_console("")
                    self._log_to_console("📄 Generando informe PDF ejecutivo...")
                    try:
                        pdf_path = pdf_generator.generate_report("informe_ejecutivo")
                        if pdf_path:
                            self._log_to_console(f"✅ PDF generado: {os.path.basename(pdf_path)}")
                        else:
                            self._log_to_console("⚠️ No se pudo generar el PDF")
                    except Exception as pe:
                        self._log_to_console(f"⚠️ Error generando PDF: {str(pe)}")
                
                if success_count > 0:
                    pdf_msg = "\n📄 Informe PDF generado" if (pdf_generator and pdf_generator.items_data) else ""
                    self.after(0, lambda: messagebox.showinfo("Completado", 
                        f"Descarga completada.\n{success_count}/{total} gráficos guardados en:\n{output_dir}{pdf_msg}"))
                else:
                    self.after(0, lambda: messagebox.showwarning("Advertencia",
                        f"No se pudieron descargar gráficos.\nRevise la consola para más detalles."))
                
            except Exception as e:
                import traceback
                error_msg = str(e)
                self._log_to_console(f"❌ Error: {error_msg}")
                self._log_to_console(f"❌ Traceback: {traceback.format_exc()}")
                self.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            
            finally:
                self.after(0, lambda: self.download_btn.configure(state="normal", text="⬇️ DESCARGAR GRÁFICOS"))
        
        threading.Thread(target=download_thread, daemon=True).start()


def main():
    """Application entry point."""
    app = ZabbixExtractorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
