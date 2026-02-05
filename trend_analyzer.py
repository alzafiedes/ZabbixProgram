"""
Trend Analyzer Module
Fetches Zabbix trends, calculates statistics with Pandas, and generates AI conclusions.
"""

import os
import csv
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
import requests

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Analyzes Zabbix item trends and generates AI conclusions."""
    
    # DeepSeek API endpoint (OpenAI compatible)
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
    
    def __init__(self, zabbix_api, deepseek_api_key: Optional[str] = None):
        """
        Initialize the trend analyzer.
        
        Args:
            zabbix_api: Authenticated pyzabbix ZabbixAPI instance
            deepseek_api_key: Optional DeepSeek API key for AI conclusions
        """
        self.api = zabbix_api
        self.deepseek_api_key = deepseek_api_key
    
    def get_trends(self, item_id: str, time_from: str, time_to: str) -> List[Dict]:
        """
        Get trend data from Zabbix API.
        
        Args:
            item_id: The item ID to get trends for
            time_from: Start time in Zabbix format (e.g., 'now-30d')
            time_to: End time in Zabbix format (e.g., 'now')
            
        Returns:
            List of trend data points
        """
        # Convert Zabbix relative time to timestamps
        from_ts, to_ts = self._convert_time_range(time_from, time_to)
        
        logger.info(f"Fetching trends for item {item_id}: {from_ts} -> {to_ts}")
        
        try:
            trends = self.api.trend.get(
                itemids=item_id,
                time_from=from_ts,
                time_till=to_ts,
                output=['itemid', 'clock', 'num', 'value_min', 'value_avg', 'value_max']
            )
            
            logger.info(f"Retrieved {len(trends)} trend data points")
            return trends
            
        except Exception as e:
            logger.error(f"Failed to get trends: {str(e)}")
            return []
    
    def _convert_time_range(self, time_from: str, time_to: str) -> Tuple[int, int]:
        """Convert Zabbix relative time format to Unix timestamps."""
        from datetime import timedelta
        now = datetime.now()
        now_ts = int(now.timestamp())
        
        def parse_time(t: str, is_to: bool = False) -> int:
            if t == "now":
                return now_ts
            elif t == "now-30d":
                return now_ts - (30 * 24 * 3600)
            elif t == "now-1M/M":
                # Previous month
                first_of_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if is_to:
                    # End of previous month (last second of last day)
                    last_of_prev = first_of_current - timedelta(seconds=1)
                    return int(last_of_prev.timestamp())
                else:
                    # Start of previous month
                    prev_month = first_of_current - timedelta(days=1)
                    first_of_prev = prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    return int(first_of_prev.timestamp())
            elif t == "now/M":
                # Start of current month
                first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return int(first_of_month.timestamp())
            else:
                # Try to parse as timestamp
                return int(t)
        
        from_ts = parse_time(time_from, is_to=False)
        to_ts = parse_time(time_to, is_to=True)
        
        logger.info(f"Time range converted: {datetime.fromtimestamp(from_ts)} -> {datetime.fromtimestamp(to_ts)}")
        
        return from_ts, to_ts
    
    def save_csv(self, trends: List[Dict], filepath: str, item_name: str, host_name: str) -> str:
        """
        Save trend data to CSV file.
        
        Args:
            trends: List of trend data points
            filepath: Output directory path
            item_name: Name of the item
            host_name: Name of the host
            
        Returns:
            Path to saved CSV file
        """
        if not trends:
            return ""
        
        # Sanitize filename
        safe_name = f"{host_name}_{item_name}".replace(" ", "_").replace("/", "_")[:50]
        csv_path = os.path.join(filepath, f"{safe_name}_trends.csv")
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'datetime', 'value_min', 'value_avg', 'value_max', 'num_samples'])
            
            for trend in trends:
                timestamp = int(trend['clock'])
                dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    timestamp,
                    dt,
                    trend.get('value_min', ''),
                    trend.get('value_avg', ''),
                    trend.get('value_max', ''),
                    trend.get('num', '')
                ])
        
        logger.info(f"Saved trend data to: {csv_path}")
        return csv_path
    
    def calculate_statistics(self, trends: List[Dict]) -> Dict[str, Any]:
        """
        Calculate statistics from trend data using Pandas.
        
        Args:
            trends: List of trend data points
            
        Returns:
            Dictionary with calculated statistics
        """
        if not trends:
            return {}
        
        # Convert to DataFrame
        df = pd.DataFrame(trends)
        
        # Convert numeric columns
        df['value_min'] = pd.to_numeric(df['value_min'], errors='coerce')
        df['value_avg'] = pd.to_numeric(df['value_avg'], errors='coerce')
        df['value_max'] = pd.to_numeric(df['value_max'], errors='coerce')
        df['clock'] = pd.to_numeric(df['clock'], errors='coerce')
        
        # Convert timestamps to datetime
        df['datetime'] = pd.to_datetime(df['clock'], unit='s')
        df['hour'] = df['datetime'].dt.hour
        df['day_name'] = df['datetime'].dt.day_name()
        
        # Calculate statistics
        stats = {
            'total_data_points': len(df),
            'avg_monthly': round(df['value_avg'].mean(), 2),
            'max_absolute': round(df['value_max'].max(), 2),
            'min_absolute': round(df['value_min'].min(), 2),
            'p95': round(df['value_avg'].quantile(0.95), 2),
            'p99': round(df['value_avg'].quantile(0.99), 2),
            'std_deviation': round(df['value_avg'].std(), 2),
        }
        
        # Peak hours (top 3 hours with highest avg values)
        hourly_avg = df.groupby('hour')['value_avg'].mean()
        peak_hours = hourly_avg.nlargest(3).index.tolist()
        stats['peak_hours'] = [f"{h:02d}:00" for h in peak_hours]
        
        # Peak days
        daily_avg = df.groupby('day_name')['value_avg'].mean()
        peak_days = daily_avg.nlargest(3).index.tolist()
        stats['peak_days'] = peak_days
        
        # Time range
        stats['period_start'] = df['datetime'].min().strftime('%Y-%m-%d')
        stats['period_end'] = df['datetime'].max().strftime('%Y-%m-%d')
        
        logger.info(f"Calculated statistics: avg={stats['avg_monthly']}, max={stats['max_absolute']}, P95={stats['p95']}")
        
        return stats
    
    def generate_summary_json(self, item_name: str, host_name: str, 
                              stats: Dict[str, Any], period: str) -> Dict:
        """
        Generate JSON summary for LLM.
        
        Args:
            item_name: Name of the item
            host_name: Name of the host
            stats: Calculated statistics
            period: Time period description
            
        Returns:
            JSON-serializable dictionary
        """
        return {
            "item_name": item_name,
            "host": host_name,
            "period": period,
            "statistics": stats
        }
    
    def get_ai_conclusion(self, summary: Dict) -> Optional[str]:
        """
        Get AI conclusion from DeepSeek API.
        
        Args:
            summary: JSON summary of statistics
            
        Returns:
            AI-generated conclusion or None if failed
        """
        if not self.deepseek_api_key:
            logger.warning("No DeepSeek API key provided")
            return None
        
        stats = summary['statistics']
        
        # Determine the month name from the period
        try:
            from datetime import datetime as dt
            period_start = dt.strptime(stats.get('period_start', ''), '%Y-%m-%d')
            month_names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                          'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            month_name = month_names[period_start.month - 1]
        except:
            month_name = "el mes anterior"
        
        # Format item name for Spanish (e.g., "CPU utilization" -> "uso de CPU")
        item_formatted = summary['item_name']
        
        # Custom descriptive prompt (no recommendations)
        prompt = f"""Actúa como un administrador de base de datos. Tu objetivo es redactar un resumen ejecutivo breve y claro.
        REGLAS DE ORO:
        NO menciones percentiles, desviaciones ni términos estadísticos avanzados.
        PROHIBIDO usar la palabra 'pico'. Usa exclusivamente 'peak' o 'peaks'.
        Usa un tono descriptivo: 'Se observa...', 'Se confirma...'.

        Datos:
        - Item: {item_formatted}
        - Host: {summary['host']}
        - Mes: {month_name}
        - Promedio: {stats.get('avg_monthly', 'N/A')}%
        - Percentil 95 (P95): {stats.get('p95', 'N/A')}%
        - Máximo registrado: {stats.get('max_absolute', 'N/A')}%
        - Horas peak: {', '.join(stats.get('peak_hours', []))}

        Estructura obligatoria: Empieza con "Se revisa el {item_formatted}", describe los hallazgos de carga normal y menciona que los picos de saturación no son sostenidos o frecuentes. Escribe en un solo párrafo fluido."""
                
        try:
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Eres un administrador de bases de datos. Responde con conclusiones descriptivas en párrafo, sin bullet points ni recomendaciones."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 250,
                "temperature": 0.3
            }
            
            logger.info("Sending request to DeepSeek API...")
            
            response = requests.post(
                self.DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            conclusion = result['choices'][0]['message']['content']
            logger.info("Received AI conclusion")
            
            return conclusion.strip()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API error: {str(e)}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse DeepSeek response: {str(e)}")
            return None
    
    def save_conclusion_txt(self, conclusion: str, stats: Dict, item_name: str, 
                            host_name: str, period_name: str, output_dir: str) -> str:
        """
        Save the AI conclusion and statistics to a .txt file.
        
        Args:
            conclusion: AI-generated conclusion text
            stats: Calculated statistics dictionary
            item_name: Name of the item
            host_name: Name of the host
            period_name: Time period description
            output_dir: Directory to save the file
            
        Returns:
            Path to the saved .txt file
        """
        # Sanitize filename
        safe_name = f"{host_name}_{item_name}".replace(" ", "_").replace("/", "_")[:50]
        txt_path = os.path.join(output_dir, f"{safe_name}_conclusion.txt")
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"ANÁLISIS DE MÉTRICAS - {item_name}\n")
            f.write(f"Host: {host_name}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("📊 ESTADÍSTICAS:\n")
            f.write(f"   • Período: {stats.get('period_start', 'N/A')} a {stats.get('period_end', 'N/A')}\n")
            f.write(f"   • Total de muestras: {stats.get('total_data_points', 'N/A')}\n")
            f.write(f"   • Promedio: {stats.get('avg_monthly', 'N/A')}%\n")
            f.write(f"   • Máximo: {stats.get('max_absolute', 'N/A')}%\n")
            f.write(f"   • Mínimo: {stats.get('min_absolute', 'N/A')}%\n")
            f.write(f"   • P95: {stats.get('p95', 'N/A')}%\n")
            f.write(f"   • P99: {stats.get('p99', 'N/A')}%\n")
            f.write(f"   • Desv. Estándar: {stats.get('std_deviation', 'N/A')}\n")
            f.write(f"   • Horas pico: {', '.join(stats.get('peak_hours', []))}\n")
            f.write(f"   • Días pico: {', '.join(stats.get('peak_days', []))}\n\n")
            
            f.write("🤖 CONCLUSIÓN IA (DeepSeek):\n")
            f.write("-" * 40 + "\n")
            f.write(conclusion + "\n")
            f.write("-" * 40 + "\n\n")
            
            f.write(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        logger.info(f"Saved conclusion to: {txt_path}")
        return txt_path
    
    def analyze_item(self, item_id: str, item_name: str, host_name: str,
                     time_from: str, time_to: str, period_name: str,
                     output_dir: str) -> Tuple[Dict, Optional[str], list]:
        """
        Complete analysis pipeline for an item.
        
        Args:
            item_id: Zabbix item ID
            item_name: Item display name
            host_name: Host display name
            time_from: Start time
            time_to: End time
            period_name: Human-readable period name
            output_dir: Directory to save CSV
            
        Returns:
            Tuple of (statistics dict, AI conclusion or None, raw trends list)
        """
        logger.info(f"Analyzing trends for: {host_name}/{item_name}")
        
        # Get trend data
        trends = self.get_trends(item_id, time_from, time_to)
        
        if not trends:
            logger.warning(f"No trend data available for item {item_id}")
            return {}, None, []
        
        # Save CSV
        csv_path = self.save_csv(trends, output_dir, item_name, host_name)
        
        # Calculate statistics
        stats = self.calculate_statistics(trends)
        
        # Generate summary
        summary = self.generate_summary_json(item_name, host_name, stats, period_name)
        
        # Get AI conclusion if API key available
        conclusion = self.get_ai_conclusion(summary)
        
        # Save conclusion to .txt file if we got one
        if conclusion:
            self.save_conclusion_txt(conclusion, stats, item_name, host_name, period_name, output_dir)
        
        return stats, conclusion, trends


