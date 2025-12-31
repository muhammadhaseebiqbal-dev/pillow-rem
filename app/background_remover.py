"""
Background Removal Module using rembg library.
Uses U2-Net deep learning model for high accuracy background removal.
"""
from rembg import remove, new_session
from PIL import Image
import io

# Create session with BiRefNet-general model for good balance of speed and accuracy
# Available models (speed vs accuracy tradeoff):
# - birefnet-general: Good accuracy, moderate size (~250MB), RECOMMENDED
# - birefnet-general-lite: Faster, smaller, slightly less accurate
# - isnet-general-use: Fast, good for products and objects
# - birefnet-massive: Best accuracy but very slow (973MB)
# - u2net: Legacy model, smaller but less accurate

# Use BiRefNet-general for good balance of speed and accuracy
SESSION = new_session("birefnet-general")


def remove_background(input_image_bytes: bytes, model: str = None) -> bytes:
    """
    Remove background from an image using the rembg library.
    
    Uses U2-Net (U-Square Net), a deep learning model 
    specifically designed for salient object detection.
    
    Args:
        input_image_bytes: Raw image bytes
        model: Optional model name (u2net, u2net_human_seg, isnet-general-use)
        
    Returns:
        bytes: PNG image with transparent background
    """
    if model:
        # Create a session with specified model
        session = new_session(model)
        output_bytes = remove(
            input_image_bytes,
            session=session,
            alpha_matting=False  # Disabled to prevent division by zero errors
        )
    else:
        # Use default session without alpha matting (more stable)
        output_bytes = remove(
            input_image_bytes,
            session=SESSION,
            alpha_matting=False  # Disabled to prevent division by zero errors
        )
    
    return output_bytes


def remove_background_simple(input_image_bytes: bytes) -> bytes:
    """
    Simple background removal without alpha matting.
    Faster but may have rougher edges.
    """
    output_bytes = remove(input_image_bytes, session=SESSION)
    return output_bytes


def remove_background_human(input_image_bytes: bytes) -> bytes:
    """
    Remove background optimized for human subjects.
    Uses u2net_human_seg model.
    """
    session = new_session("u2net_human_seg")
    output_bytes = remove(
        input_image_bytes,
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10
    )
    return output_bytes


def remove_background_with_color(input_image_bytes: bytes, bg_color: tuple = (255, 255, 255, 255)) -> bytes:
    """
    Remove background and replace with a solid color.
    
    Args:
        input_image_bytes: Raw image bytes
        bg_color: RGBA tuple for background color (default: white)
        
    Returns:
        bytes: PNG image with colored background
    """
    # First remove the background
    transparent_bytes = remove(input_image_bytes, session=SESSION)
    
    # Open the transparent image
    img = Image.open(io.BytesIO(transparent_bytes)).convert("RGBA")
    
    # Create a background with the specified color
    background = Image.new("RGBA", img.size, bg_color)
    
    # Composite the image onto the background
    composite = Image.alpha_composite(background, img)
    
    # Convert to bytes
    output_buffer = io.BytesIO()
    composite.save(output_buffer, format="PNG")
    output_buffer.seek(0)
    
    return output_buffer.getvalue()


def get_image_info(image_bytes: bytes) -> dict:
    """Get basic information about an image."""
    img = Image.open(io.BytesIO(image_bytes))
    return {
        "format": img.format,
        "mode": img.mode,
        "width": img.width,
        "height": img.height,
        "size_bytes": len(image_bytes)
    }
