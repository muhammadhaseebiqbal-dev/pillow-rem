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
from .mockup_generator import create_pillow_mockup, create_colored_pillow_mockup

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
MOCKUP_DIR = os.path.join(BASE_DIR, "data", "mockups")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")

# Ensure directories exist
for dir_path in [UPLOAD_DIR, PROCESSED_DIR, MOCKUP_DIR, STATIC_DIR, PDF_DIR]:
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


# ============== PILLOW MOCKUP ENDPOINTS ==============

@app.get("/api/images/{image_id}/mockup")
async def get_pillow_mockup(
    image_id: int,
    color: str = "white",
    db: Session = Depends(get_db)
):
    """
    Generate a pillow mockup with the processed image.
    
    - **image_id**: ID of the processed image
    - **color**: Pillow color (white, cream, beige, gray, black, navy, blush, sage)
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
        
        # Generate mockup
        loop = asyncio.get_event_loop()
        mockup_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_colored_pillow_mockup, processed_bytes, color)
        )
        
        return Response(
            content=mockup_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f"inline; filename=pillow_mockup_{image_id}.png"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating mockup: {str(e)}")


@app.post("/api/mockup")
async def create_mockup_from_upload(
    file: UploadFile = File(...),
    color: str = "white",
    remove_bg: bool = True
):
    """
    Upload an image and generate a pillow mockup directly.
    
    - **file**: Image file (PNG with transparent background, or any image if remove_bg=True)
    - **color**: Pillow color (white, cream, beige, gray, black, navy, blush, sage)
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
        
        # Generate mockup
        mockup_bytes = await loop.run_in_executor(
            thread_executor,
            partial(create_colored_pillow_mockup, processed_bytes, color)
        )
        
        return Response(
            content=mockup_bytes,
            media_type="image/png",
            headers={"Content-Disposition": "inline; filename=pillow_mockup.png"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating mockup: {str(e)}")


@app.post("/api/remove-background-with-mockup")
async def remove_background_with_mockup(
    file: UploadFile = File(...),
    color: str = "white",
    db: Session = Depends(get_db)
):
    """
    Upload an image, remove background, save it, AND return pillow mockup.
    
    - **file**: Image file (JPEG, PNG, WebP)
    - **color**: Pillow color for mockup (white, cream, beige, gray, black, navy, blush, sage)
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
        mockup_filename = f"{unique_id}_mockup.png"
        
        original_path = os.path.join(UPLOAD_DIR, original_filename)
        processed_path = os.path.join(PROCESSED_DIR, processed_filename)
        mockup_path = os.path.join(MOCKUP_DIR, mockup_filename)
        
        loop = asyncio.get_event_loop()
        
        # Save original and process concurrently
        save_task = save_file_async(original_path, file_content)
        process_task = loop.run_in_executor(process_executor, remove_background, file_content)
        
        _, processed_bytes = await asyncio.gather(save_task, process_task)
        
        # Generate mockup and save processed concurrently
        save_processed_task = save_file_async(processed_path, processed_bytes)
        mockup_task = loop.run_in_executor(
            thread_executor,
            partial(create_colored_pillow_mockup, processed_bytes, color)
        )
        
        _, mockup_bytes = await asyncio.gather(save_processed_task, mockup_task)
        
        # Save mockup
        await save_file_async(mockup_path, mockup_bytes)
        
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
            "message": "Background removed and mockup generated",
            "data": {
                "id": image_record.id,
                "original_filename": file.filename,
                "original_url": f"/api/images/{image_record.id}/original",
                "processed_url": f"/api/images/{image_record.id}/processed",
                "mockup_url": f"/api/images/{image_record.id}/mockup?color={color}",
                "original_size": len(file_content),
                "processed_size": len(processed_bytes)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing: {str(e)}")
