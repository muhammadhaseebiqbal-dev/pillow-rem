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
    padding: int = 60,
    depth: int = 25,
    shadow_offset: int = 20
) -> bytes:
    """
    Create a realistic pillow mockup that follows the shape of the design.
    
    Args:
        design_bytes: PNG image bytes (with transparent background)
        pillow_color: RGB tuple for pillow fabric color
        padding: Padding around the design (pillow border)
        depth: 3D depth effect intensity
        shadow_offset: Drop shadow offset
        
    Returns:
        bytes: PNG image of pillow mockup
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
    
    # Calculate pillow size with padding
    pillow_width = design_width + padding * 2
    pillow_height = design_height + padding * 2
    
    # Canvas size (extra space for shadow and depth)
    canvas_width = pillow_width + shadow_offset + depth + 40
    canvas_height = pillow_height + shadow_offset + depth + 40
    
    # Create canvas with transparent background
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
    
    # Create pillow shape based on design alpha
    pillow_shape = create_pillow_shape_from_design(
        alpha, pillow_width, pillow_height, padding, pillow_color
    )
    
    # Add 3D depth effect
    pillow_with_depth = add_depth_effect(pillow_shape, pillow_color, depth)
    
    # Add fabric texture
    pillow_textured = add_fabric_texture(pillow_with_depth, pillow_color)
    
    # Create drop shadow
    shadow = create_drop_shadow(pillow_textured, shadow_offset, opacity=100)
    
    # Position everything on canvas
    base_x = 20
    base_y = 20
    
    # Paste shadow first
    canvas.paste(shadow, (base_x + shadow_offset, base_y + shadow_offset), shadow)
    
    # Paste pillow with depth
    canvas.paste(pillow_textured, (base_x, base_y), pillow_textured)
    
    # Apply design with fabric effect
    design_with_effect = apply_print_effect(design)
    
    # Position design centered on pillow
    design_x = base_x + padding
    design_y = base_y + padding
    canvas.paste(design_with_effect, (design_x, design_y), design_with_effect)
    
    # Add highlight overlay for 3D effect
    canvas = add_highlight_overlay(canvas, pillow_width, pillow_height, base_x, base_y)
    
    # Add seam/stitch effect around the edge
    canvas = add_seam_effect(canvas, pillow_shape, base_x, base_y, padding)
    
    # Convert to bytes
    output = io.BytesIO()
    canvas.save(output, format="PNG", quality=95)
    output.seek(0)
    
    return output.getvalue()


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
    
    # Always use white for the 3D mesh/depth layers
    white_color = (255, 255, 255)
    
    # Create darker shade for the sides using white
    dark_factor = 0.7
    side_color = tuple(int(c * dark_factor) for c in white_color) + (255,)
    
    # Draw depth layers from back to front using white
    for i in range(depth, 0, -1):
        # Calculate shade (darker at back, lighter toward front)
        shade = 0.6 + (0.4 * (depth - i) / depth)
        layer_color = tuple(int(c * shade) for c in white_color) + (255,)
        
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


def create_colored_pillow_mockup(design_bytes: bytes, color: str = "white") -> bytes:
    """Create pillow mockup with specified color name."""
    colors = {
        "white": (255, 255, 255),
        "cream": (255, 253, 240),
        "beige": (245, 235, 220),
        "gray": (200, 200, 200),
        "black": (50, 50, 50),
        "navy": (35, 50, 85),
        "blush": (255, 228, 225),
        "sage": (198, 215, 198),
    }
    
    pillow_color = colors.get(color.lower(), (255, 255, 255))
    
    return create_pillow_mockup(
        design_bytes,
        pillow_color=pillow_color,
        padding=50,
        depth=20,
        shadow_offset=15
    )


def create_square_pillow_mockup(design_bytes: bytes) -> bytes:
    """Standard square pillow mockup."""
    return create_colored_pillow_mockup(design_bytes, "white")
