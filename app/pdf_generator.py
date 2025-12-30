"""
PDF Generator Module.
Creates high-quality PDFs from images with masonry/bento layouts.
"""
from PIL import Image
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import os
import math
from typing import List, Tuple


def create_simple_pdf(image_paths: List[str], title: str = "Images") -> bytes:
    """
    Create a simple PDF with one image per page, high quality.
    
    Args:
        image_paths: List of absolute paths to images
        title: PDF title
        
    Returns:
        bytes: PDF file content
    """
    buffer = io.BytesIO()
    page_width, page_height = A4
    
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(title)
    
    margin = 0.5 * inch
    max_width = page_width - 2 * margin
    max_height = page_height - 2 * margin
    
    for i, img_path in enumerate(image_paths):
        if not os.path.exists(img_path):
            continue
            
        try:
            img = Image.open(img_path)
            img_width, img_height = img.size
            
            # Calculate scaling to fit page while maintaining aspect ratio
            width_ratio = max_width / img_width
            height_ratio = max_height / img_height
            scale = min(width_ratio, height_ratio)
            
            new_width = img_width * scale
            new_height = img_height * scale
            
            # Center on page
            x = (page_width - new_width) / 2
            y = (page_height - new_height) / 2
            
            # Draw image
            c.drawImage(ImageReader(img), x, y, width=new_width, height=new_height, preserveAspectRatio=True)
            
            if i < len(image_paths) - 1:
                c.showPage()
                
        except Exception as e:
            print(f"Error processing image {img_path}: {e}")
            continue
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_masonry_pdf(image_paths: List[str], title: str = "Gallery", columns: int = 2) -> bytes:
    """
    Create a PDF with images in masonry/bento grid layout.
    
    Args:
        image_paths: List of absolute paths to images
        title: PDF title
        columns: Number of columns for the grid
        
    Returns:
        bytes: PDF file content
    """
    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    c.setTitle(title)
    
    margin = 0.4 * inch
    gap = 0.15 * inch
    col_width = (page_width - 2 * margin - (columns - 1) * gap) / columns
    
    # Track column heights
    col_heights = [0] * columns
    current_y = page_height - margin
    page_full_threshold = margin + 0.5 * inch
    
    # Load and process all images
    images_data = []
    for img_path in image_paths:
        if not os.path.exists(img_path):
            continue
        try:
            img = Image.open(img_path)
            # Convert RGBA to RGB for PDF compatibility if needed
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            images_data.append((img_path, img.size[0], img.size[1], img))
        except Exception as e:
            print(f"Error loading image {img_path}: {e}")
            continue
    
    if not images_data:
        c.drawString(margin, page_height - margin - 20, "No images available")
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
    
    def add_image_to_canvas(img_data, col_idx, y_pos):
        """Add single image to canvas."""
        img_path, orig_w, orig_h, img = img_data
        
        # Scale to fit column width
        scale = col_width / orig_w
        new_width = col_width
        new_height = orig_h * scale
        
        # Calculate x position
        x = margin + col_idx * (col_width + gap)
        y = y_pos - new_height
        
        try:
            c.drawImage(ImageReader(img), x, y, width=new_width, height=new_height)
        except:
            # Fallback: try with path
            c.drawImage(img_path, x, y, width=new_width, height=new_height)
        
        return new_height
    
    # Place images in masonry layout
    current_y = [page_height - margin] * columns
    
    for img_data in images_data:
        # Find shortest column
        min_col = col_heights.index(min(col_heights))
        
        img_path, orig_w, orig_h, img = img_data
        scale = col_width / orig_w
        img_height = orig_h * scale + gap
        
        # Check if image fits on current page
        if current_y[min_col] - img_height < page_full_threshold:
            # Start new page
            c.showPage()
            current_y = [page_height - margin] * columns
            col_heights = [0] * columns
            min_col = 0
        
        # Draw image
        height_used = add_image_to_canvas(img_data, min_col, current_y[min_col])
        current_y[min_col] -= height_used + gap
        col_heights[min_col] += height_used + gap
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_bento_pdf(image_paths: List[str], title: str = "Bento Gallery") -> bytes:
    """
    Create a PDF with images in an attractive bento box layout.
    Uses varying sized cells for visual interest.
    
    Args:
        image_paths: List of absolute paths to images
        title: PDF title
        
    Returns:
        bytes: PDF file content
    """
    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    c.setTitle(title)
    
    margin = 0.3 * inch
    gap = 0.1 * inch
    
    usable_width = page_width - 2 * margin
    usable_height = page_height - 2 * margin
    
    # Bento patterns (relative sizes in grid units)
    # Pattern: [(x, y, width, height), ...]
    bento_patterns = [
        # Pattern 1: Large left, two small right
        [(0, 0, 2, 2), (2, 0, 1, 1), (2, 1, 1, 1)],
        # Pattern 2: Two columns
        [(0, 0, 1, 1), (1, 0, 1, 1), (0, 1, 1, 1), (1, 1, 1, 1)],
        # Pattern 3: Large right, two small left
        [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 2, 2)],
        # Pattern 4: Row layout
        [(0, 0, 1, 2), (1, 0, 1, 2), (2, 0, 1, 2)],
    ]
    
    grid_cols = 3
    grid_rows = 2
    cell_width = (usable_width - (grid_cols - 1) * gap) / grid_cols
    cell_height = (usable_height - (grid_rows - 1) * gap) / grid_rows
    
    # Load images
    images = []
    for img_path in image_paths:
        if os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                if img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                images.append((img_path, img))
            except:
                continue
    
    if not images:
        c.drawString(margin, page_height - margin - 20, "No images available")
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
    
    img_idx = 0
    page_num = 0
    
    while img_idx < len(images):
        if page_num > 0:
            c.showPage()
        
        pattern = bento_patterns[page_num % len(bento_patterns)]
        
        for cell in pattern:
            if img_idx >= len(images):
                break
                
            gx, gy, gw, gh = cell
            
            x = margin + gx * (cell_width + gap)
            y = page_height - margin - (gy + gh) * (cell_height + gap) + gap
            w = gw * cell_width + (gw - 1) * gap
            h = gh * cell_height + (gh - 1) * gap
            
            img_path, img = images[img_idx]
            
            try:
                c.drawImage(ImageReader(img), x, y, width=w, height=h, preserveAspectRatio=True)
            except:
                c.drawImage(img_path, x, y, width=w, height=h, preserveAspectRatio=True)
            
            img_idx += 1
        
        page_num += 1
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
