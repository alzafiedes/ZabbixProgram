"""Test script for Zabbix connection and download"""
from zabbix_client import ZabbixClient
from chart_downloader import ChartDownloader
import os

# Connect
client = ZabbixClient()
client.connect('http://192.172.1.159/zabbix/', 'Admin', 'zabbix')
print('Connected OK')

# Get templates count
templates = client.get_templates()
print(f'Found {len(templates)} templates')

# Find hosts with 'fiori' in name
all_hosts = client.api.host.get(output=['hostid', 'name'], search={'name': 'fiori'})
print(f'Hosts matching "fiori": {all_hosts}')

if all_hosts:
    host = all_hosts[0]
    print(f'Testing with host: {host["name"]}')
    
    # Get items for this host
    items = client.get_items_by_host(host['hostid'])
    print(f'Total graphable items: {len(items)}')
    
    # Find CPU items
    cpu_items = [i for i in items if 'cpu' in i['name'].lower() or 'utilization' in i['name'].lower()]
    print(f'CPU/Utilization items found: {len(cpu_items)}')
    for i in cpu_items[:5]:
        print(f'  - {i["name"]} (ID: {i["itemid"]})')
    
    if cpu_items:
        # Test download
        downloader = ChartDownloader(client.get_base_url(), client.get_session_cookie())
        time_from, time_to = ChartDownloader.calculate_time_range('last_30_days')
        
        item = cpu_items[0]
        print(f'\nDownloading chart for: {item["name"]}')
        
        image_bytes = downloader.download_chart(item['itemid'], time_from, time_to)
        if image_bytes:
            print(f'Downloaded {len(image_bytes)} bytes')
            output_dir = ChartDownloader.create_output_folder(os.getcwd())
            chart_path, legend_path = downloader.process_image(image_bytes, f'{host["name"]}_{item["name"]}', output_dir)
            print(f'Chart saved to: {chart_path}')
            print(f'Legend saved to: {legend_path}')
        else:
            print('Download failed - no image data received')
else:
    print('No hosts found matching "fiori"')

client.disconnect()
print('\nTest complete!')
