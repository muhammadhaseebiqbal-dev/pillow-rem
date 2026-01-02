"""
3D Pillow Mockup Generator with White Sewn Border.
Creates 3D pillow with textured front/back and WHITE side seam bulging OUTWARD.
"""
import io
import numpy as np
from PIL import Image
import trimesh
import cv2


def create_3d_pillow_mockup(
    design_bytes: bytes,
    pillow_thickness: float = 0.08,
    pillow_puffiness: float = 0.0,
    border_width: float = 0.03,
    scale: float = 1.0
) -> bytes:
    """
    Create a 3D standee/cutout style mockup with white border.
    Flat design that follows the image contour with slight depth.
    """
    # Load the design image
    design = Image.open(io.BytesIO(design_bytes)).convert("RGBA")
    alpha = design.split()[3]
    
    # Get bounding box and crop
    bbox = alpha.getbbox()
    if bbox:
        pad = 5
        bbox = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(design.width, bbox[2] + pad),
            min(design.height, bbox[3] + pad)
        )
        design = design.crop(bbox)
        alpha = design.split()[3]
    
    width, height = design.size
    aspect = width / height
    
    alpha_np = np.array(alpha)
    contour_points = extract_contour(alpha_np)
    
    if contour_points is None or len(contour_points) < 3:
        raise ValueError("Could not extract valid contour from image")
    
    # Normalize contour
    # Store original pixels for exact UV mapping before normalization
    contour_pixels = contour_points.copy()
    contour = normalize_contour(contour_points, width, height, aspect)
    n_points = len(contour)
    center = np.mean(contour, axis=0)
    
    # Prepare texture - exact image with white strip at bottom for seam
    texture_image, height_ratio = prepare_texture_with_strip(design)
    
    # ============ CREATE SINGLE UNIFIED MESH ============
    # Flat cutout style with white border edges
    
    all_vertices = []
    all_faces = []
    all_uvs = []
    vertex_offset = 0
    
    # UV Mapping Helper Logic
    def get_uv_from_pixels(px, py):
        u = max(0.0, min(1.0, px / width))
        v_raw = py / height
        # Invert V: 1.0 is Top of image, (1.0 - height_ratio) is Bottom of image
        v = 1.0 - (v_raw * height_ratio)
        return [u, v]
    
    # ============ 1. ADD FRONT FACE (FLAT) ============
    for i in range(n_points):
        x, y = contour[i]
        all_vertices.append([x, y, 0])
        
        # UV coordinates (from original pixel position)
        px, py = contour_pixels[i]
        all_uvs.append(get_uv_from_pixels(px, py))
    
    front_center_idx = len(all_vertices)
    all_vertices.append([center[0], center[1], 0])
    # Center pixel approx
    all_uvs.append([0.5, 1.0 - (0.5 * height_ratio)])
    
    for i in range(n_points):
        next_i = (i + 1) % n_points
        all_faces.append([front_center_idx, i, next_i])
    
    vertex_offset = len(all_vertices)
    
    # ============ 2. ADD BACK FACE (FLAT) ============
    for i in range(n_points):
        x, y = contour[i]
        all_vertices.append([x, y, -pillow_thickness])
        
        # UVs (Match front exactly)
        px, py = contour_pixels[i]
        all_uvs.append(get_uv_from_pixels(px, py))
    
    back_center_idx = len(all_vertices)
    all_vertices.append([center[0], center[1], -pillow_thickness])
    all_uvs.append([0.5, 1.0 - (0.5 * height_ratio)])
    
    for i in range(n_points):
        next_i = (i + 1) % n_points
        all_faces.append([back_center_idx, vertex_offset + next_i, vertex_offset + i])
    
    vertex_offset = len(all_vertices)
    
    # ============ 3. ADD WHITE BORDER EDGE ============
    seam_subdivisions = 3
    
    for i in range(n_points):
        x, y = contour[i]
        
        z_front = 0
        z_back = -pillow_thickness
        
        # Calculate outward normal for white border
        to_point_x = x - center[0]
        to_point_y = y - center[1]
        length = np.sqrt(to_point_x**2 + to_point_y**2)
        if length > 0:
            nx = to_point_x / length
            ny = to_point_y / length
        else:
            nx, ny = 1, 0
        
        for j in range(seam_subdivisions + 1):
            t = j / seam_subdivisions
            z = z_front + (z_back - z_front) * t
            # Slight outward bulge for white border visibility
            bulge = border_width * np.sin(t * np.pi) * 0.5
            
            sx = x + nx * bulge
            sy = y + ny * bulge
            
            all_vertices.append([sx, sy, z])
            # White seam UV area
            all_uvs.append([0.5, 0.01])
    
    # Create border edge faces
    verts_per_column = seam_subdivisions + 1
    for i in range(n_points):
        next_i = (i + 1) % n_points
        col_curr = vertex_offset + i * verts_per_column
        col_next = vertex_offset + next_i * verts_per_column
        
        for j in range(seam_subdivisions):
            v0 = col_curr + j
            v1 = col_curr + j + 1
            v2 = col_next + j + 1
            v3 = col_next + j
            
            all_faces.append([v0, v1, v2])
            all_faces.append([v0, v2, v3])

# ... (helper code below)

def prepare_texture_with_strip(design: Image.Image) -> tuple[Image.Image, float]:
    """
    Prepare texture: Exact design image + 10px white strip at bottom.
    Returns: (New Image, Height Ratio of original image vs total height)
    """
    if design.mode == 'RGBA':
        background = Image.new('RGB', design.size, (255, 255, 255))
        background.paste(design, mask=design.split()[3])
        rgb_image = background
    else:
        rgb_image = design.convert('RGB')
    
    max_dim = 1024
    if max(rgb_image.size) > max_dim:
        ratio = max_dim / max(rgb_image.size)
        new_size = (int(rgb_image.width * ratio), int(rgb_image.height * ratio))
        rgb_image = rgb_image.resize(new_size, Image.Resampling.LANCZOS)
    
    w, h = rgb_image.size
    
    strip_height = 8
    total_h = h + strip_height
    
    final_img = Image.new('RGB', (w, total_h), (255, 255, 255))
    final_img.paste(rgb_image, (0, 0))
    # Bottom strip is already white
    
    height_ratio = h / total_h
    return final_img, height_ratio

def prepare_texture_cutout(design: Image.Image) -> Image.Image:
    """Prepare texture for cutout/standee style - optimized and clean."""
    # Convert to RGB with white background
    if design.mode == 'RGBA':
        background = Image.new('RGB', design.size, (255, 255, 255))
        background.paste(design, mask=design.split()[3])
        rgb_image = background
    else:
        rgb_image = design.convert('RGB')
    
    # Optimize texture size - downsample if too large
    max_dimension = 1024
    if max(rgb_image.size) > max_dimension:
        ratio = max_dimension / max(rgb_image.size)
        new_size = (int(rgb_image.width * ratio), int(rgb_image.height * ratio))
        rgb_image = rgb_image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Add small white border for edge rendering
    border = 5
    width, height = rgb_image.size
    bordered = Image.new('RGB', (width + border * 2, height + border * 2), (255, 255, 255))
    bordered.paste(rgb_image, (border, border))
    
    return bordered


def apply_texture(mesh: trimesh.Trimesh, texture_image: Image.Image, contour: np.ndarray, mirror: bool = False):
    """Apply texture to mesh with UV mapping."""
    apply_texture_with_name(mesh, texture_image, contour, mirror=mirror, material_name="front_material")


def apply_texture_with_name(mesh: trimesh.Trimesh, texture_image: Image.Image, contour: np.ndarray, mirror: bool = False, material_name: str = "material"):
    """Apply texture to mesh with UV mapping and custom material name."""
    vertices = mesh.vertices
    
    min_x, max_x = contour[:, 0].min(), contour[:, 0].max()
    min_y, max_y = contour[:, 1].min(), contour[:, 1].max()
    range_x = max_x - min_x if max_x != min_x else 1
    range_y = max_y - min_y if max_y != min_y else 1
    
    uv = np.zeros((len(vertices), 2))
    for i, (x, y, z) in enumerate(vertices):
        u = (x - min_x) / range_x
        v = (y - min_y) / range_y
        if mirror:
            u = 1.0 - u
        uv[i] = [u, v]
    
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
        metallicFactor=0.0,
        roughnessFactor=0.6,
        baseColorTexture=texture_image,
        name=material_name  # Give unique name to material
    )
    
    mesh.visual = trimesh.visual.TextureVisuals(
        uv=uv,
        material=material,
        image=texture_image
    )


def apply_white_color(mesh: trimesh.Trimesh):
    """Apply solid white color to mesh using PBR material for GLB compatibility."""
    # Create a small white texture image (better GLB compatibility than ColorVisuals)
    white_img = Image.new('RGB', (16, 16), (255, 255, 255))
    
    # Create simple UVs (all pointing to same white pixel)
    uv = np.zeros((len(mesh.vertices), 2))
    uv[:] = [0.5, 0.5]
    
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
        metallicFactor=0.0,
        roughnessFactor=0.5,
        baseColorTexture=white_img
    )
    
    mesh.visual = trimesh.visual.TextureVisuals(
        uv=uv,
        material=material,
        image=white_img
    )


def create_simple_pillow_glb(design_bytes: bytes) -> bytes:
    """Simple wrapper - creates flat cutout/standee style mockup."""
    return create_3d_pillow_mockup(
        design_bytes,
        pillow_thickness=0.06,
        pillow_puffiness=0.0,
        border_width=0.02,
        scale=1.0
    )


def create_custom_pillow_glb(
    design_bytes: bytes,
    thickness: str = "medium",
    puffiness: str = "medium"
) -> bytes:
    """Create cutout/standee with thickness options (puffiness ignored for flat style)."""
    thickness_map = {
        "thin": 0.04,
        "medium": 0.06,
        "thick": 0.10
    }
    
    border_map = {
        "thin": 0.015,
        "medium": 0.02,
        "thick": 0.03
    }
    
    t = thickness_map.get(thickness, 0.06)
    b = border_map.get(thickness, 0.02)
    
    return create_3d_pillow_mockup(
        design_bytes,
        pillow_thickness=t,
        pillow_puffiness=0.0,  # Always flat for cutout style
        border_width=b,
        scale=1.0
    )


def extract_contour(alpha_np: np.ndarray) -> np.ndarray:
    """Extract the main contour from an alpha mask - optimized for speed."""
    _, binary = cv2.threshold(alpha_np, 127, 255, cv2.THRESH_BINARY)
    binary = cv2.GaussianBlur(binary, (3, 3), 0)  # Smaller blur kernel
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    largest_contour = max(contours, key=cv2.contourArea)
    # More aggressive simplification for fewer vertices (4x larger epsilon)
    epsilon = 0.008 * cv2.arcLength(largest_contour, True)
    simplified = cv2.approxPolyDP(largest_contour, epsilon, True)
    
    points = simplified.reshape(-1, 2)
    return points if len(points) >= 3 else None


def normalize_contour(points: np.ndarray, width: int, height: int, aspect: float) -> np.ndarray:
    """Normalize contour points to centered coordinate space."""
    normalized = points.astype(float)
    normalized[:, 0] = (normalized[:, 0] / width - 0.5) * aspect
    normalized[:, 1] = -(normalized[:, 1] / height - 0.5)
    return normalized
