"""
Test script for DeepSeek API integration and CSV analysis.
This generates sample CPU/Memory data and tests the AI conclusion feature.
"""

import csv
import json
import os
import random
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np

# DeepSeek API configuration
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "sk-e6665ffa78b2459b989614eda9639387"

def generate_sample_cpu_data(days=30, pattern="normal"):
    """Generate realistic CPU utilization data."""
    data = []
    base_time = datetime.now() - timedelta(days=days)
    
    for day in range(days):
        for hour in range(24):
            timestamp = base_time + timedelta(days=day, hours=hour)
            
            # Simulate realistic patterns
            if pattern == "normal":
                # Normal workload: higher during business hours
                if 8 <= hour <= 18:
                    base = random.uniform(35, 55)
                else:
                    base = random.uniform(10, 25)
            elif pattern == "saturated":
                # High usage
                base = random.uniform(75, 95)
            elif pattern == "underutilized":
                # Low usage
                base = random.uniform(5, 20)
            else:
                base = random.uniform(20, 60)
            
            # Add some variation
            value_avg = base + random.uniform(-5, 5)
            value_min = value_avg - random.uniform(5, 15)
            value_max = value_avg + random.uniform(10, 25)
            
            # Clamp values
            value_min = max(0, value_min)
            value_max = min(100, value_max)
            value_avg = max(value_min, min(value_max, value_avg))
            
            data.append({
                'timestamp': int(timestamp.timestamp()),
                'datetime': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'value_min': round(value_min, 2),
                'value_avg': round(value_avg, 2),
                'value_max': round(value_max, 2),
                'num_samples': 60
            })
    
    return data

def save_csv(data, filename):
    """Save data to CSV file."""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'datetime', 'value_min', 'value_avg', 'value_max', 'num_samples'])
        writer.writeheader()
        writer.writerows(data)
    print(f"✓ CSV saved: {filename}")
    return filename

def calculate_statistics(csv_file):
    """Calculate comprehensive statistics from CSV."""
    df = pd.read_csv(csv_file)
    
    # Convert to numeric
    df['value_min'] = pd.to_numeric(df['value_min'], errors='coerce')
    df['value_avg'] = pd.to_numeric(df['value_avg'], errors='coerce')
    df['value_max'] = pd.to_numeric(df['value_max'], errors='coerce')
    
    # Parse datetime
    df['datetime'] = pd.to_datetime(df['datetime'])
    df['hour'] = df['datetime'].dt.hour
    df['day_name'] = df['datetime'].dt.day_name()
    
    stats = {
        'total_samples': len(df),
        'avg_value': round(df['value_avg'].mean(), 2),
        'max_value': round(df['value_max'].max(), 2),
        'min_value': round(df['value_min'].min(), 2),
        'p95': round(df['value_avg'].quantile(0.95), 2),
        'p99': round(df['value_avg'].quantile(0.99), 2),
        'std_dev': round(df['value_avg'].std(), 2),
        'period_start': df['datetime'].min().strftime('%Y-%m-%d'),
        'period_end': df['datetime'].max().strftime('%Y-%m-%d'),
    }
    
    # Peak hours
    hourly_avg = df.groupby('hour')['value_avg'].mean()
    peak_hours = hourly_avg.nlargest(3).index.tolist()
    stats['peak_hours'] = [f"{h:02d}:00" for h in peak_hours]
    
    # Peak days
    daily_avg = df.groupby('day_name')['value_avg'].mean()
    peak_days = daily_avg.nlargest(3).index.tolist()
    stats['peak_days'] = peak_days
    
    return stats

def test_deepseek_api(item_name, host_name, stats):
    """Test DeepSeek API with the new concise prompt."""
    
    # Concise prompt: 8-10 lines max
    prompt = f"""Analiza estas métricas de Zabbix y genera una conclusión técnica breve (máximo 5 líneas):

Item: {item_name} | Host: {host_name}
Promedio: {stats['avg_value']}% | Máx: {stats['max_value']}% | P95: {stats['p95']}%
Desv.Std: {stats['std_dev']} | Período: {stats['period_start']} a {stats['period_end']}
Picos: {', '.join(stats['peak_hours'])} | Días: {', '.join(stats['peak_days'][:2])}

Indica: ¿Infrautilizado (<30%), Normal (30-70%), Saturado (>80%)? ¿Anomalías? Recomendación breve."""

    print(f"\n📤 Enviando a DeepSeek API...")
    print(f"   Prompt ({len(prompt)} chars):\n")
    print("-" * 50)
    print(prompt)
    print("-" * 50)
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Eres un analista de infraestructura IT. Responde de forma concisa y directa."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 200,
        "temperature": 0.3
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        conclusion = result['choices'][0]['message']['content'].strip()
        
        print(f"\n✅ Respuesta DeepSeek:")
        print("=" * 50)
        print(conclusion)
        print("=" * 50)
        
        return conclusion
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return None

def save_conclusion_txt(conclusion, stats, item_name, host_name, output_dir):
    """Save conclusion and stats to a .txt file."""
    safe_name = f"{host_name}_{item_name}".replace(" ", "_").replace("/", "_")[:50]
    txt_path = os.path.join(output_dir, f"{safe_name}_conclusion.txt")
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"ANÁLISIS DE MÉTRICAS - {item_name}\n")
        f.write(f"Host: {host_name}\n")
        f.write(f"{'='*60}\n\n")
        
        f.write("📊 ESTADÍSTICAS:\n")
        f.write(f"   • Período: {stats['period_start']} a {stats['period_end']}\n")
        f.write(f"   • Muestras analizadas: {stats['total_samples']}\n")
        f.write(f"   • Promedio: {stats['avg_value']}%\n")
        f.write(f"   • Máximo: {stats['max_value']}%\n")
        f.write(f"   • Mínimo: {stats['min_value']}%\n")
        f.write(f"   • P95: {stats['p95']}%\n")
        f.write(f"   • P99: {stats['p99']}%\n")
        f.write(f"   • Desv. Estándar: {stats['std_dev']}\n")
        f.write(f"   • Horas pico: {', '.join(stats['peak_hours'])}\n")
        f.write(f"   • Días pico: {', '.join(stats['peak_days'])}\n\n")
        
        f.write("🤖 CONCLUSIÓN IA (DeepSeek):\n")
        f.write("-" * 40 + "\n")
        f.write(conclusion + "\n")
        f.write("-" * 40 + "\n")
        
        f.write(f"\nGenerado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"\n📄 Conclusión guardada: {txt_path}")
    return txt_path

def main():
    """Main test function."""
    output_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("=" * 60)
    print("🧪 TEST DE INTEGRACIÓN DEEPSEEK + CSV ANALYSIS")
    print("=" * 60)
    
    # Test 1: Normal CPU pattern
    print("\n📈 Generando datos de CPU Utilization (patrón normal)...")
    cpu_data = generate_sample_cpu_data(days=30, pattern="normal")
    csv_file = save_csv(cpu_data, os.path.join(output_dir, "test_cpu_utilization_trends.csv"))
    
    print("\n📊 Calculando estadísticas...")
    stats = calculate_statistics(csv_file)
    print(f"   Estadísticas: {json.dumps(stats, indent=2)}")
    
    # Test DeepSeek
    item_name = "CPU utilization"
    host_name = "ASPEN-TEST"
    
    conclusion = test_deepseek_api(item_name, host_name, stats)
    
    if conclusion:
        save_conclusion_txt(conclusion, stats, item_name, host_name, output_dir)
        print("\n✅ TEST COMPLETADO EXITOSAMENTE")
    else:
        print("\n❌ TEST FALLÓ - No se obtuvo conclusión")

if __name__ == "__main__":
    main()
