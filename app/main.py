"""
FastAPI Backend for Background Removal Service.
Optimized for concurrent processing with worker pool.
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import os
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import asyncio
from functools import partial

from .database import get_db, init_db, ImageRecord
from .background_remover import remove_background, get_image_info
from .pdf_generator import create_simple_pdf, create_masonry_pdf, create_bento_pdf
from .mockup_generator import create_pillow_mockup, create_colored_pillow_mockup, create_masonry_mockup
from .pillow_3d_generator import create_3d_pillow_mockup, create_simple_pillow_glb, create_custom_pillow_glb

# Global executor for CPU-bound tasks (background removal)
# Using ProcessPoolExecutor for true parallelism on multi-core systems
process_executor = None
thread_executor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    global process_executor, thread_executor
    
    # Startup
    init_db()
    
    # Create executors for concurrent processing
    # ProcessPoolExecutor for CPU-bound tasks (background removal)
    # ThreadPoolExecutor for I/O-bound tasks (file operations)
    cpu_count = os.cpu_count() or 4
    process_executor = ProcessPoolExecutor(max_workers=cpu_count)
    thread_executor = ThreadPoolExecutor(max_workers=cpu_count * 2)
    
    print(f"Started with {cpu_count} process workers and {cpu_count * 2} thread workers")
    
    yield
    
    # Shutdown
    if process_executor:
        process_executor.shutdown(wait=True)
    if thread_executor:
        thread_executor.shutdown(wait=True)


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Background Removal API",
    description="High-performance API for removing backgrounds from images using AI",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cattucino.store",
        "http://72.62.76.64",
        "http://72.62.76.64:8000",
        "*"  # Fallback for other origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
MOCKUP_DIR = os.path.join(BASE_DIR, "data", "mockups")
GLB_DIR = os.path.join(BASE_DIR, "data", "glb_mockups")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")

# Ensure directories exist
for dir_path in [UPLOAD_DIR, PROCESSED_DIR, MOCKUP_DIR, STATIC_DIR, PDF_DIR, GLB_DIR]:
    os.makedirs(dir_path, exist_ok=True)


async def process_image_async(file_content: bytes) -> bytes:
    """Process image in a separate process for true parallelism."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(process_executor, remove_background, file_content)


async def save_file_async(path: str, content: bytes):
    """Save file asynchronously using thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(thread_executor, lambda: open(path, 'wb').write(content))


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the test HTML page."""
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Background Removal API</h1><p>Visit /docs for API documentation</p>")


@app.post("/api/remove-background")
async def remove_background_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload an image and remove its background.
    Optimized for concurrent processing.
    
    - **file**: Image file (JPEG, PNG, WebP supported)
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1] or ".png"
        unique_id = str(uuid.uuid4())
        original_filename = f"{unique_id}_original{file_ext}"
        processed_filename = f"{unique_id}_processed.png"
        
        original_path = os.path.join(UPLOAD_DIR, original_filename)
        processed_path = os.path.join(PROCESSED_DIR, processed_filename)
        
        # Process concurrently: save original and remove background
        save_task = save_file_async(original_path, file_content)
        process_task = process_image_async(file_content)
        
        # Wait for both to complete
        _, processed_bytes = await asyncio.gather(save_task, process_task)
        
        # Save processed image
        await save_file_async(processed_path, processed_bytes)
        
        # Store in database
        image_record = ImageRecord(
            filename=file.filename,
            original_path=original_path,
            processed_path=processed_path,
            original_size=len(file_content),
            processed_size=len(processed_bytes)
        )
        db.add(image_record)
        db.commit()
        db.refresh(image_record)
        
        return {
            "success": True,
            "message": "Background removed successfully",
            "data": {
                "id": image_record.id,
                "original_filename": file.filename,
                "original_url": f"/api/images/{image_record.id}/original",
                "processed_url": f"/api/images/{image_record.id}/processed",
                "original_size": len(file_content),
                "processed_size": len(processed_bytes)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


@app.get("/api/images/{image_id}/original")
async def get_original_image(image_id: int, db: Session = Depends(get_db)):
    """Get the original uploaded image."""
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if not os.path.exists(record.original_path):
        raise HTTPException(status_code=404, detail="Original image file not found")
    
    return FileResponse(record.original_path)


@app.get("/api/images/{image_id}/processed")
async def get_processed_image(image_id: int, db: Session = Depends(get_db)):
    """Get the processed image with background removed."""
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if not os.path.exists(record.processed_path):
        raise HTTPException(status_code=404, detail="Processed image file not found")
    
    return FileResponse(record.processed_path, media_type="image/png")


@app.get("/api/images")
async def list_images(db: Session = Depends(get_db)):
    """List all processed images."""
    records = db.query(ImageRecord).order_by(ImageRecord.created_at.desc()).all()
    return {
        "success": True,
        "count": len(records),
        "images": [record.to_dict() for record in records]
    }


@app.delete("/api/images/{image_id}")
async def delete_image(image_id: int, db: Session = Depends(get_db)):
    """Delete an image record and its files."""
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete files
    if os.path.exists(record.original_path):
        os.remove(record.original_path)
    if os.path.exists(record.processed_path):
        os.remove(record.processed_path)
    
    # Delete database record
    db.delete(record)
    db.commit()
    
    return {"success": True, "message": "Image deleted successfully"}


# ============== OPTIMIZED QUICK MOCKUP ENDPOINT ==============

@app.post("/api/quick-mockup")
async def quick_mockup(
    file: UploadFile = File(...),
    thickness: str = "medium",
    puffiness: str = "medium"
):
    """
    Optimized single endpoint: Upload image → Remove background → Generate 3D GLB mockup.
    Returns GLB file directly without database storage for maximum speed.
    
    - **file**: Image file (JPEG, PNG, WebP)
    - **thickness**: Pillow thickness (thin/medium/thick)
    - **puffiness**: Pillow puffiness (flat/medium/puffy)
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        # Read file content once
        file_content = await file.read()
        
        # Step 1: Remove background (use thread pool - more stable with C libraries)
        loop = asyncio.get_event_loop()
        print(f"[DEBUG] Starting background removal")
        bg_removed_bytes = await loop.run_in_executor(
            thread_executor,  # Use thread pool instead of process pool
            remove_background,
            file_content
        )
        print(f"[DEBUG] Background removed, size: {len(bg_removed_bytes)} bytes")
        
        # Step 2: Generate 3D GLB mockup (use thread pool)
        print(f"[DEBUG] Starting 3D generation with thickness={thickness}, puffiness={puffiness}")
        glb_bytes = await loop.run_in_executor(
            thread_executor,  # Use thread pool instead of process pool
            create_custom_pillow_glb,
            bg_removed_bytes,
            thickness,
            puffiness
        )
        print(f"[DEBUG] GLB generated, size: {len(glb_bytes)} bytes")
        
        # Return GLB file directly
        return Response(
            content=glb_bytes,
            media_type="model/gltf-binary",
            headers={
                "Content-Disposition": f"attachment; filename=pillow_mockup.glb"
            }
        )
        
    except ValueError as e:
        print(f"[ERROR] ValueError: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@app.post("/api/masonry-mockup")
async def masonry_mockup(
    file: UploadFile = File(...),
    tiles: int = 6
):
    """
    Optimized endpoint: Upload image → Remove background → Generate masonry layout mockup.
    Returns a grid-style PNG mockup showing the design in multiple tiles.
    
    - **file**: Image file (JPEG, PNG, WebP)
    - **tiles**: Number of tiles in grid (4, 6, or 9) - default 6
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    # Validate tiles parameter
    if tiles not in [4, 6, 9]:
        raise HTTPException(
            status_code=400,
            detail="tiles parameter must be 4, 6, or 9"
        )
    
    try:
        # Read file content once
        file_content = await file.read()
        
        # Step 1: Remove background
        loop = asyncio.get_event_loop()
        print(f"[DEBUG] Starting background removal for masonry mockup")
        bg_removed_bytes = await loop.run_in_executor(
            thread_executor,
            remove_background,
            file_content
        )
        print(f"[DEBUG] Background removed, size: {len(bg_removed_bytes)} bytes")
        
        # Step 2: Generate masonry mockup
        print(f"[DEBUG] Starting masonry mockup generation with {tiles} tiles")
        mockup_bytes = await loop.run_in_executor(
            thread_executor,
            create_masonry_mockup,
            bg_removed_bytes,
            tiles
        )
        print(f"[DEBUG] Masonry mockup generated, size: {len(mockup_bytes)} bytes")
        
        # Return PNG file directly
        return Response(
            content=mockup_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename=masonry_mockup_{tiles}tiles.png"
            }
        )
        
    except ValueError as e:
        print(f"[ERROR] ValueError: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


# ============== PDF GENERATION ENDPOINTS ==============

@app.get("/api/pdf/originals")
async def generate_originals_pdf(db: Session = Depends(get_db)):
    """
    Generate a high-quality PDF containing all original images.
    One image per page.
    """
    records = db.query(ImageRecord).order_by(ImageRecord.created_at.desc()).all()
    
    if not records:
        raise HTTPException(status_code=404, detail="No images found")
    
    image_paths = [r.original_path for r in records if os.path.exists(r.original_path)]
    
    if not image_paths:
        raise HTTPException(status_code=404, detail="No image files found")
    
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_simple_pdf, image_paths, "Original Images Gallery")
        )
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=original_images.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


@app.get("/api/pdf/processed")
async def generate_processed_pdf(
    layout: str = "masonry",
    db: Session = Depends(get_db)
):
    """
    Generate a high-quality PDF containing all processed images.
    
    - **layout**: Layout style - 'masonry', 'bento', or 'simple' (default: masonry)
    """
    records = db.query(ImageRecord).order_by(ImageRecord.created_at.desc()).all()
    
    if not records:
        raise HTTPException(status_code=404, detail="No images found")
    
    image_paths = [r.processed_path for r in records if os.path.exists(r.processed_path)]
    
    if not image_paths:
        raise HTTPException(status_code=404, detail="No processed image files found")
    
    try:
        loop = asyncio.get_event_loop()
        
        if layout == "bento":
            pdf_bytes = await loop.run_in_executor(
                thread_executor,
                partial(create_bento_pdf, image_paths, "Processed Images - Bento Layout")
            )
        elif layout == "simple":
            pdf_bytes = await loop.run_in_executor(
                thread_executor,
                partial(create_simple_pdf, image_paths, "Processed Images Gallery")
            )
        else:  # masonry (default)
            pdf_bytes = await loop.run_in_executor(
                thread_executor,
                partial(create_masonry_pdf, image_paths, "Processed Images - Masonry Layout")
            )
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=processed_images_{layout}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


@app.get("/api/pdf/all")
async def generate_combined_pdf(db: Session = Depends(get_db)):
    """
    Generate a PDF containing both original and processed images side by side.
    """
    records = db.query(ImageRecord).order_by(ImageRecord.created_at.desc()).all()
    
    if not records:
        raise HTTPException(status_code=404, detail="No images found")
    
    # Get all image paths (original first, then processed)
    all_paths = []
    for r in records:
        if os.path.exists(r.original_path):
            all_paths.append(r.original_path)
        if os.path.exists(r.processed_path):
            all_paths.append(r.processed_path)
    
    if not all_paths:
        raise HTTPException(status_code=404, detail="No image files found")
    
    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_masonry_pdf, all_paths, "Complete Image Gallery", 2)
        )
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=complete_gallery.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "workers": {
            "process_workers": os.cpu_count() or 4,
            "thread_workers": (os.cpu_count() or 4) * 2
        }
    }


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get system statistics."""
    total_images = db.query(ImageRecord).count()
    total_original_size = sum(r.original_size or 0 for r in db.query(ImageRecord).all())
    total_processed_size = sum(r.processed_size or 0 for r in db.query(ImageRecord).all())
    
    return {
        "total_images": total_images,
        "total_original_size_mb": round(total_original_size / (1024 * 1024), 2),
        "total_processed_size_mb": round(total_processed_size / (1024 * 1024), 2),
        "storage_saved_mb": round((total_original_size - total_processed_size) / (1024 * 1024), 2)
    }


# ============== 3D PILLOW MOCKUP ENDPOINTS ==============

@app.get("/api/images/{image_id}/mockup")
async def get_pillow_mockup(
    image_id: int,
    thickness: str = "medium",
    puffiness: str = "medium",
    db: Session = Depends(get_db)
):
    """
    Generate a 3D pillow mockup (GLB) with the processed image.
    
    - **image_id**: ID of the processed image
    - **thickness**: Pillow thickness ('thin', 'medium', 'thick')
    - **puffiness**: Pillow puffiness ('flat', 'medium', 'puffy')
    """
    record = db.query(ImageRecord).filter(ImageRecord.id == image_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if not os.path.exists(record.processed_path):
        raise HTTPException(status_code=404, detail="Processed image file not found")
    
    try:
        # Read the processed image
        with open(record.processed_path, "rb") as f:
            processed_bytes = f.read()
        
        # Generate 3D mockup
        loop = asyncio.get_event_loop()
        glb_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_custom_pillow_glb, processed_bytes, thickness, puffiness)
        )
        
        return Response(
            content=glb_bytes,
            media_type="model/gltf-binary",
            headers={"Content-Disposition": f"attachment; filename=pillow_mockup_{image_id}.glb"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating 3D mockup: {str(e)}")


@app.post("/api/mockup")
async def create_mockup_from_upload(
    file: UploadFile = File(...),
    thickness: str = "medium",
    puffiness: str = "medium",
    remove_bg: bool = True
):
    """
    Upload an image and generate a 3D pillow mockup (GLB) directly.
    
    - **file**: Image file (PNG with transparent background, or any image if remove_bg=True)
    - **thickness**: Pillow thickness ('thin', 'medium', 'thick')
    - **puffiness**: Pillow puffiness ('flat', 'medium', 'puffy')
    - **remove_bg**: Whether to remove background first (default: True)
    """
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        file_content = await file.read()
        loop = asyncio.get_event_loop()
        
        # Remove background if requested
        if remove_bg:
            processed_bytes = await loop.run_in_executor(
                process_executor,
                remove_background,
                file_content
            )
        else:
            processed_bytes = file_content
        
        # Generate 3D mockup
        glb_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_custom_pillow_glb, processed_bytes, thickness, puffiness)
        )
        
        return Response(
            content=glb_bytes,
            media_type="model/gltf-binary",
            headers={"Content-Disposition": "attachment; filename=pillow_mockup.glb"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating 3D mockup: {str(e)}")


@app.post("/api/remove-background-with-mockup")
async def remove_background_with_mockup(
    file: UploadFile = File(...),
    thickness: str = "medium",
    puffiness: str = "medium",
    db: Session = Depends(get_db)
):
    """
    Upload an image, remove background, save it, AND return 3D pillow mockup (GLB).
    
    - **file**: Image file (JPEG, PNG, WebP)
    - **thickness**: Pillow thickness ('thin', 'medium', 'thick')
    - **puffiness**: Pillow puffiness ('flat', 'medium', 'puffy')
    """
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        file_content = await file.read()
        
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1] or ".png"
        unique_id = str(uuid.uuid4())
        original_filename = f"{unique_id}_original{file_ext}"
        processed_filename = f"{unique_id}_processed.png"
        glb_filename = f"{unique_id}_mockup.glb"
        
        original_path = os.path.join(UPLOAD_DIR, original_filename)
        processed_path = os.path.join(PROCESSED_DIR, processed_filename)
        glb_path = os.path.join(GLB_DIR, glb_filename)
        
        loop = asyncio.get_event_loop()
        
        # Save original and process concurrently
        save_task = save_file_async(original_path, file_content)
        process_task = loop.run_in_executor(process_executor, remove_background, file_content)
        
        _, processed_bytes = await asyncio.gather(save_task, process_task)
        
        # Generate 3D mockup and save processed concurrently
        save_processed_task = save_file_async(processed_path, processed_bytes)
        mockup_task = loop.run_in_executor(
            thread_executor,
            partial(create_custom_pillow_glb, processed_bytes, thickness, puffiness)
        )
        
        _, glb_bytes = await asyncio.gather(save_processed_task, mockup_task)
        
        # Save GLB file
        await save_file_async(glb_path, glb_bytes)
        
        # Store in database
        image_record = ImageRecord(
            filename=file.filename,
            original_path=original_path,
            processed_path=processed_path,
            original_size=len(file_content),
            processed_size=len(processed_bytes)
        )
        db.add(image_record)
        db.commit()
        db.refresh(image_record)
        
        return {
            "success": True,
            "message": "Background removed and 3D mockup generated",
            "data": {
                "id": image_record.id,
                "original_filename": file.filename,
                "original_url": f"/api/images/{image_record.id}/original",
                "processed_url": f"/api/images/{image_record.id}/processed",
                "mockup_url": f"/api/images/{image_record.id}/mockup?thickness={thickness}&puffiness={puffiness}",
                "original_size": len(file_content),
                "processed_size": len(processed_bytes),
                "glb_size": len(glb_bytes)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing: {str(e)}")
