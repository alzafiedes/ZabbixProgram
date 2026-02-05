"""
Chart Downloader Module
Handles downloading charts from Zabbix and processing images with Pillow.
"""

import os
import re
import requests
from datetime import datetime, timedelta
from typing import Tuple, Optional
from PIL import Image
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class ChartDownloader:
    """Downloads and processes chart images from Zabbix."""
    
    # Standard Zabbix chart dimensions
    CHART_HEIGHT_RATIO = 0.75  # Chart takes ~75% of image height
    
    def __init__(self, base_url: str, username: str, password: str):
        """
        Initialize the chart downloader with web session login.
        
        Args:
            base_url: Zabbix server base URL
            username: Username for web login
            password: Password for web login
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
        
        # Perform web login
        self._web_login()
    
    def _web_login(self) -> bool:
        """
        Perform web login to get session cookie for chart access.
        
        Returns:
            True if login successful
        """
        login_url = f"{self.base_url}/index.php"
        login_payload = {
            'name': self.username,
            'password': self.password,
            'enter': 'Sign in'
        }
        
        logger.info(f"Web login to: {login_url}")
        
        try:
            response = self.session.post(login_url, data=login_payload, timeout=30)
            
            # Check if login was successful (should redirect or show dashboard)
            if response.status_code == 200:
                # Check cookies
                cookies = self.session.cookies.get_dict()
                logger.info(f"Cookies received: {list(cookies.keys())}")
                
                # Check if we got a session cookie
                if any(key.startswith('zbx_session') for key in cookies):
                    self.logged_in = True
                    logger.info("✓ Web login successful")
                    return True
                
                # Some Zabbix versions might not set cookie but login might work
                if 'sign in' not in response.text.lower() and 'login' not in response.url.lower():
                    self.logged_in = True
                    logger.info("✓ Web login appears successful (no login page in response)")
                    return True
                    
            logger.error(f"Web login failed. Status: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Web login error: {str(e)}")
            return False
    
    @staticmethod
    def calculate_time_range(period_type: str) -> Tuple[str, str]:
        """
        Get Zabbix relative time range strings.
        
        Args:
            period_type: One of 'last_30_days', 'previous_month', 'current_month'
            
        Returns:
            Tuple of (from_string, to_string) in Zabbix format
        """
        if period_type == 'last_30_days':
            # Last 30 days
            time_from = "now-30d"
            time_to = "now"
            
        elif period_type == 'previous_month':
            # Previous month (complete)
            # now-1M/M means: go back 1 month, then round to month start/end
            time_from = "now-1M/M"
            time_to = "now-1M/M"
            
        elif period_type == 'current_month':
            # Current month (from start to now)
            # now/M means: round to start of current month
            time_from = "now/M"
            time_to = "now"
            
        else:
            raise ValueError(f"Tipo de período desconocido: {period_type}")
        
        return time_from, time_to
    
    def download_chart(self, item_id: str, time_from: str, time_to: str, 
                       width: int = 900, height: int = 200) -> Optional[bytes]:
        """
        Download a chart image from Zabbix.
        
        Args:
            item_id: The item ID to generate chart for
            time_from: Start time in Zabbix relative format (e.g., 'now-30d')
            time_to: End time in Zabbix relative format (e.g., 'now')
            width: Chart width in pixels
            height: Chart height in pixels
            
        Returns:
            Image bytes or None if download failed
        """
        # Try chart.php first (Zabbix 5.x+)
        result = self._try_download_chart(
            f"{self.base_url}/chart.php",
            item_id, time_from, time_to, width, height
        )
        
        if result:
            return result
        
        # Try chart2.php (legacy)
        logger.info("Trying chart2.php endpoint...")
        result = self._try_download_chart(
            f"{self.base_url}/chart2.php",
            item_id, time_from, time_to, width, height
        )
        
        return result
    
    def _try_download_chart(self, base_chart_url: str, item_id: str, 
                            time_from: str, time_to: str,
                            width: int, height: int) -> Optional[bytes]:
        """Try to download chart from a specific endpoint."""
        chart_url = (
            f"{base_chart_url}?"
            f"itemids[]={item_id}&"
            f"from={time_from}&"
            f"to={time_to}&"
            f"width={width}&"
            f"height={height}&"
            f"profileIdx=web.item.graph"
        )
        
        logger.info(f"Requesting: {chart_url}")
        
        try:
            response = self.session.get(chart_url, timeout=30)
            
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            logger.info(f"Content-Length: {len(response.content)} bytes")
            
            if response.status_code != 200:
                logger.error(f"HTTP Error: {response.status_code}")
                # Log first 500 chars of response for debugging
                logger.error(f"Response preview: {response.text[:500]}")
                return None
            
            content_type = response.headers.get('Content-Type', '')
            
            if 'image' in content_type:
                logger.info(f"✓ Downloaded image ({len(response.content)} bytes)")
                return response.content
            
            # Check if response contains login page (session expired)
            if 'login' in response.text.lower() or 'sign in' in response.text.lower():
                logger.error("Session expired - received login page")
                return None
            
            # Log unexpected content
            logger.error(f"Unexpected content type: {content_type}")
            logger.error(f"Response preview: {response.text[:300]}")
            return None
            
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return None
    
    def process_image(self, image_bytes: bytes, item_name: str, 
                      output_dir: str) -> Tuple[str, str]:
        """
        Process and crop the chart image into two parts.
        
        Args:
            image_bytes: Raw image data
            item_name: Name of the item (for filename)
            output_dir: Directory to save processed images
            
        Returns:
            Tuple of (chart_path, legend_path)
        """
        # Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)
        
        # Load image
        image = Image.open(BytesIO(image_bytes))
        width, height = image.size
        
        logger.info(f"Processing image: {width}x{height} pixels")
        
        # Calculate split point (chart is top ~75%, legend is bottom ~25%)
        split_point = int(height * self.CHART_HEIGHT_RATIO)
        
        # Crop chart (top portion)
        chart_image = image.crop((0, 0, width, split_point))
        
        # Crop legend (bottom portion)
        legend_image = image.crop((0, split_point, width, height))
        
        # Sanitize filename
        safe_name = self._sanitize_filename(item_name)
        
        # Save images
        chart_path = os.path.join(output_dir, f"{safe_name}_grafico_superior.png")
        legend_path = os.path.join(output_dir, f"{safe_name}_datos_leyenda.png")
        
        chart_image.save(chart_path, 'PNG')
        legend_image.save(legend_path, 'PNG')
        
        logger.info(f"Saved: {chart_path}")
        logger.info(f"Saved: {legend_path}")
        
        return chart_path, legend_path
    
    def save_full_image(self, image_bytes: bytes, item_name: str, 
                        output_dir: str) -> str:
        """
        Save the full chart image without cropping.
        
        Args:
            image_bytes: Raw image data
            item_name: Name of the item (for filename)
            output_dir: Directory to save image
            
        Returns:
            Path to saved image
        """
        os.makedirs(output_dir, exist_ok=True)
        
        safe_name = self._sanitize_filename(item_name)
        full_path = os.path.join(output_dir, f"{safe_name}_completo.png")
        
        image = Image.open(BytesIO(image_bytes))
        image.save(full_path, 'PNG')
        
        logger.info(f"Saved full image: {full_path}")
        return full_path
    
    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        Sanitize a string for use as a filename.
        
        Args:
            name: Original name string
            
        Returns:
            Sanitized filename-safe string
        """
        # Remove or replace invalid characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Replace spaces and multiple underscores
        safe_name = re.sub(r'\s+', '_', safe_name)
        safe_name = re.sub(r'_+', '_', safe_name)
        # Limit length
        return safe_name[:100].strip('_')
    
    @staticmethod
    def create_output_folder(base_path: str) -> str:
        """
        Create a timestamped output folder.
        
        Args:
            base_path: Base directory for downloads
            
        Returns:
            Path to created folder
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(base_path, "descargas", timestamp)
        os.makedirs(output_path, exist_ok=True)
        logger.info(f"Created output folder: {output_path}")
        return output_path
