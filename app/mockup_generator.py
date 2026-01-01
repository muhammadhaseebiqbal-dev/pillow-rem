"""
Pillow/Cushion Mockup Generator.
Creates realistic pillow mockups that match the design shape with 3D depth effect.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
import io
import math


def create_pillow_mockup(
    design_bytes: bytes,
    pillow_color: tuple = (245, 245, 245),
    padding: int = 20,
    depth: int = 0,
    shadow_offset: int = 15,
    stroke_width: int = 3,
    stroke_color: tuple = (100, 100, 100)
) -> bytes:
    """
    Create a mockup with just the design and a stroke around its edges.
    
    Args:
        design_bytes: PNG image bytes (with transparent background)
        pillow_color: RGB tuple (not used, kept for compatibility)
        padding: Padding around the design
        depth: Not used, kept for compatibility
        shadow_offset: Drop shadow offset
        stroke_width: Width of the stroke around the design
        stroke_color: RGB tuple for stroke color
        
    Returns:
        bytes: PNG image of mockup with stroke
    """
    # Load the design image
    design = Image.open(io.BytesIO(design_bytes)).convert("RGBA")
    
    # Get the alpha channel to determine shape
    alpha = design.split()[3]
    
    # Get bounding box of the design
    bbox = alpha.getbbox()
    if bbox:
        # Crop to content
        design = design.crop(bbox)
        alpha = design.split()[3]
    
    design_width, design_height = design.size
    
    # Canvas size (extra space for stroke, shadow and padding)
    canvas_width = design_width + padding * 2 + shadow_offset + stroke_width * 2
    canvas_height = design_height + padding * 2 + shadow_offset + stroke_width * 2
    
    # Create canvas with transparent background
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
    
    # Position for design
    base_x = padding + stroke_width
    base_y = padding + stroke_width
    
    # Create stroke around the design
    stroke_layer = create_stroke_around_design(alpha, stroke_width, stroke_color)
    
    # Create drop shadow from the design itself
    shadow = create_drop_shadow(design, shadow_offset, opacity=80)
    
    # Paste shadow first
    canvas.paste(shadow, (base_x + shadow_offset, base_y + shadow_offset), shadow)
    
    # Paste stroke layer (slightly offset to be behind design)
    stroke_x = base_x - stroke_width
    stroke_y = base_y - stroke_width
    canvas.paste(stroke_layer, (stroke_x, stroke_y), stroke_layer)
    
    # Paste the design on top
    canvas.paste(design, (base_x, base_y), design)
    
    # Convert to bytes
    output = io.BytesIO()
    canvas.save(output, format="PNG", quality=95)
    output.seek(0)
    
    return output.getvalue()


def create_stroke_around_design(alpha: Image.Image, stroke_width: int, 
                                 stroke_color: tuple) -> Image.Image:
    """Create a stroke/outline around the design based on its alpha channel."""
    # Expand the alpha to create stroke area
    expanded = alpha.copy()
    for _ in range(stroke_width):
        expanded = expanded.filter(ImageFilter.MaxFilter(3))
    
    # Create stroke by subtracting original from expanded
    stroke_alpha = Image.new("L", alpha.size, 0)
    
    for x in range(alpha.width):
        for y in range(alpha.height):
            exp_val = expanded.getpixel((x, y))
            orig_val = alpha.getpixel((x, y))
            # Stroke is where expanded exists but original doesn't
            if exp_val > 50 and orig_val < 200:
                stroke_alpha.putpixel((x, y), exp_val)
    
    # Smooth the stroke edges slightly
    stroke_alpha = stroke_alpha.filter(ImageFilter.GaussianBlur(0.5))
    
    # Create the stroke image with the new size (accounting for expansion)
    new_width = alpha.width + stroke_width * 2
    new_height = alpha.height + stroke_width * 2
    
    stroke_image = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
    colored_stroke = Image.new("RGBA", alpha.size, stroke_color + (255,))
    
    # Paste stroke at center
    stroke_image.paste(colored_stroke, (stroke_width, stroke_width), stroke_alpha)
    
    return stroke_image


def create_pillow_shape_from_design(alpha: Image.Image, width: int, height: int, 
                                     padding: int, color: tuple) -> Image.Image:
    """Create pillow shape that follows the design outline with padding."""
    
    # Create base shape with rounded corners
    pillow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(pillow)
    
    # Calculate corner radius based on size
    corner_radius = min(width, height) // 8
    
    # Draw rounded rectangle as base
    draw.rounded_rectangle(
        [(0, 0), (width - 1, height - 1)],
        radius=corner_radius,
        fill=color + (255,)
    )
    
    # If design has transparency, create a shape that follows it
    # Expand the alpha slightly for the pillow border
    if alpha.getbbox():
        # Resize alpha to match pillow size (with padding consideration)
        alpha_resized = alpha.resize(
            (width - padding * 2, height - padding * 2),
            Image.Resampling.LANCZOS
        )
        
        # Create expanded mask
        expanded = expand_alpha_mask(alpha_resized, padding // 2)
        
        # Create a new pillow shape based on expanded design
        design_shape = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        design_draw = ImageDraw.Draw(design_shape)
        
        # Fill with pillow color where design exists (with padding)
        paste_x = (width - expanded.width) // 2
        paste_y = (height - expanded.height) // 2
        
        # Create colored version
        colored = Image.new("RGBA", expanded.size, color + (255,))
        design_shape.paste(colored, (paste_x, paste_y), expanded)
        
        # Blend with rounded rectangle base for smooth edges
        pillow = Image.alpha_composite(pillow, design_shape)
    
    return pillow


def expand_alpha_mask(alpha: Image.Image, expand_by: int) -> Image.Image:
    """Expand an alpha mask by a certain number of pixels."""
    # Convert to mode 'L' if needed
    if alpha.mode != 'L':
        alpha = alpha.convert('L')
    
    # Use max filter to expand white areas
    for _ in range(expand_by):
        alpha = alpha.filter(ImageFilter.MaxFilter(3))
    
    # Smooth the edges
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=2))
    
    return alpha


def add_depth_effect(img: Image.Image, color: tuple, depth: int) -> Image.Image:
    """Add 3D depth/thickness effect to the pillow."""
    width, height = img.size
    
    # Create new image with extra space for depth
    result = Image.new("RGBA", (width + depth, height + depth), (0, 0, 0, 0))
    
    # Create darker shade for the sides
    dark_factor = 0.7
    side_color = tuple(int(c * dark_factor) for c in color) + (255,)
    
    # Draw depth layers from back to front
    for i in range(depth, 0, -1):
        # Calculate shade (darker at back, lighter toward front)
        shade = 0.6 + (0.4 * (depth - i) / depth)
        layer_color = tuple(int(c * shade) for c in color) + (255,)
        
        # Create a layer
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        
        # Get alpha from original
        if img.mode == "RGBA":
            alpha = img.split()[3]
        else:
            alpha = Image.new("L", img.size, 255)
        
        # Color this layer
        colored = Image.new("RGBA", img.size, layer_color)
        layer.paste(colored, mask=alpha)
        
        # Paste at offset position
        result.paste(layer, (i, i), layer)
    
    # Paste the main image on top
    result.paste(img, (0, 0), img)
    
    return result


def add_fabric_texture(img: Image.Image, color: tuple) -> Image.Image:
    """Add subtle fabric-like texture to the pillow."""
    # Slightly reduce saturation for fabric look
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        rgb = Image.merge("RGB", (r, g, b))
        
        # Add subtle noise for texture
        enhancer = ImageEnhance.Contrast(rgb)
        rgb = enhancer.enhance(0.95)
        
        # Merge back with alpha
        r, g, b = rgb.split()
        img = Image.merge("RGBA", (r, g, b, a))
    
    return img


def create_drop_shadow(img: Image.Image, offset: int, opacity: int = 80) -> Image.Image:
    """Create a soft drop shadow from the image."""
    # Get alpha channel
    if img.mode == "RGBA":
        alpha = img.split()[3]
    else:
        alpha = Image.new("L", img.size, 255)
    
    # Create shadow
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow_color = Image.new("RGBA", img.size, (0, 0, 0, opacity))
    shadow.paste(shadow_color, mask=alpha)
    
    # Blur the shadow
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=15))
    
    return shadow


def apply_print_effect(design: Image.Image) -> Image.Image:
    """Apply effect to make design look printed on fabric."""
    if design.mode != "RGBA":
        design = design.convert("RGBA")
    
    # Slightly desaturate
    r, g, b, a = design.split()
    rgb = Image.merge("RGB", (r, g, b))
    
    # Reduce contrast slightly (fabric doesn't show pure colors)
    enhancer = ImageEnhance.Contrast(rgb)
    rgb = enhancer.enhance(0.92)
    
    # Slight brightness reduction
    enhancer = ImageEnhance.Brightness(rgb)
    rgb = enhancer.enhance(0.95)
    
    r, g, b = rgb.split()
    return Image.merge("RGBA", (r, g, b, a))


def add_highlight_overlay(canvas: Image.Image, pillow_w: int, pillow_h: int,
                          offset_x: int, offset_y: int) -> Image.Image:
    """Add subtle highlight for 3D puffy effect."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Create gradient highlight in top-left area
    center_x = offset_x + pillow_w // 3
    center_y = offset_y + pillow_h // 3
    max_radius = min(pillow_w, pillow_h) // 2
    
    for r in range(max_radius, 0, -5):
        alpha = int(30 * (1 - r / max_radius))
        draw.ellipse(
            [center_x - r, center_y - r, center_x + r, center_y + r],
            fill=(255, 255, 255, alpha)
        )
    
    return Image.alpha_composite(canvas, overlay)


def add_seam_effect(canvas: Image.Image, pillow_shape: Image.Image,
                    offset_x: int, offset_y: int, margin: int) -> Image.Image:
    """Add stitching/seam effect around the pillow edge following the shape."""
    # Get alpha from pillow shape to trace the edge
    if pillow_shape.mode == "RGBA":
        alpha = pillow_shape.split()[3]
    else:
        return canvas
    
    # Create edge detection by finding the outline
    # Dilate slightly then subtract original to get edge
    dilated = alpha.filter(ImageFilter.MaxFilter(5))
    edge = Image.new("L", alpha.size, 0)
    
    # Create edge by XOR-like operation
    for x in range(alpha.width):
        for y in range(alpha.height):
            d_val = dilated.getpixel((x, y))
            a_val = alpha.getpixel((x, y))
            if d_val > 128 and a_val < 200:
                edge.putpixel((x, y), 150)
    
    # Blur slightly for softer edge
    edge = edge.filter(ImageFilter.GaussianBlur(1))
    
    # Create colored edge overlay
    edge_color = Image.new("RGBA", pillow_shape.size, (180, 180, 180, 0))
    edge_overlay = Image.new("RGBA", pillow_shape.size, (160, 160, 160, 180))
    edge_color.paste(edge_overlay, mask=edge)
    
    # Paste onto canvas
    canvas.paste(edge_color, (offset_x, offset_y), edge_color)
    
    return canvas


def create_colored_pillow_mockup(design_bytes: bytes, color: str = "gray") -> bytes:
    """Create mockup with specified stroke color name."""
    # Stroke colors for different styles
    stroke_colors = {
        "white": (255, 255, 255),
        "cream": (200, 190, 170),
        "beige": (180, 160, 140),
        "gray": (100, 100, 100),
        "black": (30, 30, 30),
        "navy": (35, 50, 85),
        "blush": (200, 150, 150),
        "sage": (120, 150, 120),
    }
    
    stroke_color = stroke_colors.get(color.lower(), (100, 100, 100))
    
    return create_pillow_mockup(
        design_bytes,
        padding=25,
        shadow_offset=12,
        stroke_width=4,
        stroke_color=stroke_color
    )


def create_square_pillow_mockup(design_bytes: bytes) -> bytes:
    """Standard square pillow mockup."""
    return create_colored_pillow_mockup(design_bytes, "white")


def create_masonry_mockup(design_bytes: bytes, tiles: int = 6) -> bytes:
    """
    Create a masonry/grid style mockup showing the design in multiple tiles.
    
    Args:
        design_bytes: PNG image bytes (with transparent background)
        tiles: Number of tiles to show (4, 6, or 9)
        
    Returns:
        bytes: PNG image of masonry layout mockup
    """
    # Load the design image
    design = Image.open(io.BytesIO(design_bytes)).convert("RGBA")
    
    # Get the alpha channel and crop to content
    alpha = design.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        design = design.crop(bbox)
    
    # Convert to RGB with white background for display
    if design.mode == 'RGBA':
        background = Image.new('RGB', design.size, (255, 255, 255))
        background.paste(design, mask=design.split()[3])
        design = background
    
    # Determine grid layout
    if tiles == 4:
        cols, rows = 2, 2
    elif tiles == 9:
        cols, rows = 3, 3
    else:  # default 6
        cols, rows = 3, 2
    
    # Calculate tile sizes
    tile_gap = 20
    tile_padding = 30
    max_tile_size = 400
    
    # Scale design to fit tile
    design_aspect = design.width / design.height
    if design_aspect > 1:  # Wider
        tile_w = min(max_tile_size, design.width)
        tile_h = int(tile_w / design_aspect)
    else:  # Taller or square
        tile_h = min(max_tile_size, design.height)
        tile_w = int(tile_h * design_aspect)
    
    design_resized = design.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
    
    # Calculate canvas size
    canvas_w = cols * tile_w + (cols - 1) * tile_gap + 2 * tile_padding
    canvas_h = rows * tile_h + (rows - 1) * tile_gap + 2 * tile_padding
    
    # Create canvas with white background
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    
    # Place tiles in grid
    for row in range(rows):
        for col in range(cols):
            x = tile_padding + col * (tile_w + tile_gap)
            y = tile_padding + row * (tile_h + tile_gap)
            
            # Add subtle shadow
            shadow_offset = 8
            shadow = Image.new("RGB", (tile_w, tile_h), (200, 200, 200))
            canvas.paste(shadow, (x + shadow_offset, y + shadow_offset))
            
            # Paste the design tile
            canvas.paste(design_resized, (x, y))
    
    # Add subtle overall shadow/depth
    enhancer = ImageEnhance.Contrast(canvas)
    canvas = enhancer.enhance(1.1)
    
    # Convert to bytes
    output = io.BytesIO()
    canvas.save(output, format="PNG", quality=95)
    output.seek(0)
    
    return output.getvalue()
