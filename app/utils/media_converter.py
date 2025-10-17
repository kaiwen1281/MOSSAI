"""Media format conversion utilities"""
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional
import subprocess

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


class MediaConverter:
    """Utility class for media format conversions"""
    
    @staticmethod
    async def download_file(url: str, save_path: str) -> str:
        """
        Download file from URL
        
        Args:
            url: File URL
            save_path: Local path to save file
            
        Returns:
            Path to downloaded file
        """
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Downloaded file from {url} to {save_path}")
                return save_path
                
        except Exception as e:
            logger.error(f"Error downloading file from {url}: {str(e)}")
            raise
    
    @staticmethod
    def gif_to_mp4_pillow(gif_path: str, mp4_path: str) -> str:
        """
        Convert GIF to MP4 using Pillow (extracts frames)
        This is a fallback method that extracts frames and uses ffmpeg
        
        Args:
            gif_path: Path to GIF file
            mp4_path: Path to output MP4 file
            
        Returns:
            Path to converted MP4 file
        """
        try:
            # Open GIF
            gif = Image.open(gif_path)
            
            # Create temporary directory for frames
            with tempfile.TemporaryDirectory() as temp_dir:
                frame_paths = []
                frame_idx = 0
                
                # Extract all frames
                try:
                    while True:
                        frame_path = os.path.join(temp_dir, f"frame_{frame_idx:04d}.png")
                        gif.save(frame_path, 'PNG')
                        frame_paths.append(frame_path)
                        frame_idx += 1
                        gif.seek(gif.tell() + 1)
                except EOFError:
                    pass  # End of frames
                
                logger.info(f"Extracted {len(frame_paths)} frames from GIF")
                
                # Get frame duration (in milliseconds)
                frame_duration = gif.info.get('duration', 100) / 1000.0  # Convert to seconds
                fps = 1.0 / frame_duration if frame_duration > 0 else 10
                
                # Use ffmpeg to create MP4 from frames
                frame_pattern = os.path.join(temp_dir, "frame_%04d.png")
                
                cmd = [
                    'ffmpeg',
                    '-y',  # Overwrite output
                    '-framerate', str(fps),
                    '-i', frame_pattern,
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart',
                    mp4_path
                ]
                
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
                
                logger.info(f"Converted GIF to MP4: {mp4_path}")
                return mp4_path
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            raise
        except Exception as e:
            logger.error(f"Error converting GIF to MP4 (Pillow): {str(e)}")
            raise
    
    @staticmethod
    def gif_to_mp4_ffmpeg(gif_path: str, mp4_path: str) -> str:
        """
        Convert GIF to MP4 using ffmpeg directly (preferred method)
        
        Args:
            gif_path: Path to GIF file
            mp4_path: Path to output MP4 file
            
        Returns:
            Path to converted MP4 file
        """
        try:
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output
                '-i', gif_path,
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # Ensure even dimensions
                mp4_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            logger.info(f"Converted GIF to MP4 using ffmpeg: {mp4_path}")
            return mp4_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            raise
        except Exception as e:
            logger.error(f"Error converting GIF to MP4 (ffmpeg): {str(e)}")
            raise
    
    @staticmethod
    async def convert_gif_to_mp4(
        gif_url: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        Download GIF and convert to MP4
        
        Args:
            gif_url: GIF file URL
            output_path: Optional output path (if None, uses temp file)
            
        Returns:
            Path to converted MP4 file
        """
        try:
            # Create temp file for GIF
            with tempfile.NamedTemporaryFile(suffix='.gif', delete=False) as gif_temp:
                gif_path = gif_temp.name
            
            # Download GIF
            await MediaConverter.download_file(gif_url, gif_path)
            
            # Create output path if not provided
            if output_path is None:
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as mp4_temp:
                    output_path = mp4_temp.name
            
            try:
                # Try ffmpeg first (preferred)
                result = MediaConverter.gif_to_mp4_ffmpeg(gif_path, output_path)
            except Exception as e:
                logger.warning(f"FFmpeg conversion failed, trying Pillow method: {str(e)}")
                # Fallback to Pillow method
                result = MediaConverter.gif_to_mp4_pillow(gif_path, output_path)
            
            # Clean up temp GIF file
            os.unlink(gif_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in GIF to MP4 conversion: {str(e)}")
            raise
    
    @staticmethod
    def check_ffmpeg_available() -> bool:
        """
        Check if ffmpeg is available in the system
        
        Returns:
            True if ffmpeg is available, False otherwise
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


# Global instance
media_converter = MediaConverter()


