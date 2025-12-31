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
    pillow_thickness: float = 0.15,
    pillow_puffiness: float = 0.08,
    border_width: float = 0.06,
    scale: float = 1.0
) -> bytes:
    """
    Create a 3D pillow mesh with visible white border seam.
    Both front and back have the image, side seam is white and bulges OUTWARD.
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
    contour = normalize_contour(contour_points, width, height, aspect)
    n_points = len(contour)
    center = np.mean(contour, axis=0)
    
    # Calculate distances for puffiness
    distances = np.linalg.norm(contour - center, axis=1)
    max_dist = np.max(distances) * 1.1
    
    # Prepare texture (now includes white padding at bottom)
    texture_image = prepare_texture(design)
    
    # Calculate UV scale factor to map only to the original image portion (not the padding)
    # Original image is at top, padding is at bottom
    texture_height_scale = design.height / texture_image.height
    
    # ============ CREATE SINGLE UNIFIED MESH ============
    # Combine front, back, and seam into ONE mesh with proper UV mapping
    
    all_vertices = []
    all_faces = []
    all_uvs = []
    vertex_offset = 0
    
    # Prepare UV bounds
    min_x, max_x = contour[:, 0].min(), contour[:, 0].max()
    min_y, max_y = contour[:, 1].min(), contour[:, 1].max()  # Fixed: was using [:, 0] for min_y
    range_x = max_x - min_x if max_x != min_x else 1
    range_y = max_y - min_y if max_y != min_y else 1
    
    # ============ 1. ADD FRONT FACE ============
    for (x, y) in contour:
        dist = np.sqrt((x - center[0])**2 + (y - center[1])**2)
        puff = pillow_puffiness * max(0, 1.0 - (dist / max_dist) ** 1.5)
        all_vertices.append([x, y, puff])
        # Normal UV mapping for front - SCALED to avoid padding
        u = (x - min_x) / range_x
        v = ((y - min_y) / range_y) * texture_height_scale  # Scale V to avoid padding
        all_uvs.append([u, v])
    
    front_center_idx = len(all_vertices)
    all_vertices.append([center[0], center[1], pillow_puffiness])
    all_uvs.append([0.5, 0.5 * texture_height_scale])
    
    for i in range(n_points):
        next_i = (i + 1) % n_points
        all_faces.append([front_center_idx, i, next_i])
    
    vertex_offset = len(all_vertices)
    
    # ============ 2. ADD BACK FACE ============
    back_puffiness = pillow_puffiness * 0.5
    for (x, y) in contour:
        dist = np.sqrt((x - center[0])**2 + (y - center[1])**2)
        puff = back_puffiness * max(0, 1.0 - (dist / max_dist) ** 1.5)
        all_vertices.append([x, y, -(pillow_thickness - puff)])
        # Use STANDARD UV mapping so texture aligns with the asymmetry of the back face
        # This results in a mirrored image, which fits the mirrored contour perfectly
        # SCALED to avoid padding
        u = (x - min_x) / range_x
        v = ((y - min_y) / range_y) * texture_height_scale  # Scale V to avoid padding
        all_uvs.append([u, v])
    
    back_center_idx = len(all_vertices)
    all_vertices.append([center[0], center[1], -(pillow_thickness - back_puffiness)])
    all_uvs.append([0.5, 0.5 * texture_height_scale])
    
    for i in range(n_points):
        next_i = (i + 1) % n_points
        all_faces.append([back_center_idx, vertex_offset + next_i, vertex_offset + i])
    
    vertex_offset = len(all_vertices)
    
    # ============ 3. ADD SEAM ============
    seam_subdivisions = 8
    
    for i in range(n_points):
        x, y = contour[i]
        
        dist = np.sqrt((x - center[0])**2 + (y - center[1])**2)
        front_puff = pillow_puffiness * max(0, 1.0 - (dist / max_dist) ** 1.5)
        back_puff = back_puffiness * max(0, 1.0 - (dist / max_dist) ** 1.5)
        
        z_front = front_puff
        z_back = -(pillow_thickness - back_puff)
        
        # Calculate outward normal
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
            bulge = border_width * np.sin(t * np.pi)
            
            sx = x + nx * bulge
            sy = y + ny * bulge
            
            all_vertices.append([sx, sy, z])
            # Point to white padding region (use v slightly above scaled image area)
            all_uvs.append([0.5, 0.99])  # Just below padding boundary for pure white
    
    # Create seam faces
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
    
    # ============ CREATE SINGLE MESH ============
    combined_mesh = trimesh.Trimesh(
        vertices=np.array(all_vertices),
        faces=np.array(all_faces),
        process=False  # CRITICAL: Prevent vertex merging so UVs match vertices
    )
    combined_mesh.fix_normals()
    
    # Apply texture with pre-computed UVs
    uv_array = np.array(all_uvs)
    
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
        metallicFactor=0.0,
        roughnessFactor=0.6,
        baseColorTexture=texture_image
    )
    
    combined_mesh.visual = trimesh.visual.TextureVisuals(
        uv=uv_array,
        material=material,
        image=texture_image
    )
    
    # ============ EXPORT TO GLB ============
    combined_mesh.apply_scale(scale)
    
    glb_bytes = combined_mesh.export(file_type='glb')
    return bytes(glb_bytes) if not isinstance(glb_bytes, bytes) else glb_bytes


def extract_contour(alpha_np: np.ndarray) -> np.ndarray:
    """Extract the main contour from an alpha mask."""
    _, binary = cv2.threshold(alpha_np, 127, 255, cv2.THRESH_BINARY)
    binary = cv2.GaussianBlur(binary, (5, 5), 0)
    _, binary = cv2.threshold(binary, 127, 255, cv2.THRESH_BINARY)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    largest_contour = max(contours, key=cv2.contourArea)
    epsilon = 0.002 * cv2.arcLength(largest_contour, True)
    simplified = cv2.approxPolyDP(largest_contour, epsilon, True)
    
    points = simplified.reshape(-1, 2)
    return points if len(points) >= 3 else None


def normalize_contour(points: np.ndarray, width: int, height: int, aspect: float) -> np.ndarray:
    """Normalize contour points to centered coordinate space."""
    normalized = points.astype(float)
    normalized[:, 0] = (normalized[:, 0] / width - 0.5) * aspect
    normalized[:, 1] = -(normalized[:, 1] / height - 0.5)
    return normalized


def prepare_texture(design: Image.Image) -> Image.Image:
    """Prepare the texture image with white padding for seam."""
    # Convert to RGB with white background
    if design.mode == 'RGBA':
        background = Image.new('RGB', design.size, (255, 255, 255))
        background.paste(design, mask=design.split()[3])
        rgb_image = background
    else:
        rgb_image = design.convert('RGB')
    
    # Add white padding at bottom (10 pixels) for seam to use
    width, height = rgb_image.size
    padded = Image.new('RGB', (width, height + 10), (255, 255, 255))
    padded.paste(rgb_image, (0, 0))
    
    return padded


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
    """Simple wrapper with default settings."""
    return create_3d_pillow_mockup(
        design_bytes,
        pillow_thickness=0.12,
        pillow_puffiness=0.06,
        border_width=0.05,
        scale=1.0
    )


def create_custom_pillow_glb(
    design_bytes: bytes,
    thickness: str = "medium",
    puffiness: str = "medium"
) -> bytes:
    """Create pillow with preset options."""
    thickness_map = {
        "thin": 0.08,
        "medium": 0.12,
        "thick": 0.18
    }
    
    puffiness_map = {
        "flat": 0.03,
        "medium": 0.06,
        "puffy": 0.12
    }
    
    border_map = {
        "thin": 0.04,
        "medium": 0.06,
        "thick": 0.08
    }
    
    t = thickness_map.get(thickness, 0.12)
    p = puffiness_map.get(puffiness, 0.06)
    b = border_map.get(thickness, 0.06)
    
    return create_3d_pillow_mockup(
        design_bytes,
        pillow_thickness=t,
        pillow_puffiness=p,
        border_width=b,
        scale=1.0
    )
